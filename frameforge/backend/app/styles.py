from __future__ import annotations

from typing import Any, Literal

StyleId = Literal[
    "pixel_art",
    "cartoon",
    "anime",
    "comic",
    "low_poly",
    "stylized_3d",
    "detailed_illustration",
    "realistic",
]

DEFAULT_STYLE: StyleId = "pixel_art"

# Green screen avoids pink fringes on white / fire subjects (magenta does not)
_CHROMA = (
    "solid bright flat green background #00FF00, chroma key green, empty void, "
    "no ground plane, no green outline or fringe on the character, "
    "single character, full body centered, readable silhouette"
)

_CHROMA_ITEM = (
    "solid bright flat green background #00FF00, chroma key green, empty void, "
    "no ground plane, no green outline or fringe on the object, "
    "single game item centered, clear readable silhouette, no character holding it"
)

STYLES: dict[str, dict[str, Any]] = {
    "pixel_art": {
        "id": "pixel_art",
        "label": "Pixel art",
        "blurb": "Modern pixel LoRA + hard pixels",
        "lora_strength": 0.9,
        "trigger": "umempart, masterpiece modern pixel art sprite",
        "style_tags": (
            "64 to 128 style chunky pixels, crisp hard edges, clean silhouette, "
            "limited palette with deliberate shading bands, "
            "strong orange yellow red fire clusters, white body with cool gray shade band, "
            "professional indie game sprite sheet quality, "
            "no anti alias glow, no soft blur, no pink rim light, "
            "no horn, not a unicorn unless the prompt asks for one"
        ),
        "resize": "nearest",
        "polish_role": "high-quality modern pixel-art game creature sprites",
        "polish_keep": (
            "single character, full body side view, solid flat green #00FF00 background, "
            "crisp pixel art with concrete anatomy and fire detail, no pink outline"
        ),
    },
    "cartoon": {
        "id": "cartoon",
        "label": "Cartoon",
        "blurb": "Soft game-mascot cartoon",
        "lora_strength": 0.0,
        "trigger": "stylized cartoon creature",
        "style_tags": "clean shapes, soft cel shading, thick readable outline, game character design",
        "resize": "lanczos",
        "polish_role": "stylized cartoon game creature sprites",
        "polish_keep": "single character, full body, solid green #00FF00 background, cartoon style",
    },
    "anime": {
        "id": "anime",
        "label": "Anime",
        "blurb": "Anime / illustration look",
        "lora_strength": 0.0,
        "trigger": "anime style creature",
        "style_tags": "anime illustration, clean linework, vibrant colors, game character sheet pose",
        "resize": "lanczos",
        "polish_role": "anime-style game creature sprites",
        "polish_keep": "single character, full body, solid green #00FF00 background, anime style",
    },
    "comic": {
        "id": "comic",
        "label": "Comic",
        "blurb": "Bold comic / inked look",
        "lora_strength": 0.0,
        "trigger": "comic book style creature",
        "style_tags": "bold ink outlines, halftone accents, dynamic comic shading, graphic novel",
        "resize": "lanczos",
        "polish_role": "comic-book style game creature sprites",
        "polish_keep": "single character, full body, solid green #00FF00 background, comic style",
    },
    "low_poly": {
        "id": "low_poly",
        "label": "Low poly",
        "blurb": "Facetted 3D low-poly render",
        "lora_strength": 0.0,
        "trigger": "low poly 3D creature",
        "style_tags": "faceted geometry, flat shaded polygons, simple 3D game asset, studio render",
        "resize": "lanczos",
        "polish_role": "low-poly 3D game creature sprites",
        "polish_keep": "single character, full body, solid green #00FF00 background, low poly",
    },
    "stylized_3d": {
        "id": "stylized_3d",
        "label": "Stylized 3D",
        "blurb": "Polished game-character 3D look",
        "lora_strength": 0.0,
        "trigger": "stylized 3D game character render",
        "style_tags": (
            "clean PBR materials, soft global illumination, rounded forms, "
            "collectible creature aesthetic, mobile game hero quality, "
            "not photoreal, not pixel art, no green screen background"
        ),
        "resize": "lanczos",
        "polish_role": "stylized 3D game creature stills",
        "polish_keep": "single character, full body, stylized 3D render, not pixel art",
    },
    "detailed_illustration": {
        "id": "detailed_illustration",
        "label": "Detailed illustration",
        "blurb": "Clean high-detail drawing / concept art",
        "lora_strength": 0.0,
        "trigger": "detailed digital illustration of a fantasy creature",
        "style_tags": (
            "crisp linework, controlled cel shading, concept-art polish, "
            "readable silhouette, rich color, game key-art illustration, "
            "not photoreal photo, not pixel art, no green screen, no chroma key"
        ),
        "resize": "lanczos",
        "polish_role": "detailed fantasy creature illustrations",
        "polish_keep": "single character, full body, detailed illustration, not a photo",
    },
    "realistic": {
        "id": "realistic",
        "label": "Realistic",
        "blurb": "Photoreal photo (RealVisXL)",
        "lora_strength": 0.0,
        "trigger": "raw photograph of a living creature",
        "style_tags": (
            "ultra photoreal, full natural color gamut, unrestricted palette, "
            "real animal fur and hide microdetail, wet reflective eyes, "
            "volumetric fire with heat haze and ember sparks lighting the scene, "
            "cinematic HDR, shot on 85mm, shallow DOF, film grain, "
            "not illustration, not flat color, not limited palette, not cartoon, "
            "not cel shading, not CGI plastic, not pixel art, no green screen"
        ),
        "resize": "lanczos",
        "polish_role": "photorealistic creature photographs",
        "polish_keep": "single living creature, photoreal photograph, full natural colors",
        "art_backend": "sdxl",
    },
}


