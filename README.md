# dnd-initiative-tracker

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![UI](https://img.shields.io/badge/ui-tkinter-informational)
![LAN](https://img.shields.io/badge/LAN-fastapi%20%2B%20websocket-ffb000)
![Version](https://img.shields.io/badge/version-v41-lightgrey)

Aye, this be a D&D initiative tracker where the DM runs a Tk desktop app, and a wee LAN/mobile client lets players claim a PC and move their token on their turn.

---

## Table o’ Contents

- [What be aboard](#what-be-aboard)
- [Features](#features)
- [Installin’ the rig](#installin-the-rig)
- [Sailin’ it](#sailin-it)
- [LAN / Mobile POC](#lan--mobile-poc)
- [YAML files](#yaml-files)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Logs](#logs)
- [Troubleshootin’](#troubleshootin)
- [Safety notes](#safety-notes)

---

## What be aboard

- `dnd_initative_tracker.py` be the launcher that layers the LAN proof‑of‑concept atop the Tk app.
- `helper_script.py` holds the main Tk tracker and map-mode guts, so keep both files in the same folder.

---

## Features

### Initiative & combat (DM-side)
- Ye can add combatants, sort initiative, and step turns forward/back with hotkeys.
- Ye get quick HP tools (damage/heal), conditions, and death-save / DOT tools from the keyboard.

### Map mode (DM-side)
- Ye can open a grid map, drag units around, and place obstacles.
- Ye can paint rough terrain and water-ish tiles, and ye can save/load obstacle presets.
- Ye can drop AoE overlays as **circle**, **square**, or **line**, with names, colors, and optional save/damage metadata.
- Ye can load a background image if Pillow be installed.

### LAN / mobile (Player-side, POC)
- Aye, the app can run a FastAPI + WebSocket server in a background thread for local play.
- Players open a LAN URL on their phones, claim a PC, and only move **their** token, and only when it be **their** turn.
- Mobile view shows whose turn it be, plus move/action/bonus-action counters for the claimed creature.

---

## Installin’ the rig

### Required
- Aye, Python **3.9+** be needed.
- Tkinter must be present (often bundled; on Linux ye may need `python3-tk`).
- Install the Python dependencies from `requirements.txt` (includes `fastapi` and `uvicorn[standard]` for the LAN server).

### OS-level dependencies (Debian/Ubuntu)
Install the base Python bits with `apt`:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk python3-pip
```

Optional extras for image popups with Tk:

```bash
sudo apt install -y python3-pil.imagetk
```

### Supported platforms
- Debian/Ubuntu-based distros with `python3`, `python3-venv`, and `python3-tk` installed.
- A freedesktop-compliant desktop environment (for `.desktop` launchers and icons).

### Linux install
Run the installer script from the repo root:

```bash
./scripts/install-linux.sh
```

This copies the app to a per-user install directory, installs the launcher icon(s), and registers a `.desktop` file so the app shows up in your desktop menus.

To install Python dependencies from `requirements.txt`, run:

```bash
INSTALL_PIP_DEPS=1 ./scripts/install-linux.sh
```

Or install them manually:

```bash
python3 -m pip install --user -r requirements.txt
```

### Linux uninstall
Run the uninstall script from the repo root:

```bash
./scripts/uninstall-linux.sh
```

This removes the per-user install directory, the installed icon(s), and the `.desktop` launcher file.

---

## Sailin’ it

Run it from the folder that holds both scripts:

```bash
python dnd_initative_tracker.py
```

The DM uses the Tk window for initiative and the map, and the crew can join via the LAN menu if ye enable the server. If ye used the Linux installer, ye can also launch it from the desktop menu entry it registers.

---

## LAN / Mobile POC

### Start/stop the server
- Use **LAN → Start LAN Server** to hoist the server.
- Use **LAN → Stop LAN Server** to strike the sails.

### Share the link
- Use **LAN → Show LAN URL** to get the URL for phones on the same Wi‑Fi.
- Use **LAN → Show QR Code** to flash a scannable square on screen.
- Use **LAN → Sessions…** to see connected clients and who’s claimed what.

### Defaults ye can tweak (in `dnd_initative_tracker.py`)
- `POC_AUTO_START_LAN = True` starts the LAN server at launch.
- `POC_AUTO_SEED_PCS = True` auto-adds PCs from `players/` and rolls initiative (handy for SSH testin’).
- Aye, the default bind be `0.0.0.0:8787`, and ye can change it in the `LanConfig` dataclass if ye fancy another port.

---

## iOS/iPadOS Web Push (16.4+)

- iOS Web Push requires Add to Home Screen — Web Push only works for web apps saved to the Home Screen.
- Notification haptics/vibration are OS-controlled and not configurable in this app.

---

## YAML files

### Case-sensitive folders (Linux)
Linux be case-sensitive, so make sure the folders be named exactly `Monsters/` and `Spells/` (capitalized).

### `players/` (optional roster seed)
Aye, any `players/*.yaml` files be read to seed PCs when `POC_AUTO_SEED_PCS` be enabled.

Example:
```yaml
name: Alice
```

Roster names come from the filename (e.g., `players/John-Twilight.yaml` → `John Twilight`).

### `players/<Name>.yaml` (optional per-PC defaults)
If a file exists for a roster name, these keys be accepted in that file:
- `base_movement` or `speed` (feet per round).
- `swim_speed` (feet per round).
- `hp` (starting HP in the tracker).

Example:
```yaml
base_movement: 30
swim_speed: 15
hp: 27
```

### `Monsters/*.yml` or `Monsters/*.yaml` (optional monster library)
Drop YAML files in a `Monsters/` folder (from the working directory), and the “Add Combatant” name field becomes a dropdown.

Minimum viable example:
```yaml
monster:
  name: Goblin
  type: humanoid
  challenge:
    cr: 0.25
  defenses:
    hit_points:
      average: 7
  speed:
    walk_ft: 30
    swim_ft: 0
  abilities:
    dex: 14
  initiative:
    modifier: 2
  saving_throws:
    dex: +2
```

### `Spells/*.yml` or `Spells/*.yaml` (optional spell presets)
Drop YAML files in a `Spells/` folder (from the working directory) to populate the spell preset list for the LAN client.

---

## Keyboard shortcuts

Arrrr, these binds be wired in the Tk app:

| Key | What it does |
|---:|---|
| `Space` | Aye, it advances to the next turn. |
| `Shift` + `Space` | Aye, it goes back to the previous turn. |
| `d` | Aye, it opens the HP tool in **damage** mode. |
| `h` | Aye, it opens the HP tool in **heal** mode. |
| `c` | Aye, it opens the conditions tool. |
| `t` | Aye, it opens the death-saves / DOT tool. |
| `m` | Aye, it opens the move tool. |
| `w` | Aye, it toggles water for the selected creature (where supported). |
| `p` | Aye, it opens map mode. |

---

## Logs

- Battle narration goes to `./logs/battle.log`.
- LAN/server operations go to `./logs/operations.log`.

---

## Troubleshootin’

- if LAN says it needs FastAPI/uvicorn, install `fastapi` and `uvicorn[standard]`.
- if QR code complains, install `qrcode`, and install `pillow` for the image popup.
- if Pillow ImageTk be missing on Linux, ye may need a distro package like `python3-pil.imagetk`.
- if phones can’t connect, make sure all devices be on the same LAN/Wi‑Fi and yer firewall ain’t blockin’ port `8787`.

---

## Safety notes

- This LAN be meant for trusted local tables, and it ain’t hardened for the wider internet.
- Keep it on yer home/table Wi‑Fi, or add auth before ye sail into rougher waters.
