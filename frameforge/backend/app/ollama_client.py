from __future__ import annotations

from typing import Any

import httpx

from .config import (
    ANIMATION_PRESETS,
    ITEM_ANIMATION_PRESETS,
    NON_LOOP_ANIM_TYPES,
    OLLAMA_MODEL,
    OLLAMA_URL,
)
from .styles import (
    fallback_character_prompt,
    fallback_item_prompt,
    get_style,
    item_polish_keep,
    item_polish_role,
)


def health() -> dict[str, Any]:
    try:
        with httpx.Client(base_url=OLLAMA_URL, timeout=5.0) as c:
            r = c.get("/api/tags")
            r.raise_for_status()
            models = [m.get("name") for m in (r.json().get("models") or [])]
            return {"ok": True, "url": OLLAMA_URL, "models": models, "default": OLLAMA_MODEL}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": OLLAMA_URL, "error": str(exc), "models": []}


def _chat(system: str, user: str, model: str | None = None) -> str:
    model = model or OLLAMA_MODEL
    with httpx.Client(base_url=OLLAMA_URL, timeout=120.0) as c:
        r = c.post(
            "/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content") or ""


def polish_character_prompt(
    prompt: str,
    style: str | None = None,
    outline: bool = False,
    game_context: str | None = None,
    palette: list[str] | None = None,
) -> str:
    text, _source = polish_character_prompt_detailed(
        prompt, style, outline=outline, game_context=game_context, palette=palette
    )
    return text


def polish_character_prompt_detailed(
    prompt: str,
    style: str | None = None,
    outline: bool = False,
    game_context: str | None = None,
    palette: list[str] | None = None,
) -> tuple[str, str]:
    """Return (polished_prompt, source) where source is 'ollama' or 'fallback'."""
    from .palettes import prompt_clause

    spec = get_style(style)
    keep = str(spec["polish_keep"])
    if outline and spec["id"] == "pixel_art":
        keep = keep + ", bold dark 1px pixel outline around the character"
    clause = prompt_clause(palette)
    if clause:
        keep = keep + ", " + clause
    context = (game_context or "").strip()
    game_line = (
        f"Game setting (match tone/world, do not quote this block):\n{context}\n\n"
        if context
        else ""
    )
    pal_line = f"Palette constraint:\n{clause}\n\n" if clause else ""
    h = health()
    if not h.get("ok"):
        return (
            fallback_character_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )
    models = h.get("models") or []
    model = OLLAMA_MODEL if any(OLLAMA_MODEL in (m or "") for m in models) else (models[0] if models else None)
    if not model:
        return (
            fallback_character_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )
    try:
        text = _chat(
            f"You write English prompts for {spec['polish_role']}. "
            "Return ONLY the prompt, no quotes. Keep under 80 words. "
            "Expand thin ideas into concrete visual details: anatomy, materials, "
            "colors, lighting shapes, pose. Avoid vague words like cute/nice alone. "
            f"Always keep: {keep}.",
            f"{game_line}{pal_line}"
            f"Improve this creature prompt for a collectible monster game "
            f"({spec['label']} style). If the idea is short, invent plausible details "
            f"that match the concept:\n{prompt}",
            model=model,
        ).strip().strip('"')
        if text:
            return text, "ollama"
        return (
            fallback_character_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )
    except Exception:
        return (
            fallback_character_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )


def polish_item_prompt(
    prompt: str,
    style: str | None = None,
    outline: bool = False,
    game_context: str | None = None,
    palette: list[str] | None = None,
) -> str:
    text, _source = polish_item_prompt_detailed(
        prompt, style, outline=outline, game_context=game_context, palette=palette
    )
    return text


