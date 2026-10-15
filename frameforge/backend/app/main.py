from __future__ import annotations

from io import BytesIO
from typing import Literal

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image

from . import (
    comfy_client,
    frame_pipeline,
    item_storage,
    jobs,
    ollama_client,
    projects as game_projects,
    storage,
)
from .animation_names import resolve_animation_name
from .config import ANIMATION_PRESETS, GAME_PROJECTS_DIR, ITEM_ANIMATION_PRESETS, PIXEL_SIZES, WAN_SQUARE_SIZES, WAN_I2V_WIDTH
from .models import (
    AnimationCreateRequest,
    AnimationRenameRequest,
    ApplyPaletteRequest,
    CreateProjectRequest,
    GenerateArtRequest,
    GenerateCharacterRequest,
    GenerateItemRequest,
    HealthResponse,
    ItemAnimationCreateRequest,
    JobStatus,
    PolishPromptRequest,
    PolishPromptResponse,
    PrepareStandingRequest,
    SelectVariantRequest,
    SetSourceImageRequest,
    UpdateProjectRequest,
)
from .asset_refs import find_by_ref
from .palettes import build_palette_from_images, list_palette_presets, normalize_palette
from .styles import list_styles, normalize_style

app = FastAPI(title="Frameforge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GAME_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
game_projects.ensure_migrated()


@app.get("/files/{asset_id}/{file_path:path}")
def serve_asset_file(asset_id: str, file_path: str) -> FileResponse:
    """Serve character or item assets under /files/{id}/…"""
    try:
        root = game_projects.resolve_asset_dir(asset_id).resolve()
    except FileNotFoundError as exc:
        raise HTTPException(404, "file not found") from exc
    target = (root / file_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(404, "file not found") from exc
    if not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, comfy=comfy_client.health(), ollama=ollama_client.health(), sizes=size_capabilities())


@app.get("/presets/sizes")
def size_capabilities() -> dict:
    return {
        "export_square_sizes": list(PIXEL_SIZES),
        "wan_square_sizes": list(WAN_SQUARE_SIZES),
        "wan_default_size": WAN_I2V_WIDTH,
        "wan_grid_multiple": 32,
        "recommended_test_size": 512,
        "experimental_sizes": [768, 1024],
        "no_scale": {
            "upload": "mode=upload, no_scale=true, auto_crop=false, outline=false, drop_shadow=false; canvas-only center crop/pad allowed if subject fits",
            "animation": "method=i2v, no_scale=true, wan_size=pixel_size; preserves frame canvas and fails on size mismatch; no pose fallback",
            "limitation": "WAN regenerates pixels; no_scale guarantees dimensions, not pixel-identical details. Higher sizes require more VRAM/time.",
        },
    }


@app.get("/presets/animations")
def animation_presets() -> dict:
    return {"presets": ANIMATION_PRESETS}


@app.get("/presets/animations/items")
def item_animation_presets() -> dict:
    return {"presets": ITEM_ANIMATION_PRESETS, "default": "destroyed"}


@app.get("/presets/styles")
def style_presets() -> dict:
    return {"styles": list_styles(), "default": "pixel_art"}


@app.get("/presets/palettes")
def palette_presets() -> dict:
    return {"presets": list_palette_presets(), "default": "none"}


@app.get("/lookup/{ref}")
def lookup_by_ref(ref: int, include_trash: bool = Query(default=False)) -> dict:
    """Resolve numeric ref to character/item/animation/standing/art (active by default)."""
    hit = find_by_ref(int(ref), include_trash=include_trash)
    if not hit:
        raise HTTPException(404, f"ref not found: {ref}")
    return hit


@app.post("/presets/palettes/from-images")
async def palette_from_images(
    files: list[UploadFile] = File(...),
    seed: str = Form(""),
) -> dict:
    """Extract fixed colors from uploads, merge with existing seed, match/fill palette."""
    if not files:
        raise HTTPException(400, "at least one image required")
    existing = normalize_palette(
        [c for c in (seed or "").replace(",", " ").split() if c.strip()]
    )
    images: list[Image.Image] = []
    for f in files[:12]:
        data = await f.read()
        if not data:
            continue
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, f"image too large (max 25MB): {f.filename or 'upload'}")
        try:
            images.append(Image.open(BytesIO(data)))
        except Exception as exc:
            raise HTTPException(400, f"invalid image: {f.filename or 'upload'}") from exc
    if not images:
        raise HTTPException(400, "no readable images")
    return build_palette_from_images(images, existing_seed=existing)


