from __future__ import annotations

import re
import shutil
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

from . import comfy_client, frame_pipeline, item_storage, ollama_client, projects as game_projects, storage, unity_export
from .animation_names import resolve_animation_name, sanitize_anim_name
from .config import ANIMATION_PRESETS, ITEM_ANIMATION_PRESETS, NON_LOOP_ANIM_TYPES, WAN_SQUARE_SIZES, WAN_I2V_WIDTH
from .styles import get_style, normalize_style


def _palette_for_project(project_id: str | None) -> list[str]:
    return game_projects.project_palette_colors(project_id)

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _update(job_id: str, **kwargs: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _start(
    kind: str,
    character_id: str | None,
    fn: Callable[[str], None],
    *,
    item_id: str | None = None,
) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "progress": 0.0,
            "message": "queued",
            "character_id": character_id,
            "item_id": item_id,
            "animation_id": None,
            "error": None,
            "result": None,
        }

    def runner() -> None:
        _update(job_id, status="running", message="starting", progress=0.05)
        try:
            fn(job_id)
            with _lock:
                if _jobs[job_id]["status"] != "failed":
                    _jobs[job_id]["status"] = "completed"
                    _jobs[job_id]["progress"] = 1.0
                    _jobs[job_id]["message"] = "done"
        except Exception as exc:  # noqa: BLE001
            _update(
                job_id,
                status="failed",
                error=str(exc),
                message="failed",
                result={"traceback": traceback.format_exc()[-2000:]},
            )

    threading.Thread(target=runner, daemon=True).start()
    return job_id


def start_character_job(
    name: str,
    prompt: str,
    pixel_size: int,
    polish: bool,
    seed: int | None,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
) -> str:
    style_id = normalize_style(style)
    spec = get_style(style_id)
    # Outline is a pixel-art option; ignore for non-pixel styles
    use_outline = bool(outline) and style_id == "pixel_art"
    meta = storage.create_character(
        name=name or "Creature",
        prompt=prompt,
        pixel_size=pixel_size,
        style=style_id,
        drop_shadow=drop_shadow,
        outline=use_outline,
        project_id=project_id,
    )
    cid = meta["id"]

    palette = _palette_for_project(project_id)

    def run(job_id: str) -> None:
        _update(job_id, character_id=cid, message="polishing prompt", progress=0.1)
        final_prompt = (
            ollama_client.polish_character_prompt(
                prompt, style_id, outline=use_outline, palette=palette or None
            )
            if polish
            else prompt
        )
        meta_local = storage.load_meta(cid)
        meta_local["prompt"] = final_prompt
        meta_local["style"] = style_id
        meta_local["drop_shadow"] = drop_shadow
        meta_local["outline"] = use_outline
        storage.save_meta(cid, meta_local)

        raw = storage.project_dir(cid) / "base_raw.png"
        _update(job_id, message="generating with ComfyUI", progress=0.25)
        comfy_client.generate_flux_character(
            final_prompt,
            raw,
            seed=seed,
            style=style_id,
            outline=use_outline,
            palette=palette or None,
        )

        _update(job_id, message="processing sprite", progress=0.85)
        base = storage.project_dir(cid) / "base.png"
        frame_pipeline.process_character_image(
            raw,
            base,
            pixel_size,
            resize=str(spec["resize"]),
            drop_shadow=drop_shadow,
            outline=use_outline,
        )
        _update(
            job_id,
            message="character ready",
            progress=0.95,
            result={"character_id": cid},
        )

    return _start("generate_character", cid, run)


def start_upload_character_job(
    *,
    image_bytes: bytes,
    filename: str,
    name: str,
    prompt: str,
    pixel_size: int,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
    key_background: bool = True,
    auto_crop: bool = True,
    no_scale: bool = False,
) -> str:
    """Create a character from an uploaded image (crop/resize pipeline, no Comfy)."""
    style_id = normalize_style(style)
    spec = get_style(style_id)
    use_outline = bool(outline) and style_id == "pixel_art"
    meta = storage.create_character(
        name=name or "Creature",
        prompt=prompt or "(uploaded)",
        pixel_size=pixel_size,
        style=style_id,
        drop_shadow=drop_shadow,
        outline=use_outline,
        project_id=project_id,
    )
    cid = meta["id"]
    root = storage.project_dir(cid)
    raw = root / "base_raw.png"
    source = root / "upload_source.png"
    _write_upload_image(image_bytes, filename, source)
    shutil.copy2(source, raw)

    def run(job_id: str) -> None:
        _update(job_id, character_id=cid, message="processing upload", progress=0.4)
        base = root / "base.png"
        frame_pipeline.process_character_image(
            raw,
            base,
            pixel_size,
            resize=str(spec["resize"]),
            drop_shadow=drop_shadow,
            outline=use_outline,
            key_background=key_background,
            auto_crop=auto_crop,
            no_scale=no_scale,
        )
        _update(
            job_id,
            message="character ready",
            progress=0.95,
            result={"character_id": cid},
        )

    return _start("upload_character", cid, run)


