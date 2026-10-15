"""Unique animation display / export names (idle, idle2, idle3, …)."""

from __future__ import annotations

from typing import Any


def sanitize_anim_name(raw: str) -> str:
    s = (raw or "").strip().lower().replace(" ", "_")
    s = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_") or "anim"


def existing_anim_names(meta: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for anim in (meta.get("animations") or {}).values():
        n = sanitize_anim_name(str(anim.get("name") or anim.get("type") or ""))
        if n:
            out.add(n)
    return out


def next_animation_name(meta: dict[str, Any], base: str) -> str:
    """First free name: base, then base2, base3, …"""
    root = sanitize_anim_name(base)
    taken = existing_anim_names(meta)
    if root not in taken:
        return root
    i = 2
    while f"{root}{i}" in taken:
        i += 1
    return f"{root}{i}"


def resolve_animation_name(meta: dict[str, Any], base: str, requested: str | None = None) -> str:
    """Use requested name if free; otherwise bump like next_animation_name."""
    want = sanitize_anim_name(requested) if (requested or "").strip() else sanitize_anim_name(base)
    taken = existing_anim_names(meta)
    if want not in taken:
        return want
    # If user asked for a taken name, fall back to numbered sequence from that base
    root = want.rstrip("0123456789") or want
    if root not in taken:
        return root
    i = 2
    while f"{root}{i}" in taken:
        i += 1
    return f"{root}{i}"
