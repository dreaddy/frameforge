"""Thin MCP stdio server wrapping Frameforge REST API (mcp 2.x)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

API = os.environ.get("FRAMEFORGE_URL", "http://127.0.0.1:8787")
UNITY_PROJECT_ROOT = os.environ.get("UNITY_PROJECT_ROOT", "").strip()
UNITY_ASSETS_SUBDIR = os.environ.get(
    "UNITY_ASSETS_SUBDIR", "Assets/Creatures/spritesheets"
).strip()
UNITY_ITEMS_ASSETS_SUBDIR = os.environ.get(
    "UNITY_ITEMS_ASSETS_SUBDIR", "Assets/Items/spritesheets"
).strip()
_UNITY_SCRIPTS_SRC = Path(__file__).resolve().parent.parent / "unity"
mcp = MCPServer("frameforge")


def _client() -> httpx.Client:
    return httpx.Client(base_url=API, timeout=30.0)


def _normalize_key(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return k
    lowered = k.lower()
    for prefix in (
        "objekt ",
        "object ",
        "item ",
        "character ",
        "creature ",
        "char ",
        "ref ",
        "nr ",
        "no. ",
        "no ",
        "#",
    ):
        if lowered.startswith(prefix):
            k = k[len(prefix) :].strip()
            lowered = k.lower()
    return k


def _compact_anims(row: dict[str, Any]) -> list[dict[str, Any]]:
    anims = row.get("animations") or {}
    out: list[dict[str, Any]] = []
    for aid, anim in anims.items():
        if not isinstance(anim, dict):
            continue
        fps = int(anim.get("fps") or 8)
        out.append(
            {
                "ref": anim.get("ref"),
                "id": aid,
                "name": anim.get("name") or anim.get("type"),
                "type": anim.get("type"),
                "fps": fps,
                "recommended_fps": fps,
            }
        )
    out.sort(key=lambda a: int(a.get("ref") or 0))
    return out


def _compact_asset(row: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Lean MCP list row — active assets only, ref first for verbal lookup."""
    return {
        "ref": row.get("ref"),
        "id": row.get("id"),
        "name": row.get("name"),
        "kind": kind,
        "project_id": row.get("project_id"),
        "style": row.get("style"),
        "pixel_size": row.get("pixel_size"),
        "animations": _compact_anims(row),
        "animation_ids": row.get("animation_ids") or list((row.get("animations") or {}).keys()),
        "preview_url": row.get("preview_url"),
    }