def polish_item_prompt_detailed(
    prompt: str,
    style: str | None = None,
    outline: bool = False,
    game_context: str | None = None,
    palette: list[str] | None = None,
) -> tuple[str, str]:
    """Return (polished_prompt, source) where source is 'ollama' or 'fallback'."""
    from .palettes import prompt_clause

    spec = get_style(style)
    keep = item_polish_keep(spec["id"])
    if outline and spec["id"] == "pixel_art":
        keep = keep + ", bold dark 1px pixel outline around the item"
    clause = prompt_clause(palette)
    if clause:
        keep = keep + ", " + clause
    context = (game_context or "").strip()
    game_line = (
        f"Game setting (match tone/world, do not quote this block):\n{context}\n\n"
        if context
        else ""
    )
    pal_line = f"Palette constraint:\n{clause}\n\n" if clause else ""
    h = health()
    if not h.get("ok"):
        return (
            fallback_item_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )
    models = h.get("models") or []
    model = OLLAMA_MODEL if any(OLLAMA_MODEL in (m or "") for m in models) else (models[0] if models else None)
    if not model:
        return (
            fallback_item_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )
    try:
        text = _chat(
            f"You write English prompts for {item_polish_role(spec['id'])}. "
            "Return ONLY the prompt, no quotes. Keep under 80 words. "
            "Expand thin ideas into concrete visual details: materials, shape, "
            "colors, ornaments, wear. Avoid vague words like cute/nice alone. "
            f"Always keep: {keep}. Never describe a character holding the item.",
            f"{game_line}{pal_line}"
            f"Improve this game-item prompt ({spec['label']} style). If the idea is short, "
            f"invent plausible prop details that match the concept:\n{prompt}",
            model=model,
        ).strip().strip('"')
        if text:
            return text, "ollama"
        return (
            fallback_item_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )
    except Exception:
        return (
            fallback_item_prompt(prompt, spec["id"], outline=outline, palette=palette),
            "fallback",
        )


def _anim_key(anim_type: str) -> str:
    return anim_type.strip().lower().replace(" ", "_")


def _is_oneshot(anim_type: str) -> bool:
    key = _anim_key(anim_type)
    return key in NON_LOOP_ANIM_TYPES or key in {"death", "die", "destroy", "break"}


def motion_prompt(
    anim_type: str,
    character_desc: str,
    variant_index: int,
    *,
    presets: dict[str, str] | None = None,
    subject: str = "character",
    motion_notes: str = "",
) -> str:
    table = presets or ANIMATION_PRESETS
    key = _anim_key(anim_type)
    preset = table.get(key) or table.get(anim_type.strip().lower())
    base_motion = preset or anim_type
    notes = (motion_notes or "").strip()
    subject_word = "item" if subject == "item" else "character"
    oneshot = _is_oneshot(key)
    h = health()
    if not h.get("ok"):
        return _fallback_motion(
            base_motion,
            character_desc,
            variant_index,
            subject=subject,
            motion_notes=notes,
            anim_type=key,
        )
    models = h.get("models") or []
    model = OLLAMA_MODEL if any(OLLAMA_MODEL in (m or "") for m in models) else (models[0] if models else None)
    if not model:
        return _fallback_motion(
            base_motion,
            character_desc,
            variant_index,
            subject=subject,
            motion_notes=notes,
            anim_type=key,
        )
    try:
        notes_line = f"\nMotion feel (honor this): {notes}" if notes else ""
        if oneshot and subject == "item":
            mode = (
                "This is a ONE-SHOT DESTROY animation. Describe breaking/cracking/shattering once. "
                "Forbidden: idle bob, shimmer loop, gentle sway, breathing. "
                "End with ruined debris settled."
            )
        elif oneshot and key in {"destroyed", "death", "die", "destroy"}:
            mode = (
                "This is a ONE-SHOT DEATH animation. Describe the creature dying and collapsing once. "
                "Forbidden: idle breathing, subtle bob, looping sway, recovering to stand. "
                "End with a limp dead pose on the ground."
            )
        elif oneshot:
            mode = (
                "This is a ONE-SHOT action (not a loop). Clear start → peak → settle. "
                "Do not describe idle breathing or looping bob."
            )
        else:
            mode = "Loop-friendly repeating motion for a game sprite."
        text = _chat(
            f"You write short English motion prompts for image-to-video of a game {subject_word} sprite. "
            f"Return ONLY one sentence. Keep the same {subject_word} identity. "
            "No camera cuts. Magenta/solid background stays empty. "
            f"{mode} "
            "Respect any Motion feel notes about speed, intensity, or timing.",
            f"{subject_word.capitalize()}: {character_desc}\nAnimation type: {key}\n"
            f"Animation: {base_motion}{notes_line}\n"
            f"Variant #{variant_index + 1} (slightly different timing/intensity).",
            model=model,
        ).strip().strip('"')
        return text or _fallback_motion(
            base_motion,
            character_desc,
            variant_index,
            subject=subject,
            motion_notes=notes,
            anim_type=key,
        )
    except Exception:
        return _fallback_motion(
            base_motion,
            character_desc,
            variant_index,
            subject=subject,
            motion_notes=notes,
            anim_type=key,
        )


