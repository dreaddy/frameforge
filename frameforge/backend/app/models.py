from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PixelSize = Literal[16, 32, 48, 64, 128, 256, 512, 768, 1024]


class HealthResponse(BaseModel):
    ok: bool
    comfy: dict[str, Any]
    ollama: dict[str, Any]
    sizes: dict[str, Any] = Field(default_factory=dict)


class GenerateCharacterRequest(BaseModel):
    prompt: str
    name: str | None = None
    project_id: str | None = None
    pixel_size: PixelSize = 128
    style: str = "pixel_art"
    drop_shadow: bool = False
    outline: bool = False
    polish_prompt: bool = False
    seed: int | None = None


class GenerateItemRequest(BaseModel):
    prompt: str
    name: str | None = None
    project_id: str | None = None
    pixel_size: PixelSize = 128
    style: str = "pixel_art"
    drop_shadow: bool = False
    outline: bool = False
    polish_prompt: bool = False
    seed: int | None = None


class ItemAnimationCreateRequest(BaseModel):
    anim_type: str = Field(
        default="destroyed",
        description="Item preset key (idle/destroyed/use/open) or free text",
    )
    variants: int = Field(default=1, ge=1, le=6)
    frames: int = Field(default=6, ge=2, le=16)
    fps: int = Field(default=8, ge=1, le=30)
    method: Literal["i2v", "pose_keyframes"] = "i2v"
    motion_notes: str = Field(
        default="",
        description="How the motion should feel, e.g. slow breathing, snappy, subtle bob",
    )
    name: str = Field(
        default="",
        description="Display/export name; empty = auto (idle, idle2, …)",
    )


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    default_style: str = "pixel_art"
    default_pixel_size: PixelSize = 128
    default_drop_shadow: bool = False
    default_outline: bool = False
    palette_preset: str = "none"
    palette: list[str] = Field(default_factory=list)
    palette_seed: list[str] = Field(default_factory=list)


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    default_style: str | None = None
    default_pixel_size: PixelSize | None = None
    default_drop_shadow: bool | None = None
    default_outline: bool | None = None
    palette_preset: str | None = None
    palette: list[str] | None = None
    palette_seed: list[str] | None = None


class ApplyPaletteRequest(BaseModel):
    include_animations: bool = True


class PolishPromptRequest(BaseModel):
    prompt: str
    style: str = "pixel_art"
    outline: bool = False
    project_id: str | None = None
    subject: Literal["character", "item"] = "character"


class PolishPromptResponse(BaseModel):
    prompt: str
    source: Literal["ollama", "fallback"]
    style: str


class AnimationCreateRequest(BaseModel):
    wan_size: Literal[256, 512, 768, 1024] | None = None
    no_scale: bool = False
    anim_type: str = Field(description="Preset key or free text")
    variants: int = Field(default=1, ge=1, le=6)
    frames: int = Field(default=6, ge=2, le=16)
    fps: int = Field(default=8, ge=1, le=30)
    method: Literal["i2v", "pose_keyframes"] = "i2v"
    source_image: Literal["base", "standing"] | None = Field(
        default=None,
        description="Which character image to animate from; None = character default",
    )
    motion_notes: str = Field(
        default="",
        description="How the motion should feel, e.g. slow idle bob, fast frantic steps",
    )
    name: str = Field(
        default="",
        description="Display/export name; empty = auto (idle, idle2, …)",
    )


class AnimationRenameRequest(BaseModel):
    """Patch animation metadata. At least one of name/fps must be set."""

    name: str | None = Field(default=None, description="New display/export name")
    fps: int | None = Field(
        default=None,
        ge=1,
        le=30,
        description="Recommended playback speed (frames per second)",
    )


class PrepareStandingRequest(BaseModel):
    """Build a pose source image from the character base (default: standing)."""

    set_as_source: bool = Field(
        default=True,
        description="After success, use this pose as the default animation source",
    )
    pose: str = Field(
        default="standing",
        description="Pose description, e.g. standing, lying, sitting, crouching",
        min_length=1,
        max_length=120,
    )


class GenerateArtRequest(BaseModel):
    """Generate a non-sprite art still of the creature (portrait / inventory / scene)."""

    style: str = Field(default="anime", description="Target art style id")
    purpose: Literal["portrait", "inventory", "showcase", "scene"] = Field(
        default="portrait",
        description="Framing for UI use: portrait, inventory, showcase, or scene",
    )
    size: Literal[512, 768, 1024, 1280] = Field(
        default=1024,
        description="Flux img2img square size (sensible for typical VRAM)",
    )
    background: str | None = Field(
        default=None,
        description="Optional environment / backdrop description (always a real scene, never chroma key)",
        max_length=300,
    )
    prompt: str | None = Field(
        default=None,
        description="Optional extra direction (lighting, mood, props)",
        max_length=400,
    )


class SetSourceImageRequest(BaseModel):
    source_image: Literal["base", "standing"] = Field(
        description="Active source for new animations: original base or standing"
    )
    standing_id: str | None = Field(
        default=None,
        description="When source_image=standing, which standing version to activate",
    )


class SelectVariantRequest(BaseModel):
    variant_index: int | None = Field(
        default=None,
        description="Variant to select, or null to clear selection",
    )


class CharacterSummary(BaseModel):
    id: str
    name: str
    prompt: str
    pixel_size: int
    created_at: str
    base_url: str
    animations: list[str]


class JobStatus(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = 0.0
    message: str = ""
    character_id: str | None = None
    item_id: str | None = None
    animation_id: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
