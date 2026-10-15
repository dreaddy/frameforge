"""Project color palettes — presets, normalization, remap, prompt hints."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
from PIL import Image

# (r, g, b) tuples
Rgb = tuple[int, int, int]

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


PALETTE_PRESETS: dict[str, dict[str, Any]] = {
    "none": {
        "id": "none",
        "label": "None (unrestricted)",
        "blurb": "No palette limit — full color",
        "colors": [],
    },
    "gameboy": {
        "id": "gameboy",
        "label": "Game Boy",
        "blurb": "Classic 4-shade green",
        "colors": ["#0f380f", "#306230", "#8bac0f", "#9bbc0f"],
    },
    "pico8": {
        "id": "pico8",
        "label": "PICO-8",
        "blurb": "Fantasy console 16 colors",
        "colors": [
            "#000000",
            "#1d2b53",
            "#7e2553",
            "#008751",
            "#ab5236",
            "#5f574f",
            "#c2c3c7",
            "#fff1e8",
            "#ff004d",
            "#ffa300",
            "#ffec27",
            "#00e436",
            "#29adff",
            "#83769c",
            "#ff77a8",
            "#ffccaa",
        ],
    },
    "sweetie16": {
        "id": "sweetie16",
        "label": "Sweetie 16",
        "blurb": "Soft readable 16-color set",
        "colors": [
            "#1a1c2c",
            "#5d275d",
            "#b13e53",
            "#ef7d57",
            "#ffcd75",
            "#a7f070",
            "#38b764",
            "#257179",
            "#29366f",
            "#3b5dc9",
            "#41a6f6",
            "#73eff7",
            "#f4f4f4",
            "#94b0c2",
            "#566c86",
            "#333c57",
        ],
    },
    "endesga32": {
        "id": "endesga32",
        "label": "Endesga 32",
        "blurb": "Popular pixel-art 32-color set",
        "colors": [
            "#be4a2f",
            "#d77643",
            "#ead4aa",
            "#e4a672",
            "#b86f50",
            "#733e39",
            "#3e2731",
            "#a22633",
            "#e43b44",
            "#f77622",
            "#feae34",
            "#fee761",
            "#63c74d",
            "#3e8948",
            "#265c42",
            "#193c3e",
            "#124e89",
            "#0099db",
            "#2ce8f5",
            "#ffffff",
            "#c0cbdc",
            "#8b9bb4",
            "#5a6988",
            "#3a4466",
            "#262b44",
            "#181425",
            "#ff0044",
            "#68386c",
            "#b55088",
            "#f6757a",
            "#e8b796",
            "#c28569",
        ],
    },
    "mono": {
        "id": "mono",
        "label": "Mono 4",
        "blurb": "Black / dark / light / white",
        "colors": ["#1a1a1a", "#555555", "#aaaaaa", "#f5f5f5"],
    },
    "ember": {
        "id": "ember",
        "label": "Ember / fire",
        "blurb": "Warm fire + ash accents",
        "colors": [
            "#1a1010",
            "#3d1f1a",
            "#6b2d1f",
            "#a84828",
            "#e07030",
            "#f0a040",
            "#ffe080",
            "#fff8e0",
            "#4a5560",
            "#8a9aa8",
            "#d0d8e0",
            "#2a1820",
        ],
    },
}


def list_palette_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "blurb": p["blurb"],
            "colors": list(p["colors"]),
        }
        for p in PALETTE_PRESETS.values()
    ]


def parse_hex(value: str) -> Rgb | None:
    m = _HEX_RE.match((value or "").strip())
    if not m:
        return None
    h = m.group(1)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def to_hex(rgb: Rgb) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def normalize_palette(colors: list[str] | None, *, max_colors: int = 64) -> list[str]:
    """Dedupe + validate hex list; returns canonical lowercase #rrggbb."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in colors or []:
        rgb = parse_hex(str(raw))
        if not rgb:
            continue
        hx = to_hex(rgb)
        if hx in seen:
            continue
        seen.add(hx)
        out.append(hx)
        if len(out) >= max_colors:
            break
    return out


