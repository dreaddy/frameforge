from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import (
    COMFY_URL,
    FLUX_POSE_IMG2IMG_WORKFLOW,
    FLUX_WORKFLOW,
    POSE_IMG2IMG_DENOISE,
    POSE_IMG2IMG_STEPS,
    QWEN_IMAGE_EDIT_WORKFLOW,
    SDXL_ART_IMG2IMG_WORKFLOW,
    SDXL_CHECKPOINT,
    SDXL_REALISM_CHECKPOINT,
    WAN_I2V_DURATION_S,
    WAN_I2V_HEIGHT,
    WAN_I2V_LENGTH,
    WAN_I2V_TURBO,
    WAN_I2V_WIDTH,
    WAN_I2V_WORKFLOW,
    WAN_SQUARE_SIZES,
)

COMFY_BIN = os.environ.get("COMFY_BIN", "comfy")


class ComfyError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(base_url=COMFY_URL, timeout=120.0)


def health() -> dict[str, Any]:
    try:
        with _client() as c:
            r = c.get("/system_stats")
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "url": COMFY_URL, "version": data.get("system", {}).get("comfyui_version")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": COMFY_URL, "error": str(exc)}


def free_memory() -> None:
    try:
        with _client() as c:
            c.post("/free", json={"unload_models": True, "free_memory": True})
    except Exception:
        pass


def upload_image(path: Path, overwrite: bool = True) -> str:
    with path.open("rb") as f, _client() as c:
        r = c.post(
            "/upload/image",
            files={"image": (path.name, f, "image/png")},
            data={"overwrite": "true" if overwrite else "false"},
        )
        r.raise_for_status()
        payload = r.json()
    name = payload.get("name") or path.name
    sub = payload.get("subfolder") or ""
    return f"{sub}/{name}".strip("/") if sub else name


def queue_prompt(workflow: dict[str, Any]) -> str:
    client_id = str(uuid.uuid4())
    with _client() as c:
        r = c.post("/prompt", json={"prompt": workflow, "client_id": client_id})
        if r.status_code >= 400:
            raise ComfyError(f"Comfy queue failed: {r.status_code} {r.text[:800]}")
        data = r.json()
    pid = data.get("prompt_id")
    if not pid:
        raise ComfyError(f"No prompt_id in response: {data}")
    return pid


