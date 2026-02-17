# Copilot Instructions — dnd-initiative-tracker

## Project summary
This is a Python desktop app (Tkinter) for the DM plus an optional LAN/mobile web client served via FastAPI + WebSockets.
The Tkinter UI runs on the main thread; the LAN server runs on a background thread; communication is queue-based.

**Important:** The main script filename is `dnd_initative_tracker.py` (historical typo). Do not rename it.

## Primary entry points
- `dnd_initative_tracker.py`: application entry point; main app class + LAN controller/config.
- `helper_script.py`: core UI and combat logic (combatants, conditions, map window, terrain presets).
- `assets/web/`: mobile/LAN client UI assets.
- `scripts/`: install/update/uninstall tooling for Linux + Windows.

## Setup (repo run)
- Create venv + install deps: `python -m venv .venv` then `pip install -r requirements.txt`
- Run: `python dnd_initative_tracker.py`

## Validation expectations (agent-friendly)
There is no formal test suite today. For PRs:
1. Run `python -m compileall .` to catch syntax errors.
2. If you touched LAN or `assets/web/`, run any available LAN smoke test scripts (see `scripts/`).
3. Keep changes minimal and targeted; avoid drive-by refactors.
4. Do not take screenshots. They usually arent helpful as the app is rendered in various UIs and doesnt have a connection

## How we collaborate (important)
When assigned an issue/bug:
1. Start with a short plan first (either PR description or an allow-empty commit titled `Initial plan`).
2. Implement in small commits with clear messages.
3. If review feedback arrives, batch fixes into a single follow-up commit (e.g., `Address review feedback`).

## Code style
- Follow existing style; keep line length ~120.
- Prefer type hints and docstrings for non-trivial logic.
- Preserve backwards compatibility: config files, saved state, and LAN protocol expectations.

## Data files (YAML)
- Monsters/Spells/players/presets YAML are data; avoid mass reformatting.
- Never introduce copyrighted non-SRD text/content. Keep additions consistent with existing schema.

## Safety / networking
- LAN server is intended for trusted local networks only.
- Do not add features that encourage internet exposure without explicit request.
