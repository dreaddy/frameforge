# Contributing to Frameforge

Thanks for helping. Small, focused changes are easiest to review.

## What this project is

Frameforge **animates images for games** (preferring local tools) and **exports** them (e.g. Unity spritesheets). UI and MCP should stay aligned so agent prompts like “create X, animate it, install into Unity” keep working.

## Development setup

Follow the Quick start in [README.md](README.md). Keep ComfyUI available if you touch generation or animation paths.

```powershell
Invoke-WebRequest http://127.0.0.1:8787/health

cd frameforge
.\backend\.venv\Scripts\python.exe -m pytest tests -q
```

(If needed: `pip install pytest` in the backend venv.)

## Guidelines

- Prefer small PRs over large refactors unless agreed up front  
- Do not commit `data/game_projects/`, logs, `.venv`, `node_modules`, or local `.env`  
- Match existing style in the file you edit  
- For Unity C#: no reflection; no `GameObject.Find` by name — use serialized references  
- Start via `npm run start` / `start.ps1`, not ad-hoc uvicorn/ng unless debugging those scripts  
- Keep MCP tool behavior discoverable for agents (clear names, stable IDs, good errors)  

## Pull requests

1. Why the change exists  
2. How you tested (UI / API / MCP / Unity)  
3. ComfyUI or model assumptions if generation/animation behavior changes  

## License

Contributions are licensed under the [MIT License](LICENSE).
