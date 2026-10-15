"""Stable numeric refs (#3294) + unique display names for characters/items."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from .config import GAME_PROJECTS_DIR

Kind = Literal["character", "item"]

_NEXT_REF_PATH = GAME_PROJECTS_DIR / "_next_ref.json"
_START_REF = 1000
_SUFFIX_RE = re.compile(r"^(.*?)(?:\s+(\d+))?$")


def _read_counter() -> int:
    GAME_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    if not _NEXT_REF_PATH.is_file():
        return _START_REF
    try:
        data = json.loads(_NEXT_REF_PATH.read_text(encoding="utf-8"))
        return max(_START_REF, int(data.get("next") or _START_REF))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _START_REF


def _write_counter(next_ref: int) -> None:
    GAME_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    _NEXT_REF_PATH.write_text(
        json.dumps({"next": int(next_ref)}, indent=2),
        encoding="utf-8",
    )


def allocate_ref() -> int:
    """Return a new globally unique numeric ref (assets + anims + standing + art)."""
    nxt = _read_counter()
    _write_counter(nxt + 1)
    return nxt


def _coerce_ref(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def ensure_ref(entry: dict[str, Any]) -> int:
    """Ensure entry has an int `ref`; allocate if missing. Returns the ref."""
    ref = _coerce_ref(entry.get("ref"))
    if ref is not None:
        entry["ref"] = ref
        return ref
    ref = allocate_ref()
    entry["ref"] = ref
    return ref


def _collect_refs_from_meta(meta: dict[str, Any], into: set[int]) -> None:
    ref = _coerce_ref(meta.get("ref"))
    if ref is not None:
        into.add(ref)
    for anim in (meta.get("animations") or {}).values():
        if isinstance(anim, dict):
            r = _coerce_ref(anim.get("ref"))
            if r is not None:
                into.add(r)
    trash = meta.get("trash") or {}
    for anim in (trash.get("animations") or {}).values():
        if isinstance(anim, dict):
            r = _coerce_ref(anim.get("ref"))
            if r is not None:
                into.add(r)
    for key in ("standing_versions", "art_versions"):
        for row in meta.get(key) or []:
            if isinstance(row, dict):
                r = _coerce_ref(row.get("ref"))
                if r is not None:
                    into.add(r)
    for key in ("standing", "art"):
        for row in trash.get(key) or []:
            if isinstance(row, dict):
                r = _coerce_ref(row.get("ref"))
                if r is not None:
                    into.add(r)


def _all_existing_refs() -> set[int]:
    refs: set[int] = set()
    if not GAME_PROJECTS_DIR.is_dir():
        return refs
    for proj in GAME_PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        for sub in ("characters", "trash", "items", "items_trash"):
            root = proj / sub
            if not root.is_dir():
                continue
            for folder in root.iterdir():
                meta_path = folder / "meta.json"
                if not meta_path.is_file():
                    continue
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                _collect_refs_from_meta(meta, refs)
    return refs


def uniquify_name(desired: str, taken: set[str], *, fallback: str = "Asset") -> str:
    """Return a name not in taken (case-insensitive). Appends ' 2', ' 3', … if needed."""
    base = (desired or "").strip() or fallback
    taken_l = {t.lower() for t in taken if t}
    if base.lower() not in taken_l:
        return base
    # If already ends with a number, bump from there
    m = _SUFFIX_RE.match(base)
    stem = (m.group(1) if m else base).rstrip() or fallback
    start = int(m.group(2)) + 1 if m and m.group(2) else 2
    n = start
    while True:
        candidate = f"{stem} {n}"
        if candidate.lower() not in taken_l:
            return candidate
        n += 1


def active_names(kind: Kind, project_id: str, *, exclude_id: str | None = None) -> set[str]:
    """Display names of active (non-trash) assets in a project."""
    from . import item_storage, storage

    names: set[str] = set()
    if kind == "character":
        for meta in storage.list_characters(project_id):
            if exclude_id and meta.get("id") == exclude_id:
                continue
            n = str(meta.get("name") or "").strip()
            if n:
                names.add(n)
    else:
        for meta in item_storage.list_items(project_id):
            if exclude_id and meta.get("id") == exclude_id:
                continue
            n = str(meta.get("name") or "").strip()
            if n:
                names.add(n)
    return names


def assign_identity(
    meta: dict[str, Any],
    *,
    kind: Kind,
    project_id: str,
    desired_name: str | None = None,
    allocate_if_missing: bool = True,
) -> dict[str, Any]:
    """Ensure meta has unique name (in project) and a numeric ref. Mutates + returns meta."""
    exclude_id = str(meta.get("id") or "") or None
    name_in = (desired_name if desired_name is not None else meta.get("name")) or ""
    taken = active_names(kind, project_id, exclude_id=exclude_id)
    meta["name"] = uniquify_name(
        str(name_in),
        taken,
        fallback="Creature" if kind == "character" else "Item",
    )
    ref = meta.get("ref")
    if isinstance(ref, str) and ref.isdigit():
        meta["ref"] = int(ref)
    elif not isinstance(ref, int):
        if allocate_if_missing:
            meta["ref"] = allocate_ref()
    return meta


def normalize_lookup_key(key: str) -> str:
    """Strip casual prefixes: 'objekt 3294', '#3294', 'creature Foo' → usable key."""
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


def parse_ref_key(key: str) -> int | None:
    k = normalize_lookup_key(key)
    if k.isdigit():
        return int(k)
    return None


def _backfill_nested_refs(meta: dict[str, Any]) -> int:
    """Assign missing refs on animations / standing / art (incl. trash). Returns count."""
    from .animation_names import resolve_animation_name, sanitize_anim_name

    n = 0
    dirty = False

    def _need(entry: dict[str, Any]) -> None:
        nonlocal n, dirty
        before = entry.get("ref")
        ensure_ref(entry)
        if entry.get("ref") != before:
            n += 1
            dirty = True

    for anim in (meta.get("animations") or {}).values():
        if isinstance(anim, dict):
            _need(anim)
    trash = meta.setdefault("trash", {})
    for anim in (trash.get("animations") or {}).values():
        if isinstance(anim, dict):
            _need(anim)
    for key in ("standing_versions", "art_versions"):
        rows = list(meta.get(key) or [])
        for row in rows:
            if isinstance(row, dict):
                _need(row)
        meta[key] = rows
    for key in ("standing", "art"):
        rows = list(trash.get(key) or [])
        for row in rows:
            if isinstance(row, dict):
                _need(row)
        trash[key] = rows

    # Uniquify active animation names within this asset
    anims = meta.get("animations") or {}
    if isinstance(anims, dict) and anims:
        ordered = sorted(
            anims.items(),
            key=lambda kv: str((kv[1] or {}).get("updated_at") or (kv[1] or {}).get("created_at") or ""),
        )
        rebuilt: dict[str, Any] = {}
        scratch: dict[str, Any] = {**meta, "animations": {}}
        for aid, anim in ordered:
            if not isinstance(anim, dict):
                rebuilt[aid] = anim
                continue
            want = sanitize_anim_name(str(anim.get("name") or anim.get("type") or aid))
            unique = resolve_animation_name(scratch, str(anim.get("type") or want), want)
            if unique != anim.get("name"):
                anim = {**anim, "name": unique}
                n += 1
                dirty = True
            rebuilt[aid] = anim
            scratch["animations"][aid] = anim
        meta["animations"] = rebuilt

    return n if dirty else 0


def backfill_all_identities() -> dict[str, int]:
    """Assign missing refs and uniquify active names. Called once after migration."""
    from . import item_storage, storage

    assigned = 0
    renamed = 0
    nested = 0
    known = _all_existing_refs()
    max_ref = max(known) if known else _START_REF - 1
    nxt = _read_counter()
    if nxt <= max_ref:
        _write_counter(max_ref + 1)

    # Pass 1: asset refs + nested refs (active + trash)
    for kind, lister, saver in (
        (
            "character",
            lambda: _iter_all_character_metas(),
            storage.save_meta,
        ),
        (
            "item",
            lambda: _iter_all_item_metas(),
            item_storage.save_meta,
        ),
    ):
        for asset_id, meta, _trashed in lister():
            changed = False
            ref = _coerce_ref(meta.get("ref"))
            if ref is None:
                meta["ref"] = allocate_ref()
                assigned += 1
                changed = True
            else:
                meta["ref"] = ref
            nested_n = _backfill_nested_refs(meta)
            if nested_n:
                nested += nested_n
                changed = True
            if changed:
                saver(asset_id, meta)

    # Pass 2: uniquify active asset names per project
    for kind, list_active, saver in (
        ("character", storage.list_characters, storage.save_meta),
        ("item", item_storage.list_items, item_storage.save_meta),
    ):
        by_project: dict[str, list[dict[str, Any]]] = {}
        for meta in list_active(None):
            pid = str(meta.get("project_id") or "")
            by_project.setdefault(pid, []).append(meta)
        for pid, rows in by_project.items():
            rows_sorted = sorted(rows, key=lambda m: m.get("created_at") or "")
            taken: set[str] = set()
            for meta in rows_sorted:
                raw = str(meta.get("name") or "").strip()
                unique = uniquify_name(
                    raw,
                    taken,
                    fallback="Creature" if kind == "character" else "Item",
                )
                taken.add(unique)
                if unique != meta.get("name"):
                    meta["name"] = unique
                    saver(str(meta["id"]), meta)
                    renamed += 1

    return {
        "refs_assigned": assigned,
        "nested_refs_or_renames": nested,
        "names_uniquified": renamed,
    }


def _iter_all_character_metas():
    from . import projects as game_projects
    from . import storage

    game_projects.ensure_migrated()
    active = set(game_projects.list_character_ids(None))
    ids = list(active) + list(game_projects.list_trashed_character_ids(None))
    for cid in ids:
        try:
            meta = storage.load_meta(cid)
        except FileNotFoundError:
            continue
        yield cid, meta, cid not in active


def _iter_all_item_metas():
    from . import item_storage
    from . import projects as game_projects

    game_projects.ensure_migrated()
    active = set(game_projects.list_item_ids(None))
    ids = list(active) + list(game_projects.list_trashed_item_ids(None))
    for iid in ids:
        try:
            meta = item_storage.load_meta(iid)
        except FileNotFoundError:
            continue
        yield iid, meta, iid not in active


def find_by_ref(ref: int, *, include_trash: bool = False) -> dict[str, Any] | None:
    """Find character/item OR nested anim/standing/art by numeric ref."""
    from . import item_storage, storage

    def _scan_meta(meta: dict[str, Any], *, kind: str, trashed: bool = False) -> dict[str, Any] | None:
        if int(meta.get("ref") or -1) == ref:
            return {**meta, "kind": kind, "trashed": trashed}
        owner_id = str(meta.get("id") or "")
        for anim_id, anim in (meta.get("animations") or {}).items():
            if isinstance(anim, dict) and int(anim.get("ref") or -1) == ref:
                return {
                    **anim,
                    "kind": "animation",
                    "parent_kind": kind,
                    "parent_id": owner_id,
                    "parent_ref": meta.get("ref"),
                    "animation_id": anim_id,
                    "trashed": trashed,
                }
        if include_trash or trashed:
            for anim_id, anim in ((meta.get("trash") or {}).get("animations") or {}).items():
                if isinstance(anim, dict) and int(anim.get("ref") or -1) == ref:
                    return {
                        **anim,
                        "kind": "animation",
                        "parent_kind": kind,
                        "parent_id": owner_id,
                        "parent_ref": meta.get("ref"),
                        "animation_id": anim_id,
                        "trashed": True,
                    }
        for row in meta.get("standing_versions") or []:
            if isinstance(row, dict) and int(row.get("ref") or -1) == ref:
                return {
                    **row,
                    "kind": "standing",
                    "parent_kind": kind,
                    "parent_id": owner_id,
                    "parent_ref": meta.get("ref"),
                    "trashed": trashed,
                }
        for row in meta.get("art_versions") or []:
            if isinstance(row, dict) and int(row.get("ref") or -1) == ref:
                return {
                    **row,
                    "kind": "art",
                    "parent_kind": kind,
                    "parent_id": owner_id,
                    "parent_ref": meta.get("ref"),
                    "trashed": trashed,
                }
        return None

    for meta in storage.list_characters(None):
        hit = _scan_meta(meta, kind="character")
        if hit:
            return hit
    for meta in item_storage.list_items(None):
        hit = _scan_meta(meta, kind="item")
        if hit:
            return hit
    if not include_trash:
        return None
    for row in storage.list_trashed_characters(None):
        try:
            meta = storage.load_meta(row["id"])
        except FileNotFoundError:
            continue
        hit = _scan_meta(meta, kind="character", trashed=True)
        if hit:
            return hit
    for row in item_storage.list_trashed_items(None):
        try:
            meta = item_storage.load_meta(row["id"])
        except FileNotFoundError:
            continue
        hit = _scan_meta(meta, kind="item", trashed=True)
        if hit:
            return hit
    return None
