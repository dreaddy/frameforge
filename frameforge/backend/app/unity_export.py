from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from .frame_pipeline import pack_sheet


def build_unity_export(
    character_name: str,
    pixel_size: int,
    animations: list[dict[str, Any]],
    out_dir: Path,
    pixels_per_unit: int = 100,
) -> dict[str, Any]:
    """
    animations: [{
      "name": "walk_side",
      "fps": 8,
      "loop": True,
      "frames": [Path, ...]  # selected variant frames
    }]
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    all_images: list[Image.Image] = []
    anim_meta: list[dict[str, Any]] = []
    cursor = 0
    for anim in animations:
        frames = [Image.open(p).convert("RGBA") for p in anim["frames"]]
        if not frames:
            continue
        indices = list(range(cursor, cursor + len(frames)))
        all_images.extend(frames)
        anim_meta.append(
            {
                "name": anim["name"],
                "frameIndices": indices,
                "fps": int(anim.get("fps") or 8),
                "loop": bool(anim.get("loop", True)),
            }
        )
        cursor += len(frames)

    if not all_images:
        raise ValueError("No animation frames selected for export")

    columns = max(1, min(8, len(all_images)))
    sheet = pack_sheet(all_images, columns=columns)
    stem = _safe_name(character_name)
    png_path = out_dir / f"{stem}_sheet.png"
    json_path = out_dir / f"{stem}_sheet.json"
    sheet.save(png_path)
    meta = {
        "name": stem,
        "cellWidth": pixel_size,
        "cellHeight": pixel_size,
        "columns": columns,
        "rows": (len(all_images) + columns - 1) // columns,
        "frameCount": len(all_images),
        "pixelsPerUnit": pixels_per_unit,
        "animations": anim_meta,
    }
    json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    readme = out_dir / "README_unity.txt"
    readme.write_text(
        "\n".join(
            [
                "Unity Frameforge export",
                "1. Copy *_sheet.png + *_sheet.json into Assets/Creatures/spritesheets/<name>/",
                "2. Ensure Editor scripts from frameforge/unity/Editor/ are in the project",
                "   (MCP install_to_unity copies them automatically).",
                "3. Unity auto-imports on refresh, or: select PNG → Assets → Frameforge → Import Selected Sheet.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    zip_path = out_dir / f"{stem}_unity.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(png_path, png_path.name)
        zf.write(json_path, json_path.name)
        zf.write(readme, readme.name)
    return {
        "stem": stem,
        "zip_path": zip_path.resolve(),
        "png_path": png_path.resolve(),
        "json_path": json_path.resolve(),
        "animations": anim_meta,
        "frame_count": len(all_images),
        "pixel_size": pixel_size,
    }


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name.strip())
    return cleaned or "Creature"