def _resolve_named(
    key: str,
    *,
    list_path: str,
    label: str,
    include_trash_path: str | None = None,
) -> dict[str, Any]:
    """Resolve by numeric ref, hex id, exact name, or unique partial name.

    Active assets only unless include_trash_path is set (restore flows).
    """
    key = _normalize_key(key)
    if not key:
        raise ValueError(f"{label} name, ref, or id is required")
    with _client() as c:
        r = c.get(list_path)
        r.raise_for_status()
        rows: list[dict[str, Any]] = r.json()
        trash_rows: list[dict[str, Any]] = []
        if include_trash_path:
            tr = c.get(include_trash_path)
            tr.raise_for_status()
            trash_rows = tr.json()

    search = rows if not include_trash_path else trash_rows

    if key.isdigit():
        ref = int(key)
        hits = [row for row in search if int(row.get("ref") or -1) == ref]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError(f"multiple {label}s with ref {ref}")
        raise ValueError(f"{label} ref not found: {ref}")

    for row in search:
        if row.get("id") == key:
            return row
    lower = key.lower()
    exact = [row for row in search if str(row.get("name") or "").lower() == lower]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(
            f"multiple {label}s named {key!r}: "
            f"{[(row.get('ref'), row.get('id')) for row in exact]} — pass ref or id"
        )
    partial = [row for row in search if lower in str(row.get("name") or "").lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise ValueError(
            f"ambiguous {label} {key!r}: "
            f"{[(row.get('ref'), row.get('name'), row.get('id')) for row in partial]}"
        )
    raise ValueError(f"{label} not found: {key!r}")


def _resolve_character(character: str) -> dict[str, Any]:
    return _resolve_named(character, list_path="/characters", label="character")


def _resolve_item(item: str) -> dict[str, Any]:
    return _resolve_named(item, list_path="/items", label="item")


def _resolve_trashed_character(character: str) -> dict[str, Any]:
    return _resolve_named(
        character,
        list_path="/characters",
        label="trashed character",
        include_trash_path="/characters/trash",
    )


def _resolve_trashed_item(item: str) -> dict[str, Any]:
    return _resolve_named(
        item,
        list_path="/items",
        label="trashed item",
        include_trash_path="/items/trash",
    )


def _character_id(character: str) -> str:
    return str(_resolve_character(character)["id"])


def _item_id(item: str) -> str:
    return str(_resolve_item(item)["id"])


def _copy_unity_editor_scripts(project_root: Path) -> list[str]:
    dest_editor = project_root / "Assets" / "Editor" / "Frameforge"
    dest_runtime = project_root / "Assets" / "Scripts" / "Frameforge"
    dest_editor.mkdir(parents=True, exist_ok=True)
    dest_runtime.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    mapping = [
        (_UNITY_SCRIPTS_SRC / "Editor" / "FrameforgeSheetImport.cs", dest_editor / "FrameforgeSheetImport.cs"),
        (_UNITY_SCRIPTS_SRC / "Editor" / "SpriteSheetImporterEditor.cs", dest_editor / "SpriteSheetImporterEditor.cs"),
        (_UNITY_SCRIPTS_SRC / "SpriteSheetImporter.cs", dest_runtime / "SpriteSheetImporter.cs"),
    ]
    for src, dst in mapping:
        if not src.is_file():
            continue
        shutil.copy2(src, dst)
        copied.append(str(dst.relative_to(project_root)).replace("\\", "/"))
    return copied


@mcp.tool()
def health() -> dict[str, Any]:
    """Check Frameforge API + Comfy + Ollama status."""
    with _client() as c:
        r = c.get("/health")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def get_size_capabilities() -> dict[str, Any]:
    """Query supported export/WAN sizes BEFORE generating or importing images.
    Returns presets, defaults, experimental sizes and strict no_scale requirements.
    Original image size is not necessarily a supported WAN size.
    """
    with _client() as c:
        r = c.get("/presets/sizes")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def list_projects() -> list[dict[str, Any]]:
    """List game projects (name, description, default style, character counts)."""
    with _client() as c:
        r = c.get("/projects")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def create_project(
    name: str,
    description: str = "",
    default_style: str = "pixel_art",
    default_pixel_size: int = 128,
    default_drop_shadow: bool = False,
    default_outline: bool = False,
) -> dict[str, Any]:
    """Create a game project. Characters generated into a project stay separate from other projects."""
    with _client() as c:
        r = c.post(
            "/projects",
            json={
                "name": name,
                "description": description,
                "default_style": default_style,
                "default_pixel_size": default_pixel_size,
                "default_drop_shadow": default_drop_shadow,
                "default_outline": default_outline,
            },
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def update_project(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    default_style: str | None = None,
    default_pixel_size: int | None = None,
    default_drop_shadow: bool | None = None,
    default_outline: bool | None = None,
) -> dict[str, Any]:
    """Update project settings (game name, description, default style/size)."""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if default_style is not None:
        payload["default_style"] = default_style
    if default_pixel_size is not None:
        payload["default_pixel_size"] = default_pixel_size
    if default_drop_shadow is not None:
        payload["default_drop_shadow"] = default_drop_shadow
    if default_outline is not None:
        payload["default_outline"] = default_outline
    with _client() as c:
        r = c.put(f"/projects/{project_id}", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def list_characters(project_id: str | None = None) -> list[dict[str, Any]]:
    """List active characters (not trash). Each row has numeric `ref` (say “object 3294”)."""
    params = {"project_id": project_id} if project_id else None
    with _client() as c:
        r = c.get("/characters", params=params)
        r.raise_for_status()
        return [_compact_asset(row, kind="character") for row in r.json()]


@mcp.tool()
def find_character(name_or_id: str) -> dict[str, Any]:
    """Find an active character by numeric ref, hex id, or name (exact / unique partial).

    Examples: `3294`, `#3294`, `objekt 3294`, `Firehorse256`. Trash is ignored.
    """
    return _resolve_character(name_or_id)


@mcp.tool()
def find_object(name_or_ref: str) -> dict[str, Any]:
    """Find active character, item, animation, standing, or art by numeric ref / id / name.

    Prefer this when the user says “objekt 3294” or “animation 3310”.
    Trash is ignored — use list_trashed_* + restore_* for that.
    """
    key = _normalize_key(name_or_ref)
    if not key:
        raise ValueError("name or ref is required")
    if key.isdigit():
        with _client() as c:
            r = c.get(f"/lookup/{int(key)}")
            if r.status_code == 404:
                raise ValueError(f"ref not found: {key}")
            r.raise_for_status()
            return r.json()
    errors: list[str] = []
    try:
        row = _resolve_character(key)
        return {**_compact_asset(row, kind="character"), **{k: row.get(k) for k in ("prompt",)}}
    except ValueError as exc:
        errors.append(str(exc))
    try:
        row = _resolve_item(key)
        return {**_compact_asset(row, kind="item"), **{k: row.get(k) for k in ("prompt",)}}
    except ValueError as exc:
        errors.append(str(exc))
    raise ValueError("; ".join(errors) if errors else f"object not found: {name_or_ref!r}")


def _resolve_animation_id(owner: dict[str, Any], animation: str) -> str:
    """Resolve animation by ref, hex id, or unique name within owner."""
    key = _normalize_key(animation)
    anims = owner.get("animations") or {}
    if key.isdigit():
        ref = int(key)
        for aid, anim in anims.items():
            if isinstance(anim, dict) and int(anim.get("ref") or -1) == ref:
                return str(aid)
        raise ValueError(f"animation ref not found on asset: {ref}")
    if key in anims:
        return key
    lower = key.lower()
    exact = [
        aid
        for aid, anim in anims.items()
        if isinstance(anim, dict)
        and str(anim.get("name") or anim.get("type") or "").lower() == lower
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"multiple animations named {key!r}")
    partial = [
        aid
        for aid, anim in anims.items()
        if isinstance(anim, dict) and lower in str(anim.get("name") or anim.get("type") or "").lower()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise ValueError(f"ambiguous animation {key!r}")
    raise ValueError(f"animation not found: {key!r}")


@mcp.tool()
def get_character(character: str) -> dict[str, Any]:
    """Get full character detail (animations, standing, art) by ref / id / name."""
    ch = _resolve_character(character)
    with _client() as c:
        r = c.get(f"/characters/{ch['id']}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def list_trashed_characters(project_id: str | None = None) -> list[dict[str, Any]]:
    """List soft-deleted characters (for restore only). Active lists never include these."""
    params = {"project_id": project_id} if project_id else None
    with _client() as c:
        r = c.get("/characters/trash", params=params)
        r.raise_for_status()
        return [
            {
                "ref": row.get("ref"),
                "id": row.get("id"),
                "name": row.get("name"),
                "kind": "character",
                "project_id": row.get("project_id"),
                "deleted_at": row.get("deleted_at"),
                "preview_url": row.get("preview_url"),
            }
            for row in r.json()
        ]


@mcp.tool()
def trash_character(character: str) -> dict[str, Any]:
    """Soft-delete a character into its project's trash (restorable). Accepts ref/name/id."""
    ch = _resolve_character(character)
    with _client() as c:
        r = c.delete(f"/characters/{ch['id']}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def restore_character(character: str) -> dict[str, Any]:
    """Restore a soft-deleted character from trash by ref / name / id."""
    ch = _resolve_trashed_character(character)
    with _client() as c:
        r = c.post(f"/characters/{ch['id']}/restore")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def polish_prompt(
    prompt: str,
    style: str = "pixel_art",
    outline: bool = False,
    project_id: str | None = None,
    subject: str = "character",
) -> dict[str, Any]:
    """Polish a creature or item prompt. subject: 'character' | 'item'."""
    if subject not in ("character", "item"):
        raise ValueError("subject must be 'character' or 'item'")
    payload: dict[str, Any] = {
        "prompt": prompt,
        "style": style,
        "outline": outline,
        "subject": subject,
    }
    if project_id:
        payload["project_id"] = project_id
    with _client() as c:
        r = c.post("/prompts/polish", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def list_styles() -> dict[str, Any]:
    """List available art styles for character generation."""
    with _client() as c:
        r = c.get("/presets/styles")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def generate_character(
    prompt: str,
    name: str = "Creature",
    project_id: str | None = None,
    pixel_size: int = 128,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    polish_prompt: bool = False,
) -> dict[str, Any]:
    """Start character generation into a project. style: pixel_art|cartoon|anime|comic|low_poly|realistic."""
    payload: dict[str, Any] = {
        "prompt": prompt,
        "name": name,
        "pixel_size": pixel_size,
        "style": style,
        "drop_shadow": drop_shadow,
        "outline": outline,
        "polish_prompt": polish_prompt,
    }
    if project_id:
        payload["project_id"] = project_id
    with _client() as c:
        r = c.post("/characters", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def create_character_from_image(
    image_path: str,
    mode: str = "upload",
    name: str = "Creature",
    project_id: str | None = None,
    pixel_size: int = 128,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    prompt: str = "",
    key_background: bool = True,
    auto_crop: bool = True,
    no_scale: bool = False,
    denoise: float | None = None,
) -> dict[str, Any]:
    """Create a character from a local image path.

    Call get_size_capabilities first. no_scale=true with auto_crop=false preserves
    subject pixels (canvas-only padding/cropping); rejects clipping.
    mode=upload: classical key/crop/resize to pixel_size (no Comfy).
    mode=img2img: Flux img2img with prompt, then sprite pipeline (Comfy required).
    """
    if mode not in ("upload", "img2img"):
        raise ValueError("mode must be 'upload' or 'img2img'")
    data = {
        "mode": mode,
        "name": name,
        "pixel_size": str(pixel_size),
        "style": style,
        "drop_shadow": str(drop_shadow).lower(),
        "outline": str(outline).lower(),
        "prompt": prompt,
        "key_background": str(key_background).lower(),
        "auto_crop": str(auto_crop).lower(),
        "no_scale": str(no_scale).lower(),
    }
    if project_id:
        data["project_id"] = project_id
    if denoise is not None:
        data["denoise"] = str(denoise)
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")
    with path.open("rb") as f:
        with _client() as c:
            r = c.post(
                "/characters/from-image",
                data=data,
                files={"file": (path.name, f)},
            )
            r.raise_for_status()
            return r.json()


@mcp.tool()
def prepare_standing(
    character_id: str,
    set_as_source: bool = True,
    pose: str = "standing",
) -> dict[str, Any]:
    """Build a pose image from the character base (default pose: standing). Optional animation source.
    character_id accepts numeric ref, hex id, or name."""
    cid = _character_id(character_id)
    with _client() as c:
        r = c.post(
            f"/characters/{cid}/standing",
            json={"set_as_source": set_as_source, "pose": pose},
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def generate_art(
    character_id: str,
    style: str = "anime",
    purpose: str = "portrait",
    size: int = 1024,
    background: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Art still. style includes stylized_3d|realistic. Optional background scene. Pose may change.
    character_id accepts numeric ref, hex id, or name."""
    cid = _character_id(character_id)
    payload: dict[str, Any] = {"style": style, "purpose": purpose, "size": size}
    if background:
        payload["background"] = background
    if prompt:
        payload["prompt"] = prompt
    with _client() as c:
        r = c.post(f"/characters/{cid}/art", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def set_source_image(
    character_id: str,
    source_image: str = "base",
    standing_id: str | None = None,
) -> dict[str, Any]:
    """Choose which image new animations use: 'base' (original) or a standing version (optional standing_id).
    character_id accepts numeric ref, hex id, or name."""
    cid = _character_id(character_id)
    payload: dict[str, Any] = {"source_image": source_image}
    if standing_id:
        payload["standing_id"] = standing_id
    with _client() as c:
        r = c.put(
            f"/characters/{cid}/source-image",
            json=payload,
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def create_animation(
    character_id: str,
    anim_type: str,
    variants: int = 1,
    frames: int = 6,
    fps: int = 8,
    method: str = "i2v",
    source_image: str | None = None,
    motion_notes: str = "",
    name: str = "",
    wan_size: int | None = None,
    no_scale: bool = False,
) -> dict[str, Any]:
    """Start animation variants. Query get_size_capabilities first.
    wan_size selects video resolution independently of export pixel_size.
    no_scale requires wan_size=pixel_size and preserves the frame canvas. source_image: 'base'|'standing'|null.
    motion_notes: optional feel (e.g. 'very slow idle bob').
    name: optional export name; empty auto-assigns idle / idle2 / idle3…
    fps: saved recommended playback speed (Unity/export use this).
    character_id accepts numeric ref, hex id, or name."""
    cid = _character_id(character_id)
    payload: dict[str, Any] = {
        "anim_type": anim_type,
        "variants": variants,
        "frames": frames,
        "fps": fps,
        "method": method,
        "motion_notes": motion_notes or "",
        "name": name or "",
    }
    payload["no_scale"] = no_scale
    if wan_size is not None:
        payload["wan_size"] = wan_size
    if source_image:
        payload["source_image"] = source_image
    with _client() as c:
        r = c.post(f"/characters/{cid}/animations", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def job_status(job_id: str) -> dict[str, Any]:
    """Poll a Frameforge job."""
    with _client() as c:
        r = c.get(f"/jobs/{job_id}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def select_variant(
    character_id: str, animation_id: str, variant_index: int | None
) -> dict[str, Any]:
    """Pick the best animation variant, or pass null to clear selection.
    character_id and animation_id accept numeric ref, hex id, or name."""
    ch = _resolve_character(character_id)
    aid = _resolve_animation_id(ch, animation_id)
    with _client() as c:
        r = c.post(
            f"/characters/{ch['id']}/animations/{aid}/select-variant",
            json={"variant_index": variant_index},
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def trash_animation(character_id: str, animation_id: str) -> dict[str, Any]:
    """Soft-delete an animation into the character trash (restorable).
    character_id and animation_id accept numeric ref, hex id, or name."""
    ch = _resolve_character(character_id)
    aid = _resolve_animation_id(ch, animation_id)
    with _client() as c:
        r = c.delete(f"/characters/{ch['id']}/animations/{aid}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def restore_animation(character_id: str, animation_id: str) -> dict[str, Any]:
    """Restore a soft-deleted animation from the character trash.
    character_id accepts ref/name/id; animation_id is the hex folder id from trash list."""
    cid = _character_id(character_id)
    with _client() as c:
        r = c.post(f"/characters/{cid}/trash/animations/{animation_id}/restore")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def trash_standing(character_id: str, standing_id: str | None = None) -> dict[str, Any]:
    """Soft-delete a standing version (or the active one) into the character trash. Ref/name/id ok."""
    cid = _character_id(character_id)
    with _client() as c:
        q = f"?standing_id={standing_id}" if standing_id else ""
        r = c.delete(f"/characters/{cid}/standing{q}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def restore_standing(character_id: str, trash_id: str) -> dict[str, Any]:
    """Restore a standing attempt from the character trash. Ref/name/id ok."""
    cid = _character_id(character_id)
    with _client() as c:
        r = c.post(f"/characters/{cid}/trash/standing/{trash_id}/restore")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def export_unity_sheet(character: str) -> dict[str, Any]:
    """Export Unity spritesheet (PNG+JSON+ZIP) for a character (name or id).

    Returns local absolute paths (png_path, json_path, zip_path) plus animation meta.
    Prefer install_to_unity when the user wants the sheet inside their Unity project.
    """
    ch = _resolve_character(character)
    with _client() as c:
        r = c.post(f"/characters/{ch['id']}/export/unity")
        r.raise_for_status()
        payload = r.json()
    payload["character_id"] = ch["id"]
    payload["character_name"] = ch.get("name")
    payload["character_ref"] = ch.get("ref")
    payload["recommended_playback"] = _compact_anims(ch)
    return payload


@mcp.tool()
def install_to_unity(
    character: str,
    unity_project: str | None = None,
    assets_subdir: str | None = None,
    ensure_editor_scripts: bool = True,
) -> dict[str, Any]:
    """Export a creature's animations and copy them into a Unity project.

    Use when the user says e.g. "nimm die Animationen von Firehorse256 und bau sie
    in mein Unity-Projekt ein". Resolves character by name/id, builds the sheet,
    copies PNG+JSON under Assets/..., and installs Frameforge Editor scripts
    so Unity auto-slices sprites and creates AnimationClips + AnimatorController.
    Each animation's recommended_fps is the saved playback speed from Frameforge.

    unity_project: path to the Unity project root (folder with Assets/). Defaults to
    env UNITY_PROJECT_ROOT. assets_subdir defaults to UNITY_ASSETS_SUBDIR or
    Assets/Creatures/spritesheets.
    """
    ch = _resolve_character(character)
    project = (unity_project or UNITY_PROJECT_ROOT or "").strip()
    if not project:
        raise ValueError(
            "unity_project is required (or set UNITY_PROJECT_ROOT in MCP env)"
        )
    root = Path(project).expanduser().resolve()
    assets = root / "Assets"
    if not assets.is_dir():
        raise FileNotFoundError(f"not a Unity project (no Assets/): {root}")

    sub = (assets_subdir or UNITY_ASSETS_SUBDIR or "Assets/Creatures/spritesheets").strip()
    sub = sub.replace("\\", "/").lstrip("/")
    if not sub.startswith("Assets/"):
        sub = f"Assets/{sub}"

    with _client() as c:
        r = c.post(f"/characters/{ch['id']}/export/unity")
        r.raise_for_status()
        export = r.json()

    png_src = Path(export["png_path"])
    json_src = Path(export["json_path"])
    stem = export.get("stem") or png_src.stem.replace("_sheet", "")
    dest_dir = root.joinpath(*sub.split("/")) / stem
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_dst = dest_dir / png_src.name
    json_dst = dest_dir / json_src.name
    shutil.copy2(png_src, png_dst)
    shutil.copy2(json_src, json_dst)

    scripts: list[str] = []
    if ensure_editor_scripts:
        scripts = _copy_unity_editor_scripts(root)

    rel_png = str(png_dst.relative_to(root)).replace("\\", "/")
    rel_json = str(json_dst.relative_to(root)).replace("\\", "/")
    rel_out = str(dest_dir.relative_to(root)).replace("\\", "/")

    # Queue import for after Unity compiles Editor scripts (first-time install).
    pending = root / "Assets" / "Editor" / "Frameforge" / "pending-imports.txt"
    pending.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if pending.is_file():
        lines = [ln.strip() for ln in pending.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if rel_png not in lines:
        lines.append(rel_png)
    pending.write_text("\n".join(lines) + "\n", encoding="utf-8")

    playback = _compact_anims(ch)
    return {
        "ok": True,
        "character_id": ch["id"],
        "character_ref": ch.get("ref"),
        "character_name": ch.get("name"),
        "unity_project": str(root),
        "texture_asset_path": rel_png,
        "json_asset_path": rel_json,
        "output_folder": rel_out,
        "animations": export.get("animations") or [],
        "recommended_playback": playback,
        "frame_count": export.get("frame_count"),
        "editor_scripts": scripts,
        "pending_import_file": str(pending.relative_to(root)).replace("\\", "/"),
        "note": (
            "Files copied and queued for Unity import. With the Editor open, after scripts "
            "compile Frameforge creates AnimationClips + AnimatorController under the "
            "creature folder (clip frame rates use each animation's recommended_fps). "
            "Manual: select PNG → Assets → Frameforge → Import Selected Sheet. "
            "Or Unity_RunCommand: FrameforgeSheetImport.ImportAtPath(texture_asset_path)."
        ),
    }


@mcp.tool()
def list_items(project_id: str | None = None) -> list[dict[str, Any]]:
    """List active items (not trash). Each row has numeric `ref` (say “object 3294”)."""
    params = {"project_id": project_id} if project_id else None
    with _client() as c:
        r = c.get("/items", params=params)
        r.raise_for_status()
        return [_compact_asset(row, kind="item") for row in r.json()]


@mcp.tool()
def find_item(name_or_id: str) -> dict[str, Any]:
    """Find an active item by numeric ref, hex id, or name. Trash is ignored."""
    return _resolve_item(name_or_id)


@mcp.tool()
def get_item(item: str) -> dict[str, Any]:
    """Get full item detail (animations, art) by ref / id / name."""
    it = _resolve_item(item)
    with _client() as c:
        r = c.get(f"/items/{it['id']}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def list_trashed_items(project_id: str | None = None) -> list[dict[str, Any]]:
    """List soft-deleted items (for restore only). Active lists never include these."""
    params = {"project_id": project_id} if project_id else None
    with _client() as c:
        r = c.get("/items/trash", params=params)
        r.raise_for_status()
        return [
            {
                "ref": row.get("ref"),
                "id": row.get("id"),
                "name": row.get("name"),
                "kind": "item",
                "project_id": row.get("project_id"),
                "deleted_at": row.get("deleted_at"),
                "preview_url": row.get("preview_url"),
            }
            for row in r.json()
        ]


@mcp.tool()
def trash_item(item: str) -> dict[str, Any]:
    """Soft-delete an item into trash (restorable). Accepts ref/name/id."""
    it = _resolve_item(item)
    with _client() as c:
        r = c.delete(f"/items/{it['id']}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def restore_item(item: str) -> dict[str, Any]:
    """Restore a soft-deleted item from trash by ref / name / id."""
    it = _resolve_trashed_item(item)
    with _client() as c:
        r = c.post(f"/items/{it['id']}/restore")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def generate_item(
    prompt: str,
    name: str = "Item",
    project_id: str | None = None,
    pixel_size: int = 128,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    polish_prompt: bool = False,
) -> dict[str, Any]:
    """Start item generation into a project. No walking anims — use idle/destroyed/use/open."""
    payload: dict[str, Any] = {
        "prompt": prompt,
        "name": name,
        "pixel_size": pixel_size,
        "style": style,
        "drop_shadow": drop_shadow,
        "outline": outline,
        "polish_prompt": polish_prompt,
    }
    if project_id:
        payload["project_id"] = project_id
    with _client() as c:
        r = c.post("/items", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def create_item_from_image(
    image_path: str,
    mode: str = "upload",
    name: str = "Item",
    project_id: str | None = None,
    pixel_size: int = 128,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    prompt: str = "",
    key_background: bool = True,
    auto_crop: bool = True,
    denoise: float | None = None,
) -> dict[str, Any]:
    """Create an item from a local image path (upload or img2img)."""
    if mode not in ("upload", "img2img"):
        raise ValueError("mode must be 'upload' or 'img2img'")
    data = {
        "mode": mode,
        "name": name,
        "pixel_size": str(pixel_size),
        "style": style,
        "drop_shadow": str(drop_shadow).lower(),
        "outline": str(outline).lower(),
        "prompt": prompt,
        "key_background": str(key_background).lower(),
        "auto_crop": str(auto_crop).lower(),
    }
    if project_id:
        data["project_id"] = project_id
    if denoise is not None:
        data["denoise"] = str(denoise)
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")
    with path.open("rb") as f:
        with _client() as c:
            r = c.post(
                "/items/from-image",
                data=data,
                files={"file": (path.name, f)},
            )
            r.raise_for_status()
            return r.json()


@mcp.tool()
def generate_item_art(
    item_id: str,
    style: str = "anime",
    purpose: str = "inventory",
    size: int = 1024,
    background: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Art still for an item (default purpose: inventory). item_id accepts ref/name/id."""
    iid = _item_id(item_id)
    payload: dict[str, Any] = {"style": style, "purpose": purpose, "size": size}
    if background:
        payload["background"] = background
    if prompt:
        payload["prompt"] = prompt
    with _client() as c:
        r = c.post(f"/items/{iid}/art", json=payload)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def create_item_animation(
    item_id: str,
    anim_type: str = "destroyed",
    variants: int = 1,
    frames: int = 6,
    fps: int = 8,
    method: str = "i2v",
    motion_notes: str = "",
    name: str = "",
) -> dict[str, Any]:
    """Start item animation variants. Presets: idle, destroyed (default death/break one-shot), use, open.
    motion_notes: optional feel. name: optional; empty → destroyed / destroyed2…
    fps: saved recommended playback speed (Unity/export use this).
    item_id accepts ref/name/id."""
    iid = _item_id(item_id)
    with _client() as c:
        r = c.post(
            f"/items/{iid}/animations",
            json={
                "anim_type": anim_type,
                "variants": variants,
                "frames": frames,
                "fps": fps,
                "method": method,
                "motion_notes": motion_notes or "",
                "name": name or "",
            },
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def select_item_variant(
    item_id: str, animation_id: str, variant_index: int | None
) -> dict[str, Any]:
    """Pick the best item animation variant, or pass null to clear selection.
    item_id and animation_id accept numeric ref, hex id, or name."""
    it = _resolve_item(item_id)
    aid = _resolve_animation_id(it, animation_id)
    with _client() as c:
        r = c.post(
            f"/items/{it['id']}/animations/{aid}/select-variant",
            json={"variant_index": variant_index},
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def trash_item_animation(item_id: str, animation_id: str) -> dict[str, Any]:
    """Soft-delete an item animation into the item trash.
    item_id and animation_id accept numeric ref, hex id, or name."""
    it = _resolve_item(item_id)
    aid = _resolve_animation_id(it, animation_id)
    with _client() as c:
        r = c.delete(f"/items/{it['id']}/animations/{aid}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def restore_item_animation(item_id: str, animation_id: str) -> dict[str, Any]:
    """Restore a soft-deleted item animation. item_id accepts ref/name/id."""
    iid = _item_id(item_id)
    with _client() as c:
        r = c.post(f"/items/{iid}/trash/animations/{animation_id}/restore")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def export_item_unity_sheet(item: str) -> dict[str, Any]:
    """Export Unity spritesheet (PNG+JSON+ZIP) for an item (name or id)."""
    it = _resolve_item(item)
    with _client() as c:
        r = c.post(f"/items/{it['id']}/export/unity")
        r.raise_for_status()
        payload = r.json()
    payload["item_id"] = it["id"]
    payload["item_ref"] = it.get("ref")
    payload["item_name"] = it.get("name")
    payload["recommended_playback"] = _compact_anims(it)
    return payload


@mcp.tool()
def install_item_to_unity(
    item: str,
    unity_project: str | None = None,
    assets_subdir: str | None = None,
    ensure_editor_scripts: bool = True,
) -> dict[str, Any]:
    """Export an item's animations and copy them into a Unity project under Assets/Items/…"""
    it = _resolve_item(item)
    project = (unity_project or UNITY_PROJECT_ROOT or "").strip()
    if not project:
        raise ValueError(
            "unity_project is required (or set UNITY_PROJECT_ROOT in MCP env)"
        )
    root = Path(project).expanduser().resolve()
    assets = root / "Assets"
    if not assets.is_dir():
        raise FileNotFoundError(f"not a Unity project (no Assets/): {root}")

    sub = (assets_subdir or UNITY_ITEMS_ASSETS_SUBDIR or "Assets/Items/spritesheets").strip()
    sub = sub.replace("\\", "/").lstrip("/")
    if not sub.startswith("Assets/"):
        sub = f"Assets/{sub}"

    with _client() as c:
        r = c.post(f"/items/{it['id']}/export/unity")
        r.raise_for_status()
        export = r.json()

    png_src = Path(export["png_path"])
    json_src = Path(export["json_path"])
    stem = export.get("stem") or png_src.stem.replace("_sheet", "")
    dest_dir = root.joinpath(*sub.split("/")) / stem
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_dst = dest_dir / png_src.name
    json_dst = dest_dir / json_src.name
    shutil.copy2(png_src, png_dst)
    shutil.copy2(json_src, json_dst)

    scripts: list[str] = []
    if ensure_editor_scripts:
        scripts = _copy_unity_editor_scripts(root)

    rel_png = str(png_dst.relative_to(root)).replace("\\", "/")
    rel_json = str(json_dst.relative_to(root)).replace("\\", "/")
    rel_out = str(dest_dir.relative_to(root)).replace("\\", "/")

    pending = root / "Assets" / "Editor" / "Frameforge" / "pending-imports.txt"
    pending.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if pending.is_file():
        lines = [ln.strip() for ln in pending.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if rel_png not in lines:
        lines.append(rel_png)
    pending.write_text("\n".join(lines) + "\n", encoding="utf-8")

    playback = _compact_anims(it)
    return {
        "ok": True,
        "item_id": it["id"],
        "item_ref": it.get("ref"),
        "item_name": it.get("name"),
        "unity_project": str(root),
        "texture_asset_path": rel_png,
        "json_asset_path": rel_json,
        "output_folder": rel_out,
        "animations": export.get("animations") or [],
        "recommended_playback": playback,
        "frame_count": export.get("frame_count"),
        "editor_scripts": scripts,
        "pending_import_file": str(pending.relative_to(root)).replace("\\", "/"),
        "note": (
            "Files copied and queued for Unity import under Assets/Items/spritesheets. "
            "Clip frame rates use each animation's recommended_fps. "
            "Manual: select PNG → Assets → Frameforge → Import Selected Sheet."
        ),
    }


def main() -> None:
    try:
        with _client() as c:
            c.get("/health")
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: Frameforge API not reachable at {API}: {exc}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
