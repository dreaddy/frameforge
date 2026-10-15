# Frameforge (app tree)

Application code for **Frameforge**. Product overview: [repository root README](../README.md).

**Core:** animate images (local tools) → export for games — also automatable via MCP from Cursor and other coding agents.

## Size / MCP notes

`get_size_capabilities()` / `GET /presets/sizes` is the authoritative runtime catalog.

- Export sides: 16, 32, 48, 64, 128, 256, 512, 768, 1024  
- WAN square sides: 256, 512, 768, 1024 (768/1024 experimental on 16 GB GPUs)  

These are application presets, not a guarantee of native model training resolutions.

For no resizing: upload with `mode="upload", pixel_size=1024, no_scale=true, auto_crop=false, outline=false, drop_shadow=false`. Animate with `wan_size=1024, no_scale=true, method="i2v"`. Frame-size mismatches fail instead of resizing.

Restart the backend and MCP client after updating tools.