def resolve_palette(
    *,
    preset_id: str | None = None,
    colors: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Return (preset_id, hex colors). Empty colors ⇒ unrestricted."""
    pid = (preset_id or "").strip().lower() or "none"
    custom = normalize_palette(colors)
    if custom:
        # If custom matches a preset exactly, keep that id; else custom
        for p in PALETTE_PRESETS.values():
            if normalize_palette(p["colors"]) == custom:
                return str(p["id"]), custom
        return "custom", custom
    if pid in PALETTE_PRESETS and pid != "none":
        cols = normalize_palette(PALETTE_PRESETS[pid]["colors"])
        return pid, cols
    return "none", []


def palette_rgbs(colors: list[str]) -> list[Rgb]:
    out: list[Rgb] = []
    for c in normalize_palette(colors):
        rgb = parse_hex(c)
        if rgb:
            out.append(rgb)
    return out


def prompt_clause(colors: list[str] | None) -> str:
    cols = normalize_palette(colors)
    if not cols:
        return ""
    joined = ", ".join(cols)
    return (
        f"strict limited color palette using ONLY these hex colors: {joined} "
        "(no other hues, flat shading bands within this set)"
    )


def map_image_to_palette(img: Image.Image, colors: list[str], *, dither: bool = False) -> Image.Image:
    """Snap opaque pixels to nearest palette color. Transparent stays transparent."""
    rgbs = palette_rgbs(colors)
    if not rgbs:
        return img.convert("RGBA")
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba).copy()
    alpha = arr[..., 3]
    keep = alpha >= 128
    if int(keep.sum()) == 0:
        return Image.fromarray(arr, "RGBA")

    palette_arr = np.asarray(rgbs, dtype=np.float32)  # (N, 3)
    pix = arr[keep, :3].astype(np.float32)  # (M, 3)
    # Squared Euclidean distance to each palette entry
    # (M, 1, 3) - (1, N, 3) → (M, N)
    diff = pix[:, None, :] - palette_arr[None, :, :]
    dist = np.sum(diff * diff, axis=2)
    idx = np.argmin(dist, axis=1)
    mapped = palette_arr[idx].astype(np.uint8)
    arr[keep, :3] = mapped
    arr[~keep] = 0
    arr[..., 3] = np.where(keep, 255, 0).astype(np.uint8)

    if dither:
        # Optional: pillow dither via temporary palette image — skip by default for crisp sprites
        pass
    return Image.fromarray(arr, "RGBA")


def write_base_preview(base_png: Image.Image, dest_preview) -> None:
    preview = Image.new("RGBA", base_png.size, (40, 40, 48, 255))
    preview.alpha_composite(base_png.convert("RGBA"))
    preview.convert("RGB").save(dest_preview)


# Chroma-key / matte greens commonly used in sprite pipelines — not palette colors.
_CHROMA_SKIP: set[Rgb] = {
    (0, 255, 0),
    (0, 254, 0),
    (1, 255, 0),
    (0, 255, 1),
}


def _luma(rgb: Rgb) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _dist2(a: Rgb, b: Rgb) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _nearest(rgb: Rgb, candidates: list[Rgb]) -> tuple[Rgb, int]:
    best = candidates[0]
    best_d = _dist2(rgb, best)
    for c in candidates[1:]:
        d = _dist2(rgb, c)
        if d < best_d:
            best = c
            best_d = d
    return best, best_d


def _merge_close(rgbs: list[Rgb], *, max_dist: int = 18) -> list[Rgb]:
    """Greedy average-merge of colors within Euclidean distance."""
    if not rgbs:
        return []
    # Frequent / earlier colors win as anchors
    clusters: list[list[float]] = []  # [r,g,b,n]
    max_d2 = max_dist * max_dist
    for rgb in rgbs:
        placed = False
        for cl in clusters:
            cr = (int(round(cl[0])), int(round(cl[1])), int(round(cl[2])))
            if _dist2(rgb, cr) <= max_d2:
                n = cl[3]
                cl[0] = (cl[0] * n + rgb[0]) / (n + 1)
                cl[1] = (cl[1] * n + rgb[1]) / (n + 1)
                cl[2] = (cl[2] * n + rgb[2]) / (n + 1)
                cl[3] = n + 1
                placed = True
                break
        if not placed:
            clusters.append([float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0])
    out: list[Rgb] = []
    for cl in clusters:
        out.append(
            (
                int(max(0, min(255, round(cl[0])))),
                int(max(0, min(255, round(cl[1])))),
                int(max(0, min(255, round(cl[2])))),
            )
        )
    return out


def extract_colors_from_image(
    img: Image.Image,
    *,
    max_colors: int = 48,
    merge_dist: int = 14,
) -> list[str]:
    """Unique opaque colors from an image (pixel-art friendly, merges near-dupes)."""
    rgba = img.convert("RGBA")
    # Downscale huge photos so histogram stays cheap
    w, h = rgba.size
    if max(w, h) > 512:
        scale = 512 / max(w, h)
        rgba = rgba.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.NEAREST if max(w, h) <= 1024 else Image.Resampling.BILINEAR,
        )
    arr = np.asarray(rgba)
    alpha = arr[..., 3]
    keep = alpha >= 128
    if int(keep.sum()) == 0:
        return []
    pix = arr[keep, :3].astype(np.uint8)
    # Frequency map
    flat = pix[:, 0].astype(np.uint32) << 16 | pix[:, 1].astype(np.uint32) << 8 | pix[:, 2].astype(
        np.uint32
    )
    uniq, counts = np.unique(flat, return_counts=True)
    order = np.argsort(-counts)
    rgbs: list[Rgb] = []
    for idx in order:
        packed = int(uniq[idx])
        rgb = ((packed >> 16) & 255, (packed >> 8) & 255, packed & 255)
        if rgb in _CHROMA_SKIP:
            continue
        # Skip near-pure chroma green (sprite key)
        if rgb[1] >= 240 and rgb[0] <= 40 and rgb[2] <= 40:
            continue
        rgbs.append(rgb)
        if len(rgbs) >= max_colors * 3:
            break
    # rgbs are already frequency-sorted; merge keeps first-seen anchors
    merged = _merge_close(rgbs, max_dist=merge_dist)
    if len(merged) > max_colors:
        merged = merged[:max_colors]
    return [to_hex(c) for c in merged]


def extract_colors_from_images(images: list[Image.Image], *, max_colors: int = 48) -> list[str]:
    seed: list[str] = []
    for im in images:
        seed = merge_seed_colors(seed, extract_colors_from_image(im, max_colors=max_colors))
    return seed[:max_colors]


def merge_seed_colors(*groups: list[str] | None, max_colors: int = 64) -> list[str]:
    return normalize_palette(
        [c for g in groups for c in (g or [])],
        max_colors=max_colors,
    )


def match_known_palette(
    seed_colors: list[str],
    *,
    max_dist: int = 28,
) -> dict[str, Any] | None:
    """If seed colors fit a known preset, return best match info."""
    seeds = palette_rgbs(seed_colors)
    if not seeds:
        return None
    max_d2 = max_dist * max_dist
    best: dict[str, Any] | None = None
    for preset in PALETTE_PRESETS.values():
        pid = str(preset["id"])
        if pid == "none" or not preset["colors"]:
            continue
        preset_rgbs = palette_rgbs(list(preset["colors"]))
        if not preset_rgbs:
            continue
        mapped = 0
        for s in seeds:
            _near, d2 = _nearest(s, preset_rgbs)
            if d2 <= max_d2:
                mapped += 1
        if mapped < len(seeds):
            continue  # every seed must land in the preset
        # How much of the preset is covered by seeds (approx)
        covered = 0
        for p in preset_rgbs:
            _near, d2 = _nearest(p, seeds)
            if d2 <= max_d2:
                covered += 1
        coverage = covered / len(preset_rgbs)
        seed_fit = mapped / len(seeds)
        # Prefer exact-ish subset of smaller palettes when coverage is solid
        score = seed_fit * 0.55 + coverage * 0.45
        # Bonus when seed count is close to preset size
        ratio = min(len(seeds), len(preset_rgbs)) / max(len(seeds), len(preset_rgbs))
        score += 0.15 * ratio
        if best is None or score > float(best["score"]):
            best = {
                "id": pid,
                "label": preset["label"],
                "score": round(score, 4),
                "coverage": round(coverage, 4),
                "colors": normalize_palette(list(preset["colors"])),
            }
    if best is None:
        return None
    # Require a minimum score so random 2 colors don't "match" endesga32
    if float(best["score"]) < 0.42 and float(best["coverage"]) < 0.35:
        return None
    # Tiny seeds need high coverage of a small preset (e.g. gameboy 4)
    if len(seeds) <= 3 and float(best["coverage"]) < 0.5:
        return None
    return best


def _lerp_rgb(a: Rgb, b: Rgb, t: float) -> Rgb:
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def supplement_palette(
    seed_colors: list[str],
    *,
    matched: dict[str, Any] | None = None,
    target_size: int | None = None,
) -> list[str]:
    """Keep fixed seed colors; fill gaps from a matched preset or by ramps."""
    seeds = normalize_palette(seed_colors)
    if not seeds:
        return []
    if matched and matched.get("colors"):
        # Fixed seeds first, then remaining preset colors
        return normalize_palette(list(seeds) + list(matched["colors"]), max_colors=64)

    seed_rgbs = palette_rgbs(seeds)
    target = target_size or min(32, max(16, len(seed_rgbs) + max(4, len(seed_rgbs) // 2)))
    if len(seed_rgbs) >= target:
        return seeds

    ordered = sorted(seed_rgbs, key=_luma)
    filled: list[Rgb] = list(ordered)
    # Anchor extremes if missing
    if _luma(ordered[0]) > 40:
        filled.insert(0, (12, 12, 16))
    if _luma(ordered[-1]) < 220:
        filled.append((245, 245, 240))

    # Insert midpoints where luminance jumps are large
    guard = 0
    while len(filled) < target and guard < 64:
        guard += 1
        filled = sorted(filled, key=_luma)
        # Find largest luma gap
        best_i = 0
        best_gap = -1.0
        for i in range(len(filled) - 1):
            gap = _luma(filled[i + 1]) - _luma(filled[i])
            # Also prefer chromatic distance
            gap += 0.05 * (_dist2(filled[i], filled[i + 1]) ** 0.5)
            if gap > best_gap:
                best_gap = gap
                best_i = i
        if best_gap < 12:
            break
        mid = _lerp_rgb(filled[best_i], filled[best_i + 1], 0.5)
        # Avoid near-dupes
        _n, d2 = _nearest(mid, filled)
        if d2 < 10 * 10:
            break
        filled.insert(best_i + 1, mid)

    return normalize_palette([to_hex(c) for c in filled] + seeds, max_colors=64)


def build_palette_from_seeds(seed_colors: list[str]) -> dict[str, Any]:
    """Match known presets if possible, otherwise supplement ramps."""
    seed = normalize_palette(seed_colors)
    matched = match_known_palette(seed)
    colors = supplement_palette(seed, matched=matched)
    preset_id = str(matched["id"]) if matched else ("custom" if colors else "none")
    return {
        "seed": seed,
        "colors": colors,
        "palette_preset": preset_id,
        "matched_preset": matched,
        "filled_count": max(0, len(colors) - len(seed)),
    }


def build_palette_from_images(
    images: list[Image.Image],
    *,
    existing_seed: list[str] | None = None,
) -> dict[str, Any]:
    extracted = extract_colors_from_images(images)
    seed = merge_seed_colors(existing_seed, extracted)
    result = build_palette_from_seeds(seed)
    result["extracted"] = extracted
    result["image_count"] = len(images)
    return result