@app.get("/projects")
def list_projects() -> list[dict]:
    return game_projects.list_projects()


@app.post("/projects")
def create_project(body: CreateProjectRequest) -> dict:
    return game_projects.create_project(
        name=body.name,
        description=body.description,
        default_style=body.default_style,
        default_pixel_size=body.default_pixel_size,
        default_drop_shadow=body.default_drop_shadow,
        default_outline=body.default_outline,
        palette_preset=body.palette_preset,
        palette=body.palette,
        palette_seed=body.palette_seed,
    )


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        return game_projects.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "project not found") from exc


@app.put("/projects/{project_id}")
def update_project(project_id: str, body: UpdateProjectRequest) -> dict:
    try:
        return game_projects.update_project(project_id, body.model_dump(exclude_unset=True))
    except FileNotFoundError as exc:
        raise HTTPException(404, "project not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    try:
        game_projects.delete_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "project not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.get("/characters")
def list_characters(project_id: str | None = Query(default=None)) -> list[dict]:
    items = []
    for meta in storage.list_characters(project_id):
        cid = meta["id"]
        payload = _character_payload(cid, meta)
        payload["animation_ids"] = list((meta.get("animations") or {}).keys())
        items.append(payload)
    return items


@app.get("/characters/trash")
def list_trashed_characters(project_id: str | None = Query(default=None)) -> list[dict]:
    return storage.list_trashed_characters(project_id)


@app.delete("/characters/{character_id}")
def trash_character(character_id: str) -> dict:
    try:
        if game_projects.is_character_trashed(character_id):
            raise HTTPException(404, "character not found")
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.soft_delete_character(character_id)
    except KeyError as exc:
        raise HTTPException(404, "character not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/characters/{character_id}/restore")
def restore_character(character_id: str) -> dict:
    try:
        meta = storage.restore_character(character_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed character not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "trashed character not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "ok": True,
        "character": _character_payload(character_id, meta),
    }


def _character_payload(character_id: str, meta: dict) -> dict:
    meta = storage.migrate_standing_versions(character_id, dict(meta))
    versions = list(meta.get("standing_versions") or [])
    active_id = meta.get("active_standing_id")
    active = next((v for v in versions if v.get("id") == active_id), None)
    has_standing = bool(versions)
    source = meta.get("source_image") or "base"
    if source == "standing" and not has_standing:
        source = "base"
    try:
        project_id = meta.get("project_id") or game_projects.project_id_for_character(character_id)
    except FileNotFoundError:
        project_id = meta.get("project_id")
    payload = {
        **meta,
        "project_id": project_id,
        "base_url": f"/files/{character_id}/base.png",
        "preview_url": f"/files/{character_id}/base_preview.png",
        "has_standing": has_standing,
        "source_image": source,
        "active_standing_id": active_id if has_standing else None,
        "standing_versions": versions,
        "art_versions": list(meta.get("art_versions") or []),
        "standing_url": (active or {}).get("preview_url")
        or (
            f"/files/{character_id}/standing_preview.png"
            if (storage.project_dir(character_id) / "standing_preview.png").exists()
            else None
        ),
    }
    return payload


@app.get("/characters/{character_id}")
def get_character(character_id: str) -> dict:
    try:
        if game_projects.is_character_trashed(character_id):
            raise HTTPException(404, "character not found")
        meta = storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    return _character_payload(character_id, meta)


@app.post("/characters/{character_id}/apply-palette")
def apply_character_palette(
    character_id: str, body: ApplyPaletteRequest | None = None
) -> dict:
    try:
        meta = storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        project_id = meta.get("project_id") or game_projects.project_id_for_character(
            character_id
        )
    except FileNotFoundError:
        project_id = meta.get("project_id")
    colors = game_projects.project_palette_colors(project_id)
    if not colors:
        raise HTTPException(400, "Active project has no palette set")
    include = True if body is None else bool(body.include_animations)
    counts = frame_pipeline.apply_palette_to_asset_dir(
        storage.project_dir(character_id),
        colors,
        include_animations=include,
    )
    return {
        "ok": True,
        "palette": colors,
        "counts": counts,
        "character": _character_payload(character_id, storage.load_meta(character_id)),
    }


@app.post("/prompts/polish", response_model=PolishPromptResponse)
def polish_prompt(body: PolishPromptRequest) -> PolishPromptResponse:
    text = (body.prompt or "").strip()
    if not text:
        raise HTTPException(400, "prompt is required")
    style_id = normalize_style(body.style)
    game_context = ""
    palette: list[str] = []
    if body.project_id:
        try:
            proj = game_projects.load_project(body.project_id)
            game_context = (proj.get("description") or "").strip()
            palette = list(proj.get("palette") or [])
        except FileNotFoundError as exc:
            raise HTTPException(404, "project not found") from exc
    outline = bool(body.outline) and style_id == "pixel_art"
    if body.subject == "item":
        polished, source = ollama_client.polish_item_prompt_detailed(
            text,
            style_id,
            outline=outline,
            game_context=game_context or None,
            palette=palette or None,
        )
    else:
        polished, source = ollama_client.polish_character_prompt_detailed(
            text,
            style_id,
            outline=outline,
            game_context=game_context or None,
            palette=palette or None,
        )
    return PolishPromptResponse(prompt=polished, source=source, style=style_id)


@app.post("/characters")
def create_character(body: GenerateCharacterRequest) -> dict:
    project_id = body.project_id
    if project_id:
        try:
            game_projects.load_project(project_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "project not found") from exc
    try:
        job_id = jobs.start_character_job(
            name=body.name or "Creature",
            prompt=body.prompt,
            pixel_size=body.pixel_size,
            polish=body.polish_prompt,
            seed=body.seed,
            style=body.style,
            drop_shadow=body.drop_shadow,
            outline=body.outline,
            project_id=project_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc) or "project required") from exc
    job = jobs.get_job(job_id)
    return {"job_id": job_id, "character_id": job.get("character_id") if job else None}


