# Frameforge → Unity

These C# scripts turn a Frameforge spritesheet export (`*_sheet.png` + sibling `*_sheet.json`) into:

- sliced sprites (point-filtered, multi-sprite)  
- one `AnimationClip` per animation in the JSON  
- an `AnimatorController` wiring those clips  

They are what GitHub reports as the project’s **C#** share. Source of truth lives here; MCP `install_to_unity` / `install_item_to_unity` copies them into the target Unity project.

Product overview: [repository root README](../../README.md#unity-integration).

---

## Files

| File | Role |
|------|------|
| `Editor/FrameforgeSheetImport.cs` | Core importer + menu **Assets → Frameforge → Import Selected Sheet** + auto-import / pending queue |
| `Editor/SpriteSheetImporterEditor.cs` | Custom inspector button on `SpriteSheetImporter` |
| `SpriteSheetImporter.cs` | Optional runtime `MonoBehaviour` with serialized refs (no `Find`) for inspector-driven reimport |

After MCP install they land under:

- `Assets/Editor/Frameforge/`  
- `Assets/Scripts/Frameforge/`  

---

## Expected assets

Place next to each other (same folder, same stem):

```text
Assets/.../MyCreature/MyCreature_sheet.png
Assets/.../MyCreature/MyCreature_sheet.json
```

Default destinations:

| Asset type | Path |
|------------|------|
| Characters | `Assets/Creatures/spritesheets/<Name>/` |
| Items | `Assets/Items/spritesheets/<Name>/` |

---

## Sheet JSON schema

Produced by Frameforge’s Unity export. Example:

```json
{
  "name": "MyCreature",
  "cellWidth": 128,
  "cellHeight": 128,
  "columns": 8,
  "rows": 2,
  "frameCount": 12,
  "pixelsPerUnit": 100,
  "animations": [
    {
      "name": "walk_side",
      "frameIndices": [0, 1, 2, 3, 4, 5],
      "fps": 8,
      "loop": true
    },
    {
      "name": "attack",
      "frameIndices": [6, 7, 8, 9],
      "fps": 10,
      "loop": false
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `cellWidth` / `cellHeight` | Pixel size of one frame cell |
| `columns` / `rows` | Grid layout on the PNG (top → bottom rows) |
| `frameCount` | Total cells used |
| `pixelsPerUnit` | Sprite PPU (default 100) |
| `animations[].frameIndices` | Cell indices into the packed sheet |
| `animations[].fps` | Clip sample rate |
| `animations[].loop` | Looping vs one-shot |

---

## How to import

### A) MCP (recommended)

With Frameforge API running and `UNITY_PROJECT_ROOT` set in MCP env:

```text
install_to_unity(character="MyCreature")
install_item_to_unity(item="Chest")
```

Copies PNG+JSON, installs these scripts, and enqueues import (pending file under `Assets/Editor/Frameforge/pending-imports.txt`). Unity should create clips after compile/refresh.

### B) Menu

1. Select the `*_sheet.png` in the Project window  
2. **Assets → Frameforge → Import Selected Sheet**  

### C) Code / unity-mcp

```csharp
FrameforgeSheetImport.ImportAtPath(
    "Assets/Creatures/spritesheets/MyCreature/MyCreature_sheet.png"
);
```

### D) Optional component

Add `SpriteSheetImporter` to a GameObject, assign texture (and optional JSON), click **Import Sheet From JSON** in the inspector.

---

## What the importer writes

Under the output folder (usually next to the sheet):

- sliced sprites on the texture  
- `*.anim` clips named after each animation  
- `*.controller` AnimatorController  

Texture import settings applied: Sprite (Multiple), Point filter, no mipmaps, uncompressed.

---

## Auto-import

`FrameforgeSheetPostprocessor` runs when a `*_sheet.png` is imported and a sibling `.json` exists. While scripts are still compiling after a fresh copy, MCP uses `EnqueueImport` so import retries after domain reload.

If nothing happens: select the PNG → menu import, or call `ImportAtPath` once.

---

## Notes

- Editor scripts require the Unity **Editor** assemblies (not in player builds).  
- Do not use `GameObject.Find` for wiring — assign references in the inspector when using `SpriteSheetImporter`.  
- Manual ZIP exports include a short `README_unity.txt` with the same steps.  
