# Frameforge

**Animate images for games — locally — and export them into your engine.**

Frameforge is a local toolkit that turns still images into game-ready animation clips. Generate or upload art, produce animation variants with ComfyUI, preview and pick the best loop, then export spritesheets (PNG + JSON) for Unity — from a web UI **or** from coding agents via [MCP](https://modelcontextprotocol.io/).

It is built for the workflow:

> Create a character → animate it → drop it into the game project.

…including when that request comes from Cursor (or another MCP-capable coding tool) in natural language.

---

## Why Frameforge?

Most sprite tools either **draw frames by hand** (Aseprite, Pixelorama) or **only pack existing sheets**. Frameforge sits in the middle of a modern game-asset pipeline:

| Step | What Frameforge does |
|------|----------------------|
| Source | Generate a still with local models, or import your own image |
| Motion | Drive local image-to-video / edit workflows (ComfyUI) into short clips |
| Curation | Preview variants, keep the one that fits |
| Ship | Pack a spritesheet + metadata; optionally install into Unity |

**Local-first:** generation and animation run on your machine (ComfyUI). No cloud account is required for the core loop. Pixel art is supported as a style, not as the product’s only use case — any game-ready still can be animated and exported.

---

## Features

- **Characters & items** — separate asset types with appropriate animation presets  
- **Generate or upload** — text-to-image (ComfyUI) or bring a finished PNG  
- **Animation variants** — multiple candidates per type; pick with “use this”  
- **Presets** — walk cycles, attack, idle, hurt, destroyed; items: idle, use, open, destroyed  
- **Local AI stack** — ComfyUI for images/video; optional Ollama for prompt polish  
- **Unity export** — spritesheet PNG + JSON, Editor importer for slices / `.anim` / AnimatorController  
- **One-shot Unity install** — MCP copies assets + scripts into `UNITY_PROJECT_ROOT`  
- **Agent automation** — full MCP tool surface for Cursor and other MCP clients  
- **Game projects** — organize assets under local projects (data stays on disk, not in git)  

---

## Architecture

```
┌─────────────┐     HTTP      ┌──────────────────┐     HTTP      ┌──────────┐
│ Angular UI  │ ────────────► │ FastAPI backend  │ ────────────► │ ComfyUI  │
│ :4200       │               │ :8787            │               │ :8000    │
└─────────────┘               └────────┬─────────┘               └──────────┘
                                       │
┌─────────────┐     stdio MCP          │
│ Cursor /    │ ───────────────────────┤  (same REST API)
│ other agent │                        │
└─────────────┘                        ▼
                               ┌───────────────┐
                               │ Local data/   │
                               │ + Unity export│
                               └───────────────┘
```

| Layer | Role |
|-------|------|
| `frameforge/frontend` | Angular app — gallery, generate, animate, preview, export |
| `frameforge/backend` | FastAPI — jobs, Comfy orchestration, sprite processing, export |
| `frameforge/mcp_server` | Thin MCP stdio server wrapping the REST API |
| `frameforge/unity` | Editor scripts (`FrameforgeSheetImport`, …) |
| ComfyUI | External — must be running with the models your workflows need |
| Ollama (optional) | Prompt polish / helpers |

Application code lives under [`frameforge/`](frameforge/). Root `npm` scripts start/stop the stack.

---

## Requirements

### Software

| Dependency | Version / notes |
|------------|-----------------|
| **Python** | 3.12+ |
| **Node.js** | 20+ (24 fine) |
| **[ComfyUI](https://github.com/comfyanonymous/ComfyUI)** | Reachable at `http://127.0.0.1:8000` (default) |
| **ffmpeg** | On `PATH`, or set `FFMPEG_PATH` (frame extract from video) |
| **[Ollama](https://ollama.com/)** | Optional — e.g. `ollama pull llama3.2` |
| **Unity** | Optional — only if you use the Editor importer / MCP install |

### Models (ComfyUI)

Exact checkpoints depend on your install. Bundled workflows under `frameforge/backend/workflows/` expect a typical local setup, for example:

- Image generation (e.g. Flux Dev FP8 + style LoRAs as configured in the flux workflow)  
- Image-to-video for sprite loops (e.g. Wan 2.2 I2V — see `wan22_i2v.json`)  
- Optional edit / art pipelines (Qwen Image Edit, SDXL img2img)  

If a workflow fails, open the matching JSON in ComfyUI and resolve missing nodes/models first.

### Hardware

- **~16 GB VRAM** class GPUs: comfortable for stills and smaller Wan sizes (256/512)  
- **768 / 1024 Wan** sizes: experimental on 16 GB — expect slow runs or OOM  
- Apple Silicon / low VRAM: stills may work; heavy I2V may not — prefer smaller presets or cloud elsewhere  

Frameforge itself is light; ComfyUI dominates GPU/RAM usage.

---

## Quick start

Commands below are for **Windows PowerShell** (primary supported path). Adjust for your shell on other OS.

### 1. Backend

```powershell
cd frameforge/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Frontend

```powershell
cd ..\frontend
npm install
```

### 3. MCP (optional, for agents)

```powershell
cd ..\mcp_server
..\backend\.venv\Scripts\pip.exe install -r requirements.txt
```

### 4. Start ComfyUI

Start your ComfyUI instance so `http://127.0.0.1:8000` answers (or point Frameforge at another URL via env — see Configuration).

### 5. Start Frameforge

From the **repository root**:

```powershell
npm run start
# or without opening a browser:
npm run start:nobrowser
```

Stop:

```powershell
npm run stop
```

| Service | URL |
|---------|-----|
| UI | http://127.0.0.1:4200 |
| API health | http://127.0.0.1:8787/health |
| ComfyUI | http://127.0.0.1:8000 |
| Logs | `frameforge/logs/` (`backend.out.log`, `backend.err.log`, …) |

**Cursor / VS Code:** Run and Debug → **Start** / **Start (no browser)** / **Stop**, or tasks **Frameforge: Start** / **Frameforge: Stop**.

---

## Configuration

See [`.env.example`](.env.example). Common variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `FRAMEFORGE_URL` | REST base URL for the MCP server | `http://127.0.0.1:8787` |
| `COMFY_LOCAL_URL` / Comfy URL | Where ComfyUI listens | `http://127.0.0.1:8000` |
| `COMFY_BIN` | `comfy` CLI binary if not on `PATH` | `comfy` |
| `FFMPEG_PATH` | Absolute path to `ffmpeg` if not on `PATH` | _(unset)_ |
| `UNITY_PROJECT_ROOT` | Target Unity project for MCP install | _(required for install)_ |
| `UNITY_ASSETS_SUBDIR` | Creature sheet destination | `Assets/Creatures/spritesheets` |
| `UNITY_ITEMS_ASSETS_SUBDIR` | Item sheet destination | `Assets/Items/spritesheets` |

Local generated data lives under `frameforge/data/` and is **gitignored** (projects, characters, items, job outputs).

---

## Using the UI

1. Open http://127.0.0.1:4200 and select/create a **game project**.  
2. **Generate** a character/item or **upload** a source image.  
3. Open the asset → choose an animation type, frame count, variants.  
4. Wait for the job → preview looping variants → **Use this** on the best one.  
5. Repeat for other animation types (walk, attack, idle, …).  
6. **Export** a Unity spritesheet ZIP, or install via MCP (below).  

Export sizes (application presets): **16, 32, 48, 64, 128, 256, 512, 768, 1024** px.  
WAN square sides: **256, 512, 768, 1024** (larger sizes may be experimental on mid-range GPUs).

Query the live catalog anytime: MCP `get_size_capabilities()` or `GET /presets/sizes`.

---

## Agent workflow (Cursor & other MCP clients)

Frameforge’s MCP server exposes the same capabilities as the UI so an agent can run the full pipeline from chat.

### Example prompts

> “Erstelle eine Katze, animiere sie (walk + idle) und bau sie in mein Unity-Projekt ein.”

> “Create a slime enemy, generate walk_side and attack with 2 variants each, then install into Unity.”

> “Nimm die von mir erstellte Katze `#203` mit allen Animationen und bau sie in Unity ein.”

> “Find character Firehorse256 and install_to_unity.”

Under the hood the agent typically: `generate_character` / `find_character` → `create_animation` → `job_status` → `select_variant` → `install_to_unity` (or `export_unity_sheet` only).

Items use the parallel tools (`generate_item`, `create_item_animation`, `install_item_to_unity`, …).

### MCP client config

Backend must be running on `:8787`. Example Cursor `%USERPROFILE%\.cursor\mcp.json` entry — **adjust absolute paths**:

```json
"frameforge": {
  "type": "stdio",
  "command": "C:/path/to/repo/frameforge/backend/.venv/Scripts/python.exe",
  "args": ["C:/path/to/repo/frameforge/mcp_server/server.py"],
  "env": {
    "FRAMEFORGE_URL": "http://127.0.0.1:8787",
    "UNITY_PROJECT_ROOT": "C:/path/to/YourUnityProject"
  }
}
```

Restart the MCP client after changing tools or env.

### Useful MCP tools

| Tool | Role |
|------|------|
| `health` | API + Comfy + Ollama status |
| `get_size_capabilities` | Supported sizes **before** generating |
| `list_projects` / `create_project` | Game projects |
| `generate_character` / `create_character_from_image` | New character |
| `find_character` / `get_character` | Resolve by name, id, or numeric `#ref` |
| `create_animation` / `job_status` / `select_variant` | Animate & curate |
| `export_unity_sheet` | Export only (no Unity copy) |
| `install_to_unity` | Export + copy into Unity + Editor scripts |
| `generate_item` / `find_item` / `create_item_animation` / `install_item_to_unity` | Same for items |
| `trash_*` / `restore_*` | Soft-delete / restore |

Assets can be addressed by **name**, **hex id**, or **numeric ref** (e.g. `#203` / `203`).

---

## Animation presets

**Characters**

| Type | Intent |
|------|--------|
| `walk_side` / `walk_up` / `walk_down` | Locomotion loops |
| `idle` | Subtle breathing / bob |
| `attack` | One-shot strike |
| `hurt` | Hit reaction |
| `destroyed` | One-shot death / collapse |

**Items** (no walk)

| Type | Intent |
|------|--------|
| `idle` | Subtle shimmer / bob |
| `use` | Activate pulse |
| `open` | Lid / container opens |
| `destroyed` | Break / shatter one-shot |

Non-looping types export as one-shots (`destroyed`, `hurt`, `attack`, `use`, `open`, …).

---

## Unity integration

### Automated (MCP)

```text
install_to_unity(character="Katze")
# or: install_to_unity(character="203")
install_item_to_unity(item="Chest")
```

Requires `UNITY_PROJECT_ROOT`. This will:

1. Build the spritesheet PNG + JSON  
2. Copy them under `Assets/Creatures/spritesheets/<Name>/` (or Items path)  
3. Install Editor/runtime scripts under `Assets/Editor/Frameforge/` and `Assets/Scripts/Frameforge/`  
4. Queue import so Unity creates sliced sprites, `.anim` clips, and an AnimatorController  

If auto-import did not run after compile, select the PNG → **Assets → Frameforge → Import Selected Sheet**, or from unity-mcp:

```csharp
FrameforgeSheetImport.ImportAtPath("Assets/Creatures/spritesheets/Katze/Katze_sheet.png");
```

### Manual

1. Unzip the export into your Assets tree  
2. Copy `frameforge/unity/Editor/*.cs` (and runtime script if needed) into the project  
3. Select `*_sheet.png` → **Assets → Frameforge → Import Selected Sheet**  

Sibling `*_sheet.json` must sit next to the PNG.

---

## Repository layout

```
.
├── README.md
├── LICENSE                 # MIT
├── CONTRIBUTING.md
├── SECURITY.md
├── NOTICE
├── package.json            # npm start / stop wrappers
├── .env.example
├── .vscode/                # launch configs & tasks
├── .github/                # issue & PR templates
├── frameforge/
│   ├── backend/            # FastAPI + Comfy workflow JSON
│   ├── frontend/           # Angular UI
│   ├── mcp_server/         # MCP stdio → REST
│   ├── unity/              # FrameforgeSheetImport, etc.
│   ├── tests/
│   ├── data/               # local projects (gitignored content)
│   ├── logs/               # runtime logs (gitignored)
│   ├── start.ps1
│   └── stop.ps1
└── workflows/              # extra / experimental Comfy graphs (optional)
```

More size / no-scale notes: [`frameforge/README.md`](frameforge/README.md).

---

## Development

```powershell
# Health check while running
Invoke-WebRequest http://127.0.0.1:8787/health

# Optional tests
cd frameforge
.\backend\.venv\Scripts\python.exe -m pytest tests -q
```

Guidelines: [CONTRIBUTING.md](CONTRIBUTING.md). Prefer `npm run start` / `start.ps1` over ad-hoc uvicorn/`ng serve` unless you are debugging those scripts.

---

## Troubleshooting

| Symptom | Things to check |
|---------|-----------------|
| UI loads, generate fails | ComfyUI up? Models/nodes for the workflow installed? `frameforge/logs/backend.err.log` |
| MCP tools fail | Backend on `:8787`? MCP paths correct? Restart MCP host after config change |
| `install_to_unity` errors | `UNITY_PROJECT_ROOT` set and pointing at a real Unity project? |
| No animation frames | `ffmpeg` on PATH / `FFMPEG_PATH`? Video job finished in Comfy? |
| Port in use | `npm run stop`, then start again; check PIDs in `frameforge/logs/pids.json` |
| Wan OOM / very slow | Lower `wan_size` (256/512); free VRAM (`free_memory` via Comfy tooling if you use it) |

Security expectations for a local tool: [SECURITY.md](SECURITY.md).

---

## License

[MIT](LICENSE) — free to use, modify, and redistribute.

**Not included / separate terms:**

- ComfyUI, custom nodes, and **model weights** (Flux, Wan, SDXL, LoRAs, …) — their licenses and usage rules apply  
- **Generated images and animations** — ownership/usage depends on the models and your jurisdiction; Frameforge does not claim them  
- Third-party libraries (Angular, FastAPI, etc.) — see their licenses  

See also [NOTICE](NOTICE).

---

## Contributing

Bug reports, fixes, and small features are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

- Issues: use the GitHub templates under `.github/ISSUE_TEMPLATE/`  
- Security: report privately per [SECURITY.md](SECURITY.md) — do not file public issues for vulnerabilities  