def start_img2img_character_job(
    *,
    image_bytes: bytes,
    filename: str,
    name: str,
    prompt: str,
    pixel_size: int,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
    seed: int | None = None,
    denoise: float | None = None,
    polish: bool = False,
) -> str:
    """Create a character via Flux img2img from an uploaded reference."""
    style_id = normalize_style(style)
    spec = get_style(style_id)
    use_outline = bool(outline) and style_id == "pixel_art"
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required for img2img")

    meta = storage.create_character(
        name=name or "Creature",
        prompt=prompt,
        pixel_size=pixel_size,
        style=style_id,
        drop_shadow=drop_shadow,
        outline=use_outline,
        project_id=project_id,
    )
    cid = meta["id"]
    root = storage.project_dir(cid)
    ref = root / "upload_source.png"
    _write_upload_image(image_bytes, filename, ref)

    palette = _palette_for_project(project_id)

    def run(job_id: str) -> None:
        _update(job_id, character_id=cid, message="polishing prompt", progress=0.1)
        final_prompt = (
            ollama_client.polish_character_prompt(
                prompt, style_id, outline=use_outline, palette=palette or None
            )
            if polish
            else prompt
        )
        meta_local = storage.load_meta(cid)
        meta_local["prompt"] = final_prompt
        storage.save_meta(cid, meta_local)

        raw = root / "base_raw.png"
        _update(job_id, message="img2img with ComfyUI", progress=0.25)
        strength = 0.72 if denoise is None else float(denoise)
        comfy_client.generate_pose_frame(
            final_prompt,
            raw,
            reference_image=ref,
            seed=seed,
            style=style_id,
            outline=use_outline,
            denoise=strength,
            max_denoise=0.9,
            identity_lock="same creature / subject as the reference image",
            palette=palette or None,
        )

        _update(job_id, message="processing sprite", progress=0.85)
        base = root / "base.png"
        frame_pipeline.process_character_image(
            raw,
            base,
            pixel_size,
            resize=str(spec["resize"]),
            drop_shadow=drop_shadow,
            outline=use_outline,
        )
        _update(
            job_id,
            message="character ready",
            progress=0.95,
            result={"character_id": cid},
        )

    return _start("img2img_character", cid, run)


def start_item_job(
    name: str,
    prompt: str,
    pixel_size: int,
    polish: bool,
    seed: int | None,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
) -> str:
    style_id = normalize_style(style)
    spec = get_style(style_id)
    use_outline = bool(outline) and style_id == "pixel_art"
    meta = item_storage.create_item(
        name=name or "Item",
        prompt=prompt,
        pixel_size=pixel_size,
        style=style_id,
        drop_shadow=drop_shadow,
        outline=use_outline,
        project_id=project_id,
    )
    iid = meta["id"]

    palette = _palette_for_project(project_id)

    def run(job_id: str) -> None:
        _update(job_id, item_id=iid, message="polishing prompt", progress=0.1)
        final_prompt = (
            ollama_client.polish_item_prompt(
                prompt, style_id, outline=use_outline, palette=palette or None
            )
            if polish
            else prompt
        )
        meta_local = item_storage.load_meta(iid)
        meta_local["prompt"] = final_prompt
        meta_local["style"] = style_id
        meta_local["drop_shadow"] = drop_shadow
        meta_local["outline"] = use_outline
        item_storage.save_meta(iid, meta_local)

        raw = item_storage.project_dir(iid) / "base_raw.png"
        _update(job_id, message="generating with ComfyUI", progress=0.25)
        comfy_client.generate_flux_character(
            final_prompt,
            raw,
            seed=seed,
            style=style_id,
            outline=use_outline,
            filename_prefix="frameforge_item",
            subject="item",
            palette=palette or None,
        )

        _update(job_id, message="processing sprite", progress=0.85)
        base = item_storage.project_dir(iid) / "base.png"
        frame_pipeline.process_character_image(
            raw,
            base,
            pixel_size,
            resize=str(spec["resize"]),
            drop_shadow=drop_shadow,
            outline=use_outline,
        )
        _update(
            job_id,
            message="item ready",
            progress=0.95,
            result={"item_id": iid},
        )

    return _start("generate_item", None, run, item_id=iid)


def start_upload_item_job(
    *,
    image_bytes: bytes,
    filename: str,
    name: str,
    prompt: str,
    pixel_size: int,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
    key_background: bool = True,
    auto_crop: bool = True,
) -> str:
    style_id = normalize_style(style)
    spec = get_style(style_id)
    use_outline = bool(outline) and style_id == "pixel_art"
    meta = item_storage.create_item(
        name=name or "Item",
        prompt=prompt or "(uploaded)",
        pixel_size=pixel_size,
        style=style_id,
        drop_shadow=drop_shadow,
        outline=use_outline,
        project_id=project_id,
    )
    iid = meta["id"]
    root = item_storage.project_dir(iid)
    raw = root / "base_raw.png"
    source = root / "upload_source.png"
    _write_upload_image(image_bytes, filename, source)
    shutil.copy2(source, raw)

    def run(job_id: str) -> None:
        _update(job_id, item_id=iid, message="processing upload", progress=0.4)
        base = root / "base.png"
        frame_pipeline.process_character_image(
            raw,
            base,
            pixel_size,
            resize=str(spec["resize"]),
            drop_shadow=drop_shadow,
            outline=use_outline,
            key_background=key_background,
            auto_crop=auto_crop,
        )
        _update(
            job_id,
            message="item ready",
            progress=0.95,
            result={"item_id": iid},
        )

    return _start("upload_item", None, run, item_id=iid)


