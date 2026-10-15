from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import projects as game_projects

_STANDING_FILES = (
    "standing.png",
    "standing_preview.png",
    "standing_i2v.png",
    "standing_raw.png",
)

_ART_FILES = (
    "art.png",
    "art_preview.png",
    "art_raw.png",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(character_id: str) -> Path:
    """On-disk folder for a character (under its game project)."""
    return game_projects.character_dir(character_id)


def trash_dir(character_id: str) -> Path:
    path = project_dir(character_id) / "trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_character(
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

    cid = uuid.uuid4().hex[:12]
    root = game_projects.characters_root(project_id) / cid
    (root / "anims").mkdir(parents=True, exist_ok=True)
    (root / "export").mkdir(parents=True, exist_ok=True)
    game_projects.register_character(project_id, cid)
    meta = {
        "id": cid,
        "project_id": project_id,
        "name": name,
        "prompt": prompt,
        "pixel_size": pixel_size,
        "style": style,
        "drop_shadow": drop_shadow,
        "outline": outline,
        "created_at": _now(),
        "source_image": "base",
        "has_standing": False,
        "active_standing_id": None,
        "standing_versions": [],
        "art_versions": [],
        "animations": {},
        "trash": {"animations": {}, "standing": [], "art": []},
    }
    assign_identity(meta, kind="character", project_id=project_id, desired_name=name)
    # meta.json must exist before project_dir()/character_dir() lookups (trash_dir)
    (root / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    trash_dir(cid)
    return meta


def save_meta(character_id: str, meta: dict[str, Any]) -> None:
    path = project_dir(character_id) / "meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_meta(character_id: str) -> dict[str, Any]:
    path = project_dir(character_id) / "meta.json"
    if not path.exists():
        raise FileNotFoundError(character_id)
    meta = json.loads(path.read_text(encoding="utf-8"))
    trash = meta.setdefault("trash", {})
    trash.setdefault("animations", {})
    trash.setdefault("standing", [])
    trash.setdefault("art", [])
    meta.setdefault("standing_versions", [])
    meta.setdefault("art_versions", [])
    if "active_standing_id" not in meta:
        meta["active_standing_id"] = None
    return meta


def standings_dir(character_id: str) -> Path:
    path = project_dir(character_id) / "standings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def arts_dir(character_id: str) -> Path:
    path = project_dir(character_id) / "arts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def art_version_dir(character_id: str, art_id: str) -> Path:
    return arts_dir(character_id) / art_id


def _art_urls(character_id: str, art_id: str) -> dict[str, str]:
    vdir = art_version_dir(character_id, art_id)
    files: dict[str, str] = {}
    for name in _ART_FILES:
        if (vdir / name).exists():
            files[name] = f"/files/{character_id}/arts/{art_id}/{name}"
    return files


def standing_version_dir(character_id: str, standing_id: str) -> Path:
    return standings_dir(character_id) / standing_id


def _version_urls(character_id: str, standing_id: str) -> dict[str, str]:
    vdir = standing_version_dir(character_id, standing_id)
    files: dict[str, str] = {}
    for name in _STANDING_FILES:
        if (vdir / name).exists():
            files[name] = f"/files/{character_id}/standings/{standing_id}/{name}"
    return files


def _sync_active_standing_files(character_id: str, standing_id: str | None) -> None:
    """Keep root standing_*.png as a copy of the active version (anim job / legacy)."""
    root = project_dir(character_id)
    for name in _STANDING_FILES:
        path = root / name
        if path.exists():
            path.unlink()
    if not standing_id:
        return
    vdir = standing_version_dir(character_id, standing_id)
    for name in _STANDING_FILES:
        src = vdir / name
        if src.exists():
            shutil.copy2(src, root / name)


def migrate_standing_versions(character_id: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ensure legacy root standing_* becomes a selectable version."""
    meta = meta or load_meta(character_id)
    versions: list[dict[str, Any]] = list(meta.get("standing_versions") or [])
    root = project_dir(character_id)
    legacy = (root / "standing_preview.png").exists() or (root / "standing.png").exists()
    if versions:
        ids = {v.get("id") for v in versions}
        if meta.get("active_standing_id") not in ids:
            meta["active_standing_id"] = versions[0]["id"]
            meta["has_standing"] = True
            _sync_active_standing_files(character_id, meta["active_standing_id"])
            save_meta(character_id, meta)
        else:
            meta["has_standing"] = True
        return meta
    if not legacy:
        meta["has_standing"] = False
        meta["active_standing_id"] = None
        meta["standing_versions"] = []
        return meta
    sid = uuid.uuid4().hex[:10]
    vdir = standing_version_dir(character_id, sid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _STANDING_FILES:
        src = root / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _version_urls(character_id, sid)
    from .asset_refs import ensure_ref

    entry = {
        "id": sid,
        "created_at": _now(),
        "label": "Standing 1",
        "files": files,
        "preview_url": files.get("standing_preview.png") or files.get("standing.png"),
    }
    ensure_ref(entry)
    meta["standing_versions"] = [entry]
    meta["active_standing_id"] = sid
    meta["has_standing"] = True
    if meta.get("source_image") not in ("base", "standing"):
        meta["source_image"] = "standing"
    save_meta(character_id, meta)
    return meta


def register_standing_version(
    character_id: str,
    *,
    src_dir: Path,
    set_as_source: bool = True,
    label: str | None = None,
    pose: str | None = None,
) -> dict[str, Any]:
    """Copy generated standing/pose files from src_dir into a new selectable version."""
    meta = migrate_standing_versions(character_id)
    sid = uuid.uuid4().hex[:10]
    vdir = standing_version_dir(character_id, sid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _STANDING_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _version_urls(character_id, sid)
    if not files:
        shutil.rmtree(vdir, ignore_errors=True)
        raise FileNotFoundError("standing files missing after generation")
    from .asset_refs import ensure_ref

    n = len(meta.get("standing_versions") or []) + 1
    pose_text = (pose or "").strip() or None
    entry = {
        "id": sid,
        "created_at": _now(),
        "label": label or (pose_text[:1].upper() + pose_text[1:] if pose_text else f"Pose {n}"),
        "pose": pose_text,
        "files": files,
        "preview_url": files.get("standing_preview.png") or files.get("standing.png"),
    }
    ensure_ref(entry)
    versions = list(meta.get("standing_versions") or [])
    versions.insert(0, entry)
    meta["standing_versions"] = versions
    meta["active_standing_id"] = sid
    meta["has_standing"] = True
    if set_as_source:
        meta["source_image"] = "standing"
    _sync_active_standing_files(character_id, sid)
    save_meta(character_id, meta)
    return entry


def set_source_image(
    character_id: str,
    source_image: str,
    standing_id: str | None = None,
) -> dict[str, Any]:
    meta = migrate_standing_versions(character_id)
    source_image = (source_image or "base").strip().lower()
    if source_image not in ("base", "standing"):
        raise ValueError("source_image must be base or standing")
    versions = list(meta.get("standing_versions") or [])
    if source_image == "standing":
        if not versions:
            raise FileNotFoundError("standing")
        sid = standing_id or meta.get("active_standing_id") or versions[0]["id"]
        if not any(v.get("id") == sid for v in versions):
            raise KeyError(sid)
        meta["active_standing_id"] = sid
        meta["source_image"] = "standing"
        meta["has_standing"] = True
        _sync_active_standing_files(character_id, sid)
    else:
        meta["source_image"] = "base"
    save_meta(character_id, meta)
    return meta


def resolve_standing_i2v(character_id: str, standing_id: str | None = None) -> Path:
    meta = migrate_standing_versions(character_id)
    sid = standing_id or meta.get("active_standing_id")
    if sid:
        path = standing_version_dir(character_id, sid) / "standing_i2v.png"
        if path.exists():
            return path
        preview = standing_version_dir(character_id, sid) / "standing_preview.png"
        if preview.exists():
            return preview
    legacy = project_dir(character_id) / "standing_i2v.png"
    if legacy.exists():
        return legacy
    raise FileNotFoundError("standing")


def soft_delete_standing_version(character_id: str, standing_id: str | None = None) -> dict[str, Any]:
    meta = migrate_standing_versions(character_id)
    versions: list[dict[str, Any]] = list(meta.get("standing_versions") or [])
    sid = standing_id or meta.get("active_standing_id")
    if not sid:
        raise FileNotFoundError("standing")
    idx = next((i for i, v in enumerate(versions) if v.get("id") == sid), None)
    if idx is None:
        raise KeyError(sid)
    entry = versions.pop(idx)
    vdir = standing_version_dir(character_id, sid)
    tdir = trash_dir(character_id) / f"standing_{sid}"
    if vdir.exists():
        if tdir.exists():
            shutil.rmtree(tdir)
        shutil.move(str(vdir), str(tdir))
    files = {
        name: f"/files/{character_id}/trash/standing_{sid}/{name}"
        for name in _STANDING_FILES
        if (tdir / name).exists()
    }
    trash_entry = {
        "id": sid,
        "kind": "standing",
        "deleted_at": _now(),
        "label": entry.get("label"),
        "files": files,
        "preview_url": files.get("standing_preview.png") or files.get("standing.png"),
    }
    meta.setdefault("trash", {}).setdefault("standing", []).insert(0, trash_entry)
    meta["standing_versions"] = versions
    if meta.get("active_standing_id") == sid:
        meta["active_standing_id"] = versions[0]["id"] if versions else None
    meta["has_standing"] = bool(versions)
    if not versions and meta.get("source_image") == "standing":
        meta["source_image"] = "base"
    _sync_active_standing_files(character_id, meta.get("active_standing_id"))
    save_meta(character_id, meta)
    return trash_entry


def soft_delete_standing(character_id: str) -> dict[str, Any]:
    """Soft-delete the active standing version."""
    return soft_delete_standing_version(character_id, None)


def register_art_version(
    character_id: str,
    *,
    src_dir: Path,
    style: str,
    purpose: str,
    prompt: str | None = None,
    background: str | None = None,
    label: str | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    meta = load_meta(character_id)
    aid = uuid.uuid4().hex[:10]
    vdir = art_version_dir(character_id, aid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _ART_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _art_urls(character_id, aid)
    if not files:
        shutil.rmtree(vdir, ignore_errors=True)
        raise FileNotFoundError("art files missing after generation")
    purpose_labels = {
        "portrait": "Portrait",
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
    save_meta(character_id, meta)
    return entry


def soft_delete_art_version(character_id: str, art_id: str) -> dict[str, Any]:
    meta = load_meta(character_id)
    versions: list[dict[str, Any]] = list(meta.get("art_versions") or [])
    idx = next((i for i, v in enumerate(versions) if v.get("id") == art_id), None)
    if idx is None:
        raise KeyError(art_id)
    entry = versions.pop(idx)
    vdir = art_version_dir(character_id, art_id)
    tdir = trash_dir(character_id) / f"art_{art_id}"
    if vdir.exists():
        if tdir.exists():
            shutil.rmtree(tdir)
        shutil.move(str(vdir), str(tdir))
    files = {
        name: f"/files/{character_id}/trash/art_{art_id}/{name}"
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
    save_meta(character_id, meta)
    return trash_entry


def restore_art(character_id: str, trash_id: str) -> dict[str, Any]:
    meta = load_meta(character_id)
    items: list[dict[str, Any]] = meta.setdefault("trash", {}).setdefault("art", [])
    idx = next((i for i, e in enumerate(items) if e.get("id") == trash_id), None)
    if idx is None:
        raise KeyError(trash_id)
    entry = items.pop(idx)
    src_dir = trash_dir(character_id) / f"art_{trash_id}"
    if not src_dir.exists():
        raise FileNotFoundError(trash_id)
    aid = trash_id
    vdir = art_version_dir(character_id, aid)
    if vdir.exists():
        aid = uuid.uuid4().hex[:10]
        vdir = art_version_dir(character_id, aid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _ART_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _art_urls(character_id, aid)
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
    save_meta(character_id, meta)
    return version


def restore_standing(character_id: str, trash_id: str) -> dict[str, Any]:
    meta = migrate_standing_versions(character_id)
    items: list[dict[str, Any]] = meta.setdefault("trash", {}).setdefault("standing", [])
    idx = next((i for i, e in enumerate(items) if e.get("id") == trash_id), None)
    if idx is None:
        raise KeyError(trash_id)
    entry = items.pop(idx)
    src_dir = trash_dir(character_id) / f"standing_{trash_id}"
    if not src_dir.exists():
        raise FileNotFoundError(trash_id)
    sid = trash_id
    vdir = standing_version_dir(character_id, sid)
    if vdir.exists():
        sid = uuid.uuid4().hex[:10]
        vdir = standing_version_dir(character_id, sid)
    vdir.mkdir(parents=True, exist_ok=True)
    for name in _STANDING_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, vdir / name)
    files = _version_urls(character_id, sid)
    n = len(meta.get("standing_versions") or []) + 1
    version = {
        "id": sid,
        "created_at": _now(),
        "label": entry.get("label") or f"Standing {n}",
        "files": files,
        "preview_url": files.get("standing_preview.png") or files.get("standing.png"),
    }
    versions = list(meta.get("standing_versions") or [])
    versions.insert(0, version)
    meta["standing_versions"] = versions
    meta["active_standing_id"] = sid
    meta["has_standing"] = True
    meta["source_image"] = "standing"
    meta["trash"]["standing"] = items
    _sync_active_standing_files(character_id, sid)
    save_meta(character_id, meta)
    return version


def list_characters(project_id: str | None = None) -> list[dict[str, Any]]:
    game_projects.ensure_migrated()
    items: list[dict[str, Any]] = []
    for cid in game_projects.list_character_ids(project_id):
        try:
            meta = load_meta(cid)
        except FileNotFoundError:
            continue
        items.append(meta)
    items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return items


def list_trashed_characters(project_id: str | None = None) -> list[dict[str, Any]]:
    game_projects.ensure_migrated()
    items: list[dict[str, Any]] = []
    for cid in game_projects.list_trashed_character_ids(project_id):
        try:
            meta = load_meta(cid)
        except FileNotFoundError:
            continue
        items.append(
            {
                "id": cid,
                "ref": meta.get("ref"),
                "project_id": meta.get("project_id") or game_projects.project_id_for_character(cid),
                "name": meta.get("name") or cid,
                "style": meta.get("style"),
                "pixel_size": meta.get("pixel_size"),
                "created_at": meta.get("created_at"),
                "deleted_at": meta.get("deleted_at"),
                "preview_url": f"/files/{cid}/base_preview.png",
                "base_url": f"/files/{cid}/base.png",
            }
        )
    items.sort(key=lambda m: m.get("deleted_at") or m.get("created_at") or "", reverse=True)
    return items


def soft_delete_character(character_id: str) -> dict[str, Any]:
    return game_projects.soft_delete_character(character_id)


def restore_character(character_id: str) -> dict[str, Any]:
    return game_projects.restore_character(character_id)


def anim_dir(character_id: str, anim_id: str) -> Path:
    return project_dir(character_id) / "anims" / anim_id


def upsert_animation(
    character_id: str,
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

    meta = load_meta(character_id)
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
    save_meta(character_id, meta)
    return anims[anim_id]


def soft_delete_animation(character_id: str, animation_id: str) -> dict[str, Any]:
    meta = load_meta(character_id)
    anims = meta.setdefault("animations", {})
    anim = anims.pop(animation_id, None)
    if not anim:
        raise KeyError(animation_id)
    entry = dict(anim)
    entry["deleted_at"] = _now()
    meta.setdefault("trash", {}).setdefault("animations", {})[animation_id] = entry
    save_meta(character_id, meta)
    return entry


def restore_animation(character_id: str, animation_id: str) -> dict[str, Any]:
    from .animation_names import resolve_animation_name
    from .asset_refs import ensure_ref

    meta = load_meta(character_id)
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
    save_meta(character_id, meta)
    return restored


def archive_standing(character_id: str, *, clear_active: bool = False) -> dict[str, Any] | None:
    """Deprecated: generating a new standing keeps prior versions selectable.

    Kept as a no-op migrator so older call sites don't trash versions on rebuild.
    """
    del clear_active
    migrate_standing_versions(character_id)
    return None
