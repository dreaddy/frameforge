"""Game / studio projects: layer above characters."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import GAME_PROJECTS_DIR, LEGACY_CHARACTERS_DIR, PIXEL_SIZES
from .palettes import normalize_palette, resolve_palette
from .styles import DEFAULT_STYLE, normalize_style

_DEFAULT_NAME = "Default"
_char_to_project: dict[str, str] = {}
_item_to_project: dict[str, str] = {}
_migrated = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def game_project_dir(project_id: str) -> Path:
    return GAME_PROJECTS_DIR / project_id


def characters_root(project_id: str) -> Path:
    path = game_project_dir(project_id) / "characters"
    path.mkdir(parents=True, exist_ok=True)
    return path


def items_root(project_id: str) -> Path:
    path = game_project_dir(project_id) / "items"
    path.mkdir(parents=True, exist_ok=True)
    return path


def trash_root(project_id: str) -> Path:
    path = game_project_dir(project_id) / "trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def items_trash_root(project_id: str) -> Path:
    path = game_project_dir(project_id) / "items_trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def character_dir(character_id: str) -> Path:
    ensure_migrated()
    pid = _char_to_project.get(character_id)
    if not pid:
        raise FileNotFoundError(character_id)
    active = characters_root(pid) / character_id
    if (active / "meta.json").is_file():
        return active
    trashed = trash_root(pid) / character_id
    if (trashed / "meta.json").is_file():
        return trashed
    raise FileNotFoundError(character_id)


def item_dir(item_id: str) -> Path:
    ensure_migrated()
    pid = _item_to_project.get(item_id)
    if not pid:
        raise FileNotFoundError(item_id)
    active = items_root(pid) / item_id
    if (active / "meta.json").is_file():
        return active
    trashed = items_trash_root(pid) / item_id
    if (trashed / "meta.json").is_file():
        return trashed
    raise FileNotFoundError(item_id)


def resolve_asset_dir(asset_id: str) -> Path:
    """Resolve a character or item folder by id (for /files serving)."""
    ensure_migrated()
    if asset_id in _char_to_project:
        return character_dir(asset_id)
    if asset_id in _item_to_project:
        return item_dir(asset_id)
    raise FileNotFoundError(asset_id)


def is_character_trashed(character_id: str) -> bool:
    ensure_migrated()
    pid = _char_to_project.get(character_id)
    if not pid:
        return False
    active = characters_root(pid) / character_id
    if (active / "meta.json").is_file():
        return False
    return (trash_root(pid) / character_id / "meta.json").is_file()


def is_item_trashed(item_id: str) -> bool:
    ensure_migrated()
    pid = _item_to_project.get(item_id)
    if not pid:
        return False
    active = items_root(pid) / item_id
    if (active / "meta.json").is_file():
        return False
    return (items_trash_root(pid) / item_id / "meta.json").is_file()


def project_id_for_character(character_id: str) -> str:
    ensure_migrated()
    pid = _char_to_project.get(character_id)
    if not pid:
        raise FileNotFoundError(character_id)
    return pid


def project_id_for_item(item_id: str) -> str:
    ensure_migrated()
    pid = _item_to_project.get(item_id)
    if not pid:
        raise FileNotFoundError(item_id)
    return pid


def rebuild_character_index() -> None:
    global _char_to_project
    index: dict[str, str] = {}
    if GAME_PROJECTS_DIR.exists():
        for proj in GAME_PROJECTS_DIR.iterdir():
            if not proj.is_dir():
                continue
            for sub in ("characters", "trash"):
                root = proj / sub
                if not root.is_dir():
                    continue
                for cdir in root.iterdir():
                    if cdir.is_dir() and (cdir / "meta.json").exists():
                        index[cdir.name] = proj.name
    _char_to_project = index


def rebuild_item_index() -> None:
    global _item_to_project
    index: dict[str, str] = {}
    if GAME_PROJECTS_DIR.exists():
        for proj in GAME_PROJECTS_DIR.iterdir():
            if not proj.is_dir():
                continue
            for sub in ("items", "items_trash"):
                root = proj / sub
                if not root.is_dir():
                    continue
                for idir in root.iterdir():
                    if idir.is_dir() and (idir / "meta.json").exists():
                        index[idir.name] = proj.name
    _item_to_project = index


def _is_character_folder(path: Path) -> bool:
    meta_path = path / "meta.json"
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    # Game-project meta has description + default_style; character has prompt/pixel_size
    if "prompt" in meta or "pixel_size" in meta or "animations" in meta:
        return True
    return False


def ensure_migrated() -> None:
    global _migrated
    if _migrated:
        return
    GAME_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_flat_characters()
    if not list_projects():
        create_project(
            name=_DEFAULT_NAME,
            description="",
            default_style=DEFAULT_STYLE,
            default_pixel_size=128,
        )
    rebuild_character_index()
    rebuild_item_index()
    # Mark migrated before backfill — list_* calls ensure_migrated() and must not recurse.
    _migrated = True
    from .asset_refs import backfill_all_identities

    backfill_all_identities()


def _migrate_legacy_flat_characters() -> None:
    legacy = LEGACY_CHARACTERS_DIR
    if not legacy.is_dir():
        return
    folders = [p for p in legacy.iterdir() if p.is_dir() and _is_character_folder(p)]
    if not folders:
        return
    projects = list_projects()
    if projects:
        default = next((p for p in projects if p.get("name") == _DEFAULT_NAME), projects[0])
    else:
        default = create_project(
            name=_DEFAULT_NAME,
            description="Migrated characters from before game projects existed.",
            default_style=DEFAULT_STYLE,
            default_pixel_size=128,
        )
    dest_root = characters_root(default["id"])
    for src in folders:
        dest = dest_root / src.name
        if dest.exists():
            continue
        shutil.move(str(src), str(dest))
        meta_path = dest / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["project_id"] = default["id"]
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    # Leave empty legacy dir (or leftover non-character junk) in place


def _count_meta_folders(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.iterdir() if p.is_dir() and (p / "meta.json").exists())


def _project_payload(meta: dict[str, Any]) -> dict[str, Any]:
    pid = meta["id"]
    chars_dir = game_project_dir(pid) / "characters"
    trash_dir = game_project_dir(pid) / "trash"
    items_dir = game_project_dir(pid) / "items"
    items_trash_dir = game_project_dir(pid) / "items_trash"
    preset, colors = resolve_palette(
        preset_id=meta.get("palette_preset"),
        colors=meta.get("palette"),
    )
    seed = normalize_palette(meta.get("palette_seed"))
    return {
        **meta,
        "palette_preset": preset,
        "palette": colors,
        "palette_seed": seed,
        "character_count": _count_meta_folders(chars_dir),
        "trash_count": _count_meta_folders(trash_dir),
        "item_count": _count_meta_folders(items_dir),
        "items_trash_count": _count_meta_folders(items_trash_dir),
    }


def list_projects() -> list[dict[str, Any]]:
    GAME_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for p in sorted(GAME_PROJECTS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        meta_path = p / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _is_character_folder(p):
            continue
        items.append(_project_payload(meta))
    return items


def load_project(project_id: str) -> dict[str, Any]:
    path = game_project_dir(project_id) / "meta.json"
    if not path.is_file():
        raise FileNotFoundError(project_id)
    meta = json.loads(path.read_text(encoding="utf-8"))
    return _project_payload(meta)


def save_project(project_id: str, meta: dict[str, Any]) -> None:
    root = game_project_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)
    characters_root(project_id)
    items_root(project_id)
    path = root / "meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def create_project(
    name: str,
    description: str = "",
    default_style: str = DEFAULT_STYLE,
    default_pixel_size: int = 128,
    default_drop_shadow: bool = False,
    default_outline: bool = False,
    palette_preset: str = "none",
    palette: list[str] | None = None,
    palette_seed: list[str] | None = None,
) -> dict[str, Any]:
    pid = uuid.uuid4().hex[:12]
    style = normalize_style(default_style)
    size = default_pixel_size if default_pixel_size in PIXEL_SIZES else 128
    preset, colors = resolve_palette(preset_id=palette_preset, colors=palette)
    meta = {
        "id": pid,
        "name": (name or "Untitled").strip() or "Untitled",
        "description": (description or "").strip(),
        "default_style": style,
        "default_pixel_size": size,
        "default_drop_shadow": bool(default_drop_shadow),
        "default_outline": bool(default_outline),
        "palette_preset": preset,
        "palette": colors,
        "palette_seed": normalize_palette(palette_seed),
        "created_at": _now(),
        "updated_at": _now(),
    }
    save_project(pid, meta)
    rebuild_character_index()
    rebuild_item_index()
    return _project_payload(meta)


def update_project(project_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    meta = load_project(project_id)
    meta.pop("character_count", None)
    meta.pop("trash_count", None)
    meta.pop("item_count", None)
    meta.pop("items_trash_count", None)
    if "name" in patch and patch["name"] is not None:
        meta["name"] = str(patch["name"]).strip() or meta["name"]
    if "description" in patch and patch["description"] is not None:
        meta["description"] = str(patch["description"]).strip()
    if "default_style" in patch and patch["default_style"] is not None:
        meta["default_style"] = normalize_style(str(patch["default_style"]))
    if "default_pixel_size" in patch and patch["default_pixel_size"] is not None:
        size = int(patch["default_pixel_size"])
        if size not in PIXEL_SIZES:
            raise ValueError(f"default_pixel_size must be one of {PIXEL_SIZES}")
        meta["default_pixel_size"] = size
    if "default_drop_shadow" in patch and patch["default_drop_shadow"] is not None:
        meta["default_drop_shadow"] = bool(patch["default_drop_shadow"])
    if "default_outline" in patch and patch["default_outline"] is not None:
        meta["default_outline"] = bool(patch["default_outline"])
    if "palette_preset" in patch or "palette" in patch:
        preset_in = (
            patch["palette_preset"] if "palette_preset" in patch else meta.get("palette_preset")
        )
        colors_in = patch["palette"] if "palette" in patch else meta.get("palette")
        preset, colors = resolve_palette(preset_id=preset_in, colors=colors_in)
        meta["palette_preset"] = preset
        meta["palette"] = colors
    if "palette_seed" in patch:
        meta["palette_seed"] = normalize_palette(patch.get("palette_seed"))
    meta["updated_at"] = _now()
    save_project(project_id, meta)
    return _project_payload(meta)


def project_palette_colors(project_id: str | None) -> list[str]:
    if not project_id:
        return []
    try:
        meta = load_project(project_id)
    except FileNotFoundError:
        return []
    _preset, colors = resolve_palette(
        preset_id=meta.get("palette_preset"),
        colors=meta.get("palette"),
    )
    return colors


def delete_project(project_id: str) -> None:
    meta = load_project(project_id)
    if int(meta.get("character_count") or 0) > 0 or int(meta.get("trash_count") or 0) > 0:
        raise ValueError("project still has characters (or trash); empty them first")
    if int(meta.get("item_count") or 0) > 0 or int(meta.get("items_trash_count") or 0) > 0:
        raise ValueError("project still has items (or items trash); empty them first")
    root = game_project_dir(project_id)
    if root.exists():
        shutil.rmtree(root)
    rebuild_character_index()
    rebuild_item_index()


def register_character(project_id: str, character_id: str) -> None:
    load_project(project_id)  # exists
    _char_to_project[character_id] = project_id


def register_item(project_id: str, item_id: str) -> None:
    load_project(project_id)
    _item_to_project[item_id] = project_id


def _ids_in_root(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return [p.name for p in root.iterdir() if p.is_dir() and (p / "meta.json").exists()]


def list_character_ids(project_id: str | None = None) -> list[str]:
    """Active (non-trashed) character ids."""
    ensure_migrated()
    if project_id is not None:
        load_project(project_id)
        return _ids_in_root(characters_root(project_id))
    ids: list[str] = []
    for proj in list_projects():
        ids.extend(_ids_in_root(characters_root(proj["id"])))
    return ids


def list_trashed_character_ids(project_id: str | None = None) -> list[str]:
    ensure_migrated()
    if project_id is not None:
        load_project(project_id)
        return _ids_in_root(trash_root(project_id))
    ids: list[str] = []
    for proj in list_projects():
        ids.extend(_ids_in_root(trash_root(proj["id"])))
    return ids


def soft_delete_character(character_id: str) -> dict[str, Any]:
    ensure_migrated()
    if is_character_trashed(character_id):
        raise KeyError(character_id)
    pid = project_id_for_character(character_id)
    src = characters_root(pid) / character_id
    if not (src / "meta.json").is_file():
        raise FileNotFoundError(character_id)
    dest = trash_root(pid) / character_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))
    meta_path = dest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["deleted_at"] = _now()
    meta["project_id"] = pid
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_character_index()
    return {
        "id": character_id,
        "ref": meta.get("ref"),
        "project_id": pid,
        "name": meta.get("name"),
        "deleted_at": meta["deleted_at"],
        "preview_url": f"/files/{character_id}/base_preview.png",
        "style": meta.get("style"),
        "pixel_size": meta.get("pixel_size"),
    }


def restore_character(character_id: str) -> dict[str, Any]:
    ensure_migrated()
    if not is_character_trashed(character_id):
        raise KeyError(character_id)
    pid = project_id_for_character(character_id)
    src = trash_root(pid) / character_id
    if not (src / "meta.json").is_file():
        raise FileNotFoundError(character_id)
    dest = characters_root(pid) / character_id
    if dest.exists():
        raise ValueError("character id already active")
    shutil.move(str(src), str(dest))
    meta_path = dest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("deleted_at", None)
    meta["project_id"] = pid
    from .asset_refs import assign_identity

    assign_identity(
        meta,
        kind="character",
        project_id=pid,
        desired_name=str(meta.get("name") or ""),
        allocate_if_missing=True,
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_character_index()
    return meta


def list_item_ids(project_id: str | None = None) -> list[str]:
    ensure_migrated()
    if project_id is not None:
        load_project(project_id)
        return _ids_in_root(items_root(project_id))
    ids: list[str] = []
    for proj in list_projects():
        ids.extend(_ids_in_root(items_root(proj["id"])))
    return ids


def list_trashed_item_ids(project_id: str | None = None) -> list[str]:
    ensure_migrated()
    if project_id is not None:
        load_project(project_id)
        return _ids_in_root(items_trash_root(project_id))
    ids: list[str] = []
    for proj in list_projects():
        ids.extend(_ids_in_root(items_trash_root(proj["id"])))
    return ids


def soft_delete_item(item_id: str) -> dict[str, Any]:
    ensure_migrated()
    if is_item_trashed(item_id):
        raise KeyError(item_id)
    pid = project_id_for_item(item_id)
    src = items_root(pid) / item_id
    if not (src / "meta.json").is_file():
        raise FileNotFoundError(item_id)
    dest = items_trash_root(pid) / item_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))
    meta_path = dest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["deleted_at"] = _now()
    meta["project_id"] = pid
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_item_index()
    return {
        "id": item_id,
        "ref": meta.get("ref"),
        "project_id": pid,
        "name": meta.get("name"),
        "deleted_at": meta["deleted_at"],
        "preview_url": f"/files/{item_id}/base_preview.png",
        "style": meta.get("style"),
        "pixel_size": meta.get("pixel_size"),
    }


def restore_item(item_id: str) -> dict[str, Any]:
    ensure_migrated()
    if not is_item_trashed(item_id):
        raise KeyError(item_id)
    pid = project_id_for_item(item_id)
    src = items_trash_root(pid) / item_id
    if not (src / "meta.json").is_file():
        raise FileNotFoundError(item_id)
    dest = items_root(pid) / item_id
    if dest.exists():
        raise ValueError("item id already active")
    shutil.move(str(src), str(dest))
    meta_path = dest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("deleted_at", None)
    meta["project_id"] = pid
    from .asset_refs import assign_identity

    assign_identity(
        meta,
        kind="item",
        project_id=pid,
        desired_name=str(meta.get("name") or ""),
        allocate_if_missing=True,
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_item_index()
    return meta