def start_img2img_item_job(
    *,
    image_bytes: bytes,
    filename: str,
    name: str,
    prompt: str,
    pixel_size: int,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
    seed: int | None = None,
    denoise: float | None = None,
    polish: bool = False,
) -> str:
    style_id = normalize_style(style)
    spec = get_style(style_id)
    use_outline = bool(outline) and style_id == "pixel_art"
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required for img2img")

    meta = item_storage.create_item(
        name=name or "Item",
        prompt=prompt,
        pixel_size=pixel_size,
        style=style_id,
        drop_shadow=drop_shadow,
        outline=use_outline,
        project_id=project_id,
    )
    iid = meta["id"]
    root = item_storage.project_dir(iid)
    ref = root / "upload_source.png"
    _write_upload_image(image_bytes, filename, ref)

    palette = _palette_for_project(project_id)

    def run(job_id: str) -> None:
        _update(job_id, item_id=iid, message="polishing prompt", progress=0.1)
        final_prompt = (
            ollama_client.polish_item_prompt(
                prompt, style_id, outline=use_outline, palette=palette or None
            )
            if polish
            else prompt
        )
        meta_local = item_storage.load_meta(iid)
        meta_local["prompt"] = final_prompt
        item_storage.save_meta(iid, meta_local)

        raw = root / "base_raw.png"
        _update(job_id, message="img2img with ComfyUI", progress=0.25)
        strength = 0.72 if denoise is None else float(denoise)
        comfy_client.generate_pose_frame(
            final_prompt,
            raw,
            reference_image=ref,
            seed=seed,
            style=style_id,
            outline=use_outline,
            denoise=strength,
            max_denoise=0.9,
            identity_lock="same item / object as the reference image",
            subject="item",
            palette=palette or None,
        )

        _update(job_id, message="processing sprite", progress=0.85)
        base = root / "base.png"
        frame_pipeline.process_character_image(
            raw,
            base,
            pixel_size,
            resize=str(spec["resize"]),
            drop_shadow=drop_shadow,
            outline=use_outline,
        )
        _update(
            job_id,
            message="item ready",
            progress=0.95,
            result={"item_id": iid},
        )

    return _start("img2img_item", None, run, item_id=iid)