def _parse_form_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/characters/from-image")
async def create_character_from_image(
    file: UploadFile = File(...),
    mode: Literal["upload", "img2img"] = Form("upload"),
    name: str = Form("Creature"),
    project_id: str | None = Form(None),
    pixel_size: int = Form(128),
    style: str = Form("pixel_art"),
    drop_shadow: bool | str = Form(False),
    outline: bool | str = Form(False),
    prompt: str = Form(""),
    key_background: bool | str = Form(True),
    auto_crop: bool | str = Form(True),
    no_scale: bool | str = Form(False),
    denoise: float | None = Form(None),
    seed: int | None = Form(None),
    polish_prompt: bool | str = Form(False),
) -> dict:
    """Create a character from an uploaded image.

    - mode=upload: classical key/crop/resize into the selected export size
    - mode=img2img: Flux img2img from the upload + prompt, then same sprite pipeline
    """
    if pixel_size not in PIXEL_SIZES:
        raise HTTPException(400, f"pixel_size must be one of {PIXEL_SIZES}")
    if project_id:
        try:
            game_projects.load_project(project_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "project not found") from exc

    data = await file.read()
    if not data:
        raise HTTPException(400, "empty image upload")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "image too large (max 25MB)")

    filename = file.filename or "upload.png"
    use_shadow = _parse_form_bool(drop_shadow)
    use_outline = _parse_form_bool(outline)
    use_key = _parse_form_bool(key_background)
    use_auto_crop = _parse_form_bool(auto_crop)
    use_no_scale = _parse_form_bool(no_scale)
    if use_no_scale and (mode != "upload" or use_auto_crop or use_outline or use_shadow):
        raise HTTPException(400, "no_scale requires upload, auto_crop=false, outline=false, drop_shadow=false")
    use_polish = _parse_form_bool(polish_prompt)

    try:
        if mode == "img2img":
            job_id = jobs.start_img2img_character_job(
                image_bytes=data,
                filename=filename,
                name=name or "Creature",
                prompt=prompt,
                pixel_size=pixel_size,
                style=style,
                drop_shadow=use_shadow,
                outline=use_outline,
                project_id=project_id,
                seed=seed,
                denoise=denoise,
                polish=use_polish,
            )
        else:
            job_id = jobs.start_upload_character_job(
                image_bytes=data,
                filename=filename,
                name=name or "Creature",
                prompt=prompt,
                pixel_size=pixel_size,
                style=style,
                drop_shadow=use_shadow,
                outline=use_outline,
                project_id=project_id,
                key_background=use_key,
                auto_crop=use_auto_crop,
                no_scale=use_no_scale,
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc) or "project required") from exc

    job = jobs.get_job(job_id)
    return {"job_id": job_id, "character_id": job.get("character_id") if job else None}