def wait_prompt(prompt_id: str, timeout_s: float = 600.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    with _client() as c:
        while time.time() < deadline:
            r = c.get(f"/history/{prompt_id}")
            r.raise_for_status()
            hist = r.json()
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status") or {}
                if status.get("status_str") == "error" or status.get("completed") is False:
                    msgs = status.get("messages") or []
                    raise ComfyError(f"Comfy job error: {msgs[-1] if msgs else status}")
                if entry.get("outputs"):
                    return entry
            time.sleep(1.0)
    raise ComfyError(f"Timeout waiting for prompt {prompt_id}")


def first_image_url(history_entry: dict[str, Any]) -> str:
    outputs = history_entry.get("outputs") or {}
    for node_out in outputs.values():
        images = node_out.get("images") or []
        if not images:
            continue
        img = images[0]
        q = urlencode(
            {
                "filename": img["filename"],
                "subfolder": img.get("subfolder") or "",
                "type": img.get("type") or "output",
            }
        )
        return f"{COMFY_URL}/view?{q}"
    raise ComfyError("No image outputs in history")


def first_video_path(history_entry: dict[str, Any]) -> str | None:
    outputs = history_entry.get("outputs") or {}
    for node_out in outputs.values():
        for key in ("gifs", "videos", "images"):
            items = node_out.get(key) or []
            for item in items:
                filename = item.get("filename")
                if not filename:
                    continue
                if not any(filename.lower().endswith(ext) for ext in (".mp4", ".webm", ".mkv", ".gif", ".webp")):
                    if key == "images":
                        continue
                q = urlencode(
                    {
                        "filename": filename,
                        "subfolder": item.get("subfolder") or "",
                        "type": item.get("type") or "output",
                    }
                )
                return f"{COMFY_URL}/view?{q}"
    return None


def download_url(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=180.0) as c:
        r = c.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


def generate_flux_character(
    prompt: str,
    dest: Path,
    seed: int | None = None,
    filename_prefix: str = "frameforge_char",
    style: str | None = None,
    outline: bool = False,
    *,
    subject: str = "character",
    palette: list[str] | None = None,
) -> Path:
    from .styles import build_generation_prompt, get_style

    free_memory()
    wf = json.loads(FLUX_WORKFLOW.read_text(encoding="utf-8"))
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    spec = get_style(style)
    subj = "item" if subject == "item" else "character"
    full_prompt = build_generation_prompt(
        prompt, spec["id"], outline=outline, subject=subj, palette=palette
    )
    wf["4"]["inputs"]["strength_model"] = float(spec["lora_strength"])
    wf["5"]["inputs"]["text"] = full_prompt
    wf["9"]["inputs"]["seed"] = seed
    if spec["id"] == "pixel_art":
        wf["9"]["inputs"]["steps"] = max(int(wf["9"]["inputs"].get("steps") or 20), 28)
        wf["6"]["inputs"]["guidance"] = 3.8
    wf["11"]["inputs"]["filename_prefix"] = filename_prefix
    pid = queue_prompt(wf)
    hist = wait_prompt(pid, timeout_s=600.0)
    url = first_image_url(hist)
    return download_url(url, dest)


def _comfy_env() -> dict[str, str]:
    env = os.environ.copy()
    env["COMFY_LOCAL_URL"] = COMFY_URL
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_comfy_cli(args: list[str], timeout_s: float = 900.0) -> None:
    cmd = [COMFY_BIN, *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_comfy_env(),
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        raise ComfyError(
            f"comfy cli failed ({proc.returncode}): {proc.stderr[-1500:] or proc.stdout[-1500:]}"
        )


def run_wan_i2v(
    image_path: Path,
    motion_prompt: str,
    dest_video: Path,
    seed: int | None = None,
    length: int | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_s: float | None = None,
    turbo: bool | None = None,
    no_scale: bool = False,
) -> Path:
    """Run Wan 2.2 I2V via a patched workflow copy (short turbo clip for sprites)."""
    if not WAN_I2V_WORKFLOW.exists():
        raise ComfyError(f"Missing Wan workflow: {WAN_I2V_WORKFLOW}")
    free_memory()

    width = int(width if width is not None else WAN_I2V_WIDTH)
    height = int(height if height is not None else WAN_I2V_HEIGHT)
    if width != height or width not in WAN_SQUARE_SIZES:
        raise ValueError(f"Supported WAN square sides: {WAN_SQUARE_SIZES}")
    length = int(length if length is not None else WAN_I2V_LENGTH)
    if length % 4 != 1:
        length = max(17, length - (length % 4) + 1)
    duration_s = float(duration_s if duration_s is not None else WAN_I2V_DURATION_S)
    turbo = WAN_I2V_TURBO if turbo is None else bool(turbo)

    # Feed Wan a small RGB still — full 640 canvas is the main time sink
    staged = image_path.parent / f"_wan_in_{uuid.uuid4().hex[:8]}.png"
    _prepare_wan_input(image_path, staged, width, height, no_scale=no_scale)
    uploaded = upload_image(staged)
    staged.unlink(missing_ok=True)

    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    tmp_dir = dest_video.parent / f"_wan_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wf_path = tmp_dir / "wan_job.json"
    shutil.copy2(WAN_I2V_WORKFLOW, wf_path)
    _patch_wan_workflow_json(
        wf_path,
        uploaded,
        motion_prompt,
        seed=seed,
        width=width,
        height=height,
        length=length,
        duration_s=duration_s,
        turbo=turbo,
    )

    _run_comfy_cli(["run", "--workflow", str(wf_path), "--wait"], timeout_s=600.0)

    video = _find_recent_output(suffixes=(".mp4", ".webm", ".mkv"))
    if video is None:
        raise ComfyError("Wan I2V finished but no video file found in Comfy output")
    dest_video.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, dest_video)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return dest_video


def _prepare_wan_input(src: Path, dest: Path, width: int, height: int, *, no_scale: bool = False) -> Path:
    from PIL import Image

    img = Image.open(src).convert("RGB")
    if img.size != (width, height):
        if no_scale:
            raise ValueError(f"No-scale WAN input is {img.size}, expected {(width, height)}")
        from PIL import ImageOps
        img = ImageOps.pad(img, (width, height), method=Image.Resampling.NEAREST, color=(0, 255, 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def _patch_wan_workflow_json(
    wf_path: Path,
    image_name: str,
    prompt: str,
    *,
    seed: int,
    width: int,
    height: int,
    length: int,
    duration_s: float,
    turbo: bool,
) -> None:
    """Force sprite-friendly Wan settings (turbo + small canvas + short clip)."""
    data = json.loads(wf_path.read_text(encoding="utf-8"))

    for node in data.get("nodes") or []:
        nid = str(node.get("id"))
        ntype = node.get("type")
        wv = node.get("widgets_values")
        if ntype == "LoadImage" and nid == "97":
            if isinstance(wv, list) and wv:
                wv[0] = image_name
            else:
                node["widgets_values"] = [image_name, "image"]
        if nid == "129" and isinstance(wv, list) and len(wv) >= 12:
            # Exposed subgraph widgets:
            # text, width, height, duration, seed, models..., enable_turbo_mode
            wv[0] = prompt
            wv[1] = width
            wv[2] = height
            wv[3] = duration_s
            wv[4] = seed
            wv[-1] = bool(turbo)
            node["widgets_values"] = wv
        if nid == "108":
            if isinstance(wv, list) and len(wv) >= 2:
                wv[0] = "frameforge/wan_i2v"
                # keep format if present
            wvn = node.get("widgets_values_named") or {}
            wvn["filename_prefix"] = "frameforge/wan_i2v"
            node["widgets_values_named"] = wvn

    for sub in (data.get("definitions") or {}).get("subgraphs") or []:
        for inner in sub.get("nodes") or []:
            iid = str(inner.get("id"))
            itype = inner.get("type")
            iwv = inner.get("widgets_values")
            if itype == "WanImageToVideo" and iid == "98" and isinstance(iwv, list) and len(iwv) >= 3:
                iwv[0] = width
                iwv[1] = height
                iwv[2] = length
                inner["widgets_values"] = iwv
            if iid == "161" and itype == "PrimitiveFloat" and isinstance(iwv, list) and iwv:
                iwv[0] = duration_s  # Float (Duration)
                inner["widgets_values"] = iwv
            if iid == "131" and itype == "PrimitiveBoolean" and isinstance(iwv, list) and iwv:
                iwv[0] = bool(turbo)  # Enable 4steps LoRA?
                inner["widgets_values"] = iwv
            # Sampler steps already 4 on turbo path; keep non-turbo path shorter too
            if itype == "KSamplerAdvanced" and isinstance(iwv, list) and len(iwv) >= 4:
                if turbo:
                    iwv[3] = 4

    wf_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_recent_output(suffixes: tuple[str, ...], max_age_s: float = 600.0) -> Path | None:
    candidates: list[Path] = []
    roots = [
        Path(r"D:\comfy\files\output"),
        Path(r"D:\Comfy-Desktop\ComfyUI-Shared\output"),
    ]
    now = time.time()
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in suffixes:
                try:
                    if now - p.stat().st_mtime <= max_age_s:
                        candidates.append(p)
                except OSError:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def run_qwen_image_edit(
    image_path: Path,
    prompt: str,
    dest: Path,
    *,
    seed: int | None = None,
    use_lightning: bool = True,
    filename_prefix: str = "frameforge_qwen_edit",
) -> Path:
    """Identity-preserving image edit via Qwen-Image-Edit-2509 (UI workflow + comfy-cli)."""
    if not QWEN_IMAGE_EDIT_WORKFLOW.exists():
        raise ComfyError(f"Missing Qwen edit workflow: {QWEN_IMAGE_EDIT_WORKFLOW}")
    if not image_path.exists():
        raise ComfyError(f"Missing edit source image: {image_path}")

    free_memory()
    uploaded = upload_image(image_path)
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    tmp_dir = dest.parent / f"_qwen_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wf_path = tmp_dir / "qwen_edit_job.json"
    shutil.copy2(QWEN_IMAGE_EDIT_WORKFLOW, wf_path)
    _patch_qwen_edit_workflow_json(
        wf_path,
        uploaded,
        prompt,
        seed=seed,
        use_lightning=use_lightning,
        filename_prefix=filename_prefix,
    )
    _run_comfy_cli(["run", "--workflow", str(wf_path), "--wait"], timeout_s=900.0)
    out = _find_recent_output(suffixes=(".png", ".jpg", ".jpeg", ".webp"))
    if out is None:
        raise ComfyError("Qwen Image Edit finished but no image found in Comfy output")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, dest)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return dest


def _patch_qwen_edit_workflow_json(
    wf_path: Path,
    image_name: str,
    prompt: str,
    *,
    seed: int,
    use_lightning: bool,
    filename_prefix: str,
) -> None:
    data = json.loads(wf_path.read_text(encoding="utf-8"))
    for node in data.get("nodes") or []:
        nid = node.get("id")
        ntype = node.get("type")
        wv = node.get("widgets_values")
        if ntype == "LoadImage" and nid == 78:
            if isinstance(wv, list) and wv:
                wv[0] = image_name
            else:
                node["widgets_values"] = [image_name, "image"]
        if nid == 433 and isinstance(wv, list) and len(wv) >= 8:
            # prompt, prompt_1, seed, unet, clip, vae, lightning_switch, lora
            wv[0] = prompt
            wv[2] = int(seed)
            wv[6] = bool(use_lightning)
        if ntype == "SaveImageAdvanced" and nid == 469 and isinstance(wv, list) and wv:
            wv[0] = filename_prefix
    wf_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# Flux img2img ImageScale sizes that stay multiples of 16 and fit typical 12–16GB cards.
ART_STILL_SIZES = (512, 768, 1024, 1280)


def normalize_art_size(size: int | None) -> int:
    if size is None:
        return 1024
    try:
        value = int(size)
    except (TypeError, ValueError):
        return 1024
    if value in ART_STILL_SIZES:
        return value
    # Snap to nearest allowed size
    return min(ART_STILL_SIZES, key=lambda s: abs(s - value))


def generate_pose_frame(
    prompt: str,
    dest: Path,
    reference_image: Path,
    seed: int | None = None,
    style: str | None = None,
    outline: bool = False,
    denoise: float | None = None,
    steps: int | None = None,
    max_denoise: float = 0.65,
    *,
    chroma: bool = True,
    identity_lock: str = "exact same character design and colors as reference, only change pose",
    size: int | None = None,
    subject: str = "character",
    palette: list[str] | None = None,
) -> Path:
    """Pose/style frame via Flux img2img from a reference — keeps identity stable."""
    from .styles import build_generation_prompt, get_style

    if not FLUX_POSE_IMG2IMG_WORKFLOW.exists():
        raise ComfyError(f"Missing pose workflow: {FLUX_POSE_IMG2IMG_WORKFLOW}")
    if not reference_image.exists():
        raise ComfyError(f"Missing reference image: {reference_image}")

    free_memory()
    uploaded = upload_image(reference_image)
    wf = json.loads(FLUX_POSE_IMG2IMG_WORKFLOW.read_text(encoding="utf-8"))
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    denoise = float(POSE_IMG2IMG_DENOISE if denoise is None else denoise)
    denoise = min(float(max_denoise), max(0.25, denoise))
    pose_steps = int(POSE_IMG2IMG_STEPS if steps is None else steps)
    pose_steps = min(48, max(12, pose_steps))
    side = normalize_art_size(size) if size is not None else 1024
    spec = get_style(style)
    subj = "item" if subject == "item" else "character"
    full_prompt = build_generation_prompt(
        prompt, spec["id"], outline=outline, chroma=chroma, subject=subj, palette=palette
    )
    lock = (identity_lock or "").strip()
    if lock and "same character" not in full_prompt.lower():
        full_prompt = f"{lock}, {full_prompt}"

    wf["4"]["inputs"]["strength_model"] = float(spec["lora_strength"])
    wf["5"]["inputs"]["text"] = full_prompt
    wf["12"]["inputs"]["image"] = uploaded
    wf["9"]["inputs"]["seed"] = seed
    wf["9"]["inputs"]["denoise"] = denoise
    wf["9"]["inputs"]["steps"] = pose_steps
    wf["13"]["inputs"]["width"] = side
    wf["13"]["inputs"]["height"] = side
    if spec["id"] == "pixel_art":
        wf["6"]["inputs"]["guidance"] = 3.6
        wf["13"]["inputs"]["upscale_method"] = "nearest-exact"
    else:
        wf["13"]["inputs"]["upscale_method"] = "lanczos"
        # Stronger style adherence for illustration / photoreal restyles
        if spec["id"] == "realistic":
            wf["6"]["inputs"]["guidance"] = 4.2
        elif spec["id"] == "stylized_3d":
            wf["6"]["inputs"]["guidance"] = 3.7
        else:
            wf["6"]["inputs"]["guidance"] = 3.8
    wf["11"]["inputs"]["filename_prefix"] = "frameforge_pose"

    pid = queue_prompt(wf)
    hist = wait_prompt(pid, timeout_s=600.0)
    url = first_image_url(hist)
    return download_url(url, dest)


_SDXL_ART_NEGATIVE = (
    "pixel art, cartoon, anime, comic, cel shading, flat illustration, "
    "limited color palette, posterized colors, vector art, logo, "
    "stylized 3d render, plastic skin, smooth CGI, unicorn horn, "
    "chroma key screen, neon lime #00FF00, solid flat green screen void, "
    "black void background, empty darkness, solid gray backdrop, "
    "underexposed night forest, pitch black trees, heavy ash smoke plate, "
    "studio seamless background, game sprite, low quality, blurry, "
    "deformed, bad anatomy"
)


def _list_checkpoint_names() -> set[str]:
    with _client() as c:
        r = c.get("/models/checkpoints")
        r.raise_for_status()
        payload = r.json()
    if isinstance(payload, dict):
        payload = payload.get("value") or payload.get("checkpoints") or []
    names: set[str] = set()
    for row in payload or []:
        if isinstance(row, str):
            names.add(row)
        elif isinstance(row, dict):
            name = row.get("name") or row.get("filename")
            if isinstance(name, str):
                names.add(name)
    return names


def _resolve_sdxl_checkpoint(prefer_realism: bool = False) -> str:
    """Pick RealVis when installed; otherwise stock SDXL base."""
    if prefer_realism:
        try:
            if SDXL_REALISM_CHECKPOINT in _list_checkpoint_names():
                return SDXL_REALISM_CHECKPOINT
        except Exception:
            pass
    return SDXL_CHECKPOINT


def generate_sdxl_art_frame(
    prompt: str,
    dest: Path,
    reference_image: Path,
    *,
    size: int = 1024,
    denoise: float = 0.78,
    steps: int = 30,
    seed: int | None = None,
    negative: str | None = None,
    prefer_realism: bool = False,
    cfg: float = 6.5,
) -> Path:
    """Photoreal-leaning art still via SDXL/RealVis img2img."""
    if not SDXL_ART_IMG2IMG_WORKFLOW.exists():
        raise ComfyError(f"Missing SDXL art workflow: {SDXL_ART_IMG2IMG_WORKFLOW}")
    if not reference_image.exists():
        raise ComfyError(f"Missing reference image: {reference_image}")

    free_memory()
    uploaded = upload_image(reference_image)
    wf = json.loads(SDXL_ART_IMG2IMG_WORKFLOW.read_text(encoding="utf-8"))
    side = normalize_art_size(size)
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    denoise = min(0.98, max(0.35, float(denoise)))
    steps = min(50, max(18, int(steps)))
    ckpt = _resolve_sdxl_checkpoint(prefer_realism=prefer_realism)

    wf["1"]["inputs"]["ckpt_name"] = ckpt
    wf["2"]["inputs"]["text"] = (prompt or "").strip()
    wf["3"]["inputs"]["text"] = (negative or _SDXL_ART_NEGATIVE).strip()
    wf["4"]["inputs"]["image"] = uploaded
    wf["5"]["inputs"]["width"] = side
    wf["5"]["inputs"]["height"] = side
    wf["5"]["inputs"]["upscale_method"] = "lanczos"
    wf["7"]["inputs"]["seed"] = seed
    wf["7"]["inputs"]["steps"] = steps
    wf["7"]["inputs"]["denoise"] = denoise
    wf["7"]["inputs"]["cfg"] = float(cfg)
    wf["7"]["inputs"]["sampler_name"] = "dpmpp_2m"
    wf["7"]["inputs"]["scheduler"] = "karras"
    wf["9"]["inputs"]["filename_prefix"] = "frameforge_sdxl_art"

    pid = queue_prompt(wf)
    hist = wait_prompt(pid, timeout_s=600.0)
    url = first_image_url(hist)
    return download_url(url, dest)
