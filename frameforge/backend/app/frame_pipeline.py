from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .config import FFMPEG_CANDIDATES
from .palettes import map_image_to_palette, write_base_preview

# Bright green chroma — works with white bodies + orange/red fire (magenta does not)
KEY_RGB = (0, 255, 0)


@lru_cache(maxsize=1)
def resolve_ffmpeg() -> str | None:
    for candidate in FFMPEG_CANDIDATES:
        if candidate and candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


def remove_background(img: Image.Image) -> Image.Image:
    """Hard green-screen key + despill so no chroma fringe survives nearest downscale."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba).astype(np.float32)
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]

    # Green dominance + distance to pure #00FF00
    green_score = g - np.maximum(r, b)
    chroma_dist = np.sqrt((r - KEY_RGB[0]) ** 2 + (g - KEY_RGB[1]) ** 2 + (b - KEY_RGB[2]) ** 2)
    is_key = ((green_score > 40) & (g > 120) & (r < 180) & (b < 180)) | (chroma_dist < 110)

    # Legacy magenta leftovers from older gens
    magenta_score = (r + b) / 2.0 - g
    is_magenta = (magenta_score > 45) & (g < 130) & (r > 100) & (b > 100)

    alpha = np.where(is_key | is_magenta, 0.0, a)

    if int((alpha > 10).sum()) > 0.92 * alpha.size:
        samples = np.concatenate(
            [
                arr[0:10, 0:10].reshape(-1, 4),
                arr[0:10, -10:].reshape(-1, 4),
                arr[-10:, 0:10].reshape(-1, 4),
                arr[-10:, -10:].reshape(-1, 4),
            ],
            0,
        )
        bg = np.median(samples, axis=0)[:3]
        diff = np.linalg.norm(arr[..., :3] - bg, axis=-1)
        alpha = np.where(diff < 42, 0.0, a)

    alpha = np.where(alpha >= 128, 255.0, 0.0)

    out = arr.copy()
    out[..., 3] = alpha
    opaque = alpha > 0

    # Green despill: pull excess G toward max(R,B)
    spill_g = opaque & (green_score > 8) & (g > np.maximum(r, b))
    if np.any(spill_g):
        target = np.maximum(r[spill_g], b[spill_g])
        out[..., 1][spill_g] = np.clip(target + (g[spill_g] - target) * 0.15, 0, 255)

    # Magenta/pink despill on whites (residual AA)
    spill_m = opaque & (magenta_score > 8) & (g < 210)
    if np.any(spill_m):
        corr = np.minimum(r[spill_m], b[spill_m]) - g[spill_m]
        corr = np.clip(corr, 0, None)
        out[..., 0][spill_m] = np.clip(r[spill_m] - corr * 1.1, 0, 255)
        out[..., 2][spill_m] = np.clip(b[spill_m] - corr * 1.1, 0, 255)

    out[..., 0][~opaque] = 0
    out[..., 1][~opaque] = 0
    out[..., 2][~opaque] = 0
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def crop_and_pad_square(img: Image.Image, pad: int = 8, bottom_extra: int = 0) -> Image.Image:
    bbox = img.getbbox()
    if not bbox:
        return img
    x0 = max(0, bbox[0] - pad)
    y0 = max(0, bbox[1] - pad)
    x1 = min(img.width, bbox[2] + pad)
    y1 = min(img.height, bbox[3] + pad + bottom_extra)
    cropped = img.crop((x0, y0, x1, y1))
    side = max(cropped.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    # Bias slightly upward so drop shadows have room at the bottom
    ox = (side - cropped.width) // 2
    oy = max(0, (side - cropped.height) // 2 - bottom_extra // 2)
    canvas.paste(cropped, (ox, oy), cropped)
    return canvas


def add_drop_shadow(img: Image.Image, pixel_mode: bool = True) -> Image.Image:
    """Simple grounded oval shadow under the sprite (optional)."""
    bbox = img.getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    w = x1 - x0
    h = y1 - y0
    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)

    cx = (x0 + x1) / 2
    # Sit just under the feet
    cy = y1 - max(1, int(h * 0.04))
    rw = max(4, int(w * 0.42))
    rh = max(2, int(h * 0.07))
    ellipse = [cx - rw, cy - rh, cx + rw, cy + rh]
    # Fully opaque dark pixels for pixel mode (survives any later alpha harden)
    if pixel_mode:
        draw.ellipse(ellipse, fill=(18, 18, 22, 255))
    else:
        draw.ellipse(ellipse, fill=(0, 0, 0, 100))
        if min(img.size) >= 64:
            from PIL import ImageFilter

            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, img.width // 48)))

    canvas = Image.alpha_composite(canvas, shadow)
    canvas = Image.alpha_composite(canvas, img)
    return canvas


def to_export_size(img: Image.Image, size: int, resize: str = "nearest") -> Image.Image:
    mode = Image.Resampling.NEAREST if resize == "nearest" else Image.Resampling.LANCZOS
    out = img.resize((size, size), mode)
    if resize == "nearest":
        arr = np.asarray(out.convert("RGBA")).copy()
        alpha = arr[..., 3]
        keep = alpha >= 128
        arr[..., 3] = np.where(keep, 255, 0).astype(np.uint8)
        for c in range(3):
            arr[..., c] = np.where(keep, arr[..., c], 0)
        out = Image.fromarray(arr, "RGBA")
        out = _quantize_opaque(out, max_colors=48)
    return out


def _quantize_opaque(img: Image.Image, max_colors: int = 48) -> Image.Image:
    """Tighten muddy AA colors while preserving hard alpha."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    alpha = arr[..., 3]
    keep = alpha >= 128
    if int(keep.sum()) < 8:
        return img
    rgb = Image.fromarray(arr[..., :3], "RGB")
    # Quantize only opaque region via mask trick: paste on unique key then restore
    quant = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    qrgb = np.asarray(quant.convert("RGB"))
    out = arr.copy()
    out[keep, :3] = qrgb[keep]
    out[~keep] = 0
    out[..., 3] = np.where(keep, 255, 0).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def to_pixel_size(img: Image.Image, size: int) -> Image.Image:
    return to_export_size(img, size, "nearest")


