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

- Aye, `dnd_initative_tracker.py` be the launcher that layers the LAN proof‑of‑concept atop the Tk app.
- Aye, `helper_script.py` holds the main Tk tracker and map-mode guts, so keep both files in the same folder.

---

## Features

### Initiative & combat (DM-side)
- Aye, ye can add combatants, sort initiative, and step turns forward/back with hotkeys.
- Aye, ye get quick HP tools (damage/heal), conditions, and death-save / DOT tools from the keyboard.

### Map mode (DM-side)
- Aye, ye can open a grid map, drag units around, and place obstacles.
- Aye, ye can paint rough terrain and water-ish tiles, and ye can save/load obstacle presets.
- Aye, ye can drop AoE overlays as **circle**, **square**, or **line**, with names, colors, and optional save/damage metadata.
- Aye, ye can load a background image if Pillow be installed.

### LAN / mobile (Player-side, POC)
- Aye, the app can run a FastAPI + WebSocket server in a background thread for local play.
- Aye, players open a LAN URL on their phones, claim a PC, and only move **their** token, and only when it be **their** turn.
- Aye, the phone view shows whose turn it be, plus move/action/bonus-action counters for the claimed creature.

---

## Installin’ the rig

### Required
- Aye, Python **3.9+** be needed.
- Aye, Tkinter must be present (often bundled; on Linux ye may need `python3-tk`).

### Optional (for extra plunder)
- Aye, LAN server wants: `fastapi` and `uvicorn[standard]`.
- Aye, monster YAML library wants: `pyyaml`.
- Aye, images (map backgrounds + QR popup) want: `pillow`.
- Aye, QR code generation wants: `qrcode`.

### One-liner install (pip)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install fastapi uvicorn[standard] pyyaml pillow qrcode
```

---

## Sailin’ it

Aye, run it from the folder that holds both scripts:

```bash
python dnd_initative_tracker.py
```

Aye, the DM uses the Tk window for initiative and the map, and the crew can join via the LAN menu if ye enable the server.

---

## LAN / Mobile POC

### Start/stop the server
- Aye, use **LAN → Start LAN Server** to hoist the server.
- Aye, use **LAN → Stop LAN Server** to strike the sails.

### Share the link
- Aye, use **LAN → Show LAN URL** to get the URL for phones on the same Wi‑Fi.
- Aye, use **LAN → Show QR Code** to flash a scannable square on screen.
- Aye, use **LAN → Sessions…** to see connected clients and who’s claimed what.

### Defaults ye can tweak (in `dnd_initative_tracker.py`)
- Aye, `POC_AUTO_START_LAN = True` starts the LAN server at launch.
- Aye, `POC_AUTO_SEED_PCS = True` auto-adds PCs from `startingplayers.yaml` and rolls initiative (handy for SSH testin’).
- Aye, the default bind be `0.0.0.0:8787`, and ye can change it in the `LanConfig` dataclass if ye fancy another port.

---

## YAML files

### `startingplayers.yaml` (optional roster seed)
Aye, this file be read to seed PCs when `POC_AUTO_SEED_PCS` be enabled.

Example:
```yaml
players:
  - Alice
  - Bob
  - Cleric
```

### `players/<Name>.yaml` (optional per-PC defaults)
Aye, if a file exists for a roster name, these keys be accepted:
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
Aye, drop YAML files in a `Monsters/` folder (from the working directory), and the “Add Combatant” name field becomes a dropdown.

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

---

## Keyboard shortcuts

Aye, these binds be wired in the Tk app:

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

- Aye, battle narration goes to `./logs/battle.log`.
- Aye, LAN/server operations go to `./logs/operations.log`.

---

## Troubleshootin’

- Aye, if LAN says it needs FastAPI/uvicorn, install `fastapi` and `uvicorn[standard]`.
- Aye, if QR code complains, install `qrcode`, and install `pillow` for the image popup.
- Aye, if Pillow ImageTk be missing on Linux, ye may need a distro package like `python3-pil.imagetk`.
- Aye, if phones can’t connect, make sure all devices be on the same LAN/Wi‑Fi and yer firewall ain’t blockin’ port `8787`.

---

## Safety notes

- Aye, this LAN be meant for trusted local tables, and it ain’t hardened for the wider internet.
- Aye, keep it on yer home/table Wi‑Fi, or add auth before ye sail into rougher waters.
