# D&D Initiative Tracker

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![UI](https://img.shields.io/badge/ui-tkinter-informational)
![LAN](https://img.shields.io/badge/LAN-fastapi%20%2B%20websocket-ffb000)
![License](https://img.shields.io/badge/license-MIT-green)

A desktop-first D&D 5e combat tracker for Dungeon Masters, with an optional local-network web client for players.

- **DM app:** Python + Tkinter desktop UI
- **Player app:** FastAPI + WebSocket mobile web client
- **Data model:** YAML-driven monsters, spells, players, and map presets

> **Important:** the main entry script is intentionally named `dnd_initative_tracker.py` (historical typo kept for compatibility). Do not rename it.

## 📚 Table of Contents

- [What this project does](#what-this-project-does)
- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Updating and uninstalling](#updating-and-uninstalling)
- [Running the tracker](#running-the-tracker)
- [LAN/mobile client](#lanmobile-client)
- [Map mode](#map-mode)
- [Configuration](#configuration)
- [YAML data files](#yaml-data-files)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Development and testing](#development-and-testing)
- [Contributing](#contributing)
- [Safety and security](#safety-and-security)
- [License and attribution](#license-and-attribution)

## What this project does

D&D Initiative Tracker is built for running combat quickly at the table while keeping player information synchronized.

### Core DM capabilities

- Add combatants and sort initiative
- Advance rounds/turns with keyboard shortcuts
- Apply damage, healing, and death saves
- Track 2024 Basic Rules conditions and durations
- Open battle map with token movement and terrain costs
- Keep battle and operations logs in `logs/`

### Core player capabilities (LAN mode)

- Join from phone/tablet/laptop browser on local network
- Claim and control assigned character during their turn
- See turn prompts, movement/action counters, and character state
- Use map interactions when permitted by DM controls

## Architecture at a glance

The app is intentionally split between desktop UI and LAN server responsibilities:

- **`helper_script.py`**
  - Core Tkinter UI
  - Initiative/combat state management
  - Map mode rendering and tools
- **`dnd_initative_tracker.py`**
  - Main app entry point
  - LAN server lifecycle and client sync
  - Host/player assignment integration
- **`assets/web/lan/`**
  - Player-facing web client
  - State updates over WebSockets
- **Queue-based thread model**
  - Tkinter stays on the main thread
  - LAN server runs in a background thread

## 🚀 Quick start

### Linux / macOS (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.sh | bash
```

Or:

```bash
wget -qO- https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.sh | bash
```

### Windows (recommended)

```powershell
irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.ps1 | iex
```

If execution policy blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.ps1 | iex"
```

After install, launch the app from your shortcut/launcher and start LAN mode from **LAN → Start LAN Server** when needed.

## Installation

### Prerequisites

- Python **3.9+**
- `pip`
- Git
- Tkinter (often bundled; Linux may need `python3-tk`)

### Manual install (all platforms)

```bash
git clone https://github.com/jeeves-jeevesenson/dnd-initiative-tracker.git
cd dnd-initiative-tracker
python -m venv .venv
```

Activate venv:

- Linux/macOS:
  ```bash
  source .venv/bin/activate
  ```
- Windows:
  ```powershell
  .venv\Scripts\activate
  ```

Install dependencies and run:

```bash
pip install -r requirements.txt
python dnd_initative_tracker.py
```

### Platform notes

- **Linux quick install** places app files in `~/.local/share/dnd-initiative-tracker`
- **Windows quick install** places app files in `%LOCALAPPDATA%\DnDInitiativeTracker`
- Quick install scripts are idempotent and can update an existing install

## Updating and uninstalling

### Updating

You can update from within the app via **Help → Check for Updates**, or run scripts directly.

- Linux/macOS quick-install path:
  ```bash
  cd ~/.local/share/dnd-initiative-tracker
  ./scripts/update-linux.sh
  ```
- Windows quick-install path:
  ```powershell
  cd $env:LOCALAPPDATA\DnDInitiativeTracker
  .\scripts\update-windows.ps1
  ```
- Manual clone installs:
  ```bash
  git pull origin main
  pip install -r requirements.txt
  ```

### Uninstalling

- Linux/macOS:
  ```bash
  curl -sSL https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/uninstall-linux.sh | bash
  ```
- Windows:
  ```powershell
  irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/uninstall-windows.ps1 | iex
  ```

If manually installed, remove the repository folder and its virtual environment.

## Running the tracker

From a clone:

```bash
python dnd_initative_tracker.py
```

Typical DM flow:

1. Add PCs/monsters and set initiative
2. Sort initiative and start combat
3. Use tools for damage/healing/conditions
4. Open map mode for movement and AoE
5. (Optional) start LAN server for player devices

## LAN/mobile client

LAN mode is optional and intended for trusted local networks.

### Quick setup

1. In DM app: **LAN → Start LAN Server**
2. Share URL via **LAN → Show LAN URL** or **LAN → Show QR Code**
3. Players open URL in browser (same local network)
4. DM can monitor with **LAN → Sessions...**

Default bind settings are in `dnd_initative_tracker.py` (`LanConfig`, default port `8787`).

### Optional startup behavior

You can change startup behavior in `dnd_initative_tracker.py`:

```python
POC_AUTO_START_LAN = True
POC_AUTO_SEED_PCS = True
```

### iOS/iPadOS web push

For iOS web push support:

- iOS/iPadOS 16.4+
- Add web app to Home Screen
- Enable notifications in iOS settings

## Map mode

Map mode provides a grid-based battle area with turn-aware movement.

Key capabilities:

- Drag-and-drop token movement
- Terrain painting (rough/swim-capable presets)
- Obstacle placement
- AoE overlays (circle/square/line)
- Optional background image support (Pillow)

## Configuration

Primary runtime toggles are in `dnd_initative_tracker.py`.

Commonly adjusted settings:

- LAN bind host/port/admin password (`LanConfig`)
- Auto-start LAN and auto-seed PCs
- Host assignment behavior

You can also customize defaults in `helper_script.py`:

- `DEFAULT_STARTING_PLAYERS`
- `DEFAULT_ROUGH_TERRAIN_PRESETS`
- `DAMAGE_TYPES`

## YAML data files

This project is data-driven; YAML content controls most game data.

- `Monsters/*.yaml` — monster stat blocks
- `Spells/*.yaml` — spell definitions/mechanics
- `players/*.yaml` — player character defaults
- `Items/Weapons/*.yaml` / `Items/Armor/*.yaml` — structured item definitions (draft schema)
- `presets/` — terrain/obstacle presets

See schema docs:

- [`Monsters/README.md`](Monsters/README.md)
- [`Spells/README.md`](Spells/README.md)
- [`players/README.md`](players/README.md)

### File/folder naming note (Linux)

Keep directory casing exactly as expected:

- `Monsters/` (capital `M`)
- `Spells/` (capital `S`)

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Space` | Next turn |
| `Shift+Space` | Previous turn |
| `d` | Damage tool |
| `h` | Heal tool |
| `c` | Conditions tool |
| `t` | Death saves / DOT tool |
| `p` | Open map mode |

## Troubleshooting

### `No module named fastapi`

```bash
pip install fastapi "uvicorn[standard]"
```

### `No module named qrcode` or PIL errors

```bash
pip install qrcode pillow
```

### `Tkinter` missing on Linux

```bash
sudo apt install python3-tk
```

### Players cannot connect in LAN mode

Check:

1. Devices are on the same network
2. Firewall allows chosen LAN port (default `8787`)
3. URL points to host machine local IP
4. DM app LAN server is actually running

## 🧪 Development and testing

### Repository layout

- `dnd_initative_tracker.py` — app entry point + LAN integration
- `helper_script.py` — core UI/combat logic
- `assets/web/` — LAN web client files
- `scripts/` — install/update/uninstall and smoke-test scripts
- `tests/` — Python test suite

### Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### Validation commands

```bash
python -m compileall .
python -m pytest
```

If you modify LAN/web behavior, run LAN smoke tooling in `scripts/` (for example `scripts/lan-smoke-playwright.py`).

## Contributing

Contributions are welcome via pull requests.

Please keep changes:

- small and reviewable
- backward compatible (especially YAML schemas and LAN payload expectations)
- documented when behavior changes

For bug reports, include:

- OS + Python version
- exact repro steps
- expected vs actual behavior
- relevant logs/screenshots

## ⚠️ Safety and security

- LAN server is designed for **trusted local networks only**
- Do **not** expose directly to the public internet
- For remote sessions, use VPN and your own access controls
- Player/IP assignment data stays local on the host machine

## License and attribution

- Project license: **MIT**
- Not affiliated with Wizards of the Coast
- Data/source notes are documented in folder-specific READMEs

Happy gaming, and good luck behind the screen.
