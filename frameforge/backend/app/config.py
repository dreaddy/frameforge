import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
# Legacy flat character folders (migrated into GAME_PROJECTS_DIR on startup)
LEGACY_CHARACTERS_DIR = DATA_DIR / "projects"
GAME_PROJECTS_DIR = DATA_DIR / "game_projects"
# Kept for older imports; points at game projects root (not character folders)
PROJECTS_DIR = GAME_PROJECTS_DIR
WORKFLOWS_DIR = BACKEND_ROOT / "workflows"

COMFY_URL = "http://127.0.0.1:8000"
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.2"
API_HOST = "127.0.0.1"
API_PORT = 8787

FLUX_WORKFLOW = WORKFLOWS_DIR / "flux_pixel_creature_api.json"
FLUX_POSE_IMG2IMG_WORKFLOW = WORKFLOWS_DIR / "flux_pose_img2img_api.json"
SDXL_ART_IMG2IMG_WORKFLOW = WORKFLOWS_DIR / "sdxl_art_img2img_api.json"
QWEN_IMAGE_EDIT_WORKFLOW = WORKFLOWS_DIR / "qwen_image_edit_2509.json"
WAN_I2V_WORKFLOW = WORKFLOWS_DIR / "wan22_i2v.json"
SDXL_CHECKPOINT = "sd_xl_base_1.0.safetensors"
# Preferred photoreal checkpoint for art stills (falls back to SDXL_CHECKPOINT)
SDXL_REALISM_CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"

# Low denoise keeps identity; too high redesigns the creature each frame
POSE_IMG2IMG_DENOISE = 0.4
POSE_IMG2IMG_STEPS = 22

DEFAULT_PIXEL_SIZE = 128
# 48 = 3x3 tiles at 16px (dungeon / top-down props)
PIXEL_SIZES = (16, 32, 48, 64, 128, 256, 512, 768, 1024)
WAN_SQUARE_SIZES = (256, 512, 768, 1024)
DEFAULT_FPS = 8
DEFAULT_ANIM_FRAMES = 6
DEFAULT_VARIANTS = 1

# Wan 14B at 640x640 / 5s / turbo-off was ~10min per variant on 5080.
# Sprite loops only need a short turbo clip at sprite-ish resolution.
WAN_I2V_WIDTH = 256
WAN_I2V_HEIGHT = 256
WAN_I2V_DURATION_S = 1.0
WAN_I2V_FPS = 16
WAN_I2V_LENGTH = 17  # must be 4n+1 for Wan
WAN_I2V_TURBO = True

FFMPEG_CANDIDATES = [
    Path(os.environ["FFMPEG_PATH"]) if os.environ.get("FFMPEG_PATH") else None,
]

ANIMATION_PRESETS = {
    "walk_side": "side view walk cycle, character walking to the right, looping steps",
    "walk_up": "top-down or back view walk cycle, character walking upward away from camera",
    "walk_down": "front view walk cycle, character walking toward camera",
    "attack": "attack animation, character striking forward once then returning to idle",
    "idle": "subtle idle breathing bob, tiny motion loop",
    "hurt": "brief hit reaction flinch then recover",
    "destroyed": (
        "ONE-SHOT death: creature is hit hard, crumples and collapses dead onto the ground, "
        "limbs go limp, final frames are a still corpse pose — NOT idle, NOT breathing, NOT a loop"
    ),
}

# Item animations — no locomotion; destroyed is the default death/break one-shot.
ITEM_ANIMATION_PRESETS = {
    "destroyed": (
        "ONE-SHOT destroy: item cracks, breaks apart or shatters into pieces, debris flies out, "
        "ends as ruined remains on the ground — NOT idle shimmer, NOT a gentle bob, NOT a loop"
    ),
    "idle": "subtle idle shimmer or bob, item stays in place, tiny looping motion",
    "use": "brief use or activate pulse (glow, shake, or trigger) then settle back",
    "open": "container or lid opens once and holds open, readable silhouette",
}

# Anim types that should export as non-looping one-shots
NON_LOOP_ANIM_TYPES = frozenset({"destroyed", "hurt", "attack", "use", "open", "death", "die"})

GAME_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
