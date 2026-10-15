# Security Policy

## Scope

Frameforge is a **local** developer tool. The FastAPI backend and Angular UI bind to `127.0.0.1` by default and are not meant to be exposed to the internet without your own hardening (auth, TLS, reverse proxy, firewall).

MCP tools can write into a configured Unity project (`UNITY_PROJECT_ROOT`). Treat that path as trusted.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Contact the maintainers privately (e.g. GitHub Security Advisories, or a channel agreed with the project owner) and include:

- Affected component (backend, MCP, Unity importer, …)  
- Steps to reproduce  
- Impact  
- Suggested fix if you have one  

## Hardening tips

- Do not publish ports `4200` / `8787` / `8000` beyond localhost unless you intentionally secure them  
- Point `UNITY_PROJECT_ROOT` and MCP paths only at projects you trust  
- Treat ComfyUI and Ollama as trusted local services on your machine  
