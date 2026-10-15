"""Item asset persistence — parallel to characters, without standing/poses."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import projects as game_projects

_ART_FILES = (
    "art.png",
    "art_preview.png",
    "art_raw.png",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(item_id: str) -> Path:
    return game_projects.item_dir(item_id)


def trash_dir(item_id: str) -> Path:
    path = project_dir(item_id) / "trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_item(
    name: str,
    prompt: str,
    pixel_size: int,
    style: str = "pixel_art",
    drop_shadow: bool = False,
    outline: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    game_projects.ensure_migrated()
    if not project_id:
        plist = game_projects.list_projects()
        if not plist:
            raise FileNotFoundError("no game project; create one first")
        project_id = plist[0]["id"]
    else:
        game_projects.load_project(project_id)

    from .asset_refs import assign_identity

    iid = uuid.uuid4().hex[:12]
    root = game_projects.items_root(project_id) / iid
    (root / "anims").mkdir(parents=True, exist_ok=True)
    (root / "export").mkdir(parents=True, exist_ok=True)
    game_projects.register_item(project_id, iid)
    meta = {
        "id": iid,
        "kind": "item",
        "project_id": project_id,
        "name": name,
        "prompt": prompt,
        "pixel_size": pixel_size,
        "style": style,
        "drop_shadow": drop_shadow,
        "outline": outline,
        "created_at": _now(),
        "art_versions": [],
        "animations": {},
        "trash": {"animations": {}, "art": []},
    }
    assign_identity(meta, kind="item", project_id=project_id, desired_name=name)
    (root / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    trash_dir(iid)
    return meta


def save_meta(item_id: str, meta: dict[str, Any]) -> None:
    path = project_dir(item_id) / "meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_meta(item_id: str) -> dict[str, Any]:
    path = project_dir(item_id) / "meta.json"
    if not path.exists():
        raise FileNotFoundError(item_id)
    meta = json.loads(path.read_text(encoding="utf-8"))
    trash = meta.setdefault("trash", {})
    trash.setdefault("animations", {})
    trash.setdefault("art", [])
    meta.setdefault("art_versions", [])
    meta.setdefault("kind", "item")
    return meta


def arts_dir(item_id: str) -> Path:
    path = project_dir(item_id) / "arts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def art_version_dir(item_id: str, art_id: str) -> Path:
    return arts_dir(item_id) / art_id


def _art_urls(item_id: str, art_id: str) -> dict[str, str]:
    vdir = art_version_dir(item_id, art_id)
    files: dict[str, str] = {}
    for name in _ART_FILES:
        if (vdir / name).exists():
            files[name] = f"/files/{item_id}/arts/{art_id}/{name}"
    return files


def register_art_version(
    item_id: str,
    *,
    src_dir: Path,
    style: str,
    purpose: str,
    prompt: str | None = None,
    background: str | None = None,
    label: str | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    meta = load_meta(item_id)
    aid = uuid.uuid4().hex[:10]
    vdir = art_version_dir(item_id, aid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _ART_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _art_urls(item_id, aid)
    if not files:
        shutil.rmtree(vdir, ignore_errors=True)
        raise FileNotFoundError("art files missing after generation")
    purpose_labels = {
        "portrait": "Icon",
        "inventory": "Inventory",
        "showcase": "Showcase",
        "scene": "Scene",
    }
    style_label = (style or "art").replace("_", " ")
    purpose_label = purpose_labels.get(purpose, purpose or "Art")
    size_label = f"{int(size)}px" if size else None
    default_label = f"{purpose_label} · {style_label}"
    if size_label:
        default_label = f"{default_label} · {size_label}"
    from .asset_refs import ensure_ref

    entry = {
        "id": aid,
        "created_at": _now(),
        "label": label or default_label,
        "style": style,
        "purpose": purpose,
        "size": int(size) if size else None,
        "prompt": prompt,
        "background": background,
        "files": files,
        "preview_url": files.get("art_preview.png") or files.get("art.png"),
    }
    ensure_ref(entry)
    versions = list(meta.get("art_versions") or [])
    versions.insert(0, entry)
    meta["art_versions"] = versions
    save_meta(item_id, meta)
    return entry


def soft_delete_art_version(item_id: str, art_id: str) -> dict[str, Any]:
    meta = load_meta(item_id)
    versions: list[dict[str, Any]] = list(meta.get("art_versions") or [])
    idx = next((i for i, v in enumerate(versions) if v.get("id") == art_id), None)
    if idx is None:
        raise KeyError(art_id)
    entry = versions.pop(idx)
    vdir = art_version_dir(item_id, art_id)
    tdir = trash_dir(item_id) / f"art_{art_id}"
    if vdir.exists():
        if tdir.exists():
            shutil.rmtree(tdir)
        shutil.move(str(vdir), str(tdir))
    files = {
        name: f"/files/{item_id}/trash/art_{art_id}/{name}"
        for name in _ART_FILES
        if (tdir / name).exists()
    }
    trash_entry = {
        "id": art_id,
        "kind": "art",
        "deleted_at": _now(),
        "label": entry.get("label"),
        "style": entry.get("style"),
        "purpose": entry.get("purpose"),
        "size": entry.get("size"),
        "background": entry.get("background"),
        "files": files,
        "preview_url": files.get("art_preview.png") or files.get("art.png"),
    }
    meta.setdefault("trash", {}).setdefault("art", []).insert(0, trash_entry)
    meta["art_versions"] = versions
    save_meta(item_id, meta)
    return trash_entry


def restore_art(item_id: str, trash_id: str) -> dict[str, Any]:
    meta = load_meta(item_id)
    items: list[dict[str, Any]] = meta.setdefault("trash", {}).setdefault("art", [])
    idx = next((i for i, e in enumerate(items) if e.get("id") == trash_id), None)
    if idx is None:
        raise KeyError(trash_id)
    entry = items.pop(idx)
    src_dir = trash_dir(item_id) / f"art_{trash_id}"
    if not src_dir.exists():
        raise FileNotFoundError(trash_id)
    aid = trash_id
    vdir = art_version_dir(item_id, aid)
    if vdir.exists():
        aid = uuid.uuid4().hex[:10]
        vdir = art_version_dir(item_id, aid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _ART_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _art_urls(item_id, aid)
    version = {
        "id": aid,
        "created_at": _now(),
        "label": entry.get("label") or "Art",
        "style": entry.get("style"),
        "purpose": entry.get("purpose"),
        "size": entry.get("size"),
        "background": entry.get("background"),
        "prompt": entry.get("prompt"),
        "files": files,
        "preview_url": files.get("art_preview.png") or files.get("art.png"),
    }
    versions = list(meta.get("art_versions") or [])
    versions.insert(0, version)
    meta["art_versions"] = versions
    meta["trash"]["art"] = items
    save_meta(item_id, meta)
    return version


def list_items(project_id: str | None = None) -> list[dict[str, Any]]:
    game_projects.ensure_migrated()
    items: list[dict[str, Any]] = []
    for iid in game_projects.list_item_ids(project_id):
        try:
            meta = load_meta(iid)
        except FileNotFoundError:
            continue
        items.append(meta)
    items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return items


def list_trashed_items(project_id: str | None = None) -> list[dict[str, Any]]:
    game_projects.ensure_migrated()
    items: list[dict[str, Any]] = []
    for iid in game_projects.list_trashed_item_ids(project_id):
        try:
            meta = load_meta(iid)
        except FileNotFoundError:
            continue
        items.append(
            {
                "id": iid,
                "ref": meta.get("ref"),
                "project_id": meta.get("project_id") or game_projects.project_id_for_item(iid),
                "name": meta.get("name") or iid,
                "style": meta.get("style"),
                "pixel_size": meta.get("pixel_size"),
                "created_at": meta.get("created_at"),
                "deleted_at": meta.get("deleted_at"),
                "preview_url": f"/files/{iid}/base_preview.png",
                "base_url": f"/files/{iid}/base.png",
            }
        )
    items.sort(key=lambda m: m.get("deleted_at") or m.get("created_at") or "", reverse=True)
    return items


def soft_delete_item(item_id: str) -> dict[str, Any]:
    return game_projects.soft_delete_item(item_id)


def restore_item(item_id: str) -> dict[str, Any]:
    return game_projects.restore_item(item_id)


def anim_dir(item_id: str, anim_id: str) -> Path:
    return project_dir(item_id) / "anims" / anim_id


def upsert_animation(
    item_id: str,
    anim_id: str,
    anim_type: str,
    fps: int,
    frames: int,
    variants: list[dict[str, Any]],
    selected_variant: int | None = None,
    motion_notes: str = "",
    name: str = "",
) -> dict[str, Any]:
    from .asset_refs import ensure_ref

    meta = load_meta(item_id)
    anims = meta.setdefault("animations", {})
    prev = anims.get(anim_id) or {}
    entry: dict[str, Any] = {
        "id": anim_id,
        "type": anim_type,
        "name": (name or anim_type or anim_id).strip(),
        "fps": fps,
        "frames": frames,
        "variants": variants,
        "selected_variant": selected_variant,
        "updated_at": _now(),
    }
    if prev.get("ref") is not None:
        entry["ref"] = prev["ref"]
    ensure_ref(entry)
    notes = (motion_notes or "").strip()
    if notes:
        entry["motion_notes"] = notes
    elif prev.get("motion_notes"):
        entry["motion_notes"] = prev["motion_notes"]
    anims[anim_id] = entry
    save_meta(item_id, meta)
    return anims[anim_id]


def soft_delete_animation(item_id: str, animation_id: str) -> dict[str, Any]:
    meta = load_meta(item_id)
    anims = meta.setdefault("animations", {})
    anim = anims.pop(animation_id, None)
    if not anim:
        raise KeyError(animation_id)
    entry = dict(anim)
    entry["deleted_at"] = _now()
    meta.setdefault("trash", {}).setdefault("animations", {})[animation_id] = entry
    save_meta(item_id, meta)
    return entry


def restore_animation(item_id: str, animation_id: str) -> dict[str, Any]:
    from .animation_names import resolve_animation_name
    from .asset_refs import ensure_ref

    meta = load_meta(item_id)
    trash_anims = meta.setdefault("trash", {}).setdefault("animations", {})
    anim = trash_anims.pop(animation_id, None)
    if not anim:
        raise KeyError(animation_id)
    restored = dict(anim)
    restored.pop("deleted_at", None)
    ensure_ref(restored)
    scratch = {**meta, "animations": dict(meta.get("animations") or {})}
    restored["name"] = resolve_animation_name(
        scratch, str(restored.get("type") or "anim"), str(restored.get("name") or "")
    )
    meta.setdefault("animations", {})[animation_id] = restored
    save_meta(item_id, meta)
    return restored