def pose_prompts(
    anim_type: str,
    character_desc: str,
    frame_count: int,
    *,
    presets: dict[str, str] | None = None,
    subject: str = "character",
    motion_notes: str = "",
) -> list[str]:
    """Pose-only phrases for img2img — must NOT redesign colors/species/props."""
    table = presets or ANIMATION_PRESETS
    preset = table.get(anim_type.strip().lower(), anim_type)
    notes = (motion_notes or "").strip()
    h = health()
    if h.get("ok"):
        models = h.get("models") or []
        model = OLLAMA_MODEL if any(OLLAMA_MODEL in (m or "") for m in models) else (models[0] if models else None)
        if model:
            try:
                notes_line = f"\nMotion feel (speed/intensity): {notes}" if notes else ""
                key = _anim_key(anim_type)
                oneshot_hint = ""
                if _is_oneshot(key):
                    if subject == "item" or key in {"destroyed", "death", "die", "destroy"}:
                        oneshot_hint = (
                            " ONE-SHOT destroy/death sequence: progress from intact/alive to "
                            "broken/dead. Never repeat idle breathing poses."
                        )
                    else:
                        oneshot_hint = " ONE-SHOT action: start → peak → settle, no idle loop."
                raw = _chat(
                    "You write pose-only instructions for img2img sprite animation. "
                    "Return a numbered list, one short pose phrase per line, no extra text. "
                    "Describe ONLY limb positions, body lean, and timing of the action. "
                    "Do NOT mention colors, species changes, horns, outfits, or new props. "
                    f"Keep the same {'item' if subject == 'item' else 'character'} identity implied. "
                    "Honor Motion feel notes when spacing poses (slow = smaller deltas, fast = larger)."
                    f"{oneshot_hint}",
                    f"{'Item' if subject == 'item' else 'Character'} lock (do not alter): {character_desc}\n"
                    f"Animation type: {key}\nAnimation: {preset}{notes_line}\nFrames: {frame_count}",
                    model=model,
                )
                lines = [
                    ln.split(".", 1)[-1].strip(" -")
                    for ln in raw.splitlines()
                    if ln.strip() and any(ch.isalpha() for ch in ln)
                ]
                if len(lines) >= frame_count:
                    return lines[:frame_count]
            except Exception:
                pass
    return _fallback_pose_prompts(anim_type, frame_count, subject=subject, motion_notes=notes)