@app.post("/characters/{character_id}/standing")
def prepare_standing(
    character_id: str,
    body: PrepareStandingRequest = Body(default_factory=PrepareStandingRequest),
) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    job_id = jobs.start_standing_job(
        character_id=character_id,
        set_as_source=body.set_as_source,
        pose=body.pose,
    )
    return {"job_id": job_id}


@app.post("/characters/{character_id}/art")
def generate_art(
    character_id: str,
    body: GenerateArtRequest = Body(default_factory=GenerateArtRequest),
) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    job_id = jobs.start_art_job(
        character_id=character_id,
        style=body.style,
        purpose=body.purpose,
        prompt=body.prompt,
        background=body.background,
        size=body.size,
    )
    return {"job_id": job_id}


@app.get("/presets/art-sizes")
def art_size_presets() -> dict:
    from .comfy_client import ART_STILL_SIZES

    return {
        "sizes": [
            {"id": 512, "label": "512 - inventory / thumb"},
            {"id": 768, "label": "768 - UI panel"},
            {"id": 1024, "label": "1024 - standard"},
            {"id": 1280, "label": "1280 - high-res still"},
        ],
        "default": 1024,
        "allowed": list(ART_STILL_SIZES),
    }


@app.delete("/characters/{character_id}/art/{art_id}")
def delete_art(character_id: str, art_id: str) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.soft_delete_art_version(character_id, art_id)
    except KeyError as exc:
        raise HTTPException(404, "art version not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/characters/{character_id}/trash/art/{trash_id}/restore")
def restore_art(character_id: str, trash_id: str) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.restore_art(character_id, trash_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed art not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "trashed art files missing") from exc
    return {
        "ok": True,
        "art": entry,
        "character": _character_payload(character_id, storage.load_meta(character_id)),
    }