def list_styles() -> list[dict[str, Any]]:
    return [
        {
            "id": s["id"],
            "label": s["label"],
            "blurb": s["blurb"],
            "resize": s["resize"],
        }
        for s in STYLES.values()
    ]


def normalize_style(style: str | None) -> str:
    key = (style or DEFAULT_STYLE).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pixel": "pixel_art",
        "pixelart": "pixel_art",
        "lowpoly": "low_poly",
        "photo": "realistic",
        "photoreal": "realistic",
        "photorealistic": "realistic",
        "stylized3d": "stylized_3d",
        "stylized": "stylized_3d",
        "3d": "stylized_3d",
        "illustration": "detailed_illustration",
        "detailed": "detailed_illustration",
        "drawing": "detailed_illustration",
        "concept_art": "detailed_illustration",
    }
    key = aliases.get(key, key)
    return key if key in STYLES else DEFAULT_STYLE


def get_style(style: str | None) -> dict[str, Any]:
    return STYLES[normalize_style(style)]


_OUTLINE_TAGS = (
    "bold dark 1px pixel outline around the whole character, black contour, "
    "outlined pixel sprite style"
)


def build_generation_prompt(
    user_prompt: str,
    style: str | None,
    outline: bool = False,
    *,
    chroma: bool = True,
    subject: Literal["character", "item"] = "character",
    palette: list[str] | None = None,
) -> str:
    from .palettes import prompt_clause

    spec = get_style(style)
    text = (user_prompt or "").strip()
    lower = text.lower()
    trigger = str(spec["trigger"])
    if subject == "item":
        # Prefer item wording when style trigger still says "creature"
        item_trigger = trigger.replace("creature", "item").replace("character", "item")
        if item_trigger.lower() not in lower and not (
            spec["id"] == "pixel_art" and "umempart" in lower
        ):
            text = f"{item_trigger}, {text}" if text else item_trigger
    elif trigger.lower() not in lower and not (
        spec["id"] == "pixel_art" and "umempart" in lower
    ):
        text = f"{trigger}, {text}" if text else trigger
    tags = str(spec["style_tags"])
    if tags and tags.split(",")[0].strip().lower() not in lower:
        text = f"{text}, {tags}" if text else tags
    if outline and "outline" not in lower and "contour" not in lower:
        text = f"{text}, {_OUTLINE_TAGS}"
    elif not outline and spec["id"] == "pixel_art" and "outline" not in lower:
        text = f"{text}, no black outline, flat filled silhouette"
    clause = prompt_clause(palette)
    if clause and "strict limited color palette" not in lower:
        text = f"{text}, {clause}" if text else clause
    if chroma and (
        "#00ff00" not in lower
        and "chroma key green" not in lower
        and "green background" not in lower
    ):
        text = f"{text}, {_CHROMA_ITEM if subject == 'item' else _CHROMA}"
    return text


def fallback_character_prompt(
    user_prompt: str,
    style: str | None,
    outline: bool = False,
    palette: list[str] | None = None,
) -> str:
    spec = get_style(style)
    body = (user_prompt or "").strip() or "collectible monster creature"
    if len(body.split()) < 16:
        body = (
            f"{body}, clear side-view silhouette, defined legs head and torso, "
            "intentional color blocks, strong contrast between body and accents"
        )
    return build_generation_prompt(
        body, spec["id"], outline=outline, subject="character", palette=palette
    )


def fallback_item_prompt(
    user_prompt: str,
    style: str | None,
    outline: bool = False,
    palette: list[str] | None = None,
) -> str:
    spec = get_style(style)
    body = (user_prompt or "").strip() or "fantasy game item, potion bottle"
    if len(body.split()) < 12:
        body = (
            f"{body}, clear item silhouette, readable materials and accents, "
            "centered prop, intentional color blocks, strong contrast"
        )
    return build_generation_prompt(
        body, spec["id"], outline=outline, subject="item", palette=palette
    )


def item_polish_role(style: str | None) -> str:
    spec = get_style(style)
    return str(spec["polish_role"]).replace("creature", "item").replace("character", "item")


def item_polish_keep(style: str | None) -> str:
    spec = get_style(style)
    keep = str(spec["polish_keep"])
    keep = keep.replace("single character, full body", "single game item, full object")
    keep = keep.replace("single living creature", "single game item")
    keep = keep.replace("side view", "clear three-quarter or side view")
    return keep
