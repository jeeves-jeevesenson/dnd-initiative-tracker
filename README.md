# dnd-initiative-tracker

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![UI](https://img.shields.io/badge/ui-tkinter-informational)
![LAN](https://img.shields.io/badge/LAN-fastapi%2Bwebsocket-ffb000)
![Status](https://img.shields.io/badge/status-LAN%20POC-important)

A D&D initiative tracker with a chunky Tk desktop UI for the DM, plus a LAN/mobile web client so players can claim their PC and drag their token about on their own turn.

---

## Table o’ Contents

- [What be this?](#what-be-this)
- [Features](#features)
- [Installin’ the rig](#installin-the-rig)
- [Sailin’ it (DM + Players)](#sailin-it-dm--players)
- [Shortcuts](#shortcuts)
- [Files an’ Folders](#files-an-folders)
- [Monsters YAML Library](#monsters-yaml-library)
- [Troubleshootin’](#troubleshootin)
- [Roadmap](#roadmap)

---

## What be this?

- The **DM** runs the Tk app on a laptop/desktop.
- The app can also run a **LAN server** so players can open a phone page, **claim a PC**, and move only their own token (only on their turn).

> WARNING: This LAN be meant fer trusted local networks, matey, not the open seas o’ the internet.

---

## Features

### Initiative & Combat
- Add combatants, track rounds/turns, and keep a battle log.
- Quick HP tools and condition/death-save widgets (DM-side).

### Map Mode (DM-side)
- Grid map with tokens, obstacles, rough terrain, and AoE overlays.
- Save/load presets for obstacles and rough terrain.
- Optional background images (requires Pillow).

### LAN / Mobile (Player-side, POC)
- Phone UI shows the map, whose turn it be, and yer movement/action counters.
- Claim a PC, then drag yer token around when it’s yer turn.
- DM menu can show LAN URL, QR code, and a Sessions panel.

---

## Installin’ the rig

### Requirements
- Python **3.9+**
- Tkinter (usually bundled with Python; on some Linux distros ye may need `python3-tk` from yer package manager)

### Optional but mighty useful deps
- **LAN server**: `fastapi` + `uvicorn`
- **YAML** monsters/roster: `pyyaml`
- **Images / QR code**: `pillow` (+ `qrcode` for the QR popup)

### Quick install (pip)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip

# LAN + YAML + images + QR (the “just gimme everything” haul)
python -m pip install fastapi uvicorn[standard] pyyaml pillow qrcode