def _fallback_pose_prompts(
    anim_type: str,
    frame_count: int,
    *,
    subject: str = "character",
    motion_notes: str = "",
) -> list[str]:
    key = anim_type.strip().lower().replace(" ", "_")
    notes = (motion_notes or "").strip()
    cycles: dict[str, list[str]] = {
        "walk_side": [
            "contact: left foreleg forward, right hindleg back",
            "passing: legs under body, slight bob down",
            "contact: right foreleg forward, left hindleg back",
            "passing: legs gather, slight bob up",
        ],
        "walk_down": [
            "step left foot forward toward camera",
            "recover center stance",
            "step right foot forward toward camera",
            "recover center stance",
        ],
        "walk_up": [
            "step left foot away from camera",
            "recover center stance",
            "step right foot away from camera",
            "recover center stance",
        ],
        "attack": [
            "wind-up lean back, front limb cocked",
            "strike extended forward",
            "follow-through slightly overextended",
            "return toward idle stance",
        ],
        "idle": [
            "neutral stance, slight inhale up",
            "neutral stance peak",
            "neutral stance, slight exhale down",
            "neutral stance settle",
        ],
        "hurt": [
            "flinch recoil lean back",
            "peak recoil",
            "start recovering forward",
            "near idle stance",
        ],
        "destroyed": [
            "stagger from fatal hit, body still upright",
            "knees buckle, torso folding down",
            "collapse mid-fall, limbs flailing limp",
            "dead on the ground, fully limp corpse pose",
        ],
        "death": [
            "stagger from fatal hit, body still upright",
            "knees buckle, torso folding down",
            "collapse mid-fall, limbs flailing limp",
            "dead on the ground, fully limp corpse pose",
        ],
        "use": [
            "item at rest",
            "activate pulse / glow begin",
            "peak activation energy",
            "settle back toward idle",
        ],
        "open": [
            "fully closed",
            "lid / hatch cracking open",
            "half open",
            "fully open held pose",
        ],
    }
    if subject == "item" and key == "idle":
        cycles["idle"] = [
            "item at rest, slight shimmer up",
            "item peak shimmer",
            "item slight bob down",
            "item settle",
        ]
    if subject == "item" and key in {"destroyed", "death", "die", "destroy"}:
        cycles[key] = [
            "item intact, first crack splits across surface",
            "breaking apart, chunks separating mid-shatter",
            "debris flying outward, silhouette fragmenting",
            "ruined remains settled on the ground",
        ]
    base = cycles.get(key) or [
        f"{key} pose phase {i + 1}" for i in range(max(frame_count, 4))
    ]
    suffix = f" ({notes})" if notes else ""
    out: list[str] = []
    for i in range(frame_count):
        out.append(f"{base[i % len(base)]}{suffix}")
    return out


def _fallback_motion(
    base_motion: str,
    character_desc: str,
    variant_index: int,
    *,
    subject: str = "character",
    motion_notes: str = "",
    anim_type: str = "",
) -> str:
    key = _anim_key(anim_type or base_motion)
    noun = "item" if subject == "item" else "creature"
    notes = (motion_notes or "").strip()
    if _is_oneshot(key) and (subject == "item" or key in {"destroyed", "death", "die", "destroy"}):
        if subject == "item":
            action = (
                "cracks violently then shatters into debris once and settles as ruined remains"
            )
        else:
            action = (
                "takes a fatal hit, collapses and dies once, ending limp dead on the ground"
            )
        feel = f", {notes}" if notes else ""
        return (
            f"The {noun} ({character_desc[:120]}) {action}{feel}, "
            "NOT idle or breathing, one-shot only, solid empty background, no camera cut."
        )
    flavors = [
        "smooth looping motion",
        "slightly snappier timing",
        "broader movement",
        "subtle bounce emphasis",
    ]
    flavor = flavors[variant_index % len(flavors)]
    feel = f", {notes}" if notes else f", {flavor}"
    return (
        f"The {noun} ({character_desc[:120]}) performs {base_motion}{feel}, "
        "keep solid empty background, no camera cut, short loop."
    )


def animation_presets_for(subject: str) -> dict[str, str]:
    return dict(ITEM_ANIMATION_PRESETS) if subject == "item" else dict(ANIMATION_PRESETS)