def _write_upload_image(image_bytes: bytes, filename: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename or "upload.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        suffix = ".png"
    tmp = dest.with_suffix(suffix)
    tmp.write_bytes(image_bytes)
    # Normalize to PNG so later pipeline steps are consistent
    if tmp.suffix.lower() != ".png":
        from PIL import Image

        Image.open(tmp).convert("RGBA").save(dest)
        tmp.unlink(missing_ok=True)
    elif tmp != dest:
        tmp.replace(dest)


def start_standing_job(
    character_id: str,
    set_as_source: bool = True,
    pose: str = "standing",
) -> str:
    """Build a pose / locomotion image for the character (selectable versions)."""

    pose_text = _normalize_pose(pose)

    def run(job_id: str) -> None:
        meta = storage.load_meta(character_id)
        pixel_size = int(meta["pixel_size"])
        style_id = normalize_style(meta.get("style"))
        resize = str(get_style(style_id)["resize"])
        drop_shadow = bool(meta.get("drop_shadow"))
        outline = bool(meta.get("outline")) and style_id == "pixel_art"
        root = storage.project_dir(character_id)
        base = root / "base.png"
        if not base.exists():
            raise FileNotFoundError("base.png missing")

        storage.migrate_standing_versions(character_id)
        work = root / f"_standing_build_{uuid.uuid4().hex[:8]}"
        work.mkdir(parents=True, exist_ok=True)

        _update(
            job_id,
            message=f"pose edit ({pose_text}) — Qwen Image Edit",
            progress=0.2,
        )
        standing_raw = work / "standing_raw.png"
        standing_preview = work / "standing_preview.png"
        standing_chroma = work / "standing_i2v.png"
        # Prefer high-res green-bg raw as edit source; fall back to base sprite.
        edit_src = root / "base_raw.png"
        if not edit_src.exists():
            edit_src = base
        _prepare_standing_source(
            character_prompt=str(meta.get("prompt") or ""),
            reference_image=edit_src,
            dest_raw=standing_raw,
            dest_preview=standing_preview,
            dest_chroma=standing_chroma,
            style_id=style_id,
            outline=outline,
            pixel_size=pixel_size,
            resize=resize,
            drop_shadow=drop_shadow,
            pose=pose_text,
            on_progress=lambda msg, p: _update(job_id, message=msg, progress=p),
        )
        standing = work / "standing.png"
        if standing_preview.exists():
            standing.write_bytes(standing_preview.read_bytes())

        version = storage.register_standing_version(
            character_id,
            src_dir=work,
            set_as_source=set_as_source,
            label=_pose_label(pose_text),
            pose=pose_text,
        )
        shutil.rmtree(work, ignore_errors=True)

        meta = storage.load_meta(character_id)
        _update(
            job_id,
            progress=0.95,
            message="pose image ready",
            result={
                "standing_id": version.get("id"),
                "standing_url": version.get("preview_url"),
                "pose": pose_text,
                "source_image": meta.get("source_image", "base"),
                "active_standing_id": meta.get("active_standing_id"),
            },
        )

    return _start("prepare_standing", character_id, run)


def start_art_job(
    character_id: str | None = None,
    style: str = "anime",
    purpose: str = "portrait",
    prompt: str | None = None,
    background: str | None = None,
    size: int = 1024,
    *,
    item_id: str | None = None,
) -> str:
    """Generate a detailed still (UI / inventory art) for a creature or item."""

    if bool(character_id) == bool(item_id):
        raise ValueError("pass exactly one of character_id or item_id")
    subject = "item" if item_id else "character"
    entity_id = item_id or character_id
    assert entity_id
    store = item_storage if subject == "item" else storage

    style_id = normalize_style(style)
    purpose_id = (purpose or ("inventory" if subject == "item" else "portrait")).strip().lower()
    if purpose_id not in _ART_PURPOSE_FRAME:
        purpose_id = "inventory" if subject == "item" else "portrait"
    extra = (prompt or "").strip()
    bg = (background or "").strip()
    side = comfy_client.normalize_art_size(size)

    def run(job_id: str) -> None:
        meta = store.load_meta(entity_id)
        root = store.project_dir(entity_id)
        base = root / "base.png"
        if not base.exists():
            raise FileNotFoundError("base.png missing")
        ref = root / "base_raw.png"
        if not ref.exists():
            ref = base

        work = root / f"_art_build_{uuid.uuid4().hex[:8]}"
        work.mkdir(parents=True, exist_ok=True)
        dest_raw = work / "art_raw.png"
        dest_preview = work / "art_preview.png"
        dest_art = work / "art.png"

        default_name = "item" if subject == "item" else "creature"
        character_prompt = str(meta.get("prompt") or meta.get("name") or default_name)
        source_style = normalize_style(meta.get("style"))
        user_bits = _art_restyle_prompt(
            style_id,
            purpose_id,
            character_prompt,
            extra,
            background=bg,
            subject=subject,
        )
        denoise, max_denoise = _art_denoise(source_style, style_id)
        steps = 36 if style_id != "pixel_art" else 28
        ref_src = base if base.exists() else ref
        soft = work / "art_ref_soft.png"
        blur = 3.4 if style_id == "realistic" else 2.2
        fill = _fill_rgb_for_background(bg, style_id)
        frame_pipeline.soften_reference_for_restyle(
            ref_src,
            soft,
            side=side,
            blur_radius=blur,
            fill_rgb=fill,
            noise_amp=18 if style_id == "realistic" else 12,
        )
        ref_for_gen = soft
        style_spec = get_style(style_id)
        use_sdxl = style_spec.get("art_backend") == "sdxl"

        _update(
            job_id,
            message=f"art still ({purpose_id} / {style_id} / {side}px"
            + (" / sdxl" if use_sdxl else "")
            + ")",
            progress=0.25,
        )
        if subject == "item":
            if style_id == "realistic":
                identity = (
                    "same recognizable game item as the reference — free photoreal "
                    "reinterpretation, new angle OK, full natural colors, no green screen, "
                    "no hand holding it unless the prompt asks"
                )
            else:
                identity = (
                    "clearly the same recognizable game item as the reference: same shape, "
                    "materials, markings and color palette. New angle is encouraged — do not "
                    "copy the sprite orientation slavishly. Fully redrawn in the target medium. "
                    "No green screen or chroma-key backdrop"
                )
        elif style_id == "realistic":
            identity = (
                "same recognizable creature species and signature flaming mane/tail idea "
                "as the reference — free photoreal reinterpretation, new pose OK, "
                "full natural colors, no green screen"
            )
        else:
            identity = (
                "clearly the same recognizable creature as the reference: same species, "
                "signature features, markings and color palette. New natural pose is "
                "encouraged — do not copy the sprite pose or stance. Fully redrawn in the "
                "target medium, not a pixel copy. No green screen or chroma-key backdrop"
            )
        if use_sdxl:
            sdxl_denoise = 0.95 if style_id == "realistic" else min(0.82, max(0.7, denoise))
            sdxl_cfg = 7.0 if (style_id == "realistic" and bg) else (
                5.5 if style_id == "realistic" else 6.5
            )
            comfy_client.generate_sdxl_art_frame(
                f"{identity}. {user_bits}",
                dest_raw,
                reference_image=ref_for_gen,
                size=side,
                denoise=sdxl_denoise,
                steps=40 if style_id == "realistic" else max(28, steps - 4),
                prefer_realism=(style_id == "realistic"),
                cfg=sdxl_cfg,
            )
        else:
            comfy_client.generate_pose_frame(
                user_bits,
                dest_raw,
                reference_image=ref_for_gen,
                seed=None,
                style=style_id,
                outline=False,
                denoise=denoise,
                steps=steps,
                max_denoise=max_denoise,
                chroma=False,
                identity_lock=identity,
                size=side,
                subject=subject,
            )
        _update(job_id, message="processing art preview", progress=0.85)
        dest_art.write_bytes(dest_raw.read_bytes())
        frame_pipeline.copy_or_resize_preview(
            dest_raw, dest_preview, max_side=min(side, 1024)
        )

        entry = store.register_art_version(
            entity_id,
            src_dir=work,
            style=style_id,
            purpose=purpose_id,
            prompt=extra or None,
            background=bg or None,
            size=side,
        )
        shutil.rmtree(work, ignore_errors=True)
        _update(
            job_id,
            progress=0.95,
            message="art still ready",
            result={
                "art_id": entry.get("id"),
                "preview_url": entry.get("preview_url"),
                "style": style_id,
                "purpose": purpose_id,
                "size": side,
                "background": bg or None,
            },
        )

    return _start(
        "generate_art",
        character_id,
        run,
        item_id=item_id,
    )


def start_animation_job(
    character_id: str | None = None,
    anim_type: str = "walk_side",
    variants: int = 1,
    frames: int = 6,
    fps: int = 8,
    method: str = "i2v",
    source_image: str | None = None,
    motion_notes: str = "",
    name: str = "",
    wan_size: int | None = None,
    no_scale: bool = False,
    *,
    item_id: str | None = None,
) -> str:
    if bool(character_id) == bool(item_id):
        raise ValueError("pass exactly one of character_id or item_id")
    subject = "item" if item_id else "character"
    entity_id = item_id or character_id
    assert entity_id
    store = item_storage if subject == "item" else storage
    presets = ITEM_ANIMATION_PRESETS if subject == "item" else ANIMATION_PRESETS

    render_side = wan_size or WAN_I2V_WIDTH
    if render_side not in WAN_SQUARE_SIZES:
        raise ValueError(f"wan_size must be one of {WAN_SQUARE_SIZES}")
    if no_scale:
        meta_check = store.load_meta(entity_id)
        if method != "i2v" or int(meta_check["pixel_size"]) != render_side:
            raise ValueError("no_scale requires i2v and wan_size equal to pixel_size")
        if meta_check.get("outline") or meta_check.get("drop_shadow"):
            raise ValueError("no_scale requires outline=false and drop_shadow=false")
    anim_id = uuid.uuid4().hex[:10]
    key = anim_type.strip().lower().replace(" ", "_")
    if key not in presets and anim_type.strip().lower() in presets:
        key = anim_type.strip().lower()
    notes = (motion_notes or "").strip()
    requested_name = (name or "").strip()

    def run(job_id: str) -> None:
        meta = store.load_meta(entity_id)
        type_key = key if key in presets else anim_type
        pixel_size = int(meta["pixel_size"])
        style_id = normalize_style(meta.get("style"))
        resize = str(get_style(style_id)["resize"])
        drop_shadow = bool(meta.get("drop_shadow"))
        outline = bool(meta.get("outline")) and style_id == "pixel_art"
        proj = store.project_dir(entity_id)
        base = proj / "base.png"
        if not base.exists():
            raise FileNotFoundError("base.png missing")

        root = store.anim_dir(entity_id, anim_id)
        root.mkdir(parents=True, exist_ok=True)

        chosen = "base"
        if subject == "character":
            chosen = (source_image or meta.get("source_image") or "base").strip().lower()
            if chosen not in ("base", "standing"):
                chosen = "base"

        base_chroma = proj / "base_i2v.png"
        frame_pipeline.write_chroma_composite(base, base_chroma)
        anim_source = base_chroma
        standing_id = meta.get("active_standing_id") if subject == "character" else None
        if subject == "character" and chosen == "standing":
            anim_source = storage.resolve_standing_i2v(entity_id, standing_id)

        _update(
            job_id,
            animation_id=anim_id,
            message=(
                f"using standing:{standing_id}" if chosen == "standing" else "using base"
            )
            + " as animation source",
            progress=0.1,
        )

        variant_infos: list[dict[str, Any]] = []

        for v in range(variants):
            _update(
                job_id,
                animation_id=anim_id,
                message=f"variant {v + 1}/{variants}",
                progress=0.15 + 0.75 * (v / max(variants, 1)),
            )
            vdir = root / f"v{v}"
            frames_dir = vdir / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            used_method = method
            video_url: str | None = None

            try:
                if method == "i2v":
                    motion = ollama_client.motion_prompt(
                        anim_type,
                        meta["prompt"],
                        v,
                        presets=presets,
                        subject=subject,
                        motion_notes=notes,
                    )
                    video = vdir / "clip.mp4"
                    comfy_client.run_wan_i2v(anim_source, motion, video, width=render_side, height=render_side, no_scale=no_scale)
                    if video.exists():
                        video_url = f"/files/{entity_id}/anims/{anim_id}/v{v}/clip.mp4"
                    raw_frames = frame_pipeline.extract_video_frames(
                        video, vdir / "raw_frames", frames
                    )
                    frame_pipeline.process_animation_frames(
                        raw_frames,
                        frames_dir,
                        pixel_size,
                        resize=resize,
                        drop_shadow=drop_shadow,
                        outline=outline,
                        preserve_canvas=no_scale,
                    )
                else:
                    used_method = "pose_keyframes"
                    _run_pose_keyframes(
                        character_prompt=str(meta.get("prompt") or ""),
                        anim_type=anim_type,
                        frames=frames,
                        variant_index=v,
                        reference_image=anim_source,
                        frames_dir=frames_dir,
                        tmp_dir=vdir / "pose_tmp",
                        pixel_size=pixel_size,
                        resize=resize,
                        drop_shadow=drop_shadow,
                        outline=outline,
                        style_id=style_id,
                        subject=subject,
                        presets=presets,
                        motion_notes=notes,
                    )
            except Exception as i2v_exc:  # noqa: BLE001
                if no_scale:
                    raise  # Never silently substitute a resized pose animation.
                used_method = "pose_keyframes"
                (vdir / "i2v_error.txt").write_text(str(i2v_exc), encoding="utf-8")
                _run_pose_keyframes(
                    character_prompt=str(meta.get("prompt") or ""),
                    anim_type=anim_type,
                    frames=frames,
                    variant_index=v,
                    reference_image=anim_source,
                    frames_dir=frames_dir,
                    tmp_dir=vdir / "pose_tmp",
                    pixel_size=pixel_size,
                    resize=resize,
                    drop_shadow=drop_shadow,
                    outline=outline,
                    style_id=style_id,
                    subject=subject,
                    presets=presets,
                    motion_notes=notes,
                )

            info: dict[str, Any] = {
                "index": v,
                "method": used_method,
                "source_image": chosen,
                "wan_size": render_side,
                "no_scale": no_scale,
                "frame_urls": [
                    f"/files/{entity_id}/anims/{anim_id}/v{v}/frames/{p.name}"
                    for p in sorted(frames_dir.glob("frame_*.png"))
                ],
            }
            if video_url:
                info["video_url"] = video_url
            variant_infos.append(info)

        # Resolve name at the end so concurrent jobs don't collide.
        latest = store.load_meta(entity_id)
        anim_name = resolve_animation_name(latest, str(type_key), requested_name)
        store.upsert_animation(
            entity_id,
            anim_id,
            anim_type=type_key,
            fps=fps,
            frames=frames,
            variants=variant_infos,
            selected_variant=None,
            motion_notes=notes,
            name=anim_name,
        )
        _update(
            job_id,
            animation_id=anim_id,
            progress=0.95,
            result={
                "animation_id": anim_id,
                "name": anim_name,
                "variants": variant_infos,
            },
            message=f"animation “{anim_name}” ready",
        )

    return _start("create_animation", character_id, run, item_id=item_id)


_ART_PURPOSE_FRAME = {
    "portrait": "portrait framing, head and upper body dominant, shallow depth of field",
    "inventory": "three-quarter collectible still, clear readable full silhouette",
    "showcase": "full body showcase, dynamic but readable pose for a character select screen",
    "scene": "creature featured in an environment scene, cinematic composition",
}

_ITEM_ART_PURPOSE_FRAME = {
    "portrait": "icon framing, item fills most of the frame, shallow depth of field",
    "inventory": "inventory icon still, clear readable full item silhouette, slight three-quarter",
    "showcase": "hero product showcase of the item, dramatic readable presentation",
    "scene": "item featured in an environment scene, cinematic composition",
}

_ART_DEFAULT_BACKGROUND = {
    "realistic": (
        "real outdoor environment with natural ground, soft atmospheric depth, "
        "believable ambient light — never a solid green void"
    ),
    "detailed_illustration": (
        "painted scenic backdrop with depth and ground plane, concept-art environment, "
        "never a solid green void"
    ),
    "stylized_3d": (
        "simple studio set with soft colored backdrop and ground plane, "
        "subtle contact shadow — never chroma key green"
    ),
    "anime": "soft painted environment backdrop with depth, never flat chroma green",
    "cartoon": "simple colorful set with ground plane, never chroma key green",
    "comic": "graphic environment with inked depth cues, never chroma key green",
    "low_poly": "minimal faceted ground and sky, never chroma key green",
    "pixel_art": "readable scenic backdrop in matching pixel style, not empty void",
}

# Strip sprite/pipeline jargon so img2img can leave the pixel look behind.
_ART_STRIP_PHRASES = (
    "umempart",
    "masterpiece modern pixel art sprite",
    "modern pixel art sprite",
    "detailed modern pixel art",
    "modern pixel art",
    "pixel art sprite",
    "pixel art",
    "pixelart",
    "pixel-art",
    "chunky pixels",
    "crisp hard edges",
    "crisp hard pixel edges",
    "hard pixel edges",
    "limited palette",
    "limited color palette",
    "deliberate shading bands",
    "two-tone white and light-gray body shading",
    "cool gray shade band",
    "shade band",
    "sharp pixel clusters",
    "fire pixels",
    "indie RPG monster sprite",
    "game mascot sprite",
    "game sprite",
    "sprite sheet",
    "no anti alias glow",
    "no soft blur",
    "no pink rim light",
    "solid bright flat green background #00FF00",
    "solid bright magenta background #FF00FF",
    "chroma key green",
    "empty void",
    "no ground plane",
    "single character, full body centered, readable silhouette",
)


def _subject_for_art_restyle(
    character_prompt: str, *, entity_kind: str = "character"
) -> str:
    """Keep identity words; drop pixel/chroma pipeline tags that fight restyle."""
    text = character_prompt or ""
    for phrase in _ART_STRIP_PHRASES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*,+", ", ", text)
    text = text.strip(" ,.")
    if text:
        return text
    return "fantasy game item" if entity_kind == "item" else "fantasy creature"


def _fill_rgb_for_background(background: str, style_id: str) -> tuple[int, int, int]:
    """Tint the img2img reference fill toward the requested environment (not a black void)."""
    text = (background or "").lower()
    if any(
        k in text
        for k in (
            "forest",
            "wood",
            "woods",
            "tree",
            "jungle",
            "grass",
            "meadow",
            "garden",
            "fairytale",
            "fairy tale",
        )
    ):
        if any(k in text for k in ("day", "daylight", "sunny", "noon", "morning")):
            return (142, 188, 118)
        return (96, 138, 88)
    if any(k in text for k in ("sky", "cloud", "daylight", "day ", "sunny", "beach")):
        return (168, 198, 228)
    if any(k in text for k in ("snow", "winter", "ice", "arctic")):
        return (190, 200, 210)
    if any(k in text for k in ("ocean", "sea", "lake", "water", "river")):
        return (90, 130, 160)
    if any(
        k in text
        for k in ("volcan", "lava", "ash", "ember", "night", "dusk", "midnight", "cave")
    ):
        return (62, 48, 36)
    if style_id == "realistic":
        return (130, 140, 128)
    return (48, 46, 44)


def _expand_art_background(background: str) -> str:
    """Turn short user background notes into concrete scenic cues."""
    raw = (background or "").strip()
    if not raw:
        return raw
    text = raw.lower()
    extras: list[str] = []
    foresty = any(
        k in text
        for k in ("forest", "wood", "woods", "tree", "jungle", "fairytale", "fairy tale")
    )
    daylight = any(k in text for k in ("day", "daylight", "sunny", "noon", "morning"))
    if foresty:
        extras.append(
            "lush green leafy canopy, mossy trunks, ferns and wildflowers, "
            "readable tree trunks and foliage depth"
        )
    if daylight or ("fairytale" in text or "fairy tale" in text):
        extras.append(
            "bright soft daylight, sunbeams through leaves, vivid greens, "
            "clear blue patches of sky, cheerful enchanted atmosphere — not night, "
            "not underexposed, not smoky ash darkness"
        )
    if not extras:
        return raw
    return f"{raw}. " + ", ".join(extras)


def _art_restyle_prompt(
    style_id: str,
    purpose_id: str,
    character_prompt: str,
    extra: str,
    background: str = "",
    *,
    subject: str = "character",
) -> str:
    entity_kind = "item" if subject == "item" else "character"
    identity = _subject_for_art_restyle(character_prompt, entity_kind=entity_kind)
    purpose_table = _ITEM_ART_PURPOSE_FRAME if entity_kind == "item" else _ART_PURPOSE_FRAME
    default_purpose = "inventory" if entity_kind == "item" else "portrait"
    purpose_bits = purpose_table.get(purpose_id, purpose_table[default_purpose])
    user_bg = (background or "").strip()
    bg = _expand_art_background(user_bg) or _ART_DEFAULT_BACKGROUND.get(
        style_id, _ART_DEFAULT_BACKGROUND["stylized_3d"]
    )
    no_chroma = (
        "no chroma-key screen, no neon lime #00FF00 void, no solid flat studio backdrop — "
        "real photographed or painted scenery with depth"
    )
    env = (
        f"set in this environment filling most of the frame: {bg}. "
        "the background must be clearly visible and match that description; "
        "not a black void, not empty darkness, not a solid color plate"
    )
    noun = "item" if entity_kind == "item" else "creature"
    if style_id == "realistic":
        if entity_kind == "item":
            medium = (
                "ultra photoreal photograph of this game item as a real physical object, "
                "full natural color range, rich materials and lighting"
            )
            anti = (
                "not illustration, not flat colors, not limited palette, not posterized, "
                "not cartoon, not cel shading, not vector art, not CGI plastic, "
                "not pixel art, not a sprite, not a black void background"
            )
            freedom = (
                "unrestricted realistic materials, metal wood glass fabric as appropriate, "
                "natural shadows, photographic detail"
            )
            pose_bit = "any clear product angle is fine; keep the item recognizable"
        else:
            medium = (
                "ultra photoreal photograph of a living horse with a real flaming mane and "
                "flaming tail, full natural color range, rich lighting, no horn"
            )
            anti = (
                "not illustration, not flat colors, not limited palette, not posterized, "
                "not cartoon, not cel shading, not vector art, not CGI plastic, "
                "not pixel art, not a sprite, not a unicorn, not a black void background"
            )
            freedom = (
                "unrestricted realistic colors and materials, volumetric fire with orange "
                "yellow and white heat illuminating the scene, natural shadows, photographic detail"
            )
            pose_bit = "any natural powerful horse pose is fine; keep the creature recognizable"
        parts = [
            env,
            medium,
            anti,
            freedom,
            no_chroma,
            purpose_bits,
            pose_bit,
            identity,
            extra,
        ]
        return ". ".join(p for p in parts if p)

    if style_id == "detailed_illustration":
        medium = f"highly detailed digital illustration / concept art of this {noun}"
        anti = "not a photograph, not photoreal, not pixel art, not a flat sprite"
    elif style_id == "stylized_3d":
        medium = f"fully re-render this {noun} as a polished stylized 3D game asset"
        anti = "not photoreal, not pixel art, not a flat sprite"
    else:
        medium = f"fully re-render this {noun} in {style_id.replace('_', ' ')} style"
        anti = (
            "not pixel art, not a sprite, not 8-bit, no visible pixel grid"
            if style_id != "pixel_art"
            else ""
        )
    parts = [
        env,
        medium,
        anti,
        no_chroma,
        purpose_bits,
        f"new natural angle ok, keep the {noun} clearly recognizable",
        identity,
        extra,
    ]
    return ". ".join(p for p in parts if p)


def _art_denoise(source_style: str, target_style: str) -> tuple[float, float]:
    """Stronger denoise when leaving pixel/sprite look for illustration styles."""
    src = normalize_style(source_style)
    dst = normalize_style(target_style)
    if src == "pixel_art" and dst == "realistic":
        return 0.93, 0.97
    if src == "pixel_art" and dst != "pixel_art":
        return 0.90, 0.95
    if src != dst:
        return 0.78, 0.90
    return 0.65, 0.80


def _normalize_pose(pose: str | None) -> str:
    text = " ".join((pose or "standing").strip().split())
    return text[:120] if text else "standing"


def _pose_label(pose: str) -> str:
    text = _normalize_pose(pose)
    return text[:1].upper() + text[1:] if text else "Pose"


def _pose_edit_prompt(pose: str) -> str:
    pose_text = _normalize_pose(pose)
    if pose_text.lower() == "standing":
        detail = (
            "a calm side-view standing on all four legs, "
            "both front hooves and both hind hooves planted on the ground, "
            "body and spine horizontal and level, neck forward, neutral idle locomotion stance. "
            "Not rearing, not jumping, not galloping, no lifted front legs"
        )
    else:
        detail = (
            f"a clear side-view {pose_text} pose, readable silhouette, "
            "full body still in frame, natural weight and limb placement"
        )
    return (
        "Keep this exact same modern pixel art character identity and colors. "
        f"Only change the pose to {detail}. "
        "Keep solid bright green background. Do not redesign the character."
    )


def _pose_refine_prompt(pose: str) -> str:
    pose_text = _normalize_pose(pose)
    return (
        f"exact same character design and colors as reference, keep this {pose_text} pose, "
        "side view, modern pixel art umempart, crisp hard pixel edges, limited palette, "
        "solid bright green background #00FF00, no soft blur, no anti alias"
    )


def _prepare_standing_source(
    *,
    character_prompt: str,
    reference_image: Path,
    dest_raw: Path,
    dest_preview: Path,
    dest_chroma: Path,
    style_id: str,
    outline: bool,
    pixel_size: int,
    resize: str,
    drop_shadow: bool,
    pose: str = "standing",
    on_progress: Callable[[str, float], None] | None = None,
) -> Path:
    """Pose via Qwen Image Edit (identity) + Flux/ume refine (pixel look)."""
    del character_prompt  # reserved for future prompt blending
    pose_text = _normalize_pose(pose)
    edited = dest_raw.with_name("standing_qwen_edit.png")
    if on_progress:
        on_progress(f"pose edit ({pose_text}) — Qwen Image Edit", 0.35)
    comfy_client.run_qwen_image_edit(
        reference_image,
        _pose_edit_prompt(pose_text),
        edited,
        use_lightning=True,
        filename_prefix="frameforge_standing_qwen",
    )
    if on_progress:
        on_progress("pixel refine (Flux + ume LoRA)", 0.65)
    comfy_client.generate_pose_frame(
        _pose_refine_prompt(pose_text),
        dest_raw,
        reference_image=edited,
        seed=None,
        style=style_id,
        outline=False,
        denoise=0.42,
        steps=28,
        max_denoise=0.55,
    )
    if on_progress:
        on_progress("processing pose sprite", 0.85)
    frame_pipeline.process_character_image(
        dest_raw,
        dest_preview,
        pixel_size,
        resize=resize,
        drop_shadow=drop_shadow,
        outline=outline,
    )
    try:
        frame_pipeline.write_chroma_composite(dest_preview, dest_chroma)
    except Exception:
        dest_chroma.write_bytes(dest_raw.read_bytes())
    return dest_chroma


def _run_pose_keyframes(
    *,
    character_prompt: str,
    anim_type: str,
    frames: int,
    variant_index: int,
    reference_image: Path,
    frames_dir: Path,
    tmp_dir: Path,
    pixel_size: int,
    resize: str,
    drop_shadow: bool,
    outline: bool,
    style_id: str,
    subject: str = "character",
    presets: dict[str, str] | None = None,
    motion_notes: str = "",
) -> list[Path]:
    """Img2img poses from the base sprite — same seed, pose-only prompts."""
    poses = ollama_client.pose_prompts(
        anim_type,
        character_prompt,
        frames,
        presets=presets,
        subject=subject,
        motion_notes=motion_notes,
    )
    tmp_dir.mkdir(parents=True, exist_ok=True)
    raw_list: list[Path] = []
    seed = 42000 + variant_index * 97
    noun = "item" if subject == "item" else "character"
    for i, pose in enumerate(poses):
        raw = tmp_dir / f"pose_raw_{i:02d}.png"
        prompt = (
            f"{pose}, full {'object' if subject == 'item' else 'body'} still centered, "
            f"keep identical {noun} and colors, "
            "do not add unrelated props, solid bright green background #00FF00"
        )
        t = i / max(frames - 1, 1)
        denoise = 0.36 + 0.1 * (1.0 - abs(0.5 - t) * 2.0)
        comfy_client.generate_pose_frame(
            prompt,
            raw,
            reference_image=reference_image,
            seed=seed,
            style=style_id,
            outline=outline,
            denoise=denoise,
            subject=subject,
        )
        raw_list.append(raw)
    return frame_pipeline.process_animation_frames(
        raw_list,
        frames_dir,
        pixel_size,
        resize=resize,
        drop_shadow=drop_shadow,
        outline=outline,
    )


def export_unity(
    character_id: str | None = None,
    *,
    item_id: str | None = None,
) -> dict[str, Any]:
    if bool(character_id) == bool(item_id):
        raise ValueError("pass exactly one of character_id or item_id")
    entity_id = item_id or character_id
    assert entity_id
    store = item_storage if item_id else storage
    meta = store.load_meta(entity_id)
    anims_out: list[dict[str, Any]] = []
    for anim_id, anim in (meta.get("animations") or {}).items():
        sel = anim.get("selected_variant")
        if sel is None:
            variants = anim.get("variants") or []
            if not variants:
                frames0 = store.anim_dir(entity_id, anim_id) / "v0" / "frames"
                if frames0.is_dir() and any(frames0.glob("frame_*.png")):
                    sel = 0
                else:
                    continue
            else:
                sel = int(variants[0].get("index", 0))
        frames_dir = store.anim_dir(entity_id, anim_id) / f"v{sel}" / "frames"
        frames = sorted(frames_dir.glob("frame_*.png"))
        if not frames:
            continue
        anim_type = str(anim.get("type") or "")
        anim_name = str(anim.get("name") or anim_type or anim_id)
        type_key = sanitize_anim_name(anim_type or anim_name)
        anims_out.append(
            {
                "name": anim_name,
                "fps": anim.get("fps") or 8,
                "loop": type_key not in NON_LOOP_ANIM_TYPES,
                "frames": frames,
            }
        )
    if not anims_out:
        raise ValueError("No animation frames available for export (generate + select a variant)")
    out_dir = store.project_dir(entity_id) / "export"
    return unity_export.build_unity_export(
        meta.get("name") or entity_id,
        int(meta["pixel_size"]),
        anims_out,
        out_dir,
    )