def add_pixel_outline(
    img: Image.Image,
    color: tuple[int, int, int, int] = (22, 22, 28, 255),
    thickness: int = 1,
) -> Image.Image:
    """1px (or N) hard dark outline around opaque pixels — classic outlined pixel style."""
    thickness = max(1, int(thickness))
    pad = thickness
    base = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    base.paste(img.convert("RGBA"), (pad, pad), img.convert("RGBA"))
    arr = np.asarray(base).copy()
    opaque = arr[..., 3] >= 128
    dil = opaque.copy()
    h, w = opaque.shape
    for dy in range(-thickness, thickness + 1):
        for dx in range(-thickness, thickness + 1):
            if dx == 0 and dy == 0:
                continue
            # Chebyshev neighborhood (8-connected at thickness 1)
            if max(abs(dx), abs(dy)) > thickness:
                continue
            ys = slice(max(0, dy), h + min(0, dy))
            xs = slice(max(0, dx), w + min(0, dx))
            yd = slice(max(0, -dy), h + min(0, -dy))
            xd = slice(max(0, -dx), w + min(0, -dx))
            dil[yd, xd] = dil[yd, xd] | opaque[ys, xs]
    ring = dil & ~opaque
    arr[ring, 0] = color[0]
    arr[ring, 1] = color[1]
    arr[ring, 2] = color[2]
    arr[ring, 3] = color[3]
    return Image.fromarray(arr, "RGBA")


def fit_canvas_without_scaling(img: Image.Image, size: int) -> Image.Image:
    """Center-pad/crop canvas only; reject cropping visible subject pixels."""
    img = img.convert("RGBA")
    left, top = (img.width - size) // 2, (img.height - size) // 2
    bbox = img.getbbox()
    if bbox and (bbox[0] < max(0, left) or bbox[1] < max(0, top)
                 or bbox[2] > min(img.width, left + size)
                 or bbox[3] > min(img.height, top + size)):
        raise ValueError("Subject does not fit requested canvas without scaling or clipping")
    return img.crop((left, top, left + size, top + size))