@app.put("/characters/{character_id}/source-image")
def set_source_image(character_id: str, body: SetSourceImageRequest) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        meta = storage.set_source_image(
            character_id,
            body.source_image,
            standing_id=body.standing_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, "standing image not available; generate it first") from exc
    except KeyError as exc:
        raise HTTPException(404, "standing version not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _character_payload(character_id, meta)


@app.post("/characters/{character_id}/animations")
def create_animation(character_id: str, body: AnimationCreateRequest) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    meta = storage.load_meta(character_id)
    if body.no_scale and (body.method != "i2v" or (body.wan_size or WAN_I2V_WIDTH) != int(meta["pixel_size"])
                          or meta.get("outline") or meta.get("drop_shadow")):
        raise HTTPException(400, "no_scale requires i2v, wan_size=pixel_size, outline=false, drop_shadow=false")
    job_id = jobs.start_animation_job(
        character_id=character_id,
        anim_type=body.anim_type,
        variants=body.variants,
        frames=body.frames,
        fps=body.fps,
        method=body.method,
        source_image=body.source_image,
        motion_notes=body.motion_notes,
        name=body.name,
        wan_size=body.wan_size,
        no_scale=body.no_scale,
    )
    return {"job_id": job_id}


@app.patch("/characters/{character_id}/animations/{animation_id}")
def rename_animation(
    character_id: str, animation_id: str, body: AnimationRenameRequest
) -> dict:
    try:
        meta = storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    from .asset_refs import ensure_ref

    if body.name is None and body.fps is None:
        raise HTTPException(400, "name or fps required")
    anim = (meta.get("animations") or {}).get(animation_id)
    if not anim:
        raise HTTPException(404, "animation not found")
    if body.name is not None:
        # Temporarily remove this anim so resolve can keep the same name if unchanged
        others = {k: v for k, v in (meta.get("animations") or {}).items() if k != animation_id}
        scratch = {**meta, "animations": others}
        anim["name"] = resolve_animation_name(
            scratch, str(anim.get("type") or body.name), body.name
        )
    if body.fps is not None:
        anim["fps"] = int(body.fps)
    ensure_ref(anim)
    meta["animations"][animation_id] = anim
    storage.save_meta(character_id, meta)
    return anim


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return JobStatus(**job)


@app.post("/characters/{character_id}/animations/{animation_id}/select-variant")
def select_variant(
    character_id: str, animation_id: str, body: SelectVariantRequest
) -> dict:
    try:
        meta = storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    anim = (meta.get("animations") or {}).get(animation_id)
    if not anim:
        raise HTTPException(404, "animation not found")
    if body.variant_index is None:
        anim["selected_variant"] = None
    else:
        if body.variant_index < 0 or body.variant_index >= len(anim.get("variants") or []):
            raise HTTPException(400, "invalid variant_index")
        anim["selected_variant"] = body.variant_index
    meta["animations"][animation_id] = anim
    storage.save_meta(character_id, meta)
    return anim


@app.delete("/characters/{character_id}/animations/{animation_id}")
def delete_animation(character_id: str, animation_id: str) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.soft_delete_animation(character_id, animation_id)
    except KeyError as exc:
        raise HTTPException(404, "animation not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/characters/{character_id}/trash/animations/{animation_id}/restore")
def restore_animation(character_id: str, animation_id: str) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.restore_animation(character_id, animation_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed animation not found") from exc
    return {"ok": True, "animation": entry}


@app.delete("/characters/{character_id}/standing")
def delete_standing(character_id: str, standing_id: str | None = None) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.soft_delete_standing_version(character_id, standing_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "standing image not found") from exc
    except KeyError as exc:
        raise HTTPException(404, "standing version not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/characters/{character_id}/trash/standing/{trash_id}/restore")
def restore_standing(character_id: str, trash_id: str) -> dict:
    try:
        storage.load_meta(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    try:
        entry = storage.restore_standing(character_id, trash_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed standing not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "trashed standing files missing") from exc
    return {"ok": True, "standing": entry, "character": _character_payload(character_id, storage.load_meta(character_id))}


@app.post("/characters/{character_id}/export/unity")
def export_unity(character_id: str) -> dict:
    try:
        result = jobs.export_unity(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "character not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    zip_path = result["zip_path"]
    return {
        "zip_url": f"/files/{character_id}/export/{zip_path.name}",
        "filename": zip_path.name,
        "stem": result["stem"],
        "zip_path": str(zip_path),
        "png_path": str(result["png_path"]),
        "json_path": str(result["json_path"]),
        "animations": result["animations"],
        "frame_count": result["frame_count"],
        "pixel_size": result["pixel_size"],
    }


@app.get("/download/{character_id}/export/{filename}")
def download_export(character_id: str, filename: str) -> FileResponse:
    try:
        root = game_projects.resolve_asset_dir(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "file not found") from exc
    path = root / "export" / filename
    if not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(path, filename=filename)


def _item_payload(item_id: str, meta: dict) -> dict:
    try:
        project_id = meta.get("project_id") or game_projects.project_id_for_item(item_id)
    except FileNotFoundError:
        project_id = meta.get("project_id")
    return {
        **meta,
        "kind": "item",
        "project_id": project_id,
        "base_url": f"/files/{item_id}/base.png",
        "preview_url": f"/files/{item_id}/base_preview.png",
        "art_versions": list(meta.get("art_versions") or []),
    }


@app.get("/items")
def list_items(project_id: str | None = Query(default=None)) -> list[dict]:
    items = []
    for meta in item_storage.list_items(project_id):
        iid = meta["id"]
        payload = _item_payload(iid, meta)
        payload["animation_ids"] = list((meta.get("animations") or {}).keys())
        items.append(payload)
    return items


@app.get("/items/trash")
def list_trashed_items(project_id: str | None = Query(default=None)) -> list[dict]:
    return item_storage.list_trashed_items(project_id)


@app.delete("/items/{item_id}")
def trash_item(item_id: str) -> dict:
    try:
        if game_projects.is_item_trashed(item_id):
            raise HTTPException(404, "item not found")
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    try:
        entry = item_storage.soft_delete_item(item_id)
    except KeyError as exc:
        raise HTTPException(404, "item not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/items/{item_id}/restore")
def restore_item(item_id: str) -> dict:
    try:
        meta = item_storage.restore_item(item_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed item not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "trashed item not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "item": _item_payload(item_id, meta)}


@app.get("/items/{item_id}")
def get_item(item_id: str) -> dict:
    try:
        if game_projects.is_item_trashed(item_id):
            raise HTTPException(404, "item not found")
        meta = item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    return _item_payload(item_id, meta)


@app.post("/items/{item_id}/apply-palette")
def apply_item_palette(item_id: str, body: ApplyPaletteRequest | None = None) -> dict:
    try:
        meta = item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    try:
        project_id = meta.get("project_id") or game_projects.project_id_for_item(item_id)
    except FileNotFoundError:
        project_id = meta.get("project_id")
    colors = game_projects.project_palette_colors(project_id)
    if not colors:
        raise HTTPException(400, "Active project has no palette set")
    include = True if body is None else bool(body.include_animations)
    counts = frame_pipeline.apply_palette_to_asset_dir(
        item_storage.project_dir(item_id),
        colors,
        include_animations=include,
    )
    return {
        "ok": True,
        "palette": colors,
        "counts": counts,
        "item": _item_payload(item_id, item_storage.load_meta(item_id)),
    }


@app.post("/items")
def create_item(body: GenerateItemRequest) -> dict:
    project_id = body.project_id
    if project_id:
        try:
            game_projects.load_project(project_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "project not found") from exc
    try:
        job_id = jobs.start_item_job(
            name=body.name or "Item",
            prompt=body.prompt,
            pixel_size=body.pixel_size,
            polish=body.polish_prompt,
            seed=body.seed,
            style=body.style,
            drop_shadow=body.drop_shadow,
            outline=body.outline,
            project_id=project_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc) or "project required") from exc
    job = jobs.get_job(job_id)
    return {"job_id": job_id, "item_id": job.get("item_id") if job else None}


@app.post("/items/from-image")
async def create_item_from_image(
    file: UploadFile = File(...),
    mode: Literal["upload", "img2img"] = Form("upload"),
    name: str = Form("Item"),
    project_id: str | None = Form(None),
    pixel_size: int = Form(128),
    style: str = Form("pixel_art"),
    drop_shadow: bool | str = Form(False),
    outline: bool | str = Form(False),
    prompt: str = Form(""),
    key_background: bool | str = Form(True),
    auto_crop: bool | str = Form(True),
    denoise: float | None = Form(None),
    seed: int | None = Form(None),
    polish_prompt: bool | str = Form(False),
) -> dict:
    if pixel_size not in PIXEL_SIZES:
        raise HTTPException(400, f"pixel_size must be one of {PIXEL_SIZES}")
    if project_id:
        try:
            game_projects.load_project(project_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "project not found") from exc

    data = await file.read()
    if not data:
        raise HTTPException(400, "empty image upload")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "image too large (max 25MB)")

    filename = file.filename or "upload.png"
    use_shadow = _parse_form_bool(drop_shadow)
    use_outline = _parse_form_bool(outline)
    use_key = _parse_form_bool(key_background)
    use_auto_crop = _parse_form_bool(auto_crop)
    use_polish = _parse_form_bool(polish_prompt)

    try:
        if mode == "img2img":
            job_id = jobs.start_img2img_item_job(
                image_bytes=data,
                filename=filename,
                name=name or "Item",
                prompt=prompt,
                pixel_size=pixel_size,
                style=style,
                drop_shadow=use_shadow,
                outline=use_outline,
                project_id=project_id,
                seed=seed,
                denoise=denoise,
                polish=use_polish,
            )
        else:
            job_id = jobs.start_upload_item_job(
                image_bytes=data,
                filename=filename,
                name=name or "Item",
                prompt=prompt,
                pixel_size=pixel_size,
                style=style,
                drop_shadow=use_shadow,
                outline=use_outline,
                project_id=project_id,
                key_background=use_key,
                auto_crop=use_auto_crop,
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc) or "project required") from exc

    job = jobs.get_job(job_id)
    return {"job_id": job_id, "item_id": job.get("item_id") if job else None}


@app.post("/items/{item_id}/art")
def generate_item_art(
    item_id: str,
    body: GenerateArtRequest = Body(default_factory=GenerateArtRequest),
) -> dict:
    try:
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    job_id = jobs.start_art_job(
        item_id=item_id,
        style=body.style,
        purpose=body.purpose,
        prompt=body.prompt,
        background=body.background,
        size=body.size,
    )
    return {"job_id": job_id}


@app.delete("/items/{item_id}/art/{art_id}")
def delete_item_art(item_id: str, art_id: str) -> dict:
    try:
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    try:
        entry = item_storage.soft_delete_art_version(item_id, art_id)
    except KeyError as exc:
        raise HTTPException(404, "art version not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/items/{item_id}/trash/art/{trash_id}/restore")
def restore_item_art(item_id: str, trash_id: str) -> dict:
    try:
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    try:
        entry = item_storage.restore_art(item_id, trash_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed art not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "trashed art files missing") from exc
    return {
        "ok": True,
        "art": entry,
        "item": _item_payload(item_id, item_storage.load_meta(item_id)),
    }


@app.post("/items/{item_id}/animations")
def create_item_animation(item_id: str, body: ItemAnimationCreateRequest) -> dict:
    try:
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    job_id = jobs.start_animation_job(
        item_id=item_id,
        anim_type=body.anim_type,
        variants=body.variants,
        frames=body.frames,
        fps=body.fps,
        method=body.method,
        motion_notes=body.motion_notes,
        name=body.name,
    )
    return {"job_id": job_id}


@app.patch("/items/{item_id}/animations/{animation_id}")
def rename_item_animation(
    item_id: str, animation_id: str, body: AnimationRenameRequest
) -> dict:
    try:
        meta = item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    from .asset_refs import ensure_ref

    if body.name is None and body.fps is None:
        raise HTTPException(400, "name or fps required")
    anim = (meta.get("animations") or {}).get(animation_id)
    if not anim:
        raise HTTPException(404, "animation not found")
    if body.name is not None:
        others = {k: v for k, v in (meta.get("animations") or {}).items() if k != animation_id}
        scratch = {**meta, "animations": others}
        anim["name"] = resolve_animation_name(
            scratch, str(anim.get("type") or body.name), body.name
        )
    if body.fps is not None:
        anim["fps"] = int(body.fps)
    ensure_ref(anim)
    meta["animations"][animation_id] = anim
    item_storage.save_meta(item_id, meta)
    return anim


@app.post("/items/{item_id}/animations/{animation_id}/select-variant")
def select_item_variant(
    item_id: str, animation_id: str, body: SelectVariantRequest
) -> dict:
    try:
        meta = item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    anim = (meta.get("animations") or {}).get(animation_id)
    if not anim:
        raise HTTPException(404, "animation not found")
    if body.variant_index is None:
        anim["selected_variant"] = None
    else:
        if body.variant_index < 0 or body.variant_index >= len(anim.get("variants") or []):
            raise HTTPException(400, "invalid variant_index")
        anim["selected_variant"] = body.variant_index
    meta["animations"][animation_id] = anim
    item_storage.save_meta(item_id, meta)
    return anim


@app.delete("/items/{item_id}/animations/{animation_id}")
def delete_item_animation(item_id: str, animation_id: str) -> dict:
    try:
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    try:
        entry = item_storage.soft_delete_animation(item_id, animation_id)
    except KeyError as exc:
        raise HTTPException(404, "animation not found") from exc
    return {"ok": True, "trashed": entry}


@app.post("/items/{item_id}/trash/animations/{animation_id}/restore")
def restore_item_animation(item_id: str, animation_id: str) -> dict:
    try:
        item_storage.load_meta(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    try:
        entry = item_storage.restore_animation(item_id, animation_id)
    except KeyError as exc:
        raise HTTPException(404, "trashed animation not found") from exc
    return {"ok": True, "animation": entry}


@app.post("/items/{item_id}/export/unity")
def export_item_unity(item_id: str) -> dict:
    try:
        result = jobs.export_unity(item_id=item_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "item not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    zip_path = result["zip_path"]
    return {
        "zip_url": f"/files/{item_id}/export/{zip_path.name}",
        "filename": zip_path.name,
        "stem": result["stem"],
        "zip_path": str(zip_path),
        "png_path": str(result["png_path"]),
        "json_path": str(result["json_path"]),
        "animations": result["animations"],
        "frame_count": result["frame_count"],
        "pixel_size": result["pixel_size"],
    }