def process_character_image(
    src: Path,
    dest: Path,
    pixel_size: int,
    resize: str = "nearest",
    drop_shadow: bool = False,
    outline: bool = False,
    *,
    key_background: bool = True,
    auto_crop: bool = True,
    no_scale: bool = False,
) -> Path:
    img = Image.open(src).convert("RGBA")
    if key_background:
        img = remove_background(img)
    if no_scale:
        if auto_crop or outline or drop_shadow:
            raise ValueError("no_scale requires auto_crop=false, outline=false, drop_shadow=false")
        img = fit_canvas_without_scaling(img, pixel_size)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest)
        if dest.name == "base.png":
            write_base_preview(img, dest.with_name("base_preview.png"))
        return dest
    # Leave bottom room before downscale so a final-res shadow fits
    bottom_extra = 48 if drop_shadow else 0
    edge_pad = 10 if outline else 8
    if auto_crop:
        img = crop_and_pad_square(img, pad=edge_pad, bottom_extra=bottom_extra)
    elif img.width != img.height:
        # Manual crop should already be square; pad if not
        img = crop_and_pad_square(img, pad=0, bottom_extra=bottom_extra)
    elif bottom_extra:
        canvas = Image.new("RGBA", (img.width, img.height + bottom_extra), (0, 0, 0, 0))
        canvas.paste(img, (0, 0), img)
        side = max(canvas.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        ox = (side - canvas.width) // 2
        oy = max(0, (side - canvas.height) // 2 - bottom_extra // 2)
        square.paste(canvas, (ox, oy), canvas)
        img = square
    # Leave 1px per side so outline lands on the final canvas size
    body_size = max(4, pixel_size - 2) if outline else pixel_size
    img = to_export_size(img, body_size, resize)
    if outline:
        img = add_pixel_outline(img, thickness=1)
        if img.size != (pixel_size, pixel_size):
            canvas = Image.new("RGBA", (pixel_size, pixel_size), (0, 0, 0, 0))
            ox = (pixel_size - img.width) // 2
            oy = (pixel_size - img.height) // 2
            canvas.paste(img, (max(0, ox), max(0, oy)), img)
            img = canvas
    # Shadow AFTER hard-alpha resize — semi-transparent pixels were being wiped
    if drop_shadow:
        img = add_drop_shadow(img, pixel_mode=(resize == "nearest"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    # Companion RGB preview only for the character base — never overwrite it when
    # processing standing / other assets that happen to live in the same folder.
    if dest.name == "base.png":
        write_base_preview(img, dest.with_name("base_preview.png"))
    return dest


def apply_palette_to_png(path: Path, colors: list[str]) -> bool:
    """Remap an existing PNG onto the project palette. Returns True if rewritten."""
    if not path.is_file() or not colors:
        return False
    img = Image.open(path).convert("RGBA")
    mapped = map_image_to_palette(img, colors)
    mapped.save(path)
    return True


def apply_palette_to_asset_dir(
    root: Path,
    colors: list[str],
    *,
    include_animations: bool = True,
) -> dict[str, int]:
    """Remap base (+ preview/chroma) and optionally animation/standing frames."""
    counts = {"base": 0, "frames": 0, "standing": 0}
    if not colors:
        return counts
    base = root / "base.png"
    if apply_palette_to_png(base, colors):
        counts["base"] += 1
        write_base_preview(Image.open(base).convert("RGBA"), root / "base_preview.png")
        chroma = root / "base_i2v.png"
        if chroma.is_file():
            try:
                write_chroma_composite(base, chroma)
            except Exception:
                apply_palette_to_png(chroma, colors)
    if include_animations:
        anims = root / "anims"
        if anims.is_dir():
            for frame in anims.rglob("frame_*.png"):
                if apply_palette_to_png(frame, colors):
                    counts["frames"] += 1
        standing = root / "standing"
        if standing.is_dir():
            for png in standing.rglob("*.png"):
                if apply_palette_to_png(png, colors):
                    counts["standing"] += 1
        # Flat standing previews next to base
        for name in ("standing_preview.png", "standing.png", "standing_i2v.png"):
            p = root / name
            if p.is_file() and apply_palette_to_png(p, colors):
                counts["standing"] += 1
    return counts


def extract_video_frames(video_path: Path, out_dir: Path, frame_count: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.png"):
        old.unlink()
    ffmpeg = resolve_ffmpeg()
    if ffmpeg:
        pattern = str(out_dir / "raw_%04d.png")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"fps={max(frame_count, 1)}/1",
                pattern,
            ],
            capture_output=True,
            check=False,
        )
        raws = sorted(out_dir.glob("raw_*.png"))
        if not raws:
            subprocess.run(
                [ffmpeg, "-y", "-i", str(video_path), str(out_dir / "raw_%04d.png")],
                capture_output=True,
                check=False,
            )
            raws = sorted(out_dir.glob("raw_*.png"))
    else:
        raws = _extract_with_pillow(video_path, out_dir)

    if not raws:
        raise RuntimeError(f"Could not extract frames from {video_path} (is ffmpeg installed?)")

    indices = _sample_indices(len(raws), frame_count)
    frames: list[Path] = []
    for i, idx in enumerate(indices):
        dest = out_dir / f"frame_{i:02d}.png"
        shutil.copy2(raws[idx], dest)
        frames.append(dest)
    for raw in out_dir.glob("raw_*.png"):
        raw.unlink(missing_ok=True)
    return frames


def _extract_with_pillow(video_path: Path, out_dir: Path) -> list[Path]:
    try:
        import imageio.v3 as iio  # type: ignore
    except Exception:
        return []
    try:
        meta = iio.improps(video_path)
        n = int(getattr(meta, "n_images", 0) or 0)
    except Exception:
        n = 0
    paths: list[Path] = []
    try:
        for i, frame in enumerate(iio.imiter(video_path)):
            p = out_dir / f"raw_{i:04d}.png"
            Image.fromarray(frame).save(p)
            paths.append(p)
            if n and i >= n:
                break
            if i > 200:
                break
    except Exception:
        return paths
    return paths


def _sample_indices(total: int, want: int) -> list[int]:
    if total <= 0:
        return []
    if want >= total:
        return list(range(total))
    if want == 1:
        return [0]
    return [round(i * (total - 1) / (want - 1)) for i in range(want)]


def process_animation_frames(
    frame_paths: list[Path],
    out_dir: Path,
    pixel_size: int,
    resize: str = "nearest",
    drop_shadow: bool = False,
    outline: bool = False,
    preserve_canvas: bool = False,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for i, src in enumerate(frame_paths):
        img = Image.open(src)
        img = remove_background(img)
        if preserve_canvas:
            if img.size != (pixel_size, pixel_size):
                raise ValueError(f"Video frame {img.size} differs from no-scale export {(pixel_size, pixel_size)}")
            dest = out_dir / f"frame_{i:02d}.png"
            img.save(dest)
            result.append(dest)
            continue
        bottom_extra = 32 if drop_shadow else 0
        edge_pad = 10 if outline else 8
        img = crop_and_pad_square(img, pad=edge_pad, bottom_extra=bottom_extra)
        body_size = max(4, pixel_size - 2) if outline else pixel_size
        img = to_export_size(img, body_size, resize)
        if outline:
            img = add_pixel_outline(img, thickness=1)
            if img.size != (pixel_size, pixel_size):
                canvas = Image.new("RGBA", (pixel_size, pixel_size), (0, 0, 0, 0))
                ox = (pixel_size - img.width) // 2
                oy = (pixel_size - img.height) // 2
                canvas.paste(img, (max(0, ox), max(0, oy)), img)
                img = canvas
        if drop_shadow:
            img = add_drop_shadow(img, pixel_mode=(resize == "nearest"))
        dest = out_dir / f"frame_{i:02d}.png"
        img.save(dest)
        result.append(dest)
    return result


def pack_sheet(frames: list[Image.Image], columns: int | None = None) -> Image.Image:
    if not frames:
        raise ValueError("No frames to pack")
    cell_w, cell_h = frames[0].size
    columns = columns or max(1, int(len(frames) ** 0.5 + 0.999))
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), (0, 0, 0, 0))
    for i, fr in enumerate(frames):
        x = (i % columns) * cell_w
        y = (i // columns) * cell_h
        sheet.paste(fr.convert("RGBA"), (x, y), fr.convert("RGBA"))
    return sheet


def copy_or_resize_preview(src: Path, dest: Path, max_side: int = 768) -> Path:
    """Save an art still preview without sprite crunching (keeps soft detail)."""
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side and longest > 0:
        scale = max_side / float(longest)
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def soften_reference_for_restyle(
    src: Path,
    dest: Path,
    side: int = 1024,
    blur_radius: float = 2.2,
    fill_rgb: tuple[int, int, int] = (48, 46, 44),
    noise_amp: int = 12,
) -> Path:
    """Key out chroma green, flatten on an environment-tinted fill, soften for art restyle."""
    from PIL import ImageFilter

    img = Image.open(src).convert("RGBA")
    # Sprite pipeline bakes #00FF00 into base_raw — never feed that green into art img2img.
    keyed = remove_background(img)
    if keyed.getbbox() is None:
        keyed = img
    keyed = crop_and_pad_square(keyed, pad=10)
    fill = tuple(int(max(0, min(255, c))) for c in fill_rgb)
    bg = Image.new("RGBA", keyed.size, (*fill, 255))
    bg.alpha_composite(keyed)
    rgb = bg.convert("RGB")
    side = max(64, int(side))
    rgb = rgb.resize((side, side), Image.Resampling.LANCZOS)
    # Noise + soft vertical gradient so the fill does not read as a solid plate to keep.
    arr = np.asarray(rgb).astype(np.float32)
    amp = max(4, min(28, int(noise_amp)))
    noise = np.random.randint(-amp, amp + 1, size=arr.shape).astype(np.float32)
    h = arr.shape[0]
    # Slight top→bottom lift (sky-ish) so daylight scenes are not floor-dark.
    ramp = np.linspace(14.0, -10.0, h, dtype=np.float32).reshape(h, 1, 1)
    arr = np.clip(arr + noise + ramp, 0, 255)
    rgb = Image.fromarray(arr.astype(np.uint8), "RGB")
    radius = max(0.5, float(blur_radius))
    rgb = rgb.filter(ImageFilter.GaussianBlur(radius=radius))
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(dest)
    return dest


def write_chroma_composite(base_rgba: Path, dest: Path) -> None:
    """Composite transparent sprite onto solid key-green for I2V."""
    img = Image.open(base_rgba).convert("RGBA")
    bg = Image.new("RGBA", img.size, (*KEY_RGB, 255))
    bg.alpha_composite(img)
    bg.convert("RGB").save(dest)
