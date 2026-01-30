#!/usr/bin/env python3
"""
DnD Initiative Tracker (v41) — LAN Proof-of-Concept

This edition layers a small LAN/mobile web client on top of the Tk app without rewriting it.
- DM runs the Tk app.
- LAN server starts automatically (and can be stopped/restarted from the "LAN" menu).
- Players open the LAN URL on mobile and are auto-assigned a Player Character by IP, then can move their token (on their turn).
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
import json
import queue
import socket
import ipaddress
import fnmatch
import importlib.util
import importlib
import threading
import time
import logging
import re
import os
import hashlib
import hmac
import secrets
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox, ttk

# Monster YAML loader (PyYAML)
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

# Import the full tracker as the base.
# Keep this file in the same folder as helper_script.py
try:
    import helper_script as base
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "Arrr! I can’t find/load helper_script.py in this folder.\n"
        "Make sure helper_script and dnd_initative_tracker be in the same directory.\n\n"
        f"Import error: {e}"
    )


def _ensure_logs_dir() -> Path:
    """Create ./logs in the current working directory (best effort)."""
    try:
        base_dir = Path.cwd()
    except Exception:
        base_dir = Path(".")
    logs = base_dir / "logs"
    try:
        logs.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return logs


def _make_ops_logger() -> logging.Logger:
    """Return a logger that writes to terminal + ./logs/operations.log."""
    lg = logging.getLogger("inittracker.ops")
    if getattr(lg, "_inittracker_configured", False):
        return lg

    lg.setLevel(logging.INFO)
    logs = _ensure_logs_dir()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")

    try:
        fh = logging.FileHandler(logs / "operations.log", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception:
        pass

    try:
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        lg.addHandler(sh)
    except Exception:
        pass

    lg.propagate = False
    setattr(lg, "_inittracker_configured", True)
    return lg


def _read_index_file(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_index_file(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _file_stat_metadata(fp: Path) -> Dict[str, object]:
    try:
        stat = fp.stat()
        return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
    except Exception:
        return {"mtime_ns": 0, "size": 0}


def _metadata_matches(entry: Dict[str, object], meta: Dict[str, object]) -> bool:
    return entry.get("mtime_ns") == meta.get("mtime_ns") and entry.get("size") == meta.get("size")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- App metadata ---
APP_VERSION = "41"

# --- LAN POC switches ---
POC_AUTO_START_LAN = True
POC_AUTO_SEED_PCS = True  # auto-add Player Characters from startingplayers.yaml (useful over SSH testing)

DAMAGE_TYPES = list(base.DAMAGE_TYPES)


def _build_damage_type_options(damage_types: List[str]) -> str:
    return "\n".join(
        f'              <option value="{damage_type}">{damage_type}</option>'
        if damage_type
        else '              <option value=""></option>'
        for damage_type in damage_types
    )


DAMAGE_TYPE_OPTIONS = _build_damage_type_options(DAMAGE_TYPES)

# ----------------------------- LAN Server -----------------------------

HTML_INDEX = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="default" />
  <meta name="apple-mobile-web-app-title" content="InitTracker LAN" />
  <link rel="apple-touch-icon" href="/assets/graphic.png" />
  <link rel="manifest" href="/assets/manifest.webmanifest" />
  <title>InitTracker LAN</title>
  <script>window.PUSH_PUBLIC_KEY=__PUSH_PUBLIC_KEY__;</script>
  <style>
    :root{
      --bg:#0b0d10;
      --panel:#141923;
      --panel2:#0f1320;
      --text:#e8eef7;
      --muted:#93a2b8;
      --accent:#6aa9ff;
      --danger:#ff5b5b;
      --safeInsetTop: env(safe-area-inset-top, 0px);
      --safeInsetBottom: env(safe-area-inset-bottom, 0px);
      --modalTopOffset: 0px;
      --modalBottomOffset: 0px;
      --topbar-height: 0px;
      --bottombar-height: 0px;
    }
    html,body{height:100%; margin:0; background:var(--bg); color:var(--text); font-family: system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif; overflow:hidden;}
    .app{height:100dvh; display:flex; flex-direction:column; min-height:0;}
    .topbar{
      padding: calc(10px + var(--safeInsetTop)) 12px 10px 12px;
      background: linear-gradient(180deg, var(--panel), var(--panel2));
      border-bottom: 1px solid rgba(255,255,255,0.08);
      display:flex; align-items:center; gap:10px; flex-wrap:wrap;
      position:sticky; top:0; z-index:20;
    }
    .topbar h1{font-size:14px; margin:0; font-weight:650;}
    .pill{font-size:12px; color:var(--muted); padding:6px 10px; border:1px solid rgba(255,255,255,0.10); border-radius:999px;}
    .conn-wrap{
      position:relative;
      display:inline-flex;
      align-items:center;
    }
    .conn-pill{
      display:inline-flex;
      align-items:center;
      gap:6px;
      cursor:pointer;
      background: transparent;
      font: inherit;
    }
    .conn-full-text{display:inline;}
    .conn-compact-label,
    .conn-compact-dot{display:none;}
    .conn-compact .conn-full-text{display:none;}
    .conn-compact .conn-compact-label,
    .conn-compact .conn-compact-dot{display:inline-flex;}
    .conn-compact-label{font-weight:700; letter-spacing:0.5px;}
    .conn-compact-dot{
      width:8px;
      height:8px;
      border-radius:50%;
      background: var(--accent);
    }
    .conn-popover{
      position:absolute;
      top: calc(100% + 10px);
      left: 0;
      min-width: 160px;
      padding: 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(15,19,32,0.98);
      box-shadow: 0 12px 30px rgba(0,0,0,0.45);
      display:flex;
      flex-direction:column;
      gap:10px;
      opacity:0;
      transform: translateY(-4px);
      pointer-events:none;
      transition: opacity 0.15s ease, transform 0.15s ease;
      z-index: 30;
    }
    .conn-popover::before{
      content:"";
      position:absolute;
      top: -6px;
      left: 16px;
      width: 12px;
      height: 12px;
      background: rgba(15,19,32,0.98);
      border-left: 1px solid rgba(255,255,255,0.12);
      border-top: 1px solid rgba(255,255,255,0.12);
      transform: rotate(45deg);
    }
    .conn-popover.show{
      opacity:1;
      transform: translateY(0);
      pointer-events:auto;
    }
    .conn-popover-status{
      font-size:12px;
      color: var(--muted);
    }
    .conn-style-toggle{
      display:inline-flex;
      gap:6px;
      flex-wrap:wrap;
    }
    .conn-style-btn{
      padding:6px 10px;
      font-size:12px;
    }
    .conn-style-btn.active{
      border-color: rgba(106,169,255,0.65);
      background: rgba(106,169,255,0.2);
      color: var(--text);
    }
    .menu-wrap{
      position:relative;
      display:inline-flex;
      align-items:center;
    }
    .menu-btn{
      display:inline-flex;
      align-items:center;
      gap:6px;
    }
    .menu-popover{
      position:absolute;
      top: calc(100% + 10px);
      left: 0;
      min-width: 190px;
      padding: 6px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(15,19,32,0.98);
      box-shadow: 0 12px 30px rgba(0,0,0,0.45);
      display:flex;
      flex-direction:column;
      gap:6px;
      opacity:0;
      transform: translateY(-4px);
      pointer-events:none;
      transition: opacity 0.15s ease, transform 0.15s ease;
      z-index: 30;
    }
    .menu-popover.show{
      opacity:1;
      transform: translateY(0);
      pointer-events:auto;
    }
    .menu-item{
      border:none;
      background: transparent;
      color: var(--text);
      font-size: 13px;
      font-weight: 600;
      text-align: left;
      padding: 8px 10px;
      border-radius: 10px;
      cursor:pointer;
    }
    .menu-item:hover,
    .menu-item:focus{
      background: rgba(255,255,255,0.08);
      outline:none;
    }
    .hidden{display:none !important;}
    .spacer{flex:1;}
    .btn{
      border:1px solid rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 13px;
      font-weight: 650;
      touch-action: manipulation;
    }
    .btn:active{transform: translateY(1px);}
    .btn.danger{background: rgba(255,91,91,0.14); border-color: rgba(255,91,91,0.35);}
    .btn.accent{background: rgba(106,169,255,0.14); border-color: rgba(106,169,255,0.35);}
    .topbar-controls{
      display:flex;
      flex-wrap:wrap;
      gap:10px;
      align-items:center;
    }

    .mapWrap{flex:1 1 auto; min-height:0; position:relative; overflow:hidden; background:#0a0c12;}
    canvas{position:absolute; inset:0; width:100%; height:100%; touch-action:none;}
    .map-tooltip{
      position:absolute;
      z-index:4;
      pointer-events:none;
      max-width:240px;
      padding:4px 8px;
      border-radius:6px;
      background:rgba(16,18,24,0.92);
      color:#eef2f7;
      font-size:12px;
      font-weight:600;
      box-shadow:0 2px 8px rgba(0,0,0,0.35);
      opacity:0;
      transition:opacity 0.08s ease;
      white-space:nowrap;
    }
    .map-tooltip.show{opacity:1;}
    .waiting{
      position:absolute; inset:0; display:none; align-items:center; justify-content:center;
      background: rgba(10,12,18,0.82); color: var(--muted); font-size: 16px; letter-spacing: 0.4px;
      text-transform: lowercase;
    }
    .waiting.show{display:flex;}

    .sheet-wrap{
      position:sticky; bottom:0; z-index:20;
      display:flex; flex-direction:column;
      background: rgba(20,25,35,0.92);
      border-top: 1px solid rgba(255,255,255,0.08);
      backdrop-filter: blur(10px);
      min-height: 180px;
      max-height: 75vh;
    }
    .sheet-handle{
      height: 18px;
      display:flex;
      align-items:center;
      justify-content:center;
      cursor: ns-resize;
      touch-action: none;
      flex:0 0 auto;
    }
    .menus-locked .sheet-handle{
      cursor: not-allowed;
      opacity: 0.45;
      pointer-events: none;
    }
    .sheet-handle::before{
      content:"";
      width: 44px;
      height: 4px;
      border-radius: 999px;
      background: rgba(255,255,255,0.25);
    }
    .sheet{
      padding: 10px 12px calc(12px + var(--safeInsetBottom)) 12px;
      display:flex;
      flex-direction:column;
      flex:1 1 auto;
      min-height:0;
    }
    .sheet-content{
      display:flex;
      flex-direction:column;
      flex:1 1 auto;
      min-height:0;
    }
    .cast-panel{
      margin-top: 10px;
      padding: 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(10,14,22,0.55);
    }
    .turn-alerts-panel{
      margin-top: 10px;
      padding: 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(10,14,22,0.55);
    }
    .turn-alerts-panel legend{
      padding: 0 6px;
      font-weight: 700;
    }
    .turn-alerts-row{
      display:flex;
      gap:10px;
      align-items:center;
      flex-wrap:wrap;
    }
    .turn-alerts-status{
      font-size: 12px;
      color: var(--muted);
    }
    .turn-alerts-note{
      margin-top: 6px;
      font-size: 11px;
      color: var(--muted);
    }
    .cast-panel summary{
      cursor:pointer;
      font-weight:700;
      list-style:none;
    }
    .cast-panel summary::-webkit-details-marker{display:none;}
    .cast-panel[open] summary{margin-bottom:8px;}
    .cast-menu-trigger{
      margin-top: 10px;
      display:flex;
    }
    .cast-menu-trigger .btn{
      flex:1;
    }
    .cast-overlay{
      background: var(--bg);
      display:none;
      flex-direction:column;
      padding: 10px 12px calc(12px + var(--safeInsetBottom)) 12px;
      z-index:40;
      height:100%;
      overflow:auto;
      flex:1 1 auto;
      min-height: 0;
    }
    .cast-overlay.show{
      display:flex;
    }
    .cast-overlay-header{
      display:flex;
      align-items:center;
      gap:12px;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .cast-overlay-header .btn{
      white-space: nowrap;
    }
    .cast-overlay-title{
      font-size: 14px;
      font-weight: 700;
    }
    .cast-overlay-spacer{
      flex:1;
    }
    .cast-overlay-body{
      margin-top: 10px;
      overflow:auto;
      flex:1 1 auto;
      min-height:0;
    }
    .cast-overlay .cast-panel{
      margin-top: 0;
      padding: 0;
      border: none;
      background: transparent;
    }
    .spell-select-overlay{
      position:fixed;
      inset: 0;
      top: var(--topbar-height);
      bottom: var(--bottombar-height);
      background: var(--bg);
      display:none;
      flex-direction:column;
      padding: 10px 12px calc(12px + var(--safeInsetBottom)) 12px;
      z-index:45;
      min-height:0;
    }
    .spell-select-overlay.show{
      display:flex;
    }
    .spell-select-header{
      display:flex;
      align-items:center;
      gap:12px;
      padding-bottom:8px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      flex-wrap:wrap;
    }
    .spell-select-title{
      font-size: 14px;
      font-weight: 700;
    }
    .spell-select-spacer{
      flex:1;
    }
    .spell-select-body{
      margin-top: 10px;
      display:flex;
      flex-direction:column;
      gap:10px;
      flex:1 1 auto;
      min-height:0;
    }
    .spell-select-summary{
      font-size: 12px;
      color: var(--muted);
    }
    .spell-select-table-wrap{
      overflow:auto;
      max-height: calc(100dvh - var(--topbar-height) - var(--bottombar-height) - 170px);
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(8,12,20,0.6);
    }
    .spell-select-table{
      width:100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .spell-select-table th,
    .spell-select-table td{
      padding: 8px 10px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      text-align:left;
      vertical-align:top;
    }
    .spell-select-check-col,
    .spell-select-check-cell{
      width: 38px;
      text-align:center;
    }
    .spell-select-overlay:not(.selecting) .spell-select-check-col,
    .spell-select-overlay:not(.selecting) .spell-select-check-cell{
      display:none;
    }
    .spell-select-table th{
      position: sticky;
      top: 0;
      background: rgba(12,16,26,0.98);
      z-index: 2;
      font-size: 11px;
      letter-spacing: 0.3px;
      text-transform: uppercase;
      color: var(--muted);
    }
    .spell-select-table tr:last-child td{
      border-bottom:none;
    }
    .spell-select-name-btn{
      background: none;
      border: none;
      padding: 0;
      color: var(--accent);
      cursor:pointer;
      font-weight: 600;
      text-align:left;
    }
    .spell-select-link{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }
    .spell-select-link:hover{
      text-decoration: underline;
    }
    .spell-select-details-row td{
      padding-top: 0;
      background: rgba(10,14,22,0.45);
    }
    .spell-select-details-row details{
      padding: 6px 0 10px 0;
    }
    .spell-select-details-row summary{
      cursor:pointer;
      list-style:none;
      font-weight: 700;
      color: var(--text);
    }
    .spell-select-details-row summary::-webkit-details-marker{display:none;}
    .spell-select-details-grid{
      margin-top: 8px;
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 6px;
      font-size: 11px;
      color: var(--muted);
    }
    .spell-select-actions{
      display:flex;
      align-items:center;
      gap:8px;
      flex-wrap:wrap;
    }
    .spell-select-overlay:not(.selecting) .spell-select-save-btn{
      display:none;
    }
    .spell-select-details-item strong{
      color: var(--text);
      font-weight: 600;
      display:block;
      margin-bottom: 2px;
    }
    .spell-select-controls{
      display:flex;
      gap:8px;
      align-items:center;
    }
    .spell-select-controls select{
      flex:1;
    }
    .form-grid{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap:8px;
    }
    .spell-filter-panel{
      margin-bottom: 10px;
      padding: 8px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(8,12,20,0.6);
    }
    .spell-filter-panel legend{
      padding: 0 6px;
      font-weight: 700;
      font-size: 12px;
    }
    .spell-details{
      margin-top: 10px;
      padding: 8px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(8,12,20,0.6);
      font-size: 12px;
      color: var(--muted);
    }
    .spell-details-grid{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 6px;
    }
    .spell-details-row{
      display:flex;
      gap:6px;
      align-items:baseline;
    }
    .spell-details-label{
      font-size: 11px;
      color: var(--muted);
      min-width: 64px;
    }
    .spell-details-value{
      font-size: 12px;
      color: var(--text);
      font-weight: 600;
    }
    .manual-entry-badge{
      display: none;
      align-items: center;
      gap: 4px;
      padding: 2px 6px;
      border-radius: 999px;
      border: 1px solid rgba(255,180,90,0.6);
      background: rgba(255,140,60,0.2);
      color: #ffcc9b;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .manual-entry-badge.show{
      display: inline-flex;
    }
    .form-field{display:flex; flex-direction:column; gap:4px;}
    .form-field label{font-size:11px; color:var(--muted);}
    .form-field input,
    .form-field select{
      border:1px solid rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 12px;
    }
    .form-field select{
      background: var(--panel2);
      color: var(--text);
    }
    .form-field select option{
      background: var(--panel2);
      color: var(--text);
    }
    .form-field input[type="color"]{
      padding:0;
      height:36px;
      width:100%;
      border:none;
      background:none;
    }
    .damage-type-controls{
      display:flex;
      gap:6px;
      align-items:center;
    }
    .damage-type-controls select{flex:1;}
    .damage-type-list{
      display:flex;
      flex-wrap:wrap;
      gap:6px;
      min-height:24px;
    }
    .damage-type-chip{
      display:inline-flex;
      align-items:center;
      gap:6px;
    }
    .chip button{
      border:none;
      background:none;
      color: var(--text);
      font-size: 14px;
      cursor:pointer;
      padding:0;
      line-height:1;
    }
    .form-actions{margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;}
    .row{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
    .row + .row{margin-top:10px;}
    .sheet-actions{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
    .initiative-hidden .sheet-turn-order-row{display:none;}
    .initiative-compact .turn-order{max-height: 60px; overflow:auto;}
    .initiative-compact .turn-order-status{display:none;}
    .label{font-size:12px; color:var(--muted);}
    .value{font-size:14px; font-weight:700;}
    .chip{font-size:12px; padding:6px 10px; border-radius:999px; border:1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05);}
    .chip input{margin-right:6px;}
    .turn-order{display:flex; flex-wrap:wrap; gap:6px; align-items:center;}
    .turn-chip{
      min-width: 26px;
      font-size:12px;
      padding:4px 8px;
      border-radius:999px;
      border:1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      display:inline-flex;
      align-items:center;
      gap:6px;
    }
    .turn-chip-index{font-weight:700;}
    .turn-chip-name{
      max-width: 140px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .turn-chip-marker{
      display:none;
      width:8px;
      height:8px;
      border-radius:50%;
      background: rgba(255,255,255,0.3);
      flex:0 0 auto;
    }
    .turn-chip-marker.active-marker{
      background: var(--accent);
      box-shadow: 0 0 6px rgba(106,169,255,0.6);
    }
    .turn-chip-marker.claimed-marker{
      background: rgba(106,169,255,0.55);
      border: 1px solid rgba(106,169,255,0.85);
    }
    .initiative-compact .turn-chip-name{display:none;}
    .initiative-compact .turn-chip-marker{display:inline-block;}
    .initiative-compact .turn-chip.active{
      background: rgba(106,169,255,0.2);
      border-color: var(--accent);
      box-shadow: 0 0 0 1px rgba(106,169,255,0.5);
    }
    .turn-chip.claimed{
      border-color: rgba(106,169,255,0.45);
      box-shadow: inset 0 0 0 1px rgba(106,169,255,0.18);
    }
    .turn-chip.active{
      border-color: var(--accent);
      box-shadow: 0 0 0 1px rgba(106,169,255,0.35);
    }
    .modal{
      position:fixed; inset:0; background: rgba(0,0,0,0.55);
      display:none; align-items:center; justify-content:center;
      padding: calc(var(--modalTopOffset) + 12px) 14px calc(var(--modalBottomOffset) + 12px);
    }
    .modal.show{display:flex;}
    .card{
      width:min(520px, 100%);
      background: var(--panel);
      border:1px solid rgba(255,255,255,0.12);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.5);
      display:flex;
      flex-direction:column;
      overflow:auto;
      max-height: calc(100dvh - var(--safeInsetTop) - var(--safeInsetBottom) - var(--modalTopOffset) - var(--modalBottomOffset) - 24px);
    }
    .config-card{overflow:hidden;}
    .card-scroll{
      max-height: calc(100dvh - var(--safeInsetTop) - var(--safeInsetBottom) - var(--modalTopOffset) - var(--modalBottomOffset) - 24px);
      overflow:auto;
    }
    .modal-body{
      flex: 1 1 auto;
      min-height: 0;
      overflow: auto;
    }
    .card h2{margin:0 0 8px 0; font-size:16px;}
    .list{max-height: 50vh; overflow:auto; border:1px solid rgba(255,255,255,0.10); border-radius:12px;}
    .item{
      padding: 12px;
      border-bottom:1px solid rgba(255,255,255,0.08);
      display:flex; align-items:center; gap:10px;
      touch-action: manipulation;
    }
    .item:last-child{border-bottom:none;}
    .item .name{font-weight:750;}
    .item .meta{font-size:12px; color:var(--muted);}
    .item:active{background: rgba(255,255,255,0.04);}
    .hint{font-size:12px; color:var(--muted); margin-top:10px; line-height:1.4;}
    .hint.hidden{display:none;}
    .modal-actions{display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;}
    .modal-actions .btn{flex:1; min-width:120px;}
    .admin-header{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:10px;
      margin-bottom:8px;
    }
    .admin-status{
      font-size:12px;
      color: var(--muted);
      margin-bottom:8px;
    }
    .admin-session-list{
      display:flex;
      flex-direction:column;
      gap:10px;
      margin-top:6px;
    }
    .admin-session{
      border:1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      padding: 10px;
      background: rgba(10,14,22,0.55);
      display:flex;
      flex-direction:column;
      gap:8px;
    }
    .admin-session-top{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:8px;
      flex-wrap:wrap;
    }
    .admin-session-ip{
      font-weight:700;
      font-size:13px;
    }
    .admin-session-meta{
      font-size:12px;
      color: var(--muted);
    }
    .admin-session-status{
      font-size:11px;
      padding:4px 8px;
      border-radius:999px;
      border:1px solid rgba(255,255,255,0.16);
    }
    .admin-session-status.connected{
      border-color: rgba(106,169,255,0.55);
      color: var(--accent);
    }
    .admin-session-status.offline{
      border-color: rgba(255,255,255,0.2);
      color: var(--muted);
    }
    .admin-session-assign{
      display:flex;
      gap:8px;
      align-items:center;
      flex-wrap:wrap;
    }
    .admin-session-assign select{
      flex:1 1 200px;
      border:1px solid rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 12px;
    }
    .admin-login-fields{
      display:flex;
      flex-direction:column;
      gap:12px;
      margin-top: 10px;
    }
    .admin-login-fields label{
      font-size: 12px;
      color: var(--muted);
    }
    .admin-login-input{
      width: 100%;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.12);
      background: #0f1422;
      color: var(--text);
      font-size: 14px;
    }
    .config-section{margin-top:8px;}
    .config-section summary{
      cursor:pointer;
      list-style:none;
      font-weight:700;
      font-size:14px;
      padding: 6px 4px;
    }
    .config-section summary::-webkit-details-marker{display:none;}
    .config-list{
      display:flex;
      flex-direction:column;
      gap:10px;
      margin-top:8px;
    }
    .config-item{
      display:flex;
      flex-direction:column;
      gap:8px;
      padding: 10px;
      border-radius: 12px;
      border:1px solid rgba(255,255,255,0.1);
      background: rgba(10,14,22,0.55);
    }
    .config-item-title{font-size:13px; font-weight:650;}
    .config-controls{display:flex; align-items:center; gap:8px; flex-wrap:wrap;}
    .preset-actions{display:flex; align-items:center; gap:8px; flex-wrap:wrap;}
    .preset-status{font-size:12px; color:var(--accent); min-height:16px;}
    .config-toggle{
      display:flex;
      align-items:center;
      gap:6px;
      font-size:12px;
      color: var(--muted);
    }
    .config-toggle input{transform: scale(1.05);}
    .hotkey-input{
      width:120px;
      border-radius:8px;
      border:1px solid rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      padding:6px 8px;
      font-size:12px;
    }
    .hotkey-input.conflict{
      border-color: rgba(255,91,91,0.55);
      box-shadow: 0 0 0 1px rgba(255,91,91,0.3);
    }
    .hotkey-conflict{
      min-height:14px;
      font-size:11px;
      color: var(--danger);
    }
    .hotkey-hint{font-size:11px; color: var(--muted);}
    .color-row{display:flex; align-items:center; gap:12px; flex-wrap:wrap;}
    .color-swatch{width:36px; height:36px; border-radius:50%; border:2px solid rgba(255,255,255,0.2); background:#6aa9ff;}
    .color-input{width:64px; height:44px; border:none; background:none; padding:0;}
    .turn-modal{
      position:fixed;
      inset:0;
      display:flex;
      align-items:center;
      justify-content:center;
      padding: 20px 14px;
      background: rgba(0,0,0,0.6);
      opacity:0;
      pointer-events:none;
      transition: opacity 0.2s ease;
    }
    .turn-modal.show{
      opacity:1;
      pointer-events:auto;
    }
    .turn-card{
      width:min(380px, 100%);
      background: var(--panel);
      border:1px solid rgba(255,255,255,0.16);
      border-radius: 16px;
      padding: 18px 16px;
      text-align:center;
      box-shadow: 0 16px 40px rgba(0,0,0,0.5);
      display:flex;
      flex-direction:column;
      max-height: calc(100vh - var(--safeInsetTop) - var(--safeInsetBottom) - 40px);
    }
    .turn-card h2{margin:0 0 12px 0; font-size:18px;}
    .log-content{
      overflow:auto;
      flex:1;
      min-height:0;
      padding: 10px;
      border:1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      background: rgba(8,10,16,0.65);
      font-size: 12px;
      white-space: pre-wrap;
      line-height: 1.4;
    }
    .initiative-order-content{
      flex:1 1 auto;
      min-height:0;
      overflow:auto;
      position:relative;
    }
    .sheet-turn-order-row{
      flex:1 1 auto;
      min-height:0;
      align-items:stretch;
    }
    .turn-order-status{
      margin-top: 6px;
      font-size: 12px;
      color: var(--muted);
    }
    .turn-order-bubble{
      position:absolute;
      left:0;
      top:0;
      transform: translate(-50%, 0);
      background: rgba(16,20,28,0.95);
      border: 1px solid rgba(255,255,255,0.16);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      color: var(--text);
      box-shadow: 0 10px 24px rgba(0,0,0,0.4);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.15s ease;
      z-index: 2;
      max-width: 240px;
      text-align: center;
    }
    .turn-order-bubble.show{
      opacity: 1;
    }
    .turn-chip.selected{
      border-color: rgba(255,255,255,0.5);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
    }
    @media (max-width: 720px), (max-height: 720px){
      .btn{padding: 6px 8px; font-size: 12px;}
      .topbar{gap:8px; padding: calc(8px + var(--safeInsetTop)) 10px 8px 10px;}
      .sheet{padding: 8px 10px calc(10px + var(--safeInsetBottom)) 10px;}
    }
  </style>
</head>
<body>
<div class="app">
  <div class="topbar">
    <h1 id="topbarTitle">InitTracker LAN</h1>
    <div class="conn-wrap">
      <button class="pill conn-pill" id="conn" type="button" title="Connecting…" aria-haspopup="dialog" aria-expanded="false">
        <span class="conn-full-text" id="connFullText">Connecting…</span>
        <span class="conn-compact-label" id="connCompactLabel" aria-hidden="true">C</span>
        <span class="conn-compact-dot" id="connDot" aria-hidden="true"></span>
      </button>
      <div class="conn-popover" id="connPopover" role="dialog" aria-hidden="true">
        <div class="conn-popover-status" id="connPopoverStatus">Connecting…</div>
        <button class="btn" id="connReconnectBtn" type="button">Reconnect</button>
      </div>
    </div>
    <div class="menu-wrap">
      <button class="btn menu-btn" id="adminMenuBtn" type="button" aria-haspopup="menu" aria-expanded="false">
        Admin <span aria-hidden="true">▾</span>
      </button>
      <div class="menu-popover" id="adminMenuPopover" role="menu" aria-hidden="true">
        <button class="menu-item" id="adminMenuOpen" type="button" role="menuitem">Sessions</button>
        <button class="menu-item" id="adminMenuRefresh" type="button" role="menuitem">Refresh Sessions</button>
      </div>
    </div>
    <div class="spacer"></div>
    <button class="btn" id="configBtn" aria-controls="configModal" aria-expanded="false">Config</button>
    <div class="topbar-controls">
      <button class="btn" id="lockMap">Lock Map</button>
      <button class="btn" id="centerMap">Center on Me</button>
      <button class="btn" id="tokenColorModeBtn">Token Color</button>
      <button class="btn" id="measureToggle" aria-pressed="false">Measure</button>
      <button class="btn" id="measureClear">Clear Measure</button>
      <button class="btn accent" id="zoomIn">Zoom +</button>
      <button class="btn accent" id="zoomOut">Zoom −</button>
      <button class="btn" id="battleLog">Battle Log</button>
    </div>
  </div>

  <div class="mapWrap">
    <canvas id="c"></canvas>
    <div class="waiting" id="waitingOverlay">(waiting for combat...)</div>
    <div class="map-tooltip" id="tokenTooltip" role="tooltip" aria-hidden="true"></div>

    <div class="modal" id="colorModal" aria-hidden="true">
      <div class="card">
        <h2>Pick yer token color</h2>
        <div class="row color-row">
          <div class="color-swatch" id="tokenColorSwatch"></div>
          <input class="color-input" type="color" id="tokenColorInput" value="#6aa9ff" />
          <div class="label">No red or white, matey.</div>
        </div>
        <div class="modal-actions">
          <button class="btn accent" id="tokenColorConfirm">Confirm</button>
          <button class="btn" id="tokenColorCancel">Cancel</button>
        </div>
      </div>
    </div>
    <div class="modal" id="dashModal" aria-hidden="true">
      <div class="card">
        <h2>Use Action or Bonus Action?</h2>
        <div class="modal-actions">
          <button class="btn accent" id="dashAction">Use Action</button>
          <button class="btn accent" id="dashBonusAction">Use Bonus Action</button>
          <button class="btn" id="dashCancel">Cancel</button>
        </div>
      </div>
    </div>
    <div class="modal" id="logModal" aria-hidden="true">
      <div class="card card-scroll">
        <h2>Battle Log</h2>
        <div class="log-content" id="logContent">Loading…</div>
        <div class="modal-actions">
          <button class="btn accent" id="logRefresh">Refresh</button>
          <button class="btn" id="logClose">Close</button>
        </div>
      </div>
    </div>
    <div class="modal" id="configModal" aria-hidden="true">
      <div class="card config-card">
        <h2>Config</h2>
        <div class="modal-body">
          <details class="config-section">
            <summary>Top Bar</summary>
            <div class="config-list">
              <div class="config-item">
                <div class="config-item-title">InitTracker LAN title</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleTopbarTitle" />Show</label>
                  <input class="hotkey-input" id="hotkeyTopbarTitle" data-hotkey-action="toggleTopbarTitle" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictTopbarTitle"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Connection indicator</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleConnIndicator" />Show</label>
                  <div class="conn-style-toggle" role="group" aria-label="Connection indicator style">
                    <button class="btn conn-style-btn" type="button" data-conn-style="full">Full</button>
                    <button class="btn conn-style-btn" type="button" data-conn-style="compact">Compact</button>
                  </div>
                  <input class="hotkey-input" id="hotkeyConnStyle" data-hotkey-action="toggleConnStyle" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictConnStyle"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Lock Map</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleLockMap" />Show</label>
                  <input class="hotkey-input" id="hotkeyLockMap" data-hotkey-action="lockMap" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictLockMap"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Center on Me</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleCenterMap" />Show</label>
                  <input class="hotkey-input" id="hotkeyCenterMap" data-hotkey-action="centerMap" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictCenterMap"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Measure</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleMeasure" />Show</label>
                  <input class="hotkey-input" id="hotkeyMeasure" data-hotkey-action="measure" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictMeasure"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Clear Measure</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleMeasureClear" />Show</label>
                  <input class="hotkey-input" id="hotkeyMeasureClear" data-hotkey-action="measureClear" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictMeasureClear"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Zoom +</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleZoomIn" />Show</label>
                  <input class="hotkey-input" id="hotkeyZoomIn" data-hotkey-action="zoomIn" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictZoomIn"></div>
              </div>
              <div class="config-item">
                <div class="config-item-title">Zoom -</div>
                <div class="config-controls">
                  <label class="config-toggle"><input type="checkbox" id="toggleZoomOut" />Show</label>
                  <input class="hotkey-input" id="hotkeyZoomOut" data-hotkey-action="zoomOut" placeholder="Hotkey" readonly />
                </div>
                <div class="hotkey-conflict" id="hotkeyConflictZoomOut"></div>
              </div>
              <div class="config-item">
              <div class="config-item-title">Battle Log</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleBattleLog" />Show</label>
                <input class="hotkey-input" id="hotkeyBattleLog" data-hotkey-action="battleLog" placeholder="Hotkey" readonly />
              </div>
              <div class="hotkey-conflict" id="hotkeyConflictBattleLog"></div>
            </div>
          </div>
        </details>
        <details class="config-section">
          <summary>Bottom Bar</summary>
          <div class="config-list">
            <div class="config-item">
              <div class="config-item-title">Initiative strip</div>
              <div class="config-controls">
                <select id="initiativeStyleSelect">
                  <option value="full">Full</option>
                  <option value="compact">Compact</option>
                  <option value="hidden">Hidden</option>
                </select>
              </div>
            </div>
            <div class="config-item">
              <div class="config-item-title">Action</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleUseAction" />Show</label>
                <input class="hotkey-input" id="hotkeyUseAction" data-hotkey-action="useAction" placeholder="Hotkey" readonly />
              </div>
              <div class="hotkey-conflict" id="hotkeyConflictUseAction"></div>
            </div>
            <div class="config-item">
              <div class="config-item-title">Bonus Action</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleUseBonusAction" />Show</label>
                <input class="hotkey-input" id="hotkeyUseBonusAction" data-hotkey-action="useBonusAction" placeholder="Hotkey" readonly />
              </div>
              <div class="hotkey-conflict" id="hotkeyConflictUseBonusAction"></div>
            </div>
            <div class="config-item">
              <div class="config-item-title">Dash</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleDash" />Show</label>
                <input class="hotkey-input" id="hotkeyDash" data-hotkey-action="dash" placeholder="Hotkey" readonly />
              </div>
              <div class="hotkey-conflict" id="hotkeyConflictDash"></div>
            </div>
            <div class="config-item">
              <div class="config-item-title">Stand</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleStandUp" />Show</label>
                <input class="hotkey-input" id="hotkeyStandUp" data-hotkey-action="standUp" placeholder="Hotkey" readonly />
              </div>
              <div class="hotkey-conflict" id="hotkeyConflictStandUp"></div>
            </div>
            <div class="config-item">
              <div class="config-item-title">Reset</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleResetTurn" />Show</label>
                <input class="hotkey-input" id="hotkeyResetTurn" data-hotkey-action="resetTurn" placeholder="Hotkey" readonly />
              </div>
              <div class="hotkey-conflict" id="hotkeyConflictResetTurn"></div>
            </div>
            <div class="config-item">
              <div class="config-item-title">Hide spell menu for non spell casters</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleSpellMenu" />Hide</label>
              </div>
            </div>
          </div>
        </details>
        <details class="config-section">
          <summary>Presets</summary>
          <div class="config-list">
            <div class="config-item">
              <div class="config-item-title">Lock menus</div>
              <div class="config-controls">
                <label class="config-toggle"><input type="checkbox" id="toggleLockMenus" />Lock</label>
              </div>
              <div class="hotkey-hint">Settings are stored per device.</div>
            </div>
            <div class="config-item">
              <div class="config-item-title">GUI preset</div>
              <div class="preset-actions">
                <button class="btn" id="savePreset" type="button">Save Preset</button>
                <button class="btn" id="loadPreset" type="button">Load Preset</button>
                <div class="preset-status" id="presetStatus" aria-live="polite"></div>
              </div>
            </div>
          </div>
        </details>
        <details class="config-section">
          <summary>Notifications</summary>
          <div class="config-list">
            <div class="config-item">
              <div class="config-item-title">Push notifications</div>
              <div class="config-controls">
                <button class="btn" id="enableNotifications" type="button">Enable</button>
                <div class="preset-status" id="notificationStatus" aria-live="polite"></div>
              </div>
            </div>
          </div>
        </details>
        <div class="hint hidden" id="iosInstallHint">
          Open Safari → Share → Add to Home Screen.
          <a href="https://support.apple.com/en-us/HT201366" target="_blank" rel="noopener">Learn more</a>
        </div>
        </div>
        <div class="modal-actions">
          <button class="btn" id="configClose">Close</button>
        </div>
      </div>
    </div>
    <div class="modal" id="adminModal" aria-hidden="true">
      <div class="card card-scroll">
        <div class="admin-header">
          <h2>Admin Sessions</h2>
          <button class="btn" id="adminRefresh" type="button">Refresh</button>
        </div>
        <div class="admin-status" id="adminStatus">Loading…</div>
        <div class="admin-session-list" id="adminSessionList"></div>
        <div class="hint">Assignments persist per IP address and auto-apply on reconnect.</div>
        <div class="modal-actions">
          <button class="btn" id="adminClose">Close</button>
        </div>
      </div>
    </div>
    <div class="modal" id="adminLoginModal" aria-hidden="true">
      <div class="card">
        <h2>Admin Login</h2>
        <div class="hint">Enter the DM password to manage LAN sessions.</div>
        <div class="admin-login-fields">
          <label for="adminPasswordInput">Admin password</label>
          <input class="admin-login-input" id="adminPasswordInput" type="password" autocomplete="current-password" />
        </div>
        <div class="admin-status" id="adminLoginStatus"></div>
        <div class="modal-actions">
          <button class="btn" id="adminLoginSubmit" type="button">Login</button>
          <button class="btn" id="adminLoginCancel" type="button">Cancel</button>
        </div>
      </div>
    </div>
  </div>

  <div class="sheet-wrap" id="sheetWrap">
    <div class="sheet-handle" id="sheetHandle" role="separator" aria-orientation="horizontal" aria-label="Resize sheet"></div>
    <div class="sheet" id="sheet">
      <div class="sheet-content">
      <div class="row">
        <div class="label">Ye be:</div>
        <div class="value" id="me">(unclaimed)</div>
        <div class="spacer"></div>
        <div class="sheet-actions">
          <button class="btn" id="useAction">Use Action</button>
          <button class="btn" id="useBonusAction">Use Bonus Action</button>
          <button class="btn" id="dash">Dash</button>
          <button class="btn" id="standUp">Stand Up</button>
          <button class="btn" id="resetTurn">Reset Turn</button>
          <button class="btn danger" id="endTurn">End Turn</button>
        </div>
      </div>
      <div class="row">
        <div class="form-field">
          <label for="actionSelect">Action</label>
          <select id="actionSelect">
            <option value="">None/Custom</option>
          </select>
        </div>
        <div class="form-field">
          <label for="bonusActionSelect">Bonus Action</label>
          <select id="bonusActionSelect">
            <option value="">None/Custom</option>
          </select>
        </div>
      </div>
      <div class="row sheet-turn-order-row">
        <div class="initiative-order-content">
          <div class="turn-order" id="turnOrder" aria-label="Turn order"></div>
          <div class="turn-order-status" id="turnOrderStatus"></div>
          <div class="turn-order-bubble" id="turnOrderBubble" role="status" aria-live="polite"></div>
        </div>
      </div>
      <div class="row">
        <div class="chip" id="move">Move: —</div>
        <div class="chip" id="action">Action: —</div>
        <div class="chip" id="bonusAction">Bonus Action: —</div>
        <div class="chip" id="turn">Turn: —</div>
        <div class="chip" id="note">Tip: drag yer token</div>
        <label class="chip"><input type="checkbox" id="showAllNames">Show All Names</label>
      </div>
      <fieldset class="turn-alerts-panel" id="turnAlertsPanel">
        <legend>Turn Alerts</legend>
        <div class="turn-alerts-row">
          <div class="turn-alerts-status" id="turnAlertStatus" aria-live="polite">Not installed.</div>
          <button class="btn" id="enableTurnAlerts" type="button">Enable Turn Alerts</button>
          <button class="btn" id="hideTurnAlerts" type="button">Hide</button>
        </div>
        <div class="turn-alerts-note">Only works when installed as an app.</div>
      </fieldset>
      <div class="cast-menu-trigger" id="castMenuTrigger">
        <button class="btn" id="castOverlayOpen" type="button">Cast Spell</button>
      </div>
      </div>
    </div>
    <div class="cast-overlay hidden" id="sheetCastView" aria-hidden="true">
      <div class="cast-overlay-header">
        <button class="btn" id="castOverlayBack" type="button">Back</button>
        <div class="cast-overlay-title" id="castOverlayTitle">Cast Spell</div>
        <div class="cast-overlay-spacer"></div>
        <button class="btn" id="spellPreparedOpen" type="button">Prepared Spells</button>
        <button class="btn" id="spellConfigOpen" type="button">Known Spells</button>
      </div>
      <div class="cast-overlay-body" role="dialog" aria-modal="true" aria-labelledby="castOverlayTitle">
        <div class="cast-panel" id="castPanel">
          <form id="castForm">
            <fieldset class="spell-filter-panel" id="spellFilterPanel">
              <legend>Spell Filters</legend>
              <div class="form-grid">
                <div class="form-field">
                  <label for="castFilterLevel">Level</label>
                  <select id="castFilterLevel">
                    <option value="" selected>Any</option>
                    <option value="0">Cantrip</option>
                    <option value="1">1st</option>
                    <option value="2">2nd</option>
                    <option value="3">3rd</option>
                    <option value="4">4th</option>
                    <option value="5">5th</option>
                    <option value="6">6th</option>
                    <option value="7">7th</option>
                    <option value="8">8th</option>
                    <option value="9">9th</option>
                  </select>
                </div>
              <div class="form-field">
                <label for="castFilterSchool">School</label>
                <select id="castFilterSchool">
                  <option value="" selected>Any</option>
                </select>
              </div>
              <div class="form-field">
                <label for="castFilterTags">Tags</label>
                <input id="castFilterTags" type="text" placeholder="fire, area" />
              </div>
              <div class="form-field">
                <label for="castFilterCastingTime">Casting Time</label>
                <select id="castFilterCastingTime">
                  <option value="" selected>Any</option>
                </select>
              </div>
              <div class="form-field">
                <label for="castFilterRange">Range</label>
                <select id="castFilterRange">
                  <option value="" selected>Any</option>
                </select>
              </div>
              <div class="form-field">
                <label for="castFilterRitual">Ritual</label>
                <select id="castFilterRitual">
                  <option value="" selected>Any</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
              <div class="form-field">
                <label for="castFilterConcentration">Concentration</label>
                <select id="castFilterConcentration">
                  <option value="" selected>Any</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
              <div class="form-field">
                <label for="castFilterList">Lists</label>
                <select id="castFilterList">
                  <option value="" selected>Any</option>
                </select>
              </div>
            </div>
          </fieldset>
          <div class="form-grid">
            <div class="form-field">
              <label for="castPreset">Preset <span class="manual-entry-badge" id="castManualEntryBadge" title="Manual entry required.">Manual entry required</span></label>
              <div class="spell-select-controls">
                <select id="castPreset">
                  <option value="" selected>Custom</option>
                </select>
              </div>
            </div>
            <div class="form-field">
              <label for="castName">Name</label>
              <input id="castName" type="text" placeholder="Fireball" />
            </div>
            <div class="form-field">
              <label for="castShape">Shape</label>
              <select id="castShape">
                <option value="" selected>Choose shape</option>
                <option value="circle">Circle</option>
                <option value="square">Square</option>
                <option value="line">Line</option>
                <option value="sphere">Sphere</option>
                <option value="cube">Cube</option>
                <option value="cone">Cone</option>
                <option value="cylinder">Cylinder</option>
                <option value="wall">Wall</option>
              </select>
            </div>
            <div class="form-field cast-size-field" id="castRadiusField">
              <label for="castRadius">Radius (ft)</label>
              <input id="castRadius" type="number" min="5" step="5" value="10" readonly disabled />
            </div>
            <div class="form-field cast-size-field" id="castSideField">
              <label for="castSide">Side (ft)</label>
              <input id="castSide" type="number" min="5" step="5" value="10" readonly disabled />
            </div>
            <div class="form-field cast-size-field" id="castLengthField">
              <label for="castLength">Length (ft)</label>
              <input id="castLength" type="number" min="5" step="5" value="30" readonly disabled />
            </div>
            <div class="form-field cast-size-field" id="castWidthField">
              <label for="castWidth">Width (ft)</label>
              <input id="castWidth" type="number" min="5" step="5" value="5" readonly disabled />
            </div>
            <div class="form-field cast-size-field" id="castAngleField">
              <label for="castAngle">Angle (deg)</label>
              <input id="castAngle" type="number" min="0" step="5" value="90" readonly disabled />
            </div>
            <div class="form-field cast-size-field" id="castOrientField">
              <label for="castOrient">Orientation</label>
              <select id="castOrient" disabled>
                <option value="vertical" selected>Vertical</option>
                <option value="horizontal">Horizontal</option>
              </select>
            </div>
            <div class="form-field cast-size-field" id="castThicknessField">
              <label for="castThickness">Thickness (ft)</label>
              <input id="castThickness" type="number" min="1" step="1" value="5" readonly disabled />
            </div>
            <div class="form-field cast-size-field" id="castHeightField">
              <label for="castHeight">Height (ft)</label>
              <input id="castHeight" type="number" min="1" step="1" value="10" readonly disabled />
            </div>
            <div class="form-field">
              <label for="castDcType">DC Type</label>
              <select id="castDcType">
                <option value="">None</option>
                <option value="str">STR</option>
                <option value="dex">DEX</option>
                <option value="con">CON</option>
                <option value="int">INT</option>
                <option value="wis">WIS</option>
                <option value="cha">CHA</option>
              </select>
            </div>
            <div class="form-field">
              <label for="castDcValue">Save DC</label>
              <input id="castDcValue" type="number" min="0" step="1" placeholder="15" />
            </div>
            <div class="form-field">
              <label for="castDefaultDamage">Default Damage</label>
              <input id="castDefaultDamage" type="text" placeholder="28" />
            </div>
            <div class="form-field">
              <label for="castDice">Damage Dice</label>
              <input id="castDice" type="text" placeholder="8d6" />
            </div>
            <div class="form-field">
              <label for="castSlotLevel">Slot Level</label>
              <input id="castSlotLevel" type="number" min="0" step="1" placeholder="1" disabled />
            </div>
            <div class="form-field">
              <label for="castDamageType">Damage Types</label>
              <div class="damage-type-controls">
                <select id="castDamageType">
                  <option value="" selected>Select a type</option>
__DAMAGE_TYPE_OPTIONS__
                </select>
                <button class="btn" type="button" id="castAddDamageType">Add</button>
              </div>
              <div class="damage-type-list" id="castDamageTypeList" aria-live="polite"></div>
            </div>
            <div class="form-field">
              <label for="castColor">Color</label>
              <input id="castColor" type="color" value="#6aa9ff" />
            </div>
          </div>
          <div class="spell-details" id="spellPresetDetails" aria-live="polite">
            Select a preset to see spell details.
          </div>
          <div class="form-actions">
            <button class="btn accent" type="submit">Cast</button>
          </div>
        </form>
      </div>
    </div>
  </div>
  </div>
  <div class="spell-select-overlay" id="spellSelectOverlay" aria-hidden="true">
    <div class="spell-select-header">
      <button class="btn" id="spellSelectBack" type="button">Back</button>
      <div class="spell-select-title" id="spellSelectTitle">Select Spells</div>
      <div class="spell-select-spacer"></div>
      <div class="spell-select-actions">
        <button class="btn" id="spellSelectModeToggle" type="button">Select Known</button>
        <button class="btn accent spell-select-save-btn" id="spellSelectSaveKnown" type="button">Save Known Spells</button>
      </div>
      <button class="btn" id="spellSelectClose" type="button">Close</button>
    </div>
    <div class="spell-select-body" role="dialog" aria-modal="true" aria-labelledby="spellSelectTitle">
      <div class="spell-select-summary" id="spellSelectSummary">Loading spell presets…</div>
      <div class="spell-select-table-wrap" id="spellSelectTableWrap">
        <table class="spell-select-table">
          <thead>
            <tr>
              <th scope="col" class="spell-select-check-col" id="spellSelectCheckHeader">Known</th>
              <th scope="col">Name</th>
              <th scope="col">Damage</th>
              <th scope="col">AoE</th>
              <th scope="col">Level</th>
              <th scope="col">School</th>
              <th scope="col">Link</th>
            </tr>
          </thead>
          <tbody id="spellSelectTableBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>
<div class="turn-modal" id="turnModal" aria-hidden="true">
  <div class="turn-card" role="dialog" aria-live="assertive">
    <h2>It’s your turn!</h2>
    <button class="btn accent" id="turnModalOk">OK</button>
  </div>
</div>
<div class="modal" id="spellConfigModal" aria-hidden="true">
  <div class="card">
    <h2>Known Spells</h2>
    <div class="hint">Track known spells for your claimed character.</div>
    <form id="spellConfigForm">
      <div class="form-grid">
        <div class="form-field">
          <label for="spellConfigCantrips">Cantrips</label>
          <input id="spellConfigCantrips" type="number" min="0" step="1" placeholder="0" />
        </div>
        <div class="form-field">
          <label for="spellConfigSpells">Spells</label>
          <input id="spellConfigSpells" type="number" min="0" step="1" value="15" />
        </div>
      </div>
    </form>
    <div class="modal-actions">
      <button class="btn" id="spellConfigCancel" type="button">Cancel</button>
      <button class="btn accent" id="spellConfigSave" type="button">Continue</button>
    </div>
  </div>
</div>

<script>
(() => {
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  const canVibrate = "vibrate" in navigator;
  function vibrate(pattern){
    if (!canVibrate) return false;
    return navigator.vibrate(pattern);
  }

  const qs = new URLSearchParams(location.search);
  const wsProto = (location.protocol === "https:") ? "wss" : "ws";
  const wsUrl = `${wsProto}://${location.host}/ws`;
  const pushPublicKey = (window.PUSH_PUBLIC_KEY || "").trim();
  const turnAlertStorageKey = "inittracker_turnAlertSubscription";
  const turnAlertHideKey = "inittracker_hideTurnAlerts";
  let swRegistration = null;

  function setNotificationStatus(message){
    if (!notificationStatus) return;
    notificationStatus.textContent = message;
  }

  function setTurnAlertStatus(message){
    if (!turnAlertStatus) return;
    turnAlertStatus.textContent = message;
  }

  function isStandaloneDisplay(){
    return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  }

  function getTurnAlertIdentity(){
    const playerId = claimedCid !== null && claimedCid !== undefined ? Number(claimedCid) : null;
    const claimedUnit = getClaimedUnit();
    const playerName = claimedUnit?.name ? String(claimedUnit.name) : "";
    return {
      playerId,
      username: null,
      playerName: playerName || null,
    };
  }

  function formatTurnAlertLabel(identity){
    if (identity?.playerName) return identity.playerName;
    if (identity?.username) return identity.username;
    if (identity?.playerId !== null && identity?.playerId !== undefined){
      return `#${identity.playerId}`;
    }
    return "";
  }

  function persistTurnAlertSubscription(subscription, identity){
    if (!subscription) return;
    const payload = {
      subscription: subscription.toJSON ? subscription.toJSON() : subscription,
      playerId: identity?.playerId ?? null,
      username: identity?.username ?? null,
      label: formatTurnAlertLabel(identity),
      createdAt: new Date().toISOString(),
    };
    try {
      localStorage.setItem(turnAlertStorageKey, JSON.stringify(payload));
    } catch (err){
      console.warn("Unable to store turn alert subscription.", err);
    }
  }

  function loadTurnAlertSubscription(){
    try {
      const raw = localStorage.getItem(turnAlertStorageKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") return parsed;
    } catch (err){
      console.warn("Unable to read turn alert subscription.", err);
    }
    return null;
  }

  function formatTurnAlertStatus(identity){
    const label = formatTurnAlertLabel(identity);
    return label ? `Subscribed (${label})` : "Subscribed";
  }

  async function syncTurnAlertSubscription(subscription, identity){
    if (!subscription || !identity?.playerId) return;
    const payload = {
      subscription: subscription.toJSON ? subscription.toJSON() : subscription,
      playerId: identity.playerId,
    };
    try {
      await fetch("/api/push/subscribe", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
    } catch (err){
      console.warn("Unable to sync turn alert subscription.", err);
    }
  }

  async function refreshTurnAlertStatus(){
    if (!turnAlertStatus) return;
    if (!isStandaloneDisplay()){
      setTurnAlertStatus("Not installed.");
      return;
    }
    if (!("Notification" in window)){
      setTurnAlertStatus("Notifications not supported.");
      return;
    }
    if (Notification.permission === "denied"){
      setTurnAlertStatus("Permission denied.");
      return;
    }
    if (!("serviceWorker" in navigator)){
      setTurnAlertStatus("Service worker unsupported.");
      return;
    }
    if (!("PushManager" in window)){
      setTurnAlertStatus("Push not supported.");
      return;
    }
    setTurnAlertStatus("Not subscribed.");
    try {
      swRegistration = swRegistration || await navigator.serviceWorker.ready;
      const existing = await swRegistration.pushManager.getSubscription();
      if (existing){
        const stored = loadTurnAlertSubscription();
        setTurnAlertStatus(formatTurnAlertStatus(stored || getTurnAlertIdentity()));
      }
    } catch (err){
      console.warn("Unable to check push subscription.", err);
    }
  }

  async function ensurePushSubscribed({vapidPublicKey, playerId}){
    if (!isStandaloneDisplay()){
      throw new Error("Not installed.");
    }
    if (!vapidPublicKey){
      throw new Error("Missing push public key.");
    }
    if (!playerId){
      throw new Error("Claim a character first.");
    }
    if (!("Notification" in window)){
      throw new Error("Notifications are not supported.");
    }
    if (!("serviceWorker" in navigator)){
      throw new Error("Service worker unsupported.");
    }
    if (!("PushManager" in window)){
      throw new Error("Push is not supported.");
    }
    try {
      swRegistration = swRegistration || await navigator.serviceWorker.ready;
    } catch (err){
      throw new Error("Service worker not ready.");
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted"){
      throw new Error(permission === "denied" ? "Permission denied." : "Permission required.");
    }
    const existing = await swRegistration.pushManager.getSubscription();
    if (existing){
      const identity = getTurnAlertIdentity();
      setTurnAlertStatus(formatTurnAlertStatus(identity));
      await syncTurnAlertSubscription(existing, identity);
      return existing;
    }
    const subscription = await swRegistration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    });
    const identity = getTurnAlertIdentity();
    persistTurnAlertSubscription(subscription, identity);
    setTurnAlertStatus(formatTurnAlertStatus(identity));
    await syncTurnAlertSubscription(subscription, identity);
    return subscription;
  }

  function routeDeepLink(url){
    if (!url) return;
    try {
      const target = new URL(url, location.origin);
      if (target.origin === location.origin){
        location.href = target.href;
      } else {
        location.href = url;
      }
    } catch (err){
      location.href = url;
    }
  }

  function urlBase64ToUint8Array(base64String){
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i){
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  if ("serviceWorker" in navigator){
    navigator.serviceWorker.register("/sw.js")
      .then(() => navigator.serviceWorker.ready)
      .then((registration) => {
        swRegistration = registration;
        navigator.serviceWorker.addEventListener("message", (event) => {
          const data = event.data || {};
          if (data && data.type === "deep-link" && typeof data.url === "string"){
            routeDeepLink(data.url);
          }
        });
      })
      .catch((err) => {
        console.warn("Service worker registration failed.", err);
      });
  }

  const connEl = document.getElementById("conn");
  const connFullTextEl = document.getElementById("connFullText");
  const connCompactLabelEl = document.getElementById("connCompactLabel");
  const connDotEl = document.getElementById("connDot");
  const topbarTitleEl = document.getElementById("topbarTitle");
  const connPopoverEl = document.getElementById("connPopover");
  const connPopoverStatusEl = document.getElementById("connPopoverStatus");
  const connReconnectBtn = document.getElementById("connReconnectBtn");
  const connStyleButtons = Array.from(document.querySelectorAll(".conn-style-btn"));
  const meEl = document.getElementById("me");
  const moveEl = document.getElementById("move");
  const actionEl = document.getElementById("action");
  const bonusActionEl = document.getElementById("bonusAction");
  const turnEl = document.getElementById("turn");
  const turnOrderEl = document.getElementById("turnOrder");
  const turnOrderStatusEl = document.getElementById("turnOrderStatus");
  const turnOrderBubbleEl = document.getElementById("turnOrderBubble");
  const noteEl = document.getElementById("note");
  const colorModal = document.getElementById("colorModal");
  const tokenColorInput = document.getElementById("tokenColorInput");
  const tokenColorSwatch = document.getElementById("tokenColorSwatch");
  const tokenColorConfirm = document.getElementById("tokenColorConfirm");
  const tokenColorCancel = document.getElementById("tokenColorCancel");
  const tokenColorModeBtn = document.getElementById("tokenColorModeBtn");
  const dashModal = document.getElementById("dashModal");
  const dashActionBtn = document.getElementById("dashAction");
  const dashBonusActionBtn = document.getElementById("dashBonusAction");
  const dashCancelBtn = document.getElementById("dashCancel");
  const battleLogBtn = document.getElementById("battleLog");
  const lockMapBtn = document.getElementById("lockMap");
  const centerMapBtn = document.getElementById("centerMap");
  const zoomInBtn = document.getElementById("zoomIn");
  const zoomOutBtn = document.getElementById("zoomOut");
  const dashBtn = document.getElementById("dash");
  const configBtn = document.getElementById("configBtn");
  const adminMenuBtn = document.getElementById("adminMenuBtn");
  const adminMenuPopover = document.getElementById("adminMenuPopover");
  const adminMenuOpenBtn = document.getElementById("adminMenuOpen");
  const adminMenuRefreshBtn = document.getElementById("adminMenuRefresh");
  const configModal = document.getElementById("configModal");
  const configCloseBtn = document.getElementById("configClose");
  const adminModal = document.getElementById("adminModal");
  const adminLoginModal = document.getElementById("adminLoginModal");
  const adminPasswordInput = document.getElementById("adminPasswordInput");
  const adminLoginStatus = document.getElementById("adminLoginStatus");
  const adminLoginSubmit = document.getElementById("adminLoginSubmit");
  const adminLoginCancel = document.getElementById("adminLoginCancel");
  const adminSessionList = document.getElementById("adminSessionList");
  const adminStatus = document.getElementById("adminStatus");
  const adminRefreshBtn = document.getElementById("adminRefresh");
  const adminCloseBtn = document.getElementById("adminClose");
  const toggleTopbarTitle = document.getElementById("toggleTopbarTitle");
  const toggleConnIndicator = document.getElementById("toggleConnIndicator");
  const toggleLockMap = document.getElementById("toggleLockMap");
  const toggleCenterMap = document.getElementById("toggleCenterMap");
  const toggleMeasure = document.getElementById("toggleMeasure");
  const toggleMeasureClear = document.getElementById("toggleMeasureClear");
  const toggleZoomIn = document.getElementById("toggleZoomIn");
  const toggleZoomOut = document.getElementById("toggleZoomOut");
  const toggleBattleLog = document.getElementById("toggleBattleLog");
  const initiativeStyleSelect = document.getElementById("initiativeStyleSelect");
  const toggleUseAction = document.getElementById("toggleUseAction");
  const toggleUseBonusAction = document.getElementById("toggleUseBonusAction");
  const toggleDash = document.getElementById("toggleDash");
  const toggleStandUp = document.getElementById("toggleStandUp");
  const toggleResetTurn = document.getElementById("toggleResetTurn");
  const toggleSpellMenu = document.getElementById("toggleSpellMenu");
  const toggleLockMenus = document.getElementById("toggleLockMenus");
  const presetSaveBtn = document.getElementById("savePreset");
  const presetLoadBtn = document.getElementById("loadPreset");
  const presetStatus = document.getElementById("presetStatus");
  const enableNotificationsBtn = document.getElementById("enableNotifications");
  const notificationStatus = document.getElementById("notificationStatus");
  const enableTurnAlertsBtn = document.getElementById("enableTurnAlerts");
  const hideTurnAlertsBtn = document.getElementById("hideTurnAlerts");
  const turnAlertsPanel = document.getElementById("turnAlertsPanel");
  const turnAlertStatus = document.getElementById("turnAlertStatus");
  const hotkeyTopbarTitleInput = document.getElementById("hotkeyTopbarTitle");
  const hotkeyConnStyleInput = document.getElementById("hotkeyConnStyle");
  const hotkeyLockMapInput = document.getElementById("hotkeyLockMap");
  const hotkeyCenterMapInput = document.getElementById("hotkeyCenterMap");
  const hotkeyMeasureInput = document.getElementById("hotkeyMeasure");
  const hotkeyMeasureClearInput = document.getElementById("hotkeyMeasureClear");
  const hotkeyZoomInInput = document.getElementById("hotkeyZoomIn");
  const hotkeyZoomOutInput = document.getElementById("hotkeyZoomOut");
  const hotkeyBattleLogInput = document.getElementById("hotkeyBattleLog");
  const hotkeyUseActionInput = document.getElementById("hotkeyUseAction");
  const hotkeyUseBonusActionInput = document.getElementById("hotkeyUseBonusAction");
  const hotkeyDashInput = document.getElementById("hotkeyDash");
  const hotkeyStandUpInput = document.getElementById("hotkeyStandUp");
  const hotkeyResetTurnInput = document.getElementById("hotkeyResetTurn");
  const iosInstallHint = document.getElementById("iosInstallHint");
  const measureToggle = document.getElementById("measureToggle");
  const measureClear = document.getElementById("measureClear");
  const logModal = document.getElementById("logModal");
  const logContent = document.getElementById("logContent");
  const logRefreshBtn = document.getElementById("logRefresh");
  const logCloseBtn = document.getElementById("logClose");
  const waitingOverlay = document.getElementById("waitingOverlay");
  const turnModal = document.getElementById("turnModal");
  const turnModalOk = document.getElementById("turnModalOk");
  const useActionBtn = document.getElementById("useAction");
  const useBonusActionBtn = document.getElementById("useBonusAction");
  const actionSelectEl = document.getElementById("actionSelect");
  const bonusActionSelectEl = document.getElementById("bonusActionSelect");
  const resetTurnBtn = document.getElementById("resetTurn");
  const standUpBtn = document.getElementById("standUp");
  const showAllNamesEl = document.getElementById("showAllNames");
  const castOverlay = document.getElementById("sheetCastView");
  const castOverlayOpenBtn = document.getElementById("castOverlayOpen");
  const castOverlayBackBtn = document.getElementById("castOverlayBack");
  const castMenuTrigger = document.getElementById("castMenuTrigger");
  const castPanel = document.getElementById("castPanel");
  const castForm = document.getElementById("castForm");
  const castFilterLevelInput = document.getElementById("castFilterLevel");
  const castFilterSchoolInput = document.getElementById("castFilterSchool");
  const castFilterTagsInput = document.getElementById("castFilterTags");
  const castFilterCastingTimeInput = document.getElementById("castFilterCastingTime");
  const castFilterRangeInput = document.getElementById("castFilterRange");
  const castFilterRitualInput = document.getElementById("castFilterRitual");
  const castFilterConcentrationInput = document.getElementById("castFilterConcentration");
  const castFilterListInput = document.getElementById("castFilterList");
  const castPresetInput = document.getElementById("castPreset");
  const castManualEntryBadge = document.getElementById("castManualEntryBadge");
  const castNameInput = document.getElementById("castName");
  const castShapeInput = document.getElementById("castShape");
  const castRadiusField = document.getElementById("castRadiusField");
  const castSideField = document.getElementById("castSideField");
  const castLengthField = document.getElementById("castLengthField");
  const castWidthField = document.getElementById("castWidthField");
  const castAngleField = document.getElementById("castAngleField");
  const castOrientField = document.getElementById("castOrientField");
  const castThicknessField = document.getElementById("castThicknessField");
  const castHeightField = document.getElementById("castHeightField");
  const castRadiusInput = document.getElementById("castRadius");
  const castSideInput = document.getElementById("castSide");
  const castLengthInput = document.getElementById("castLength");
  const castWidthInput = document.getElementById("castWidth");
  const castAngleInput = document.getElementById("castAngle");
  const castOrientInput = document.getElementById("castOrient");
  const castThicknessInput = document.getElementById("castThickness");
  const castHeightInput = document.getElementById("castHeight");
  const castDcTypeInput = document.getElementById("castDcType");
  const castDcValueInput = document.getElementById("castDcValue");
  const castDefaultDamageInput = document.getElementById("castDefaultDamage");
  const castDiceInput = document.getElementById("castDice");
  const castSlotLevelInput = document.getElementById("castSlotLevel");
  const castDamageTypeInput = document.getElementById("castDamageType");
  const castDamageTypeList = document.getElementById("castDamageTypeList");
  const castAddDamageTypeBtn = document.getElementById("castAddDamageType");
  const castColorInput = document.getElementById("castColor");
  const spellPresetDetails = document.getElementById("spellPresetDetails");
  const spellSelectOverlay = document.getElementById("spellSelectOverlay");
  const spellSelectBackBtn = document.getElementById("spellSelectBack");
  const spellSelectCloseBtn = document.getElementById("spellSelectClose");
  const spellSelectTitle = document.getElementById("spellSelectTitle");
  const spellSelectCheckHeader = document.getElementById("spellSelectCheckHeader");
  const spellSelectModeBtn = document.getElementById("spellSelectModeToggle");
  const spellSelectSaveBtn = document.getElementById("spellSelectSaveKnown");
  const spellSelectSummary = document.getElementById("spellSelectSummary");
  const spellSelectTableBody = document.getElementById("spellSelectTableBody");
  const spellPreparedOpenBtn = document.getElementById("spellPreparedOpen");
  const spellConfigOpenBtn = document.getElementById("spellConfigOpen");
  const spellConfigModal = document.getElementById("spellConfigModal");
  const spellConfigForm = document.getElementById("spellConfigForm");
  const spellConfigCantripsInput = document.getElementById("spellConfigCantrips");
  const spellConfigSpellsInput = document.getElementById("spellConfigSpells");
  const spellConfigCancelBtn = document.getElementById("spellConfigCancel");
  const spellConfigSaveBtn = document.getElementById("spellConfigSave");
  const sheetWrap = document.getElementById("sheetWrap");
  const sheet = document.getElementById("sheet");
  const sheetHandle = document.getElementById("sheetHandle");
  const tokenTooltip = document.getElementById("tokenTooltip");
  const turnAlertAudio = new Audio("/assets/alert.wav");
  turnAlertAudio.preload = "auto";
  const koAlertAudio = new Audio("/assets/ko.wav");
  koAlertAudio.preload = "auto";
  let audioUnlocked = false;
  let pendingTurnAlert = false;
  let pendingVibrate = false;
  let lastVibrateSupported = canVibrate;
  let userHasInteracted = navigator.userActivation?.hasBeenActive ?? false;
  let castOverlayPreviousFocus = null;
  let spellSelectPreviousFocus = null;
  let spellConfigPreviousFocus = null;
  const spellConfigDefaults = {cantrips: 0, spells: 15};
  const preparedSpellDefaults = {prepared: [], max: null, maxFormula: ""};
  let spellSelectContext = "known";
  let spellSelectMode = false;
  let spellSelectLastCount = 0;
  let selectedKnownSpellKeys = new Set();
  let selectedPreparedSpellKeys = new Set();
  let spellPresetIndex = new Map();

  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");

  let ws = null;
  let state = null;
  let reconnectTimer = null;
  let reconnecting = false;
  let claimedCid = null;
  let shownNoOwnedToast = false;
  let pendingClaim = null;
  let lastPcList = [];
  let lastActiveCid = null;
  let lastTurnRound = null;
  let selectedTurnCid = null;
  let hoveredTurnCid = null;
  let adminSessions = [];
  let adminPcs = [];
  const adminTokenKey = "inittracker_admin_auth";
  let adminAuthPromise = null;
  let adminAuthResolve = null;
  let adminAuthReject = null;

  // view transform
  let zoom = 32; // px per square
  let panX = 0, panY = 0;
  let dragging = null; // {cid, startX, startY, origCol, origRow}
  let draggingAoe = null; // {aid, cx, cy}
  const aoeDragOverrides = new Map(); // aid -> {cx, cy}
  let selectedAoeId = null;
  let panning = null;  // {x,y, panX, panY}
  let centeredCid = null;
  let initialCenterDone = false;
  let initialCenterFallback = false;
  let lockMap = false;
  let lastGrid = {cols: null, rows: null};
  let lastGridVersion = null;
  let fittedToGrid = false;
  let showAllNames = localStorage.getItem("inittracker_showAllNames") === "1";
  let measurementMode = false;
  let measurement = {start: null, end: null};
  let losPreview = null; // {start:{col,row}, end:{col,row}, blocked, expiresAt}
  const LOS_PREVIEW_MS = 900;
  const sheetHeightKey = "inittracker_sheetHeight";
  const uiToggleKeys = {
    topbarTitle: "inittracker_ui_topbarTitle",
    connIndicator: "inittracker_ui_connIndicator",
    lockMap: "inittracker_ui_lockMap",
    centerMap: "inittracker_ui_centerMap",
    measure: "inittracker_ui_measure",
    measureClear: "inittracker_ui_measureClear",
    zoomIn: "inittracker_ui_zoomIn",
    zoomOut: "inittracker_ui_zoomOut",
    battleLog: "inittracker_ui_battleLog",
    useAction: "inittracker_ui_useAction",
    useBonusAction: "inittracker_ui_useBonusAction",
    dash: "inittracker_ui_dash",
    standUp: "inittracker_ui_standUp",
    resetTurn: "inittracker_ui_resetTurn",
    hideSpellMenu: "inittracker_ui_hideSpellMenu",
    lockMenus: "inittracker_lockMenus",
  };
  const uiSelectKeys = {
    connStyle: "inittracker_ui_connStyle",
    initiativeStyle: "inittracker_ui_initiativeStyle",
  };
  let showTopbarTitle = readToggle(uiToggleKeys.topbarTitle, true);
  let showConnIndicator = readToggle(uiToggleKeys.connIndicator, true);
  let showLockMap = readToggle(uiToggleKeys.lockMap, true);
  let showCenterMap = readToggle(uiToggleKeys.centerMap, true);
  let showMeasure = readToggle(uiToggleKeys.measure, true);
  let showMeasureClear = readToggle(uiToggleKeys.measureClear, true);
  let showZoomIn = readToggle(uiToggleKeys.zoomIn, true);
  let showZoomOut = readToggle(uiToggleKeys.zoomOut, true);
  let showBattleLog = readToggle(uiToggleKeys.battleLog, true);
  let showUseAction = readToggle(uiToggleKeys.useAction, true);
  let showUseBonusAction = readToggle(uiToggleKeys.useBonusAction, true);
  let showDash = readToggle(uiToggleKeys.dash, true);
  let showStandUp = readToggle(uiToggleKeys.standUp, true);
  let showResetTurn = readToggle(uiToggleKeys.resetTurn, true);
  let hideSpellMenu = readToggle(uiToggleKeys.hideSpellMenu, false);
  let menusLocked = readToggle(uiToggleKeys.lockMenus, false);
  let connStyle = "full";
  let initiativeStyle = "full";
  let sheetHeight = null;
  if (turnAlertStatus){
    refreshTurnAlertStatus();
  }
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const isSafariEngine = /AppleWebKit/.test(navigator.userAgent);
  const isAltBrowser = /CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
  const isStandalone = window.navigator.standalone === true;
  if (iosInstallHint){
    const showHint = isIOS && isSafariEngine && !isAltBrowser && !isStandalone;
    iosInstallHint.classList.toggle("hidden", !showHint);
  }
  if (turnAlertsPanel){
    const hideTurnAlerts = localStorage.getItem(turnAlertHideKey) === "1";
    const shouldHideAlerts = !isIOS || hideTurnAlerts;
    turnAlertsPanel.classList.toggle("hidden", shouldHideAlerts);
  }
  if (showAllNamesEl){
    showAllNamesEl.checked = showAllNames;
    showAllNamesEl.addEventListener("change", (ev) => {
      showAllNames = !!ev.target.checked;
      localStorage.setItem("inittracker_showAllNames", showAllNames ? "1" : "0");
      draw();
    });
  }

  window.addEventListener("resize", () => {
    if (sheetWrap){
      applySheetHeight(sheetHeight);
    }
  });

  function updateConnDisplay(){
    if (connFullTextEl) connFullTextEl.textContent = connStatusText;
    if (connEl) connEl.setAttribute("title", connStatusText);
    if (connCompactLabelEl) connCompactLabelEl.textContent = "C";
    if (connDotEl){
      connDotEl.style.background = connStatusOk ? "var(--accent)" : "var(--danger)";
    }
    if (connPopoverStatusEl){
      connPopoverStatusEl.textContent = connStatusText;
    }
  }

  function setConn(ok, txt){
    connStatusOk = !!ok;
    connStatusText = String(txt || "");
    if (connEl){
      connEl.style.borderColor = connStatusOk ? "rgba(106,169,255,0.35)" : "rgba(255,91,91,0.35)";
      connEl.style.background = connStatusOk ? "rgba(106,169,255,0.14)" : "rgba(255,91,91,0.14)";
    }
    updateConnDisplay();
  }

  function setConnPopover(open){
    if (!connPopoverEl || !connEl) return;
    connPopoverEl.classList.toggle("show", open);
    connPopoverEl.setAttribute("aria-hidden", open ? "false" : "true");
    connEl.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeConnPopover(){
    setConnPopover(false);
  }

  function scheduleReconnect(delayMs){
    if (reconnectTimer){
      clearTimeout(reconnectTimer);
    }
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delayMs);
  }

  function softReconnect(){
    reconnecting = true;
    setConn(false, "Reconnecting…");
    closeConnPopover();
    if (ws && ws.readyState === 1){
      ws.close(4001, "reconnect");
    } else {
      scheduleReconnect(200);
    }
  }

  function resize(){
    const r = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(r.width * dpr));
    canvas.height = Math.max(1, Math.floor(r.height * dpr));
    ctx.setTransform(dpr,0,0,dpr,0,0);
    draw();
  }
  window.addEventListener("resize", resize);

  function getSheetConstraints(){
    const viewportHeight = window.innerHeight || 0;
    const min = Math.max(180, Math.round(viewportHeight * 0.2));
    const max = Math.max(min + 80, Math.round(viewportHeight * 0.7));
    return {min, max};
  }

  function updateModalOffsets(){
    const topbarHeight = document.querySelector(".topbar")?.getBoundingClientRect().height || 0;
    const sheetHeight = document.getElementById("sheetWrap")?.getBoundingClientRect().height || 0;
    const rootStyle = document.documentElement.style;
    rootStyle.setProperty("--modalTopOffset", `${topbarHeight}px`);
    rootStyle.setProperty("--modalBottomOffset", `${sheetHeight}px`);
    rootStyle.setProperty("--topbar-height", `${topbarHeight}px`);
    rootStyle.setProperty("--bottombar-height", `${sheetHeight}px`);
  }

  function applySheetHeight(value){
    if (!sheetWrap) return;
    const {min, max} = getSheetConstraints();
    let target = Number(value);
    if (!Number.isFinite(target)){
      target = Math.round((min + max) / 2);
    }
    target = Math.min(max, Math.max(min, target));
    sheetWrap.style.height = `${target}px`;
    sheetWrap.style.minHeight = `${min}px`;
    sheetWrap.style.maxHeight = `${max}px`;
    sheetHeight = target;
    resize();
    updateModalOffsets();
  }

  function setCastOverlayOpen(open){
    if (!castOverlay) return;
    castOverlay.classList.toggle("show", open);
    castOverlay.classList.toggle("hidden", !open);
    castOverlay.setAttribute("aria-hidden", open ? "false" : "true");
    if (sheet){
      sheet.classList.toggle("hidden", open);
    }
    if (!open){
      setSpellSelectOverlayOpen(false);
    }
    if (open){
      castOverlayPreviousFocus = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      requestAnimationFrame(() => {
        castOverlayBackBtn?.focus();
      });
    } else if (castOverlayPreviousFocus){
      castOverlayPreviousFocus.focus();
      castOverlayPreviousFocus = null;
    }
    updateModalOffsets();
    resize();
  }

  function normalizeSpellConfigValue(value, fallback){
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(0, Math.floor(parsed));
  }

  function getClaimedPlayerName(){
    const claimedUnit = getClaimedUnit();
    if (!claimedUnit?.name) return null;
    return String(claimedUnit.name);
  }

  function getPlayerProfile(name){
    if (!name) return null;
    const profiles = state?.player_profiles;
    if (!profiles || typeof profiles !== "object") return null;
    const profile = profiles[name];
    if (!profile || typeof profile !== "object") return null;
    return profile;
  }

  function getPlayerSpellConfig(name){
    const defaults = {...spellConfigDefaults};
    if (!name) return {cantrips: defaults.cantrips, spells: defaults.spells, names: []};
    let raw = null;
    const profile = getPlayerProfile(name);
    if (profile?.spellcasting && typeof profile.spellcasting === "object"){
      raw = profile.spellcasting;
    } else {
      const store = state?.player_spells;
      if (store && typeof store === "object"){
        raw = store[name];
      }
    }
    if (!raw || typeof raw !== "object"){
      return {cantrips: defaults.cantrips, spells: defaults.spells, names: []};
    }
    const names = Array.isArray(raw.known_spell_names)
      ? raw.known_spell_names.map(normalizeTextValue).filter(Boolean)
      : [];
    return {
      cantrips: normalizeSpellConfigValue(raw.known_cantrips, defaults.cantrips),
      spells: normalizeSpellConfigValue(raw.known_spells, defaults.spells),
      names,
    };
  }

  function normalizePreparedSpellList(list){
    if (!Array.isArray(list)) return [];
    return list.map(normalizeTextValue).filter(Boolean);
  }

  function evaluatePreparedFormula(formula, variables){
    if (typeof formula !== "string") return null;
    const trimmed = formula.trim();
    if (!trimmed) return null;
    if (!/^[0-9+\-*/(). _a-zA-Z]+$/.test(trimmed)) return null;
    let expr = trimmed;
    Object.entries(variables).forEach(([key, value]) => {
      const safeValue = Number.isFinite(value) ? String(value) : "0";
      const pattern = new RegExp(`\\b${key}\\b`, "g");
      expr = expr.replace(pattern, safeValue);
    });
    if (/[a-zA-Z]/.test(expr)) return null;
    try {
      const result = Function(`"use strict"; return (${expr});`)();
      if (!Number.isFinite(result)) return null;
      return Math.max(0, Math.floor(result));
    } catch (err){
      return null;
    }
  }

  function getAbilityModifier(profile, key){
    const abilities = profile?.abilities;
    if (!abilities || typeof abilities !== "object") return 0;
    const modValue = Number(abilities[`${key}_mod`] ?? abilities[`${key}_modifier`]);
    if (Number.isFinite(modValue)){
      return Math.floor(modValue);
    }
    const scoreValue = Number(
      abilities[key]
      ?? abilities[key.toUpperCase()]
      ?? abilities[`${key}_score`]
    );
    if (Number.isFinite(scoreValue)){
      return Math.floor((scoreValue - 10) / 2);
    }
    return 0;
  }

  function getPreparedSpellLimit(profile, preparedData){
    const maxFormula = preparedData?.maxFormula;
    const maxValue = preparedData?.maxValue;
    const levelRaw = profile?.leveling?.level ?? profile?.leveling?.total_level ?? profile?.leveling?.lvl;
    const level = Number.isFinite(Number(levelRaw)) ? Math.max(0, Math.floor(Number(levelRaw))) : 0;
    const variables = {
      level,
      total_level: level,
      str_mod: getAbilityModifier(profile, "str"),
      dex_mod: getAbilityModifier(profile, "dex"),
      con_mod: getAbilityModifier(profile, "con"),
      int_mod: getAbilityModifier(profile, "int"),
      wis_mod: getAbilityModifier(profile, "wis"),
      cha_mod: getAbilityModifier(profile, "cha"),
    };
    const evaluated = evaluatePreparedFormula(maxFormula, variables);
    if (Number.isFinite(evaluated)){
      return evaluated;
    }
    if (Number.isFinite(maxValue)){
      return Math.max(0, Math.floor(maxValue));
    }
    const fallbackKnown = Number(profile?.spellcasting?.known_spells);
    if (Number.isFinite(fallbackKnown)){
      return Math.max(0, Math.floor(fallbackKnown));
    }
    return null;
  }

  function getPlayerPreparedSpellConfig(name){
    const defaults = {...preparedSpellDefaults};
    if (!name) return defaults;
    let raw = null;
    const profile = getPlayerProfile(name);
    if (profile?.spellcasting && typeof profile.spellcasting === "object"){
      raw = profile.spellcasting;
    } else {
      const store = state?.player_spells;
      if (store && typeof store === "object"){
        raw = store[name];
      }
    }
    const preparedData = raw?.prepared_spells;
    if (!preparedData || typeof preparedData !== "object"){
      return defaults;
    }
    const maxFormula = typeof preparedData.max_formula === "string"
      ? preparedData.max_formula.trim()
      : "";
    const maxValue = Number(preparedData.max ?? preparedData.max_spells ?? preparedData.max_prepared);
    const limit = getPreparedSpellLimit(profile, {maxFormula, maxValue});
    return {
      prepared: normalizePreparedSpellList(preparedData.prepared),
      max: limit,
      maxFormula,
    };
  }

  function loadSpellConfig(cid){
    const claimedUnit = getClaimedUnit();
    if (!claimedUnit || String(claimedUnit.cid) !== String(cid)){
      return {...spellConfigDefaults};
    }
    const config = getPlayerSpellConfig(String(claimedUnit.name || ""));
    return {cantrips: config.cantrips, spells: config.spells};
  }

  function loadKnownSpells(cid){
    const claimedUnit = getClaimedUnit();
    if (!claimedUnit || String(claimedUnit.cid) !== String(cid)){
      return [];
    }
    const config = getPlayerSpellConfig(String(claimedUnit.name || ""));
    return config.names;
  }

  function loadPreparedSpells(cid){
    const claimedUnit = getClaimedUnit();
    if (!claimedUnit || String(claimedUnit.cid) !== String(cid)){
      return [];
    }
    const config = getPlayerPreparedSpellConfig(String(claimedUnit.name || ""));
    return config.prepared;
  }

  function getActiveSelectionSet(){
    return spellSelectContext === "prepared" ? selectedPreparedSpellKeys : selectedKnownSpellKeys;
  }

  function setSpellSelectContext(next){
    spellSelectContext = next === "prepared" ? "prepared" : "known";
    updateSpellSelectUiLabels();
    updateSpellSelectSummary();
  }

  function updateSpellSelectUiLabels(){
    const isPrepared = spellSelectContext === "prepared";
    if (spellSelectTitle){
      spellSelectTitle.textContent = isPrepared ? "Prepared Spells" : "Select Spells";
    }
    if (spellSelectCheckHeader){
      spellSelectCheckHeader.textContent = isPrepared ? "Prepared" : "Known";
    }
    if (spellSelectModeBtn){
      spellSelectModeBtn.textContent = spellSelectMode
        ? "Exit Selection"
        : (isPrepared ? "Select Prepared" : "Select Known");
    }
    if (spellSelectSaveBtn){
      spellSelectSaveBtn.textContent = isPrepared ? "Save Prepared Spells" : "Save Known Spells";
    }
  }

  function setSpellSelectOverlayOpen(open){
    if (!spellSelectOverlay) return;
    spellSelectOverlay.classList.toggle("show", open);
    spellSelectOverlay.setAttribute("aria-hidden", open ? "false" : "true");
    if (open){
      spellSelectPreviousFocus = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      if (claimedCid){
        const stored = spellSelectContext === "prepared"
          ? loadPreparedSpells(claimedCid)
          : loadKnownSpells(claimedCid);
        const nextKeys = new Set(stored.map(getSpellKey));
        if (spellSelectContext === "prepared"){
          selectedPreparedSpellKeys = nextKeys;
        } else {
          selectedKnownSpellKeys = nextKeys;
        }
      }
      updateSpellSelectUiLabels();
      if (spellSelectSaveBtn){
        spellSelectSaveBtn.disabled = !spellSelectMode;
      }
      renderSpellSelectTable(cachedSpellPresets);
      requestAnimationFrame(() => {
        spellSelectCloseBtn?.focus();
      });
    } else if (spellSelectPreviousFocus){
      spellSelectPreviousFocus.focus();
      spellSelectPreviousFocus = null;
    }
  }

  function updateLocalPlayerSpellConfig(name, config){
    if (!name) return;
    if (!state || typeof state !== "object") state = {};
    if (!state.player_spells || typeof state.player_spells !== "object"){
      state.player_spells = {};
    }
    const preparedNames = Array.isArray(config.prepared)
      ? normalizePreparedSpellList(config.prepared)
      : [];
    const preparedMaxFormula = typeof config.preparedMaxFormula === "string"
      ? config.preparedMaxFormula.trim()
      : "";
    state.player_spells[name] = {
      known_cantrips: normalizeSpellConfigValue(config.cantrips, spellConfigDefaults.cantrips),
      known_spells: normalizeSpellConfigValue(config.spells, spellConfigDefaults.spells),
      known_spell_names: Array.isArray(config.names)
        ? config.names.map(normalizeTextValue).filter(Boolean)
        : [],
      prepared_spells: {
        prepared: preparedNames,
        ...(preparedMaxFormula ? {max_formula: preparedMaxFormula} : {}),
      },
    };
    if (!state.player_profiles || typeof state.player_profiles !== "object"){
      state.player_profiles = {};
    }
    if (!state.player_profiles[name] || typeof state.player_profiles[name] !== "object"){
      state.player_profiles[name] = {name};
    }
    const profile = state.player_profiles[name];
    if (!profile.spellcasting || typeof profile.spellcasting !== "object"){
      profile.spellcasting = {};
    }
    profile.spellcasting.known_cantrips = normalizeSpellConfigValue(
      config.cantrips,
      spellConfigDefaults.cantrips
    );
    profile.spellcasting.known_spells = normalizeSpellConfigValue(
      config.spells,
      spellConfigDefaults.spells
    );
    profile.spellcasting.known_spell_names = Array.isArray(config.names)
      ? config.names.map(normalizeTextValue).filter(Boolean)
      : [];
    if (!profile.spellcasting.prepared_spells || typeof profile.spellcasting.prepared_spells !== "object"){
      profile.spellcasting.prepared_spells = {};
    }
    profile.spellcasting.prepared_spells.prepared = preparedNames;
    if (preparedMaxFormula){
      profile.spellcasting.prepared_spells.max_formula = preparedMaxFormula;
    }
  }

  async function persistPlayerSpellConfig(name, config){
    if (!name) return false;
    const preparedNames = Array.isArray(config.prepared)
      ? normalizePreparedSpellList(config.prepared)
      : [];
    const preparedMaxFormula = typeof config.preparedMaxFormula === "string"
      ? config.preparedMaxFormula.trim()
      : "";
    const payload = {
      known_cantrips: normalizeSpellConfigValue(config.cantrips, spellConfigDefaults.cantrips),
      known_spells: normalizeSpellConfigValue(config.spells, spellConfigDefaults.spells),
      known_spell_names: Array.isArray(config.names)
        ? config.names.map(normalizeTextValue).filter(Boolean)
        : [],
      prepared_spells: {
        prepared: preparedNames,
        ...(preparedMaxFormula ? {max_formula: preparedMaxFormula} : {}),
      },
    };
    try {
      const response = await fetch(`/api/players/${encodeURIComponent(name)}/spells`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (!response.ok){
        const detail = await response.text();
        throw new Error(detail || "Save failed.");
      }
      const data = await response.json();
      const player = data?.player;
      if (player && typeof player === "object"){
        const preparedData = player.prepared_spells || {};
        updateLocalPlayerSpellConfig(name, {
          cantrips: player.known_cantrips,
          spells: player.known_spells,
          names: player.known_spell_names,
          prepared: preparedData.prepared,
          preparedMaxFormula: preparedData.max_formula || preparedMaxFormula,
        });
      } else {
        updateLocalPlayerSpellConfig(name, {
          cantrips: payload.known_cantrips,
          spells: payload.known_spells,
          names: payload.known_spell_names,
          prepared: payload.prepared_spells.prepared,
          preparedMaxFormula: payload.prepared_spells.max_formula || preparedMaxFormula,
        });
      }
      return true;
    } catch (err){
      console.warn("Unable to persist known spells.", err);
      localToast("Unable to save known spells.");
      return false;
    }
  }

  function setSpellConfigOpen(open){
    if (!spellConfigModal) return;
    if (open){
      if (!claimedCid){
        localToast("Claim a character first.");
        return;
      }
      spellConfigPreviousFocus = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      const config = loadSpellConfig(claimedCid);
      if (spellConfigCantripsInput){
        spellConfigCantripsInput.value = String(config.cantrips);
      }
      if (spellConfigSpellsInput){
        spellConfigSpellsInput.value = String(config.spells);
      }
    }
    spellConfigModal.classList.toggle("show", open);
    spellConfigModal.setAttribute("aria-hidden", open ? "false" : "true");
    if (open){
      requestAnimationFrame(() => {
        spellConfigCantripsInput?.focus();
      });
    } else if (spellConfigPreviousFocus){
      spellConfigPreviousFocus.focus();
      spellConfigPreviousFocus = null;
    }
  }

  function persistSheetHeight(){
    if (!Number.isFinite(sheetHeight)) return;
    localStorage.setItem(sheetHeightKey, String(Math.round(sheetHeight)));
  }

  function loadSheetHeight(){
    if (!sheetWrap) return;
    const stored = Number(localStorage.getItem(sheetHeightKey));
    applySheetHeight(stored);
  }

  function readToggle(key, defaultValue){
    const stored = localStorage.getItem(key);
    if (stored === null || stored === undefined) return defaultValue;
    return stored === "1";
  }

  function readChoice(key, allowed, defaultValue){
    const stored = localStorage.getItem(key);
    if (stored && allowed.includes(stored)) return stored;
    return defaultValue;
  }

  function persistToggle(key, value){
    localStorage.setItem(key, value ? "1" : "0");
  }

  function persistChoice(key, value){
    if (!value){
      localStorage.removeItem(key);
      return;
    }
    localStorage.setItem(key, value);
  }

  connStyle = readChoice(uiSelectKeys.connStyle, ["full", "compact"], "full");
  initiativeStyle = readChoice(uiSelectKeys.initiativeStyle, ["full", "compact", "hidden"], "full");
  let connStatusText = "Connecting…";
  let connStatusOk = false;

  const hotkeyConfig = {
    toggleTopbarTitle: {
      input: hotkeyTopbarTitleInput,
      conflictEl: document.getElementById("hotkeyConflictTopbarTitle"),
      storageKey: "inittracker_hotkey_toggleTopbarTitle",
      action: () => {
        showTopbarTitle = !showTopbarTitle;
        persistToggle(uiToggleKeys.topbarTitle, showTopbarTitle);
        applyUiConfig();
      },
    },
    toggleConnStyle: {
      input: hotkeyConnStyleInput,
      conflictEl: document.getElementById("hotkeyConflictConnStyle"),
      storageKey: "inittracker_hotkey_toggleConnStyle",
      action: () => {
        connStyle = connStyle === "compact" ? "full" : "compact";
        persistChoice(uiSelectKeys.connStyle, connStyle);
        applyUiConfig();
      },
    },
    lockMap: {
      input: hotkeyLockMapInput,
      conflictEl: document.getElementById("hotkeyConflictLockMap"),
      storageKey: "inittracker_hotkey_lockMap",
      action: () => lockMapBtn && lockMapBtn.click(),
    },
    centerMap: {
      input: hotkeyCenterMapInput,
      conflictEl: document.getElementById("hotkeyConflictCenterMap"),
      storageKey: "inittracker_hotkey_centerMap",
      action: () => centerMapBtn && centerMapBtn.click(),
    },
    measure: {
      input: hotkeyMeasureInput,
      conflictEl: document.getElementById("hotkeyConflictMeasure"),
      storageKey: "inittracker_hotkey_measure",
      action: () => measureToggle && measureToggle.click(),
    },
    measureClear: {
      input: hotkeyMeasureClearInput,
      conflictEl: document.getElementById("hotkeyConflictMeasureClear"),
      storageKey: "inittracker_hotkey_measureClear",
      action: () => measureClear && measureClear.click(),
    },
    zoomIn: {
      input: hotkeyZoomInInput,
      conflictEl: document.getElementById("hotkeyConflictZoomIn"),
      storageKey: "inittracker_hotkey_zoomIn",
      action: () => zoomInBtn && zoomInBtn.click(),
    },
    zoomOut: {
      input: hotkeyZoomOutInput,
      conflictEl: document.getElementById("hotkeyConflictZoomOut"),
      storageKey: "inittracker_hotkey_zoomOut",
      action: () => zoomOutBtn && zoomOutBtn.click(),
    },
    battleLog: {
      input: hotkeyBattleLogInput,
      conflictEl: document.getElementById("hotkeyConflictBattleLog"),
      storageKey: "inittracker_hotkey_battleLog",
      action: () => battleLogBtn && battleLogBtn.click(),
    },
    useAction: {
      input: hotkeyUseActionInput,
      conflictEl: document.getElementById("hotkeyConflictUseAction"),
      storageKey: "inittracker_hotkey_useAction",
      action: () => useActionBtn && useActionBtn.click(),
    },
    useBonusAction: {
      input: hotkeyUseBonusActionInput,
      conflictEl: document.getElementById("hotkeyConflictUseBonusAction"),
      storageKey: "inittracker_hotkey_useBonusAction",
      action: () => useBonusActionBtn && useBonusActionBtn.click(),
    },
    dash: {
      input: hotkeyDashInput,
      conflictEl: document.getElementById("hotkeyConflictDash"),
      storageKey: "inittracker_hotkey_dash",
      action: () => dashBtn && dashBtn.click(),
    },
    standUp: {
      input: hotkeyStandUpInput,
      conflictEl: document.getElementById("hotkeyConflictStandUp"),
      storageKey: "inittracker_hotkey_standUp",
      action: () => standUpBtn && standUpBtn.click(),
    },
    resetTurn: {
      input: hotkeyResetTurnInput,
      conflictEl: document.getElementById("hotkeyConflictResetTurn"),
      storageKey: "inittracker_hotkey_resetTurn",
      action: () => resetTurnBtn && resetTurnBtn.click(),
    },
  };

  let hotkeyBindings = new Map();

  function normalizeHotkeyEvent(event){
    if (!event) return null;
    if (event.key === "Shift" || event.key === "Control" || event.key === "Alt" || event.key === "Meta"){
      return null;
    }
    const parts = [];
    if (event.ctrlKey) parts.push("Ctrl");
    if (event.altKey) parts.push("Alt");
    if (event.metaKey) parts.push("Meta");
    if (event.shiftKey) parts.push("Shift");
    let key = event.key;
    if (key === " ") key = "Space";
    if (key.length === 1) key = key.toUpperCase();
    parts.push(key);
    return parts.join("+");
  }

  function isTypingTarget(target){
    if (!target) return false;
    const tag = target.tagName ? target.tagName.toLowerCase() : "";
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (target.isContentEditable) return true;
    return false;
  }

  function setHotkey(action, value){
    const config = hotkeyConfig[action];
    if (!config) return;
    const stored = value ? String(value) : "";
    if (stored){
      localStorage.setItem(config.storageKey, stored);
    } else {
      localStorage.removeItem(config.storageKey);
    }
    updateHotkeyInputs();
  }

  function updateHotkeyInputs(){
    const usage = {};
    hotkeyBindings = new Map();
    Object.entries(hotkeyConfig).forEach(([action, config]) => {
      if (!config || !config.input) return;
      const stored = localStorage.getItem(config.storageKey) || "";
      const normalized = stored.trim();
      config.input.value = normalized;
      if (normalized){
        if (!usage[normalized]) usage[normalized] = [];
        usage[normalized].push(action);
      }
    });
    Object.entries(hotkeyConfig).forEach(([action, config]) => {
      if (!config || !config.input) return;
      const stored = (localStorage.getItem(config.storageKey) || "").trim();
      const conflicts = stored && usage[stored] && usage[stored].length > 1;
      config.input.classList.toggle("conflict", !!conflicts);
      if (config.conflictEl){
        config.conflictEl.textContent = conflicts ? "Conflict" : "";
      }
      if (stored && !conflicts){
        hotkeyBindings.set(stored, action);
      }
    });
  }

  let presetStatusTimer = null;
  const presetStorageKey = "inittracker_gui_preset";

  function setPresetStatus(text, durationMs=2000){
    if (!presetStatus) return;
    presetStatus.textContent = text || "";
    if (presetStatusTimer){
      clearTimeout(presetStatusTimer);
      presetStatusTimer = null;
    }
    if (text && durationMs > 0){
      presetStatusTimer = setTimeout(() => {
        if (presetStatus) presetStatus.textContent = "";
        presetStatusTimer = null;
      }, durationMs);
    }
  }

  function normalizePresetHotkey(value){
    if (value === null || value === undefined) return "";
    const normalized = String(value).trim();
    return normalized;
  }

  function buildGuiPreset(){
    const hotkeys = {};
    Object.entries(hotkeyConfig).forEach(([action, config]) => {
      if (!config || !config.storageKey) return;
      hotkeys[action] = normalizePresetHotkey(localStorage.getItem(config.storageKey) || "");
    });
    return {
      version: 1,
      toggles: {
        topbarTitle: showTopbarTitle,
        connIndicator: showConnIndicator,
        lockMap: showLockMap,
        centerMap: showCenterMap,
        measure: showMeasure,
        measureClear: showMeasureClear,
        zoomIn: showZoomIn,
        zoomOut: showZoomOut,
        battleLog: showBattleLog,
        useAction: showUseAction,
        useBonusAction: showUseBonusAction,
        dash: showDash,
        standUp: showStandUp,
        resetTurn: showResetTurn,
        hideSpellMenu: hideSpellMenu,
        lockMenus: menusLocked,
      },
      choices: {
        connStyle,
        initiativeStyle,
      },
      showAllNames: showAllNames,
      sheetHeight: Number.isFinite(sheetHeight) ? Math.round(sheetHeight) : null,
      hotkeys,
    };
  }

  function persistLocalPreset(preset){
    try {
      localStorage.setItem(presetStorageKey, JSON.stringify(preset));
    } catch (err){
      console.warn("Failed to persist GUI preset locally.", err);
    }
  }

  function loadLocalPreset(){
    try {
      const raw = localStorage.getItem(presetStorageKey);
      if (!raw) return null;
      const preset = JSON.parse(raw);
      if (preset && typeof preset === "object"){
        return preset;
      }
    } catch (err){
      console.warn("Failed to load GUI preset from storage.", err);
    }
    return null;
  }

  function applyGuiPreset(preset, options = {}){
    if (!preset || typeof preset !== "object") return;
    const persist = options.persist !== false;
    const toggles = preset.toggles && typeof preset.toggles === "object" ? preset.toggles : {};
    const choices = preset.choices && typeof preset.choices === "object" ? preset.choices : {};
    if (typeof toggles.topbarTitle === "boolean") showTopbarTitle = toggles.topbarTitle;
    if (typeof toggles.connIndicator === "boolean") showConnIndicator = toggles.connIndicator;
    if (typeof toggles.lockMap === "boolean") showLockMap = toggles.lockMap;
    if (typeof toggles.centerMap === "boolean") showCenterMap = toggles.centerMap;
    if (typeof toggles.measure === "boolean") showMeasure = toggles.measure;
    if (typeof toggles.measureClear === "boolean") showMeasureClear = toggles.measureClear;
    if (typeof toggles.zoomIn === "boolean") showZoomIn = toggles.zoomIn;
    if (typeof toggles.zoomOut === "boolean") showZoomOut = toggles.zoomOut;
    if (typeof toggles.battleLog === "boolean") showBattleLog = toggles.battleLog;
    if (typeof toggles.useAction === "boolean") showUseAction = toggles.useAction;
    if (typeof toggles.useBonusAction === "boolean") showUseBonusAction = toggles.useBonusAction;
    if (typeof toggles.dash === "boolean") showDash = toggles.dash;
    if (typeof toggles.standUp === "boolean") showStandUp = toggles.standUp;
    if (typeof toggles.resetTurn === "boolean") showResetTurn = toggles.resetTurn;
    if (typeof toggles.hideSpellMenu === "boolean") hideSpellMenu = toggles.hideSpellMenu;
    if (typeof toggles.lockMenus === "boolean") menusLocked = toggles.lockMenus;
    if (persist){
      persistToggle(uiToggleKeys.topbarTitle, showTopbarTitle);
      persistToggle(uiToggleKeys.connIndicator, showConnIndicator);
      persistToggle(uiToggleKeys.lockMap, showLockMap);
      persistToggle(uiToggleKeys.centerMap, showCenterMap);
      persistToggle(uiToggleKeys.measure, showMeasure);
      persistToggle(uiToggleKeys.measureClear, showMeasureClear);
      persistToggle(uiToggleKeys.zoomIn, showZoomIn);
      persistToggle(uiToggleKeys.zoomOut, showZoomOut);
      persistToggle(uiToggleKeys.battleLog, showBattleLog);
      persistToggle(uiToggleKeys.useAction, showUseAction);
      persistToggle(uiToggleKeys.useBonusAction, showUseBonusAction);
      persistToggle(uiToggleKeys.dash, showDash);
      persistToggle(uiToggleKeys.standUp, showStandUp);
      persistToggle(uiToggleKeys.resetTurn, showResetTurn);
      persistToggle(uiToggleKeys.hideSpellMenu, hideSpellMenu);
      persistToggle(uiToggleKeys.lockMenus, menusLocked);
    }
    if (choices.connStyle && ["full", "compact"].includes(choices.connStyle)){
      connStyle = choices.connStyle;
      if (persist){
        persistChoice(uiSelectKeys.connStyle, connStyle);
      }
    }
    if (choices.initiativeStyle && ["full", "compact", "hidden"].includes(choices.initiativeStyle)){
      initiativeStyle = choices.initiativeStyle;
      if (persist){
        persistChoice(uiSelectKeys.initiativeStyle, initiativeStyle);
      }
    }
    if (typeof preset.showAllNames === "boolean"){
      showAllNames = preset.showAllNames;
      if (showAllNamesEl){
        showAllNamesEl.checked = showAllNames;
      }
      if (persist){
        localStorage.setItem("inittracker_showAllNames", showAllNames ? "1" : "0");
      }
    }
    if (Number.isFinite(Number(preset.sheetHeight))){
      applySheetHeight(Number(preset.sheetHeight));
      if (persist){
        persistSheetHeight();
      }
    }
    if (preset.hotkeys && typeof preset.hotkeys === "object"){
      Object.entries(preset.hotkeys).forEach(([action, value]) => {
        const config = hotkeyConfig[action];
        if (!config || !config.storageKey) return;
        const normalized = normalizePresetHotkey(value);
        if (persist){
          if (normalized){
            localStorage.setItem(config.storageKey, normalized);
          } else {
            localStorage.removeItem(config.storageKey);
          }
        }
        if (config.input){
          config.input.value = normalized;
        }
      });
    }
    applyUiConfig();
    updateHotkeyInputs();
  }

  function applyConnStyle(){
    if (!connEl) return;
    connEl.classList.toggle("conn-compact", connStyle === "compact");
    updateConnDisplay();
  }

  function applyUiConfig(){
    document.body.classList.toggle("menus-locked", menusLocked);
    document.body.classList.toggle("initiative-compact", initiativeStyle === "compact");
    document.body.classList.toggle("initiative-hidden", initiativeStyle === "hidden");
    if (topbarTitleEl) topbarTitleEl.classList.toggle("hidden", !showTopbarTitle);
    if (connEl) connEl.classList.toggle("hidden", !showConnIndicator);
    if (!showConnIndicator){
      closeConnPopover();
    }
    if (lockMapBtn) lockMapBtn.classList.toggle("hidden", !showLockMap);
    if (centerMapBtn) centerMapBtn.classList.toggle("hidden", !showCenterMap);
    if (measureToggle) measureToggle.classList.toggle("hidden", !showMeasure);
    if (measureClear) measureClear.classList.toggle("hidden", !showMeasureClear);
    if (zoomInBtn) zoomInBtn.classList.toggle("hidden", !showZoomIn);
    if (zoomOutBtn) zoomOutBtn.classList.toggle("hidden", !showZoomOut);
    if (battleLogBtn) battleLogBtn.classList.toggle("hidden", !showBattleLog);
    if (useActionBtn) useActionBtn.classList.toggle("hidden", !showUseAction);
    if (useBonusActionBtn) useBonusActionBtn.classList.toggle("hidden", !showUseBonusAction);
    if (dashBtn) dashBtn.classList.toggle("hidden", !showDash);
    if (standUpBtn) standUpBtn.classList.toggle("hidden", !showStandUp);
    if (resetTurnBtn) resetTurnBtn.classList.toggle("hidden", !showResetTurn);
    if (toggleTopbarTitle) toggleTopbarTitle.checked = showTopbarTitle;
    if (toggleConnIndicator) toggleConnIndicator.checked = showConnIndicator;
    if (connStyleButtons.length){
      connStyleButtons.forEach((button) => {
        const isActive = button.dataset.connStyle === connStyle;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
    }
    if (toggleLockMap) toggleLockMap.checked = showLockMap;
    if (toggleCenterMap) toggleCenterMap.checked = showCenterMap;
    if (toggleMeasure) toggleMeasure.checked = showMeasure;
    if (toggleMeasureClear) toggleMeasureClear.checked = showMeasureClear;
    if (toggleZoomIn) toggleZoomIn.checked = showZoomIn;
    if (toggleZoomOut) toggleZoomOut.checked = showZoomOut;
    if (toggleBattleLog) toggleBattleLog.checked = showBattleLog;
    if (initiativeStyleSelect) initiativeStyleSelect.value = initiativeStyle;
    if (toggleUseAction) toggleUseAction.checked = showUseAction;
    if (toggleUseBonusAction) toggleUseBonusAction.checked = showUseBonusAction;
    if (toggleDash) toggleDash.checked = showDash;
    if (toggleStandUp) toggleStandUp.checked = showStandUp;
    if (toggleResetTurn) toggleResetTurn.checked = showResetTurn;
    if (toggleSpellMenu) toggleSpellMenu.checked = hideSpellMenu;
    if (toggleLockMenus) toggleLockMenus.checked = menusLocked;
    if (sheetHandle){
      sheetHandle.setAttribute("aria-disabled", menusLocked ? "true" : "false");
    }
    applyConnStyle();
    updateHotkeyInputs();
    updateSpellPanelVisibility();
  }

  const localPreset = loadLocalPreset();
  if (localPreset){
    applyGuiPreset(localPreset, {persist: true});
    if (!Number.isFinite(Number(localPreset.sheetHeight))){
      loadSheetHeight();
    }
  } else {
    applyUiConfig();
    loadSheetHeight();
  }
  if (sheetHandle && sheetWrap){
    let dragState = null;
    sheetHandle.addEventListener("pointerdown", (event) => {
      if (menusLocked) return;
      sheetHandle.setPointerCapture(event.pointerId);
      dragState = {
        startY: event.clientY,
        startHeight: sheetWrap.getBoundingClientRect().height,
      };
      event.preventDefault();
    });
    sheetHandle.addEventListener("pointermove", (event) => {
      if (!dragState) return;
      const delta = dragState.startY - event.clientY;
      applySheetHeight(dragState.startHeight + delta);
    });
    sheetHandle.addEventListener("pointerup", () => {
      if (!dragState) return;
      dragState = null;
      persistSheetHeight();
    });
    sheetHandle.addEventListener("pointercancel", () => {
      if (!dragState) return;
      dragState = null;
      persistSheetHeight();
    });
  }

  function showConfigModal(){
    if (!configModal) return;
    configModal.classList.add("show");
    configModal.setAttribute("aria-hidden", "false");
    if (configBtn){
      configBtn.setAttribute("aria-expanded", "true");
    }
  }

  function hideConfigModal(){
    if (!configModal) return;
    configModal.classList.remove("show");
    configModal.setAttribute("aria-hidden", "true");
    if (configBtn){
      configBtn.setAttribute("aria-expanded", "false");
    }
  }

  function setAdminMenu(open){
    if (!adminMenuPopover || !adminMenuBtn) return;
    adminMenuPopover.classList.toggle("show", open);
    adminMenuPopover.setAttribute("aria-hidden", open ? "false" : "true");
    adminMenuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAdminMenu(){
    setAdminMenu(false);
  }

  function showAdminModal(){
    if (!adminModal) return;
    adminModal.classList.add("show");
    adminModal.setAttribute("aria-hidden", "false");
  }

  function hideAdminModal(){
    if (!adminModal) return;
    adminModal.classList.remove("show");
    adminModal.setAttribute("aria-hidden", "true");
  }

  function showAdminLoginModal(){
    if (!adminLoginModal) return;
    adminLoginModal.classList.add("show");
    adminLoginModal.setAttribute("aria-hidden", "false");
    if (adminPasswordInput){
      adminPasswordInput.value = "";
      setTimeout(() => adminPasswordInput.focus(), 50);
    }
  }

  function hideAdminLoginModal(){
    if (!adminLoginModal) return;
    adminLoginModal.classList.remove("show");
    adminLoginModal.setAttribute("aria-hidden", "true");
    setAdminLoginStatus("");
  }

  function setAdminStatus(text){
    if (!adminStatus) return;
    adminStatus.textContent = text || "";
  }

  function setAdminLoginStatus(text){
    if (!adminLoginStatus) return;
    adminLoginStatus.textContent = text || "";
  }

  function getAdminAuth(){
    try {
      const raw = sessionStorage.getItem(adminTokenKey);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || typeof data !== "object") return null;
      if (!data.token) return null;
      if (data.expiresAt && Date.now() > Number(data.expiresAt)){
        sessionStorage.removeItem(adminTokenKey);
        return null;
      }
      return data.token;
    } catch (err){
      sessionStorage.removeItem(adminTokenKey);
      return null;
    }
  }

  function setAdminAuth(token, expiresIn){
    if (!token) return;
    const expiresMs = Math.max(1, Number(expiresIn || 0)) * 1000;
    const payload = {token, expiresAt: Date.now() + expiresMs};
    sessionStorage.setItem(adminTokenKey, JSON.stringify(payload));
  }

  function clearAdminAuth(){
    sessionStorage.removeItem(adminTokenKey);
  }

  function requestAdminLogin(){
    if (getAdminAuth()){
      return Promise.resolve(getAdminAuth());
    }
    if (adminAuthPromise){
      return adminAuthPromise;
    }
    adminAuthPromise = new Promise((resolve, reject) => {
      adminAuthResolve = resolve;
      adminAuthReject = reject;
      showAdminLoginModal();
    });
    return adminAuthPromise;
  }

  function finalizeAdminLogin(success, token){
    if (!adminAuthPromise) return;
    const resolve = adminAuthResolve;
    const reject = adminAuthReject;
    adminAuthPromise = null;
    adminAuthResolve = null;
    adminAuthReject = null;
    if (success && resolve){
      resolve(token);
    } else if (!success && reject){
      reject(new Error("Admin login canceled."));
    }
  }

  async function adminFetch(url, options = {}){
    const token = await requestAdminLogin();
    const headers = new Headers(options.headers || {});
    if (token){
      headers.set("Authorization", `Bearer ${token}`);
    }
    const res = await fetch(url, {...options, headers});
    if ((res.status === 401 || res.status === 403) && !options._retry){
      clearAdminAuth();
      try {
        await requestAdminLogin();
      } catch (err){
        return res;
      }
      return adminFetch(url, {...options, _retry: true});
    }
    return res;
  }

  function buildAdminPcOptions(selectedCid){
    const options = [];
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "(unassigned)";
    options.push(blank);
    adminPcs.forEach((pc) => {
      const opt = document.createElement("option");
      opt.value = String(pc.cid);
      opt.textContent = pc.name || `cid ${pc.cid}`;
      if (selectedCid !== null && selectedCid !== undefined && String(pc.cid) === String(selectedCid)){
        opt.selected = true;
      }
      options.push(opt);
    });
    return options;
  }

  async function submitAdminLogin(){
    const password = adminPasswordInput ? adminPasswordInput.value : "";
    if (!password){
      setAdminLoginStatus("Enter a password to continue.");
      return;
    }
    try {
      setAdminLoginStatus("Signing in…");
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password}),
      });
      if (!res.ok){
        if (res.status === 403){
          setAdminLoginStatus("Admin password is not configured.");
        } else {
          setAdminLoginStatus("Invalid password. Try again.");
        }
        return;
      }
      const payload = await res.json();
      if (!payload || !payload.token){
        setAdminLoginStatus("Login failed.");
        return;
      }
      setAdminAuth(payload.token, payload.expires_in);
      hideAdminLoginModal();
      finalizeAdminLogin(true, payload.token);
    } catch (err){
      console.warn("Admin login failed.", err);
      setAdminLoginStatus("Login failed. Try again.");
    }
  }

  function renderAdminSessions(){
    if (!adminSessionList) return;
    adminSessionList.innerHTML = "";
    if (!adminSessions.length){
      const empty = document.createElement("div");
      empty.className = "hint";
      empty.textContent = "No sessions found yet.";
      adminSessionList.appendChild(empty);
      return;
    }
    adminSessions.forEach((session) => {
      const row = document.createElement("div");
      row.className = "admin-session";
      const top = document.createElement("div");
      top.className = "admin-session-top";
      const ipWrap = document.createElement("div");
      const ipText = document.createElement("div");
      ipText.className = "admin-session-ip";
      ipText.textContent = session.ip || session.host || "(unknown)";
      const metaText = document.createElement("div");
      metaText.className = "admin-session-meta";
      const reverseDns = session.reverse_dns ? `rDNS: ${session.reverse_dns}` : "rDNS: —";
      const lastSeen = session.last_seen ? `Last seen: ${session.last_seen}` : "";
      metaText.textContent = [reverseDns, lastSeen].filter(Boolean).join(" · ");
      ipWrap.appendChild(ipText);
      ipWrap.appendChild(metaText);
      const status = document.createElement("span");
      status.className = "admin-session-status";
      const statusValue = String(session.status || "offline").toLowerCase();
      status.classList.add(statusValue === "connected" ? "connected" : "offline");
      status.textContent = statusValue === "connected" ? "Connected" : "Offline";
      top.appendChild(ipWrap);
      top.appendChild(status);

      const assignRow = document.createElement("div");
      assignRow.className = "admin-session-assign";
      const assignedText = document.createElement("div");
      assignedText.className = "admin-session-meta";
      const assignedLabel = session.assigned_name || "Unassigned";
      const yamlLabel = session.yaml_assigned_name ? `YAML: ${session.yaml_assigned_name}` : "";
      assignedText.textContent = `Assigned: ${assignedLabel}${yamlLabel ? ` · ${yamlLabel}` : ""}`;
      const select = document.createElement("select");
      buildAdminPcOptions(session.assigned_cid).forEach((opt) => select.appendChild(opt));
      const assignBtn = document.createElement("button");
      assignBtn.className = "btn";
      assignBtn.type = "button";
      assignBtn.textContent = "Save";
      assignBtn.addEventListener("click", async () => {
        const value = select.value;
        const cid = value ? Number(value) : null;
        await assignAdminIp(session.ip || session.host || "", cid);
      });
      assignRow.appendChild(assignedText);
      assignRow.appendChild(select);
      assignRow.appendChild(assignBtn);

      row.appendChild(top);
      row.appendChild(assignRow);
      adminSessionList.appendChild(row);
    });
  }

  async function fetchAdminSessions({silent} = {}){
    try {
      if (!silent) setAdminStatus("Loading sessions…");
      const res = await adminFetch("/api/admin/sessions");
      if (!res.ok){
        throw new Error(`HTTP ${res.status}`);
      }
      const payload = await res.json();
      adminSessions = Array.isArray(payload.sessions) ? payload.sessions : [];
      adminPcs = Array.isArray(payload.pcs) ? payload.pcs : [];
      setAdminStatus(`Loaded ${adminSessions.length} session${adminSessions.length === 1 ? "" : "s"}.`);
      renderAdminSessions();
    } catch (err){
      console.warn("Failed to load admin sessions.", err);
      setAdminStatus("Failed to load sessions.");
    }
  }

  async function assignAdminIp(ip, cid){
    const host = String(ip || "").trim();
    if (!host){
      setAdminStatus("Missing IP address.");
      return;
    }
    try {
      setAdminStatus("Saving assignment…");
      const res = await adminFetch("/api/admin/assign_ip", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ip: host, cid}),
      });
      if (!res.ok){
        throw new Error(`HTTP ${res.status}`);
      }
      await res.json();
      await fetchAdminSessions({silent: true});
      setAdminStatus("Assignment saved.");
    } catch (err){
      console.warn("Failed to assign session.", err);
      setAdminStatus("Failed to save assignment.");
    }
  }

  function send(msg){
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify(msg));
  }

  function localToast(text){
    if (!noteEl) return;
    noteEl.textContent = text || "…";
    setTimeout(() => noteEl.textContent = "Tip: drag yer token", 2500);
  }

  function normalizeHexColor(raw){
    if (!raw) return null;
    const value = String(raw).trim().toLowerCase();
    if (!/^#[0-9a-f]{6}$/.test(value)) return null;
    return value;
  }

  function setLocalAoeCenter(aid, cx, cy){
    if (!state || !Array.isArray(state.aoes)) return;
    const target = state.aoes.find(a => Number(a.aid) === Number(aid));
    if (!target) return;
    target.cx = cx;
    target.cy = cy;
  }

  function setLocalAoeMoveRemaining(aid, remaining){
    if (!state || !Array.isArray(state.aoes)) return;
    const target = state.aoes.find(a => Number(a.aid) === Number(aid));
    if (!target) return;
    target.move_remaining_ft = remaining;
  }

  function setSelectedAoe(aid){
    if (aid === null || aid === undefined){
      selectedAoeId = null;
    } else {
      const parsed = Number(aid);
      selectedAoeId = Number.isFinite(parsed) ? parsed : null;
    }
  }

  function syncSelectedAoe(){
    if (selectedAoeId === null || selectedAoeId === undefined){
      return;
    }
    const exists = Array.isArray(state?.aoes)
      && state.aoes.some(a => Number(a.aid) === Number(selectedAoeId));
    if (!exists){
      selectedAoeId = null;
    }
  }

  function hexToRgb(hex){
    const value = normalizeHexColor(hex);
    if (!value) return null;
    return {
      r: parseInt(value.slice(1, 3), 16),
      g: parseInt(value.slice(3, 5), 16),
      b: parseInt(value.slice(5, 7), 16),
    };
  }

  function isForbiddenColor(hex){
    const rgb = hexToRgb(hex);
    if (!rgb) return false;
    if (rgb.r >= 245 && rgb.g >= 245 && rgb.b >= 245) return true;
    if (rgb.r >= 200 && rgb.g <= 80 && rgb.b <= 80) return true;
    return false;
  }

  function rgbaFromHex(hex, alpha){
    const rgb = hexToRgb(hex);
    if (!rgb) return null;
    return `rgba(${rgb.r},${rgb.g},${rgb.b},${alpha})`;
  }

  function updateTokenColorSwatch(color){
    if (!tokenColorSwatch) return;
    tokenColorSwatch.style.background = color || "#6aa9ff";
  }

  function openColorModal(unit){
    if (!colorModal || !tokenColorInput) return;
    const targetUnit = unit || getClaimedUnit();
    if (!targetUnit){
      localToast("Claim a character first, matey.");
      return;
    }
    pendingClaim = targetUnit;
    let preferred = normalizeHexColor(targetUnit?.token_color)
      || normalizeHexColor(localStorage.getItem("inittracker_tokenColor"))
      || "#6aa9ff";
    if (isForbiddenColor(preferred)){
      preferred = "#6aa9ff";
    }
    tokenColorInput.value = preferred;
    updateTokenColorSwatch(preferred);
    colorModal.classList.add("show");
    colorModal.setAttribute("aria-hidden", "false");
  }

  function closeColorModal(){
    if (!colorModal) return;
    colorModal.classList.remove("show");
    colorModal.setAttribute("aria-hidden", "true");
    pendingClaim = null;
  }

  function openClaimedColorModal(){
    openColorModal(getClaimedUnit());
  }

  function validateTokenColor(raw){
    const color = normalizeHexColor(raw);
    if (!color){
      localToast("Pick a valid hex color, matey.");
      return null;
    }
    if (isForbiddenColor(color)){
      localToast("No red or white, matey.");
      return null;
    }
    return color;
  }

  function showNoOwnedPcToast(pcs){
    if (shownNoOwnedToast) return;
    if (claimedCid) return;
    const list = Array.isArray(pcs) ? pcs : [];
    if (!list.length) return;
    localToast("No assigned PCs found. Ask the DM to assign yer character.");
    shownNoOwnedToast = true;
  }

  function showDashModal(){
    if (!dashModal) return;
    dashModal.classList.add("show");
    dashModal.setAttribute("aria-hidden", "false");
  }

  function hideDashModal(){
    if (!dashModal) return;
    dashModal.classList.remove("show");
    dashModal.setAttribute("aria-hidden", "true");
  }

  function showLogModal(){
    if (!logModal) return;
    logModal.classList.add("show");
    logModal.setAttribute("aria-hidden", "false");
  }

  function hideLogModal(){
    if (!logModal) return;
    logModal.classList.remove("show");
    logModal.setAttribute("aria-hidden", "true");
  }

  function requestBattleLog(){
    if (logContent){
      logContent.textContent = "Loading…";
    }
    send({type:"log_request"});
  }

  function gridToScreen(col,row){
    return {x: panX + col*zoom + zoom/2, y: panY + row*zoom + zoom/2};
  }
  function screenToGrid(x,y){
    return {col: Math.floor((x - panX)/zoom), row: Math.floor((y - panY)/zoom)};
  }
  function screenToGridFloat(x,y){
    const col = (x - panX) / zoom;
    const row = (y - panY) / zoom;
    return {col: Math.round(col * 2) / 2, row: Math.round(row * 2) / 2};
  }

  function hitTestAoe(p){
    if (!state || !state.aoes || !state.aoes.length) return null;
    for (let i = state.aoes.length - 1; i >= 0; i--){
      const a = state.aoes[i];
      if (!a || !a.kind) continue;
      const remainingTurns = Number(a.remaining_turns);
      if (Number.isFinite(remainingTurns) && remainingTurns <= 0){
        continue;
      }
      const cx = Number(a.cx ?? 0);
      const cy = Number(a.cy ?? 0);
      const center = gridToScreen(cx, cy);
      const dx = p.x - center.x;
      const dy = p.y - center.y;
      if (a.kind === "circle" || a.kind === "sphere" || a.kind === "cylinder"){
        const r = Math.max(0, Number(a.radius_sq || 0)) * zoom;
        if (dx * dx + dy * dy <= r * r){
          return a;
        }
      } else if (a.kind === "square" || a.kind === "cube"){
        const half = Math.max(0, Number(a.side_sq || 0)) * zoom / 2;
        if (Math.abs(dx) <= half && Math.abs(dy) <= half){
          return a;
        }
      } else if (a.kind === "line" || a.kind === "wall"){
        const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
        const widthPx = Math.max(0, Number(a.width_sq || 0)) * zoom;
        const orient = a.orient === "horizontal" ? "horizontal" : "vertical";
        const angleDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : (orient === "horizontal" ? 0 : 90);
        const angle = (-angleDeg * Math.PI) / 180;
        const rx = dx * Math.cos(angle) - dy * Math.sin(angle);
        const ry = dx * Math.sin(angle) + dy * Math.cos(angle);
        if (Math.abs(rx) <= lengthPx / 2 && Math.abs(ry) <= widthPx / 2){
          return a;
        }
      } else if (a.kind === "cone"){
        const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
        const spreadDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : 90;
        const headingDeg = a.orient === "horizontal" ? 0 : -90;
        const dist = Math.hypot(dx, dy);
        if (dist <= lengthPx){
          let angle = Math.atan2(dy, dx);
          const heading = (headingDeg * Math.PI) / 180;
          angle -= heading;
          while (angle <= -Math.PI) angle += Math.PI * 2;
          while (angle > Math.PI) angle -= Math.PI * 2;
          const halfSpread = (spreadDeg * Math.PI) / 360;
          if (Math.abs(angle) <= halfSpread){
            return a;
          }
        }
      }
    }
    return null;
  }

  function gridReady(){
    if (!state || !state.grid) return false;
    if (state.grid.ready === false) return false;
    return Number.isFinite(state.grid.cols) && Number.isFinite(state.grid.rows);
  }

  function updateWaitingOverlay(){
    if (!waitingOverlay) return;
    waitingOverlay.classList.toggle("show", !gridReady());
  }

  function formatFeet(feet){
    const rounded = Math.round(feet * 10) / 10;
    const label = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
    return `${label} ft`;
  }

  function updateMeasurementControls(){
    if (measureToggle){
      measureToggle.textContent = measurementMode ? "Measuring…" : "Measure";
      measureToggle.classList.toggle("accent", measurementMode);
      measureToggle.setAttribute("aria-pressed", measurementMode ? "true" : "false");
    }
    if (measureClear){
      measureClear.disabled = !(measurement.start || measurement.end);
    }
  }

  function getClaimedUnit(){
    if (!state || !state.units || claimedCid === null) return null;
    return state.units.find(u => Number(u.cid) === Number(claimedCid)) || null;
  }

  function isUnitSpellcaster(unit){
    if (!unit) return false;
    if (unit.is_spellcaster !== undefined && unit.is_spellcaster !== null){
      return !!unit.is_spellcaster;
    }
    if (unit.spellcaster !== undefined && unit.spellcaster !== null){
      return !!unit.spellcaster;
    }
    return true;
  }

  function updateSpellPanelVisibility(){
    if (!castPanel) return;
    const claimedUnit = getClaimedUnit();
    const hideForNonCaster = hideSpellMenu && claimedUnit && !isUnitSpellcaster(claimedUnit);
    castPanel.classList.toggle("hidden", hideForNonCaster);
    if (castMenuTrigger){
      castMenuTrigger.classList.toggle("hidden", hideForNonCaster);
    }
    if (castOverlay){
      castOverlay.classList.toggle("hidden", hideForNonCaster);
    }
    if (hideForNonCaster && castOverlay?.classList.contains("show")){
      setCastOverlayOpen(false);
    }
  }

  function defaultAoeCenter(){
    const unit = getClaimedUnit();
    if (unit){
      return {cx: Number(unit.pos.col), cy: Number(unit.pos.row)};
    }
    const cols = state?.grid?.cols ?? 0;
    const rows = state?.grid?.rows ?? 0;
    return {cx: Math.max(0, (cols - 1) / 2), cy: Math.max(0, (rows - 1) / 2)};
  }

  function toGridPoint(point){
    if (!point) return {col: 0, row: 0};
    const colValue = point.col ?? point.cx ?? 0;
    const rowValue = point.row ?? point.cy ?? 0;
    return {col: Math.round(Number(colValue)), row: Math.round(Number(rowValue))};
  }

  function isLineOfSightBlocked(startPoint, endPoint){
    if (!state || !state.obstacles || !state.obstacles.length) return false;
    const start = toGridPoint(startPoint);
    const end = toGridPoint(endPoint);
    const obstacles = new Set(state.obstacles.map(o => `${Number(o.col)},${Number(o.row)}`));
    let x0 = start.col;
    let y0 = start.row;
    const x1 = end.col;
    const y1 = end.row;
    const dx = Math.abs(x1 - x0);
    const dy = Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1;
    const sy = y0 < y1 ? 1 : -1;
    let err = dx - dy;
    let first = true;
    while (true){
      if (!first && obstacles.has(`${x0},${y0}`)){
        return true;
      }
      if (x0 === x1 && y0 === y1){
        break;
      }
      const e2 = 2 * err;
      if (e2 > -dy){
        err -= dy;
        x0 += sx;
      }
      if (e2 < dx){
        err += dx;
        y0 += sy;
      }
      first = false;
    }
    return false;
  }

  function setLosPreview(startPoint, endPoint, blocked){
    losPreview = {
      start: toGridPoint(startPoint),
      end: toGridPoint(endPoint),
      blocked: !!blocked,
      expiresAt: Date.now() + LOS_PREVIEW_MS,
    };
    setTimeout(() => {
      if (losPreview && Date.now() >= losPreview.expiresAt){
        losPreview = null;
        draw();
      }
    }, LOS_PREVIEW_MS + 25);
    draw();
  }

  function clearMeasurement(){
    measurement = {start: null, end: null};
    updateMeasurementControls();
    draw();
  }

  function setMeasurementPoint(p){
    if (!gridReady()) return;
    const g = screenToGrid(p.x, p.y);
    const point = {col: g.col, row: g.row};
    if (!measurement.start || measurement.end){
      measurement = {start: point, end: null};
    } else {
      measurement.end = point;
    }
    updateMeasurementControls();
    draw();
  }

  function draw(){
    if (!state) return;
    if (!gridReady()){
      updateWaitingOverlay();
      return;
    }
    updateWaitingOverlay();
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;

    ctx.clearRect(0,0,w,h);

    // background
    ctx.fillStyle = "#0a0c12";
    ctx.fillRect(0,0,w,h);

    const cols = state.grid.cols, rows = state.grid.rows;
    if (cols !== lastGrid.cols || rows !== lastGrid.rows){
      fittedToGrid = false;
      lastGrid = {cols, rows};
    }

    // auto-fit on first draw
    if (!fittedToGrid){
      const pad = 24;
      const sx = (w - pad*2) / (cols*zoom);
      const sy = (h - pad*2) / (rows*zoom);
      const s = Math.min(1.0, Math.max(0.35, Math.min(sx, sy)));
      zoom = Math.floor(zoom * s);
      panX = Math.floor((w - cols*zoom)/2);
      panY = Math.floor((h - rows*zoom)/2);
      fittedToGrid = true;
    }

    // grid
    ctx.strokeStyle = "rgba(255,255,255,0.07)";
    ctx.lineWidth = 1;
    for(let c=0;c<=cols;c++){
      const x = panX + c*zoom;
      ctx.beginPath(); ctx.moveTo(x, panY); ctx.lineTo(x, panY + rows*zoom); ctx.stroke();
    }
    for(let r=0;r<=rows;r++){
      const y = panY + r*zoom;
      ctx.beginPath(); ctx.moveTo(panX, y); ctx.lineTo(panX + cols*zoom, y); ctx.stroke();
    }

    // rough terrain
    if (state.rough_terrain && state.rough_terrain.length){
      state.rough_terrain.forEach(cell => {
        const x = panX + cell.col*zoom;
        const y = panY + cell.row*zoom;
        const colorHex = normalizeHexColor(cell.color || "");
        const isSwim = !!cell.is_swim;
        const isRough = !!cell.is_rough;
        let alpha = isSwim ? 0.35 : 0.25;
        if (isRough && !isSwim){
          alpha = 0.3;
        }
        const fallback = isSwim ? "rgba(74,163,223,0.32)" : "rgba(141,110,99,0.25)";
        ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, alpha) : fallback;
        ctx.fillRect(x+1,y+1,zoom-2,zoom-2);
      });
    }

    // movement range (claimed token)
    const isMyTurn = claimedCid != null
      && state.active_cid != null
      && Number(state.active_cid) === Number(claimedCid);
    if (isMyTurn && state.units){
      const me = state.units.find(u => Number(u.cid) === Number(claimedCid));
      if (me){
        const move = Math.max(0, Number(me.move_remaining || 0));
        const feet = Math.max(1, Number(state.grid.feet_per_square || 5));
        const rangeSquares = move / feet;
        if (rangeSquares > 0){
          const {x,y} = gridToScreen(me.pos.col, me.pos.row);
          const radius = rangeSquares * zoom;
          ctx.save();
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(106,169,255,0.12)";
          ctx.fill();
          ctx.lineWidth = 2;
          ctx.strokeStyle = "rgba(106,169,255,0.35)";
          ctx.stroke();
          ctx.restore();
        }
      }
    }

    // obstacles
    if (state.obstacles && state.obstacles.length){
      ctx.fillStyle = "rgba(255,255,255,0.10)";
      state.obstacles.forEach(o => {
        const x = panX + o.col*zoom;
        const y = panY + o.row*zoom;
        ctx.fillRect(x+1,y+1,zoom-2,zoom-2);
      });
    }

    // AoE overlays
    if (state.aoes && state.aoes.length){
      state.aoes.forEach(a => {
        if (!a || !a.kind) return;
        const remainingTurnsRaw = a.remaining_turns;
        const remainingTurnsValue = (remainingTurnsRaw === null || remainingTurnsRaw === undefined)
          ? null
          : Number(remainingTurnsRaw);
        if (Number.isFinite(remainingTurnsValue) && remainingTurnsValue <= 0){
          return;
        }
        const preview = (draggingAoe && draggingAoe.aid === a.aid) ? draggingAoe : null;
        const override = aoeDragOverrides.get(Number(a.aid));
        const cx = Number((preview || override) ? (preview || override).cx : a.cx ?? 0);
        const cy = Number((preview || override) ? (preview || override).cy : a.cy ?? 0);
        const {x,y} = gridToScreen(cx, cy);
        const colorHex = normalizeHexColor(a.color || "");
        ctx.save();
        ctx.lineWidth = 2;
        ctx.setLineDash([6,4]);
        if (a.kind === "circle" || a.kind === "sphere" || a.kind === "cylinder"){
          const r = Math.max(0, Number(a.radius_sq || 0)) * zoom;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, 0.28) : "rgba(168,197,255,0.32)";
          ctx.strokeStyle = colorHex || "rgba(45,79,138,0.85)";
          ctx.fill();
          ctx.stroke();
        } else if (a.kind === "line" || a.kind === "wall"){
          const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
          const widthPx = Math.max(0, Number(a.width_sq || 0)) * zoom;
          const angleDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : null;
          const orient = a.orient === "horizontal" ? "horizontal" : "vertical";
          const halfW = orient === "horizontal" ? lengthPx / 2 : widthPx / 2;
          const halfH = orient === "horizontal" ? widthPx / 2 : lengthPx / 2;
          ctx.fillStyle = colorHex
            ? rgbaFromHex(colorHex, 0.28)
            : (a.kind === "wall" ? "rgba(255,230,153,0.32)" : "rgba(183,255,224,0.32)");
          ctx.strokeStyle = colorHex || (a.kind === "wall" ? "rgba(181,125,34,0.85)" : "rgba(45,138,87,0.85)");
          if (angleDeg !== null){
            ctx.save();
            ctx.translate(x, y);
            ctx.rotate((angleDeg * Math.PI) / 180);
            ctx.beginPath();
            ctx.rect(-lengthPx / 2, -widthPx / 2, lengthPx, widthPx);
            ctx.fill();
            ctx.stroke();
            ctx.restore();
          } else {
            ctx.beginPath();
            ctx.rect(x - halfW, y - halfH, halfW * 2, halfH * 2);
            ctx.fill();
            ctx.stroke();
          }
        } else if (a.kind === "square" || a.kind === "cube"){
          const sidePx = Math.max(0, Number(a.side_sq || 0)) * zoom;
          const half = sidePx / 2;
          ctx.beginPath();
          ctx.rect(x - half, y - half, sidePx, sidePx);
          ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, 0.28) : "rgba(226,182,255,0.32)";
          ctx.strokeStyle = colorHex || "rgba(107,61,138,0.85)";
          ctx.fill();
          ctx.stroke();
        } else if (a.kind === "cone"){
          const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
          const spreadDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : 90;
          const headingDeg = a.orient === "horizontal" ? 0 : -90;
          const halfSpread = (spreadDeg * Math.PI) / 360;
          const headingRad = (headingDeg * Math.PI) / 180;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.arc(x, y, lengthPx, headingRad - halfSpread, headingRad + halfSpread);
          ctx.closePath();
          ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, 0.28) : "rgba(255,189,110,0.32)";
          ctx.strokeStyle = colorHex || "rgba(181,110,34,0.85)";
          ctx.fill();
          ctx.stroke();
        }
        ctx.setLineDash([]);
        const label = a.name ? String(a.name) : "";
        const labelText = label
          ? (a.pinned && Number.isFinite(remainingTurns) ? `${label} (${remainingTurns}t)` : label)
          : "";
        if (labelText){
          ctx.font = `700 ${Math.max(10, Math.floor(zoom*0.32))}px system-ui`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "rgba(20,25,35,0.9)";
          ctx.fillText(labelText, x + 1, y + 1);
          ctx.fillStyle = "rgba(232,238,247,0.95)";
          ctx.fillText(labelText, x, y);
        }
        if (selectedAoeId !== null && Number(a.aid) === Number(selectedAoeId)){
          ctx.save();
          ctx.lineWidth = 3;
          ctx.setLineDash([]);
          ctx.strokeStyle = "rgba(255,214,102,0.95)";
          if (a.kind === "circle" || a.kind === "sphere" || a.kind === "cylinder"){
            const r = Math.max(0, Number(a.radius_sq || 0)) * zoom;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.stroke();
          } else if (a.kind === "line" || a.kind === "wall"){
            const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
            const widthPx = Math.max(0, Number(a.width_sq || 0)) * zoom;
            const angleDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : null;
            if (angleDeg !== null){
              ctx.translate(x, y);
              ctx.rotate((angleDeg * Math.PI) / 180);
              ctx.beginPath();
              ctx.rect(-lengthPx / 2, -widthPx / 2, lengthPx, widthPx);
              ctx.stroke();
            } else {
              const orient = a.orient === "horizontal" ? "horizontal" : "vertical";
              const halfW = orient === "horizontal" ? lengthPx / 2 : widthPx / 2;
              const halfH = orient === "horizontal" ? widthPx / 2 : lengthPx / 2;
              ctx.beginPath();
              ctx.rect(x - halfW, y - halfH, halfW * 2, halfH * 2);
              ctx.stroke();
            }
          } else if (a.kind === "square" || a.kind === "cube"){
            const sidePx = Math.max(0, Number(a.side_sq || 0)) * zoom;
            const half = sidePx / 2;
            ctx.beginPath();
            ctx.rect(x - half, y - half, sidePx, sidePx);
            ctx.stroke();
          } else if (a.kind === "cone"){
            const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
            const spreadDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : 90;
            const headingDeg = a.orient === "horizontal" ? 0 : -90;
            const halfSpread = (spreadDeg * Math.PI) / 360;
            const headingRad = (headingDeg * Math.PI) / 180;
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.arc(x, y, lengthPx, headingRad - halfSpread, headingRad + halfSpread);
            ctx.closePath();
            ctx.stroke();
          }
          ctx.restore();
        }
        ctx.restore();
      });
    }

    // measurement line
    if (measurement.start){
      const start = gridToScreen(measurement.start.col, measurement.start.row);
      ctx.save();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "rgba(255,233,106,0.9)";
      ctx.fillStyle = "rgba(255,233,106,0.9)";
      ctx.beginPath();
      ctx.arc(start.x, start.y, Math.max(6, zoom * 0.12), 0, Math.PI * 2);
      ctx.fill();
      if (measurement.end){
        const end = gridToScreen(measurement.end.col, measurement.end.row);
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(end.x, end.y, Math.max(6, zoom * 0.12), 0, Math.PI * 2);
        ctx.fill();
        const feetPerSquare = Math.max(1, Number(state.grid.feet_per_square || 5));
        const dx = measurement.end.col - measurement.start.col;
        const dy = measurement.end.row - measurement.start.row;
        const feet = Math.hypot(dx, dy) * feetPerSquare;
        const label = formatFeet(feet);
        const midX = (start.x + end.x) / 2;
        const midY = (start.y + end.y) / 2;
        ctx.font = `700 ${Math.max(11, Math.floor(zoom * 0.32))}px system-ui`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        ctx.fillText(label, midX + 1, midY - 7 + 1);
        ctx.fillStyle = "rgba(255,255,255,0.95)";
        ctx.fillText(label, midX, midY - 7);
      }
      ctx.restore();
    }

    if (losPreview && Date.now() <= losPreview.expiresAt){
      const start = gridToScreen(losPreview.start.col, losPreview.start.row);
      const end = gridToScreen(losPreview.end.col, losPreview.end.row);
      ctx.save();
      ctx.lineWidth = 3;
      ctx.setLineDash([8, 6]);
      ctx.strokeStyle = losPreview.blocked ? "rgba(255,120,120,0.95)" : "rgba(123,233,173,0.95)";
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(end.x, end.y);
      ctx.stroke();
      ctx.restore();
    }

    // tokens
    const tokens = state.units || [];
    // group labels by cell
    const cellMap = new Map();
    tokens.forEach(u => {
      const key = `${u.pos.col},${u.pos.row}`;
      if (!cellMap.has(key)) cellMap.set(key, []);
      cellMap.get(key).push(u);
    });

    // draw token circles first
    tokens.forEach(u => {
      const {x,y} = gridToScreen(u.pos.col,u.pos.row);
      const r = Math.max(10, zoom*0.35);
      const active = (state.active_cid !== null && Number(state.active_cid) === Number(u.cid));
      const mine = (claimedCid && Number(claimedCid) === Number(u.cid));
      ctx.beginPath();
      ctx.arc(x,y,r,0,Math.PI*2);

      // color
      const customFill = u.token_color ? rgbaFromHex(u.token_color, 0.28) : null;
      if (customFill){
        ctx.fillStyle = customFill;
      } else if (u.role === "enemy") {
        ctx.fillStyle = "rgba(255,91,91,0.28)";
      } else {
        ctx.fillStyle = "rgba(106,255,176,0.18)";
      }
      ctx.fill();

      ctx.lineWidth = active ? 3 : 2;
      ctx.strokeStyle = mine ? "rgba(106,169,255,0.95)" : (active ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.25)");
      ctx.stroke();

      // condition markers inside
      const marks = (u.marks || "").trim();
      if (marks){
        ctx.font = `${Math.max(10, Math.floor(zoom*0.33))}px system-ui`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "rgba(255,255,255,0.95)";
        ctx.fillText(marks, x, y);
      }
    });

    // labels above: name or group name
    const labelBoxes = [];
    const labelFontSize = Math.max(11, Math.floor(zoom*0.32));
    const labelOffset = zoom*0.40;
    const labelPad = 2;
    const labelStep = Math.max(6, Math.floor(labelFontSize * 0.7));
    const labelOffsets = [0, -labelStep, labelStep, -2*labelStep, 2*labelStep];
    const labelEntries = [];
    cellMap.forEach((arr, key) => {
      const [col,row] = key.split(",").map(Number);
      const {x,y} = gridToScreen(col,row);
      let label = "";
      if (arr.length >= 2){
        const names = arr.map(a => a.name).join(", ");
        label = `Group (${arr.length}): ${names}`;
      } else {
        label = arr[0].name;
      }
      const isActive = arr.some(a => state.active_cid !== null && Number(state.active_cid) === Number(a.cid));
      labelEntries.push({label, x, y: y - labelOffset, isActive});
    });
    labelEntries.sort((a, b) => Number(a.isActive) - Number(b.isActive));
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.font = `600 ${labelFontSize}px system-ui`;
    const overlaps = (a, b) => !(a.x2 < b.x1 || a.x1 > b.x2 || a.y2 < b.y1 || a.y1 > b.y2);
    labelEntries.forEach(entry => {
      const width = ctx.measureText(entry.label).width;
      let placed = false;
      for (const offset of labelOffsets){
        const y = entry.y + offset;
        const box = {
          x1: entry.x - width / 2 - labelPad,
          x2: entry.x + width / 2 + labelPad,
          y1: y - labelFontSize - labelPad,
          y2: y + labelPad,
        };
        if (!labelBoxes.some(b => overlaps(b, box))){
          // shadow
          ctx.fillStyle = "rgba(0,0,0,0.55)";
          ctx.fillText(entry.label, entry.x + 1, y + 1);
          ctx.fillStyle = "rgba(232,238,247,0.92)";
          ctx.fillText(entry.label, entry.x, y);
          labelBoxes.push(box);
          placed = true;
          break;
        }
      }
      if (!placed && (showAllNames || entry.isActive)){
        const y = entry.y;
        const box = {
          x1: entry.x - width / 2 - labelPad,
          x2: entry.x + width / 2 + labelPad,
          y1: y - labelFontSize - labelPad,
          y2: y + labelPad,
        };
        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.fillText(entry.label, entry.x + 1, y + 1);
        ctx.fillStyle = "rgba(232,238,247,0.92)";
        ctx.fillText(entry.label, entry.x, y);
        labelBoxes.push(box);
      }
    });

  }

  function centerOnPoint(col, row){
    if (!state || !state.grid) return false;
    if (!gridReady()) return false;
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;
    const cols = state.grid.cols, rows = state.grid.rows;
    const desiredX = (w / 2) - (Number(col) + 0.5) * zoom;
    const desiredY = (h / 2) - (Number(row) + 0.5) * zoom;
    const gridW = cols * zoom;
    const gridH = rows * zoom;
    if (gridW <= w) {
      panX = Math.floor((w - gridW) / 2);
    } else {
      const minX = w - gridW;
      panX = Math.min(0, Math.max(minX, desiredX));
    }
    if (gridH <= h) {
      panY = Math.floor((h - gridH) / 2);
    } else {
      const minY = h - gridH;
      panY = Math.min(0, Math.max(minY, desiredY));
    }
    return true;
  }

  function centerOnClaimed(){
    if (!state || !state.units || claimedCid === null || claimedCid === undefined) return false;
    if (!gridReady()) return false;
    const me = state.units.find(u => Number(u.cid) === Number(claimedCid));
    if (!me) return false;
    const ok = centerOnPoint(me.pos.col, me.pos.row);
    if (ok){
      centeredCid = String(claimedCid);
      draw();
    }
    return ok;
  }

  function centerOnGridCenter(){
    if (!state || !state.grid) return false;
    if (!gridReady()) return false;
    const cols = Number(state.grid.cols || 0);
    const rows = Number(state.grid.rows || 0);
    const col = Math.max(0, (cols - 1) / 2);
    const row = Math.max(0, (rows - 1) / 2);
    const ok = centerOnPoint(col, row);
    if (ok){
      draw();
    }
    return ok;
  }

  function autoCenterOnJoin(){
    if (!gridReady()) return;
    if (claimedCid !== null && claimedCid !== undefined){
      if (!initialCenterDone || (initialCenterFallback && centeredCid !== String(claimedCid))){
        if (centerOnClaimed()){
          initialCenterDone = true;
          initialCenterFallback = false;
        }
      }
    } else if (!initialCenterDone) {
      if (centerOnGridCenter()){
        initialCenterDone = true;
        initialCenterFallback = true;
      }
    }
  }

  function formatTurnOrderLabel(unit){
    if (!unit) return "";
    const role = String(unit.role || "enemy");
    let label = `${unit.name} (${role})`;
    if ((role === "pc" || role === "ally") && Number.isFinite(Number(unit.hp))){
      label += ` ${Number(unit.hp)} HP`;
    }
    return label;
  }

  function showTurnOrderBubble(chip, unit){
    if (!turnOrderBubbleEl){
      return;
    }
    if (!chip || !unit){
      turnOrderBubbleEl.classList.remove("show");
      return;
    }
    turnOrderBubbleEl.textContent = formatTurnOrderLabel(unit);
    turnOrderBubbleEl.classList.add("show");
    const container = turnOrderBubbleEl.offsetParent || turnOrderEl;
    if (!container){
      return;
    }
    const containerRect = container.getBoundingClientRect();
    const chipRect = chip.getBoundingClientRect();
    const bubbleRect = turnOrderBubbleEl.getBoundingClientRect();
    const left = chipRect.left - containerRect.left + (chipRect.width / 2);
    let top = chipRect.top - containerRect.top - bubbleRect.height - 8;
    if (top < 0){
      top = chipRect.bottom - containerRect.top + 8;
    }
    turnOrderBubbleEl.style.left = `${left}px`;
    turnOrderBubbleEl.style.top = `${top}px`;
  }

  function updateTurnOrder(){
    if (!turnOrderEl){
      return;
    }
    const TURN_CHIP_NAME_MAX = 20;
    const formatTurnChipName = (name) => {
      const fullName = String(name ?? "");
      if (fullName.length <= TURN_CHIP_NAME_MAX){
        return fullName;
      }
      return `${fullName.slice(0, TURN_CHIP_NAME_MAX - 1).trimEnd()}…`;
    };
    const order = Array.isArray(state?.turn_order) ? state.turn_order : [];
    turnOrderEl.innerHTML = "";
    if (!order.length){
      if (turnOrderStatusEl){
        turnOrderStatusEl.textContent = "";
      }
      if (turnOrderBubbleEl){
        turnOrderBubbleEl.classList.remove("show");
      }
      return;
    }
    const activeCid = state?.active_cid;
    const activeIndex = (activeCid === null || activeCid === undefined)
      ? -1
      : order.findIndex(cid => Number(cid) === Number(activeCid));
    const claimedIndex = (claimedCid === null || claimedCid === undefined)
      ? -1
      : order.findIndex(cid => Number(cid) === Number(claimedCid));
    const unitsByCid = new Map();
    if (Array.isArray(state?.units)){
      state.units.forEach((unit) => {
        if (unit && unit.cid !== undefined && unit.cid !== null){
          unitsByCid.set(Number(unit.cid), unit);
        }
      });
    }
    const chipByCid = new Map();
    order.forEach((cid, idx) => {
      const unit = unitsByCid.get(Number(cid));
      const chip = document.createElement("div");
      chip.className = "turn-chip";
      if (idx === claimedIndex){
        chip.classList.add("claimed");
      }
      if (idx === activeIndex){
        chip.classList.add("active");
      }
      chip.setAttribute("role", "button");
      chip.setAttribute("tabindex", "0");
      const unitName = unit?.name ? String(unit.name) : `#${cid}`;
      const truncatedUnitName = formatTurnChipName(unitName);
      chip.setAttribute("aria-label", `Turn ${idx + 1}: ${unitName}`);
      chip.setAttribute("data-full-name", unitName);
      chip.setAttribute("title", unitName);
      if (idx === claimedIndex){
        const claimedMarker = document.createElement("span");
        claimedMarker.className = "turn-chip-marker claimed-marker";
        claimedMarker.setAttribute("aria-hidden", "true");
        chip.appendChild(claimedMarker);
      }
      if (idx === activeIndex){
        const activeMarker = document.createElement("span");
        activeMarker.className = "turn-chip-marker active-marker";
        activeMarker.setAttribute("aria-hidden", "true");
        chip.appendChild(activeMarker);
      }
      const indexEl = document.createElement("span");
      indexEl.className = "turn-chip-index";
      indexEl.textContent = String(idx + 1);
      chip.appendChild(indexEl);
      const nameEl = document.createElement("span");
      nameEl.className = "turn-chip-name";
      nameEl.textContent = truncatedUnitName;
      nameEl.setAttribute("data-full-name", unitName);
      nameEl.setAttribute("title", unitName);
      chip.appendChild(nameEl);
      chip.addEventListener("click", () => {
        setSelectedTurnCid(Number(cid));
      });
      chip.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " "){
          ev.preventDefault();
          setSelectedTurnCid(Number(cid));
        }
      });
      chip.addEventListener("mouseenter", () => {
        hoveredTurnCid = Number(cid);
        showTurnOrderBubble(chip, unit);
      });
      chip.addEventListener("mouseleave", () => {
        if (hoveredTurnCid === Number(cid)){
          hoveredTurnCid = null;
        }
        if (selectedTurnCid !== null && chipByCid.has(Number(selectedTurnCid))){
          const selectedChip = chipByCid.get(Number(selectedTurnCid));
          const selectedUnit = unitsByCid.get(Number(selectedTurnCid));
          showTurnOrderBubble(selectedChip, selectedUnit);
        } else {
          showTurnOrderBubble(null, null);
        }
      });
      turnOrderEl.appendChild(chip);
      chipByCid.set(Number(cid), chip);
    });
    const setSelectedTurnCid = (cid) => {
      selectedTurnCid = cid;
      chipByCid.forEach((chip, key) => {
        chip.classList.toggle("selected", Number(key) === Number(cid));
      });
      if (hoveredTurnCid === null){
        showTurnOrderBubble(chipByCid.get(Number(cid)), unitsByCid.get(Number(cid)));
      }
    };
    const claimedUnit = claimedIndex >= 0 ? unitsByCid.get(Number(claimedCid)) : null;
    if (turnOrderStatusEl){
      if (claimedIndex >= 0 && claimedUnit){
        turnOrderStatusEl.textContent = `You are #${claimedIndex + 1}: ${claimedUnit.name}`;
      } else {
        turnOrderStatusEl.textContent = "You are not in initiative.";
      }
    }
    let fallbackCid = selectedTurnCid;
    if (fallbackCid === null || !chipByCid.has(Number(fallbackCid))){
      if (claimedIndex >= 0){
        fallbackCid = Number(claimedCid);
      } else if (activeIndex >= 0){
        fallbackCid = Number(order[activeIndex]);
      } else {
        fallbackCid = Number(order[0]);
      }
    }
    setSelectedTurnCid(fallbackCid);
  }

  function populateActionSelect(selectEl, options, placeholder){
    if (!selectEl) return;
    const previousValue = selectEl.value;
    selectEl.textContent = "";
    const placeholderOption = document.createElement("option");
    placeholderOption.value = "";
    placeholderOption.textContent = placeholder;
    selectEl.appendChild(placeholderOption);
    const items = Array.isArray(options) ? options : [];
    const normalized = items
      .map((item) => String(item || "").trim())
      .filter((item) => item.length > 0);
    normalized.forEach((item) => {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      selectEl.appendChild(option);
    });
    if (previousValue && normalized.includes(previousValue)){
      selectEl.value = previousValue;
    } else {
      selectEl.value = "";
    }
  }

  function updateHud(){
    if (!state){ return; }
    const active = state.active_cid;
    const round = state.round_num;
    turnEl.textContent = (active === null) ? "Turn: (not started)" : `Round ${round}`;
    const myTurn = claimedCid && active !== null && String(active) === String(claimedCid);
    if (resetTurnBtn){
      resetTurnBtn.disabled = !myTurn;
    }
    if (claimedCid && state.units){
      const me = state.units.find(u => Number(u.cid) === Number(claimedCid));
      if (me){
        meEl.textContent = me.name;
        moveEl.textContent = `Move: ${me.move_remaining}/${me.move_total}`;
        actionEl.textContent = `Action: ${me.action_remaining ?? 0}`;
        bonusActionEl.textContent = `Bonus Action: ${me.bonus_action_remaining ?? 0}`;
        useActionBtn.disabled = Number(me.action_remaining || 0) <= 0;
        useBonusActionBtn.disabled = Number(me.bonus_action_remaining || 0) <= 0;
        populateActionSelect(actionSelectEl, me.actions, "None/Custom");
        populateActionSelect(bonusActionSelectEl, me.bonus_actions, "None/Custom");
        if (actionSelectEl){
          actionSelectEl.disabled = false;
        }
        if (bonusActionSelectEl){
          bonusActionSelectEl.disabled = false;
        }
        if (standUpBtn){
          standUpBtn.disabled = !(myTurn && me.is_prone);
        }
      } else {
        actionEl.textContent = "Action: —";
        bonusActionEl.textContent = "Bonus Action: —";
        useActionBtn.disabled = true;
        useBonusActionBtn.disabled = true;
        populateActionSelect(actionSelectEl, [], "None/Custom");
        populateActionSelect(bonusActionSelectEl, [], "None/Custom");
        if (actionSelectEl){
          actionSelectEl.disabled = true;
        }
        if (bonusActionSelectEl){
          bonusActionSelectEl.disabled = true;
        }
        if (standUpBtn){
          standUpBtn.disabled = true;
        }
      }
    } else {
      actionEl.textContent = "Action: —";
      bonusActionEl.textContent = "Bonus Action: —";
      useActionBtn.disabled = true;
      useBonusActionBtn.disabled = true;
      populateActionSelect(actionSelectEl, [], "None/Custom");
      populateActionSelect(bonusActionSelectEl, [], "None/Custom");
      if (actionSelectEl){
        actionSelectEl.disabled = true;
      }
      if (bonusActionSelectEl){
        bonusActionSelectEl.disabled = true;
      }
      if (standUpBtn){
        standUpBtn.disabled = true;
      }
    }
    updateTurnOrder();
    updateSpellPanelVisibility();
  }

  function hideTurnModal(){
    if (!turnModal) return;
    turnModal.classList.remove("show");
    turnModal.setAttribute("aria-hidden", "true");
  }

  function playTurnAlert(){
    turnAlertAudio.currentTime = 0;
    turnAlertAudio.play().catch((err) => {
      console.warn("Turn alert audio failed to play.", err);
    });
  }

  function playKoAlert(){
    koAlertAudio.currentTime = 0;
    koAlertAudio.play().catch((err) => {
      console.warn("KO audio failed to play.", err);
    });
  }

  function fireVibrate(){
    if (!lastVibrateSupported) return false;
    const didVibrate = vibrate([200, 120, 200]);
    if (!didVibrate){
      lastVibrateSupported = false;
      console.debug("Vibration blocked or unsupported.");
    }
    return didVibrate;
  }

  function handleUserGesture(){
    userHasInteracted = true;
    if (!audioUnlocked){
      turnAlertAudio.play().then(() => {
        turnAlertAudio.pause();
        turnAlertAudio.currentTime = 0;
        audioUnlocked = true;
        if (pendingTurnAlert){
          pendingTurnAlert = false;
          playTurnAlert();
        }
        if (pendingVibrate){
          fireVibrate();
          pendingVibrate = false;
        }
      }).catch((err) => {
        console.warn("Turn alert audio unlock failed.", err);
      });
      return;
    }
    if (pendingTurnAlert){
      pendingTurnAlert = false;
      playTurnAlert();
    }
    if (pendingVibrate){
      fireVibrate();
      pendingVibrate = false;
    }
  }

  function showTurnModal(){
    if (!turnModal) return;
    if (document.visibilityState === "hidden") return;
    turnModal.classList.add("show");
    turnModal.setAttribute("aria-hidden", "false");
    if (audioUnlocked){
      playTurnAlert();
    } else {
      pendingTurnAlert = true;
    }
    if (userHasInteracted || navigator.userActivation?.hasBeenActive){
      fireVibrate();
    } else {
      pendingVibrate = true;
    }
  }

  function maybeShowTurnAlert(){
    if (!state || !claimedCid) return;
    const activeCid = state.active_cid;
    const round = state.round_num;
    const isNowMyTurn = (activeCid !== null && String(activeCid) === String(claimedCid));
    const wasMyTurn = (lastActiveCid !== null && String(lastActiveCid) === String(claimedCid));
    const activeChanged = String(activeCid) !== String(lastActiveCid);
    const roundChanged = round !== lastTurnRound;
    if (isNowMyTurn && (!wasMyTurn || activeChanged || roundChanged)){
      showTurnModal();
    }
    lastActiveCid = activeCid;
    lastTurnRound = round;
  }

  function connect(){
    ws = new WebSocket(wsUrl);
    ws.addEventListener("open", () => {
      reconnecting = false;
      setConn(true, "Connected");
      send({type:"grid_request"});
    });
    ws.addEventListener("close", () => {
      const wasReconnect = reconnecting;
      reconnecting = false;
      if (wasReconnect){
        setConn(false, "Reconnecting…");
        scheduleReconnect(200);
      } else {
        setConn(false, "Disconnected");
        scheduleReconnect(1000);
      }
    });
    ws.addEventListener("message", (ev) => {
      let msg = null;
      try { msg = JSON.parse(ev.data); } catch(e){ return; }
      if (msg.type === "preset"){
        if (msg.preset && typeof msg.preset === "object"){
          applyGuiPreset(msg.preset, {persist: true});
          persistLocalPreset(msg.preset);
        } else {
          setPresetStatus("No preset saved.", 2500);
        }
      } else if (msg.type === "preset_saved"){
        setPresetStatus("Saved!");
      } else if (msg.type === "preset_error"){
        setPresetStatus(msg.error || "Preset error.", 2500);
      } else if (msg.type === "state"){
        state = (msg.state && typeof msg.state === "object") ? msg.state : {};
        if (!Array.isArray(state.spell_presets)){
          state.spell_presets = [];
        }
        updateSpellPresetOptions(state.spell_presets);
        aoeDragOverrides.clear();
        syncSelectedAoe();
        lastPcList = msg.pcs || msg.claimable || [];
        updateWaitingOverlay();
        draw();
        updateHud();
        maybeShowTurnAlert();
        autoCenterOnJoin();
        syncKnownSpellsFromState();
        if (!claimedCid){
          showNoOwnedPcToast(msg.pcs || msg.claimable || []);
        } else {
          const exists = (state.units || []).some(u => Number(u.cid) === Number(claimedCid));
            if (!exists){
              claimedCid = null;
              meEl.textContent = "(unclaimed)";
              shownNoOwnedToast = false;
              showNoOwnedPcToast(msg.pcs || msg.claimable || []);
              spellSelectMode = false;
              spellSelectOverlay?.classList.remove("selecting");
              updateSpellSelectUiLabels();
              if (spellSelectSaveBtn){
                spellSelectSaveBtn.disabled = true;
              }
              selectedKnownSpellKeys = new Set();
              selectedPreparedSpellKeys = new Set();
              updateSpellSelectSummary();
              renderSpellSelectTable(cachedSpellPresets);
              refreshSpellPresetOptions();
            }
        }
        refreshTurnAlertStatus();
      } else if (msg.type === "force_claim"){
        if (msg.cid !== null && msg.cid !== undefined){
          claimedCid = String(msg.cid);
          shownNoOwnedToast = false;
          autoCenterOnJoin();
          syncKnownSpellsFromState({force: true});
        }
        noteEl.textContent = msg.text || "Assigned by the DM.";
        setTimeout(() => noteEl.textContent = "Tip: drag yer token", 2500);
        refreshTurnAlertStatus();
      } else if (msg.type === "force_unclaim"){
        claimedCid = null;
        meEl.textContent = "(unclaimed)";
        shownNoOwnedToast = false;
        showNoOwnedPcToast(msg.pcs || lastPcList || []);
        spellSelectMode = false;
        spellSelectOverlay?.classList.remove("selecting");
        updateSpellSelectUiLabels();
        if (spellSelectSaveBtn){
          spellSelectSaveBtn.disabled = true;
        }
        selectedKnownSpellKeys = new Set();
        selectedPreparedSpellKeys = new Set();
        updateSpellSelectSummary();
        renderSpellSelectTable(cachedSpellPresets);
        refreshSpellPresetOptions();
        refreshTurnAlertStatus();
      } else if (msg.type === "toast"){
        noteEl.textContent = msg.text || "…";
        setTimeout(() => noteEl.textContent = "Tip: drag yer token", 2500);
      } else if (msg.type === "battle_log"){
        if (logContent){
          const lines = Array.isArray(msg.lines) ? msg.lines : [];
          logContent.textContent = lines.length ? lines.join("\n") : "No log entries yet.";
        }
        showLogModal();
      } else if (msg.type === "grid_update"){
        if (!state){ state = {}; }
        if ("grid" in msg){
          state.grid = msg.grid;
        }
        if (gridReady()){
          const cols = state.grid.cols;
          const rows = state.grid.rows;
          const gridChanged = cols !== lastGrid.cols || rows !== lastGrid.rows;
          if (gridChanged){
            fittedToGrid = false;
            lastGrid = {cols, rows};
          }
        }
        updateWaitingOverlay();
        lastGridVersion = msg.version ?? lastGridVersion;
        send({type:"grid_ack", version: msg.version});
        draw();
      } else if (msg.type === "play_audio"){
        if (!msg.audio) return;
        if (msg.audio !== "ko") return;
        if (!audioUnlocked) return;
        if (msg.cid !== undefined && msg.cid !== null){
          if (!claimedCid || String(msg.cid) !== String(claimedCid)) return;
        }
        playKoAlert();
      }
    });
  }

  // input
  function pointerPos(ev){
    const r = canvas.getBoundingClientRect();
    return {x: ev.clientX - r.left, y: ev.clientY - r.top};
  }

  function hitTestToken(p){
    if (!state || !state.units) return null;
    for (let i=state.units.length-1; i>=0; i--){
      const u = state.units[i];
      const {x,y} = gridToScreen(u.pos.col,u.pos.row);
      const r = Math.max(12, zoom*0.45);
      const dx = p.x - x, dy = p.y - y;
      if (dx*dx + dy*dy <= r*r){
        return u;
      }
    }
    return null;
  }

  function buildCellMap(tokens){
    const cellMap = new Map();
    tokens.forEach(u => {
      const key = `${u.pos.col},${u.pos.row}`;
      if (!cellMap.has(key)) cellMap.set(key, []);
      cellMap.get(key).push(u);
    });
    return cellMap;
  }

  function groupLabelFromTokens(arr){
    if (!arr || !arr.length) return "";
    const groupName = arr.find(a => a.group_name || a.group_label || a.group)
      ?.group_name
      ?? arr.find(a => a.group_label)?.group_label
      ?? arr.find(a => a.group)?.group;
    if (groupName) return groupName;
    const names = arr.map(a => a.name).filter(Boolean);
    if (!names.length) return `Group (${arr.length})`;
    const first = names[0];
    const allSame = names.every(n => n === first);
    if (allSame){
      return `${arr.length}x ${first}`;
    }
    if (showAllNames){
      return `Group (${arr.length}): ${names.join(", ")}`;
    }
    return `Group (${arr.length})`;
  }

  function setTokenTooltip(text, clientX, clientY){
    if (!tokenTooltip) return;
    if (!text){
      tokenTooltip.classList.remove("show");
      tokenTooltip.setAttribute("aria-hidden", "true");
      return;
    }
    const wrapRect = mapWrap?.getBoundingClientRect();
    if (!wrapRect) return;
    tokenTooltip.textContent = text;
    const pad = 12;
    const left = clientX - wrapRect.left + pad;
    const top = clientY - wrapRect.top + pad;
    tokenTooltip.style.left = `${left}px`;
    tokenTooltip.style.top = `${top}px`;
    tokenTooltip.classList.add("show");
    tokenTooltip.setAttribute("aria-hidden", "false");
  }

  function clampZoom(value){
    return Math.min(90, Math.max(12, value));
  }

  function zoomAt(newZoom, focusX, focusY){
    const preZoom = zoom;
    const nextZoom = clampZoom(newZoom);
    if (Math.abs(nextZoom - preZoom) < 0.01) return;
    const col = (focusX - panX) / preZoom;
    const row = (focusY - panY) / preZoom;
    zoom = nextZoom;
    panX = focusX - col * zoom;
    panY = focusY - row * zoom;
    draw();
  }

  const activePointers = new Map();
  let pinchState = null;

  function enforceLoginGate(){
    return false;
  }

  function startPinch(){
    if (activePointers.size < 2) return;
    const pts = Array.from(activePointers.values());
    const dx = pts[0].x - pts[1].x;
    const dy = pts[0].y - pts[1].y;
    const dist = Math.hypot(dx, dy);
    pinchState = {startDist: dist || 1, startZoom: zoom};
  }

  function updatePinch(){
    if (!pinchState || activePointers.size < 2) return;
    const pts = Array.from(activePointers.values());
    const midX = (pts[0].x + pts[1].x) / 2;
    const midY = (pts[0].y + pts[1].y) / 2;
    const dx = pts[0].x - pts[1].x;
    const dy = pts[0].y - pts[1].y;
    const dist = Math.hypot(dx, dy);
    if (pinchState.startDist <= 0) return;
    const scale = dist / pinchState.startDist;
    zoomAt(pinchState.startZoom * scale, midX, midY);
  }

  canvas.addEventListener("pointerdown", (ev) => {
    if (enforceLoginGate()) return;
    setTokenTooltip(null);
    canvas.setPointerCapture(ev.pointerId);
    const p = pointerPos(ev);
    activePointers.set(ev.pointerId, p);
    if (activePointers.size >= 2){
      dragging = null;
      draggingAoe = null;
      panning = null;
      startPinch();
      return;
    }
    if (measurementMode){
      setMeasurementPoint(p);
      return;
    }

    // Try token hit
    const hit = hitTestToken(p);
    if (hit){
      // only drag own token
      if (!claimedCid || Number(hit.cid) !== Number(claimedCid)){
        send({type:"toast", text:"Arrr, that token ain’t yers."});
        return;
      }
      // only on your turn
      if (state.active_cid === null || Number(state.active_cid) !== Number(claimedCid)){
        send({type:"toast", text:"Not yer turn yet, matey."});
        return;
      }
      dragging = {cid: hit.cid, startX: p.x, startY: p.y, origCol: hit.pos.col, origRow: hit.pos.row};
      return;
    }
    const aoeHit = hitTestAoe(p);
    if (aoeHit){
      setSelectedAoe(aoeHit.aid);
      if (!claimedCid){
        localToast("Claim a character first, matey.");
        return;
      }
      if (aoeHit.owner_cid !== null && aoeHit.owner_cid !== undefined
          && Number(aoeHit.owner_cid) !== Number(claimedCid)){
        localToast("That spell be not yers.");
        return;
      }
      if (aoeHit.pinned){
        localToast("That spell be pinned.");
        return;
      }
      const movePerTurn = Number(aoeHit.move_per_turn_ft);
      const hasMoveLimit = Number.isFinite(movePerTurn) && movePerTurn > 0;
      const moveRemaining = Number.isFinite(Number(aoeHit.move_remaining_ft))
        ? Number(aoeHit.move_remaining_ft)
        : (hasMoveLimit ? movePerTurn : null);
      if (hasMoveLimit){
        if (state?.active_cid === null || Number(state.active_cid) !== Number(claimedCid)){
          localToast("Not yer turn yet, matey.");
          return;
        }
        if (!Number.isFinite(moveRemaining) || moveRemaining <= 0){
          localToast("That spell can't move any more this turn.");
          return;
        }
      }
      draggingAoe = {
        aid: aoeHit.aid,
        cx: aoeHit.cx,
        cy: aoeHit.cy,
        startCx: aoeHit.cx,
        startCy: aoeHit.cy,
        moveRemainingFt: moveRemaining,
        movePerTurnFt: hasMoveLimit ? movePerTurn : null,
      };
      return;
    }
    setSelectedAoe(null);
    // else pan (if map not locked)
    if (!lockMap){
      panning = {x: p.x, y: p.y, panX, panY};
    }
  });

  canvas.addEventListener("pointermove", (ev) => {
    if (enforceLoginGate()) return;
    const p = pointerPos(ev);
    if (activePointers.has(ev.pointerId)){
      activePointers.set(ev.pointerId, p);
    }
    if (pinchState && activePointers.size >= 2){
      updatePinch();
      setTokenTooltip(null);
      return;
    }
    if (ev.pointerType === "touch"){
      setTokenTooltip(null);
      return;
    }
    if (dragging){
      // update local preview by shifting pan temporarily? simplest: draw ghost at pointer
      draw();
      // ghost
      ctx.save();
      ctx.globalAlpha = 0.85;
      ctx.beginPath();
      ctx.arc(p.x, p.y, Math.max(10, zoom*0.35), 0, Math.PI*2);
      ctx.fillStyle = "rgba(106,169,255,0.25)";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "rgba(106,169,255,0.95)";
      ctx.stroke();
      ctx.restore();
      setTokenTooltip(null);
    } else if (draggingAoe){
      const g = screenToGridFloat(p.x, p.y);
      draggingAoe.cx = g.col;
      draggingAoe.cy = g.row;
      aoeDragOverrides.set(Number(draggingAoe.aid), {cx: g.col, cy: g.row});
      draw();
      setTokenTooltip(null);
    } else if (panning){
      panX = panning.panX + (p.x - panning.x);
      panY = panning.panY + (p.y - panning.y);
      draw();
      setTokenTooltip(null);
    } else if (measurementMode){
      setTokenTooltip(null);
    } else {
      const tokens = state?.units || [];
      const hit = hitTestToken(p);
      if (hit){
        const cellMap = buildCellMap(tokens);
        const key = `${hit.pos.col},${hit.pos.row}`;
        const group = cellMap.get(key) || [];
        const label = group.length > 1 ? groupLabelFromTokens(group) : (hit.name || "Unknown");
        setTokenTooltip(label, ev.clientX, ev.clientY);
      } else {
        setTokenTooltip(null);
      }
    }
  });

  canvas.addEventListener("pointerup", (ev) => {
    if (enforceLoginGate()) return;
    const p = pointerPos(ev);
    activePointers.delete(ev.pointerId);
    if (activePointers.size < 2){
      pinchState = null;
    }
    setTokenTooltip(null);
    dragging && (function(){
      const g = screenToGrid(p.x, p.y);
      send({type:"move", cid: Number(dragging.cid), to: {col: g.col, row: g.row}});
      dragging = null;
    })();
    draggingAoe && (function(){
      const g = screenToGridFloat(p.x, p.y);
      const aid = Number(draggingAoe.aid);
      const movePerTurn = Number(draggingAoe.movePerTurnFt);
      if (Number.isFinite(movePerTurn) && movePerTurn > 0){
        const feetPerSquare = Math.max(1, Number(state?.grid?.feet_per_square || 5));
        const dx = Number(g.col) - Number(draggingAoe.startCx);
        const dy = Number(g.row) - Number(draggingAoe.startCy);
        const distFt = Math.hypot(dx, dy) * feetPerSquare;
        const remaining = Number(draggingAoe.moveRemainingFt);
        if (!Number.isFinite(remaining) || distFt > remaining + 0.01){
          localToast(`That spell can only move ${Number.isFinite(remaining) ? remaining.toFixed(1) : 0} ft this turn.`);
          aoeDragOverrides.delete(aid);
          setLocalAoeCenter(aid, draggingAoe.startCx, draggingAoe.startCy);
          draggingAoe = null;
          draw();
          return;
        }
        const nextRemaining = Math.max(0, remaining - distFt);
        setLocalAoeMoveRemaining(aid, nextRemaining);
      }
      aoeDragOverrides.set(aid, {cx: g.col, cy: g.row});
      setLocalAoeCenter(aid, g.col, g.row);
      send({type:"aoe_move", aid: Number(draggingAoe.aid), to: {cx: g.col, cy: g.row}});
      draggingAoe = null;
      draw();
    })();
    panning = null;
  });

  canvas.addEventListener("pointercancel", (ev) => {
    if (enforceLoginGate()) return;
    activePointers.delete(ev.pointerId);
    if (activePointers.size < 2){
      pinchState = null;
    }
    setTokenTooltip(null);
    if (draggingAoe){
      aoeDragOverrides.delete(Number(draggingAoe.aid));
      draggingAoe = null;
      draw();
    }
  });

  canvas.addEventListener("pointerleave", () => {
    setTokenTooltip(null);
  });

  canvas.addEventListener("wheel", (ev) => {
    if (enforceLoginGate()) return;
    if (pinchState) return;
    ev.preventDefault();
    const p = pointerPos(ev);
    const delta = ev.deltaY || 0;
    const factor = delta > 0 ? 0.9 : 1.1;
    zoomAt(zoom * factor, p.x, p.y);
  }, {passive: false});

  if (zoomInBtn){
    zoomInBtn.addEventListener("click", () => {
      if (enforceLoginGate()) return;
      const r = canvas.getBoundingClientRect();
      zoomAt(zoom + 4, r.width / 2, r.height / 2);
    });
  }
  if (zoomOutBtn){
    zoomOutBtn.addEventListener("click", () => {
      if (enforceLoginGate()) return;
      const r = canvas.getBoundingClientRect();
      zoomAt(zoom - 4, r.width / 2, r.height / 2);
    });
  }
  if (lockMapBtn){
    lockMapBtn.addEventListener("click", (ev) => {
      if (enforceLoginGate()) return;
      lockMap = !lockMap;
      ev.target.textContent = lockMap ? "Unlock Map" : "Lock Map";
    });
  }
  if (centerMapBtn){
    centerMapBtn.addEventListener("click", () => {
      if (enforceLoginGate()) return;
      if (!centerOnClaimed()){
        centerOnGridCenter();
      }
    });
  }
  if (measureToggle){
    measureToggle.addEventListener("click", () => {
      if (enforceLoginGate()) return;
      measurementMode = !measurementMode;
      updateMeasurementControls();
    });
  }
  if (measureClear){
    measureClear.addEventListener("click", () => {
      if (enforceLoginGate()) return;
      clearMeasurement();
    });
  }
  if (tokenColorModeBtn){
    tokenColorModeBtn.addEventListener("click", () => {
      if (enforceLoginGate()) return;
      openClaimedColorModal();
    });
  }

  if (tokenColorInput){
    tokenColorInput.addEventListener("input", (ev) => {
      updateTokenColorSwatch(ev.target.value);
    });
  }
  if (tokenColorConfirm){
    tokenColorConfirm.addEventListener("click", () => {
      const claimedUnit = getClaimedUnit();
      if (!claimedUnit){
        localToast("Claim a character first, matey.");
        closeColorModal();
        return;
      }
      pendingClaim = claimedUnit;
      const color = validateTokenColor(tokenColorInput ? tokenColorInput.value : "");
      if (!color) return;
      localStorage.setItem("inittracker_tokenColor", color);
      send({type:"set_color", cid: Number(pendingClaim.cid), color});
      meEl.textContent = pendingClaim.name;
      closeColorModal();
    });
  }
  if (tokenColorCancel){
    tokenColorCancel.addEventListener("click", () => {
      closeColorModal();
      showNoOwnedPcToast(lastPcList || []);
    });
  }

  let lastSpellPresetSignature = "";
  let cachedSpellPresets = [];
  const normalizeSpellPresets = (presets) => Array.isArray(presets) ? presets.filter(p => p && typeof p === "object") : [];
  const formatSpellLevelLabel = (level) => {
    const num = Number(level);
    if (!Number.isFinite(num)) return "Unknown";
    if (num === 0) return "Cantrip";
    const suffix = num === 1 ? "st" : num === 2 ? "nd" : num === 3 ? "rd" : "th";
    return `${num}${suffix}`;
  };
  const formatListGroupLabel = (value) => String(value || "")
    .replace(/_/g, " ")
    .replace(/\\b\\w/g, (char) => char.toUpperCase());
  const normalizeTextValue = (value) => String(value || "").trim();
  const normalizeLowerValue = (value) => normalizeTextValue(value).toLowerCase();
  const getSpellKey = (name) => normalizeLowerValue(name);
  const loadKnownSpellFilterList = () => {
    const name = getClaimedPlayerName();
    if (!name) return null;
    const config = getPlayerSpellConfig(name);
    if (!config.names.length) return null;
    return config.names.map(normalizeTextValue).filter(Boolean);
  };
  const loadPreparedSpellFilterList = () => {
    const name = getClaimedPlayerName();
    if (!name) return null;
    const config = getPlayerPreparedSpellConfig(name);
    if (!config.prepared.length) return null;
    return config.prepared.map(normalizeTextValue).filter(Boolean);
  };
  const getKnownSpellFilterSet = () => {
    if (!claimedCid) return null;
    const list = loadKnownSpellFilterList();
    if (!list) return null;
    return new Set(list.map(getSpellKey));
  };
  const getPreparedSpellFilterSet = () => {
    if (!claimedCid) return null;
    const list = loadPreparedSpellFilterList();
    if (!list) return null;
    return new Set(list.map(getSpellKey));
  };
  const filterPresetsByKnownList = (presets, knownSpellSet) => {
    if (!knownSpellSet) return presets;
    return presets.filter((preset) => {
      const name = normalizeTextValue(preset.name);
      if (!name) return false;
      return knownSpellSet.has(getSpellKey(name));
    });
  };
  const getSpellListEntries = (lists) => {
    if (!lists || typeof lists !== "object") return [];
    const entries = [];
    Object.entries(lists).forEach(([group, values]) => {
      if (!Array.isArray(values)) return;
      values.forEach((value) => {
        const trimmed = normalizeTextValue(value);
        if (!trimmed) return;
        entries.push({group, value: trimmed});
      });
    });
    return entries;
  };
  const getPresetLevelNumber = (preset) => {
    const num = Number(preset?.level);
    return Number.isFinite(num) ? num : null;
  };
  const buildSpellPresetIndex = (presets) => {
    const index = new Map();
    normalizeSpellPresets(presets).forEach((preset) => {
      const name = normalizeTextValue(preset.name);
      if (!name) return;
      index.set(getSpellKey(name), {name, level: getPresetLevelNumber(preset)});
    });
    return index;
  };
  const getKnownSpellCounts = () => {
    let cantrips = 0;
    let spells = 0;
    selectedKnownSpellKeys.forEach((key) => {
      const entry = spellPresetIndex.get(key);
      if (!entry) return;
      if (entry.level === 0){
        cantrips += 1;
      } else {
        spells += 1;
      }
    });
    return {cantrips, spells};
  };
  const getSelectedSpellNames = (selectionSet) => {
    const names = [];
    selectionSet.forEach((key) => {
      const entry = spellPresetIndex.get(key);
      if (entry?.name){
        names.push(entry.name);
      }
    });
    return names.sort((a, b) => a.localeCompare(b));
  };
  const syncKnownSpellsFromState = ({force = false} = {}) => {
    if (!claimedCid || spellSelectMode) return;
    const stored = loadKnownSpells(claimedCid);
    const nextKeys = new Set(stored.map(getSpellKey));
    if (!force && nextKeys.size === selectedKnownSpellKeys.size){
      let same = true;
      nextKeys.forEach((key) => {
        if (!selectedKnownSpellKeys.has(key)){
          same = false;
        }
      });
      if (same){
        return;
      }
    }
    selectedKnownSpellKeys = nextKeys;
    updateSpellSelectSummary();
    renderSpellSelectTable(cachedSpellPresets);
    refreshSpellPresetOptions();
  };
  const updateManualEntryBadge = (preset) => {
    if (!castManualEntryBadge) return;
    if (!preset){
      castManualEntryBadge.classList.remove("show");
      castManualEntryBadge.setAttribute("aria-hidden", "true");
      castManualEntryBadge.removeAttribute("title");
      castManualEntryBadge.removeAttribute("aria-label");
      return;
    }
    const reasons = [];
    const automation = normalizeLowerValue(preset.automation);
    if (automation === "partial" || automation === "manual"){
      reasons.push(`automation is ${automation}`);
    }
    if (!preset.shape){
      reasons.push("shape is missing");
    }
    if (preset.incomplete){
      const missing = Array.isArray(preset.incomplete_fields)
        ? preset.incomplete_fields.map((field) => String(field || "").trim()).filter(Boolean)
        : [];
      if (missing.length){
        reasons.push(`missing ${missing.join(", ")}`);
      } else {
        reasons.push("missing dimensions");
      }
    }
    if (reasons.length){
      const tooltip = `Manual entry required: ${reasons.join("; ")}.`;
      castManualEntryBadge.classList.add("show");
      castManualEntryBadge.setAttribute("aria-hidden", "false");
      castManualEntryBadge.title = tooltip;
      castManualEntryBadge.setAttribute("aria-label", tooltip);
    } else {
      castManualEntryBadge.classList.remove("show");
      castManualEntryBadge.setAttribute("aria-hidden", "true");
      castManualEntryBadge.removeAttribute("title");
      castManualEntryBadge.removeAttribute("aria-label");
    }
  };
  const updateSpellPresetDetails = (preset) => {
    if (!spellPresetDetails) return;
    if (!preset){
      spellPresetDetails.textContent = "Select a preset to see spell details.";
      updateManualEntryBadge(null);
      return;
    }
    updateManualEntryBadge(preset);
    const detailsGrid = document.createElement("div");
    detailsGrid.className = "spell-details-grid";
    const levelLabel = formatSpellLevelLabel(preset.level);
    const tags = Array.isArray(preset.tags) ? preset.tags.filter(Boolean) : [];
    const tagLabel = tags.length ? tags.join(", ") : "—";
    const castingTime = normalizeTextValue(preset.casting_time) || "—";
    const range = normalizeTextValue(preset.range) || "—";
    const ritual = preset.ritual === true ? "Yes" : preset.ritual === false ? "No" : "—";
    const concentration = preset.concentration === true ? "Yes" : preset.concentration === false ? "No" : "—";
    const lists = getSpellListEntries(preset.lists);
    const listLabel = lists.length
      ? lists.map((entry) => `${formatListGroupLabel(entry.group)}: ${entry.value}`).join(" · ")
      : "—";
    const fields = [
      {label: "Level", value: levelLabel},
      {label: "School", value: normalizeTextValue(preset.school) || "—"},
      {label: "Tags", value: tagLabel},
      {label: "Casting", value: castingTime},
      {label: "Range", value: range},
      {label: "Ritual", value: ritual},
      {label: "Concentration", value: concentration},
      {label: "Lists", value: listLabel},
    ];
    fields.forEach((field) => {
      const row = document.createElement("div");
      row.className = "spell-details-row";
      const label = document.createElement("span");
      label.className = "spell-details-label";
      label.textContent = field.label;
      const value = document.createElement("span");
      value.className = "spell-details-value";
      value.textContent = field.value;
      row.appendChild(label);
      row.appendChild(value);
      detailsGrid.appendChild(row);
    });
    spellPresetDetails.textContent = "";
    spellPresetDetails.appendChild(detailsGrid);
  };
  const formatSpellDamageLabel = (preset) => {
    const base = preset?.default_damage ?? preset?.dice ?? "";
    const baseLabel = base !== null && base !== undefined && String(base).trim() ? String(base).trim() : "";
    const damageTypes = Array.isArray(preset?.damage_types)
      ? preset.damage_types.map((entry) => String(entry || "").trim()).filter(Boolean)
      : [];
    if (baseLabel && damageTypes.length){
      return `${baseLabel} (${damageTypes.join(", ")})`;
    }
    if (baseLabel) return baseLabel;
    if (damageTypes.length) return damageTypes.join(", ");
    return "—";
  };
  const hasAoeShape = (preset) => {
    if (!preset || typeof preset !== "object") return false;
    return Boolean(
      preset.shape ||
      preset.radius_ft ||
      preset.side_ft ||
      preset.length_ft ||
      preset.width_ft ||
      preset.angle_deg ||
      preset.height_ft ||
      preset.thickness_ft
    );
  };
  const buildOptionalSpellDetails = (preset) => {
    if (!preset || typeof preset !== "object") return [];
    const tags = Array.isArray(preset.tags) ? preset.tags.filter(Boolean) : [];
    const lists = getSpellListEntries(preset.lists);
    const listLabel = lists.length
      ? lists.map((entry) => `${formatListGroupLabel(entry.group)}: ${entry.value}`).join(" · ")
      : "";
    const fields = [
      {label: "Casting Time", value: normalizeTextValue(preset.casting_time)},
      {label: "Range", value: normalizeTextValue(preset.range)},
      {label: "Ritual", value: preset.ritual === true ? "Yes" : preset.ritual === false ? "No" : ""},
      {label: "Concentration", value: preset.concentration === true ? "Yes" : preset.concentration === false ? "No" : ""},
      {label: "Tags", value: tags.length ? tags.join(", ") : ""},
      {label: "Lists", value: listLabel},
      {label: "Shape", value: normalizeTextValue(preset.shape)},
      {label: "Radius (ft)", value: Number.isFinite(Number(preset.radius_ft)) ? String(preset.radius_ft) : ""},
      {label: "Side (ft)", value: Number.isFinite(Number(preset.side_ft)) ? String(preset.side_ft) : ""},
      {label: "Length (ft)", value: Number.isFinite(Number(preset.length_ft)) ? String(preset.length_ft) : ""},
      {label: "Width (ft)", value: Number.isFinite(Number(preset.width_ft)) ? String(preset.width_ft) : ""},
      {label: "Angle (deg)", value: Number.isFinite(Number(preset.angle_deg)) ? String(preset.angle_deg) : ""},
      {label: "Height (ft)", value: Number.isFinite(Number(preset.height_ft)) ? String(preset.height_ft) : ""},
      {label: "Duration (turns)", value: Number.isFinite(Number(preset.duration_turns)) ? String(preset.duration_turns) : ""},
      {label: "Save", value: preset.save_type ? String(preset.save_type || "").toUpperCase() : ""},
      {label: "Save DC", value: Number.isFinite(Number(preset.save_dc)) ? String(preset.save_dc) : ""},
    ];
    return fields.filter((field) => field.value);
  };
  const updateSpellSelectSummary = (totalCount = spellSelectLastCount) => {
    if (!spellSelectSummary) return;
    const count = Number.isFinite(totalCount) ? totalCount : 0;
    if (!spellSelectMode){
      spellSelectSummary.textContent = `${count} spell${count === 1 ? "" : "s"} available.`;
      return;
    }
    const availableLabel = `${count} spell${count === 1 ? "" : "s"} available.`;
    if (!claimedCid){
      spellSelectSummary.textContent = spellSelectContext === "prepared"
        ? "Claim a character to track prepared spells."
        : "Claim a character to track known spells.";
      return;
    }
    if (spellSelectContext === "prepared"){
      const playerName = getClaimedPlayerName();
      const config = playerName ? getPlayerPreparedSpellConfig(playerName) : preparedSpellDefaults;
      const limit = config.max;
      const selected = selectedPreparedSpellKeys.size;
      const limitLabel = Number.isFinite(limit) ? `${selected}/${limit} prepared spells selected` : `${selected} prepared spells selected`;
      spellSelectSummary.textContent = `${limitLabel}. ${availableLabel}`;
      return;
    }
    const limits = loadSpellConfig(claimedCid);
    const counts = getKnownSpellCounts();
    const cantripLabel = `${counts.cantrips}/${limits.cantrips} cantrips selected`;
    const spellLabel = `${counts.spells}/${limits.spells} spells selected`;
    spellSelectSummary.textContent = `${cantripLabel}, ${spellLabel}. ${availableLabel}`;
  };
  const setSpellSelectMode = (active) => {
    if (active && !claimedCid){
      localToast("Claim a character first.");
      return;
    }
    spellSelectMode = !!active;
    spellSelectOverlay?.classList.toggle("selecting", spellSelectMode);
    if (spellSelectMode && claimedCid){
      const stored = spellSelectContext === "prepared"
        ? loadPreparedSpells(claimedCid)
        : loadKnownSpells(claimedCid);
      const nextKeys = new Set(stored.map(getSpellKey));
      if (spellSelectContext === "prepared"){
        selectedPreparedSpellKeys = nextKeys;
      } else {
        selectedKnownSpellKeys = nextKeys;
      }
    }
    updateSpellSelectUiLabels();
    if (spellSelectSaveBtn){
      spellSelectSaveBtn.disabled = !spellSelectMode;
    }
    renderSpellSelectTable(cachedSpellPresets);
  };
  const toggleSpellSelection = (key, shouldSelect) => {
    if (!claimedCid) return false;
    if (spellSelectContext === "prepared"){
      if (shouldSelect){
        const playerName = getClaimedPlayerName();
        const config = playerName ? getPlayerPreparedSpellConfig(playerName) : preparedSpellDefaults;
        const limit = config.max;
        const nextCount = selectedPreparedSpellKeys.size + 1;
        if (Number.isFinite(limit) && limit !== null && nextCount > limit){
          localToast(`Prepared spells limited to ${limit}.`);
          return false;
        }
        selectedPreparedSpellKeys.add(key);
      } else {
        selectedPreparedSpellKeys.delete(key);
      }
      updateSpellSelectSummary();
      return true;
    }
    if (shouldSelect){
      const entry = spellPresetIndex.get(key);
      const isCantrip = entry?.level === 0;
      const limits = loadSpellConfig(claimedCid);
      const counts = getKnownSpellCounts();
      const nextCantrips = counts.cantrips + (isCantrip ? 1 : 0);
      const nextSpells = counts.spells + (isCantrip ? 0 : 1);
      if (isCantrip && nextCantrips > limits.cantrips){
        localToast(`Cantrips limited to ${limits.cantrips}.`);
        return false;
      }
      if (!isCantrip && nextSpells > limits.spells){
        localToast(`Spells limited to ${limits.spells}.`);
        return false;
      }
      selectedKnownSpellKeys.add(key);
    } else {
      selectedKnownSpellKeys.delete(key);
    }
    updateSpellSelectSummary();
    return true;
  };
  const renderSpellSelectTable = (presets) => {
    if (!spellSelectTableBody || !spellSelectSummary) return;
    const filterSet = spellSelectMode
      ? null
      : (spellSelectContext === "prepared" ? getPreparedSpellFilterSet() : getKnownSpellFilterSet());
    const list = filterPresetsByKnownList(normalizeSpellPresets(presets), filterSet)
      .slice()
      .sort((a, b) => {
      return normalizeTextValue(a.name).localeCompare(normalizeTextValue(b.name));
    });
    spellPresetIndex = buildSpellPresetIndex(list);
    spellSelectTableBody.textContent = "";
    if (!list.length){
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 7;
      cell.textContent = "No spell presets available.";
      row.appendChild(cell);
      spellSelectTableBody.appendChild(row);
      spellSelectLastCount = 0;
      updateSpellSelectSummary(0);
      return;
    }
    spellSelectLastCount = list.length;
    updateSpellSelectSummary(list.length);
    const fragment = document.createDocumentFragment();
    list.forEach((preset) => {
      const name = normalizeTextValue(preset.name) || "Unnamed";
      const spellKey = getSpellKey(name);
      const row = document.createElement("tr");
      row.className = "spell-select-row";
      const checkCell = document.createElement("td");
      checkCell.className = "spell-select-check-cell";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = getActiveSelectionSet().has(spellKey);
      checkbox.disabled = !spellSelectMode || !claimedCid;
      checkbox.addEventListener("change", () => {
        const applied = toggleSpellSelection(spellKey, checkbox.checked);
        if (!applied){
          checkbox.checked = false;
        }
      });
      checkCell.appendChild(checkbox);
      const nameCell = document.createElement("td");
      const nameBtn = document.createElement("button");
      nameBtn.type = "button";
      nameBtn.className = "spell-select-name-btn";
      nameBtn.textContent = name;
      nameBtn.addEventListener("click", () => {
        if (spellSelectMode){
          const applied = toggleSpellSelection(spellKey, !checkbox.checked);
          if (applied){
            checkbox.checked = !checkbox.checked;
          }
          return;
        }
        const optionExists = castPresetInput
          ? Array.from(castPresetInput.options).some((option) => option.value === name)
          : false;
        if (castPresetInput && optionExists){
          castPresetInput.value = name;
        }
        updateSpellPresetDetails(preset);
        applySpellPreset(preset);
        setSpellSelectOverlayOpen(false);
      });
      nameCell.appendChild(nameBtn);
      const damageCell = document.createElement("td");
      damageCell.textContent = formatSpellDamageLabel(preset);
      const aoeCell = document.createElement("td");
      aoeCell.textContent = hasAoeShape(preset) ? "Yes" : "No";
      const levelCell = document.createElement("td");
      levelCell.textContent = formatSpellLevelLabel(preset.level);
      const schoolCell = document.createElement("td");
      schoolCell.textContent = normalizeTextValue(preset.school) || "—";
      const linkCell = document.createElement("td");
      if (preset.url){
        const link = document.createElement("a");
        link.href = String(preset.url);
        link.target = "_blank";
        link.rel = "noopener";
        link.className = "spell-select-link";
        link.textContent = "Open";
        linkCell.appendChild(link);
      } else {
        linkCell.textContent = "—";
      }
      row.appendChild(checkCell);
      row.appendChild(nameCell);
      row.appendChild(damageCell);
      row.appendChild(aoeCell);
      row.appendChild(levelCell);
      row.appendChild(schoolCell);
      row.appendChild(linkCell);
      fragment.appendChild(row);

      const detailFields = buildOptionalSpellDetails(preset);
      if (detailFields.length){
        const detailRow = document.createElement("tr");
        detailRow.className = "spell-select-details-row";
        const detailCell = document.createElement("td");
        detailCell.colSpan = 7;
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "More details";
        const detailsGrid = document.createElement("div");
        detailsGrid.className = "spell-select-details-grid";
        detailFields.forEach((field) => {
          const item = document.createElement("div");
          item.className = "spell-select-details-item";
          const label = document.createElement("strong");
          label.textContent = field.label;
          const value = document.createElement("span");
          value.textContent = field.value;
          item.appendChild(label);
          item.appendChild(value);
          detailsGrid.appendChild(item);
        });
        details.appendChild(summary);
        details.appendChild(detailsGrid);
        detailCell.appendChild(details);
        detailRow.appendChild(detailCell);
        fragment.appendChild(detailRow);
      }
    });
    spellSelectTableBody.appendChild(fragment);
  };
  const updateSelectOptions = (selectEl, values) => {
    if (!selectEl) return;
    const currentValue = selectEl.value;
    selectEl.textContent = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Any";
    selectEl.appendChild(placeholder);
    values.forEach((value) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      selectEl.appendChild(opt);
    });
    if (currentValue && values.includes(currentValue)){
      selectEl.value = currentValue;
    } else {
      selectEl.value = "";
    }
  };
  const updateListFilterOptions = (listGroups) => {
    if (!castFilterListInput) return;
    const currentValue = castFilterListInput.value;
    castFilterListInput.textContent = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Any";
    castFilterListInput.appendChild(placeholder);
    Array.from(listGroups.entries()).forEach(([group, values]) => {
      const optgroup = document.createElement("optgroup");
      optgroup.label = formatListGroupLabel(group);
      Array.from(values).sort((a, b) => a.localeCompare(b)).forEach((value) => {
        const opt = document.createElement("option");
        opt.value = `${group}::${value}`;
        opt.textContent = value;
        optgroup.appendChild(opt);
      });
      castFilterListInput.appendChild(optgroup);
    });
    if (currentValue){
      castFilterListInput.value = currentValue;
      if (castFilterListInput.value !== currentValue){
        castFilterListInput.value = "";
      }
    }
  };
  const updateSpellFilterOptions = () => {
    const schools = new Set();
    const castingTimes = new Set();
    const ranges = new Set();
    const listGroups = new Map();
    cachedSpellPresets.forEach((preset) => {
      const school = normalizeTextValue(preset.school);
      if (school) schools.add(school);
      const castingTime = normalizeTextValue(preset.casting_time);
      if (castingTime) castingTimes.add(castingTime);
      const range = normalizeTextValue(preset.range);
      if (range) ranges.add(range);
      getSpellListEntries(preset.lists).forEach((entry) => {
        if (!listGroups.has(entry.group)){
          listGroups.set(entry.group, new Set());
        }
        listGroups.get(entry.group).add(entry.value);
      });
    });
    updateSelectOptions(castFilterSchoolInput, Array.from(schools).sort((a, b) => a.localeCompare(b)));
    updateSelectOptions(castFilterCastingTimeInput, Array.from(castingTimes).sort((a, b) => a.localeCompare(b)));
    updateSelectOptions(castFilterRangeInput, Array.from(ranges).sort((a, b) => a.localeCompare(b)));
    updateListFilterOptions(listGroups);
  };
  const getTagFilters = () => {
    if (!castFilterTagsInput) return [];
    const raw = normalizeLowerValue(castFilterTagsInput.value);
    if (!raw) return [];
    return raw.split(",").map(tag => tag.trim()).filter(Boolean);
  };
  const matchesSpellFilters = (preset) => {
    const levelFilter = castFilterLevelInput ? normalizeTextValue(castFilterLevelInput.value) : "";
    if (levelFilter){
      const levelNum = getPresetLevelNumber(preset);
      if (!Number.isFinite(levelNum) || levelNum !== Number(levelFilter)){
        return false;
      }
    }
    const schoolFilter = castFilterSchoolInput ? normalizeLowerValue(castFilterSchoolInput.value) : "";
    if (schoolFilter){
      if (normalizeLowerValue(preset.school) !== schoolFilter){
        return false;
      }
    }
    const castingTimeFilter = castFilterCastingTimeInput ? normalizeLowerValue(castFilterCastingTimeInput.value) : "";
    if (castingTimeFilter){
      if (!normalizeLowerValue(preset.casting_time).includes(castingTimeFilter)){
        return false;
      }
    }
    const rangeFilter = castFilterRangeInput ? normalizeLowerValue(castFilterRangeInput.value) : "";
    if (rangeFilter){
      if (!normalizeLowerValue(preset.range).includes(rangeFilter)){
        return false;
      }
    }
    const ritualFilter = castFilterRitualInput ? normalizeTextValue(castFilterRitualInput.value) : "";
    if (ritualFilter){
      const ritualValue = ritualFilter === "true";
      if (preset.ritual !== ritualValue){
        return false;
      }
    }
    const concentrationFilter = castFilterConcentrationInput ? normalizeTextValue(castFilterConcentrationInput.value) : "";
    if (concentrationFilter){
      const concentrationValue = concentrationFilter === "true";
      if (preset.concentration !== concentrationValue){
        return false;
      }
    }
    const listFilter = castFilterListInput ? normalizeTextValue(castFilterListInput.value) : "";
    if (listFilter){
      const [group, value] = listFilter.split("::");
      const listValues = preset.lists && typeof preset.lists === "object" ? preset.lists[group] : null;
      if (!Array.isArray(listValues) || !listValues.map(normalizeLowerValue).includes(normalizeLowerValue(value))){
        return false;
      }
    }
    const tagFilters = getTagFilters();
    if (tagFilters.length){
      const presetTags = Array.isArray(preset.tags) ? preset.tags.map(normalizeLowerValue) : [];
      const matchesAll = tagFilters.every(tag => presetTags.includes(tag));
      if (!matchesAll) return false;
    }
    return true;
  };
  const refreshSpellPresetOptions = () => {
    if (!castPresetInput) return;
    const currentValue = String(castPresetInput.value || "");
    castPresetInput.textContent = "";
    if (!cachedSpellPresets.length){
      castPresetInput.disabled = true;
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Presets unavailable";
      castPresetInput.appendChild(placeholder);
      castPresetInput.value = "";
      updateSpellPresetDetails(null);
      return;
    }
    castPresetInput.disabled = false;
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Custom";
    castPresetInput.appendChild(blank);
    const knownSpellSet = getKnownSpellFilterSet();
    const filtered = filterPresetsByKnownList(cachedSpellPresets, knownSpellSet)
      .filter(matchesSpellFilters);
    if (!filtered.length){
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "No spells match filters";
      empty.disabled = true;
      castPresetInput.appendChild(empty);
      castPresetInput.value = "";
      updateSpellPresetDetails(null);
      return;
    }
    const groups = new Map();
    filtered.forEach((preset) => {
      const level = getPresetLevelNumber(preset);
      const key = level === null ? "unknown" : String(level);
      if (!groups.has(key)){
        groups.set(key, []);
      }
      groups.get(key).push(preset);
    });
    const orderedLevels = [];
    for (let i = 0; i <= 9; i += 1){
      if (groups.has(String(i))){
        orderedLevels.push(String(i));
      }
    }
    if (groups.has("unknown")){
      orderedLevels.push("unknown");
    }
    orderedLevels.forEach((levelKey) => {
      const list = groups.get(levelKey) || [];
      list.sort((a, b) => normalizeTextValue(a.name).localeCompare(normalizeTextValue(b.name)));
      const optgroup = document.createElement("optgroup");
      optgroup.label = levelKey === "unknown"
        ? "Unknown Level"
        : formatSpellLevelLabel(Number(levelKey));
      list.forEach((preset) => {
        const name = normalizeTextValue(preset.name);
        if (!name) return;
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        optgroup.appendChild(opt);
      });
      castPresetInput.appendChild(optgroup);
    });
    if (currentValue && filtered.some(p => normalizeTextValue(p.name) === currentValue)){
      castPresetInput.value = currentValue;
    } else {
      castPresetInput.value = "";
    }
    const selected = filtered.find(p => normalizeTextValue(p.name) === castPresetInput.value);
    updateSpellPresetDetails(selected || null);
  };
  const updateSpellPresetOptions = (presets) => {
    const list = normalizeSpellPresets(presets);
    const signature = JSON.stringify(list.map(p => [
      String(p.name || ""),
      String(p.level || ""),
      String(p.school || ""),
      String(p.casting_time || ""),
      String(p.range || ""),
      String(p.ritual || ""),
      String(p.concentration || ""),
      JSON.stringify(p.tags || []),
      JSON.stringify(p.lists || {}),
    ]));
    if (signature === lastSpellPresetSignature){
      return;
    }
    lastSpellPresetSignature = signature;
    cachedSpellPresets = list;
    spellPresetIndex = buildSpellPresetIndex(list);
    updateSpellFilterOptions();
    refreshSpellPresetOptions();
    renderSpellSelectTable(cachedSpellPresets);
  };

  const registerSpellFilterListener = (input, useInputEvent = false) => {
    if (!input) return;
    const handler = () => refreshSpellPresetOptions();
    input.addEventListener("change", handler);
    if (useInputEvent){
      input.addEventListener("input", handler);
    }
  };
  registerSpellFilterListener(castFilterLevelInput);
  registerSpellFilterListener(castFilterSchoolInput);
  registerSpellFilterListener(castFilterTagsInput, true);
  registerSpellFilterListener(castFilterCastingTimeInput);
  registerSpellFilterListener(castFilterRangeInput);
  registerSpellFilterListener(castFilterRitualInput);
  registerSpellFilterListener(castFilterConcentrationInput);
  registerSpellFilterListener(castFilterListInput);

  const setCastFieldEnabled = (input, enabled) => {
    if (!input) return;
    input.disabled = !enabled;
    input.readOnly = !enabled;
  };

  const setCastFieldVisible = (field, visible) => {
    if (!field) return;
    field.style.display = visible ? "" : "none";
  };

  const updateCastShapeFields = () => {
    const shape = String(castShapeInput?.value || "").toLowerCase();
    const usesRadius = shape === "circle" || shape === "sphere" || shape === "cylinder";
    const usesSide = shape === "square" || shape === "cube";
    const usesLength = shape === "line" || shape === "cone" || shape === "wall";
    const usesWidth = shape === "line" || shape === "wall";
    const usesAngle = shape === "line" || shape === "cone" || shape === "wall";
    const usesOrient = shape === "line" || shape === "cone" || shape === "wall";
    const usesThickness = shape === "wall";
    const usesHeight = shape === "wall" || shape === "cylinder";
    setCastFieldVisible(castRadiusField, usesRadius);
    setCastFieldVisible(castSideField, usesSide);
    setCastFieldVisible(castLengthField, usesLength);
    setCastFieldVisible(castWidthField, usesWidth);
    setCastFieldVisible(castAngleField, usesAngle);
    setCastFieldVisible(castOrientField, usesOrient);
    setCastFieldVisible(castThicknessField, usesThickness);
    setCastFieldVisible(castHeightField, usesHeight);
    setCastFieldEnabled(castRadiusInput, usesRadius);
    setCastFieldEnabled(castSideInput, usesSide);
    setCastFieldEnabled(castLengthInput, usesLength);
    setCastFieldEnabled(castWidthInput, usesWidth);
    setCastFieldEnabled(castAngleInput, usesAngle);
    setCastFieldEnabled(castOrientInput, usesOrient);
    setCastFieldEnabled(castThicknessInput, usesThickness);
    setCastFieldEnabled(castHeightInput, usesHeight);
  };

  if (castShapeInput){
    castShapeInput.addEventListener("change", updateCastShapeFields);
    updateCastShapeFields();
  }

  const parseDiceSpec = (value) => {
    if (typeof value !== "string") return null;
    const raw = value.trim().toLowerCase();
    const match = raw.match(/^(\\d+)d(4|6|8|10|12)$/);
    if (!match) return null;
    const count = Number(match[1]);
    const sides = Number(match[2]);
    if (!Number.isFinite(count) || count <= 0) return null;
    return {count, sides};
  };

  const formatDiceSpec = (spec) => `${spec.count}d${spec.sides}`;

  const normalizeUpcastConfig = (upcast) => {
    if (!upcast || typeof upcast !== "object") return null;
    const baseLevel = Number(upcast.base_level);
    if (!Number.isFinite(baseLevel) || baseLevel < 0){
      console.warn("Invalid upcast base_level; ignoring upcast config.", upcast);
      return null;
    }
    const rawIncrements = Array.isArray(upcast.increments) ? upcast.increments : [];
    const increments = [];
    const slotAddDice = typeof upcast.add_per_slot_above === "string" ? upcast.add_per_slot_above : "";
    if (slotAddDice && parseDiceSpec(slotAddDice)){
      increments.push({
        levels_per_increment: 1,
        add_dice: slotAddDice,
      });
    }
    rawIncrements.forEach((entry) => {
      if (!entry || typeof entry !== "object"){
        console.warn("Invalid upcast increment entry; skipping.", entry);
        return;
      }
      const addDice = typeof entry.add_dice === "string" ? entry.add_dice : "";
      if (!parseDiceSpec(addDice)){
        console.warn("Invalid upcast add_dice; skipping.", entry);
        return;
      }
      const levelsPer = Number(entry.levels_per_increment);
      if (Number.isFinite(levelsPer) && levelsPer > 0){
        increments.push({
          levels_per_increment: levelsPer,
          add_dice: addDice,
        });
        return;
      }
      const levelThreshold = Number(entry.level);
      if (Number.isFinite(levelThreshold) && levelThreshold > baseLevel){
        increments.push({
          level: levelThreshold,
          add_dice: addDice,
        });
        return;
      }
      console.warn("Invalid upcast increment entry; skipping.", entry);
    });
    if (!increments.length){
      console.warn("Upcast increments contained no valid entries; ignoring upcast config.", upcast);
      return null;
    }
    return {base_level: baseLevel, increments};
  };

  const computeUpcastValues = (baseDice, baseDefaultDamage, upcastConfig, slotLevel) => {
    if (!upcastConfig || !Number.isFinite(slotLevel)) return {dice: baseDice, defaultDamage: baseDefaultDamage};
    const baseLevel = Number(upcastConfig.base_level);
    if (!Number.isFinite(baseLevel)) return {dice: baseDice, defaultDamage: baseDefaultDamage};
    const deltaLevels = Math.floor(slotLevel - baseLevel);
    if (deltaLevels <= 0) return {dice: baseDice, defaultDamage: baseDefaultDamage};
    const baseDiceSpec = parseDiceSpec(baseDice) || parseDiceSpec(baseDefaultDamage);
    let totalDiceSpec = baseDiceSpec ? {count: baseDiceSpec.count, sides: baseDiceSpec.sides} : null;
    let applied = false;
    (upcastConfig.increments || []).forEach((inc) => {
      const addDiceSpec = parseDiceSpec(inc.add_dice);
      if (!addDiceSpec) return;
      let steps = 0;
      const levelsPer = Number(inc.levels_per_increment);
      if (Number.isFinite(levelsPer) && levelsPer > 0){
        steps = Math.floor(deltaLevels / levelsPer);
      } else {
        const levelThreshold = Number(inc.level);
        if (Number.isFinite(levelThreshold) && slotLevel >= levelThreshold){
          steps = 1;
        }
      }
      if (steps <= 0) return;
      const addCount = addDiceSpec.count * steps;
      if (!totalDiceSpec){
        totalDiceSpec = {count: addCount, sides: addDiceSpec.sides};
        applied = true;
        return;
      }
      if (totalDiceSpec.sides !== addDiceSpec.sides){
        console.warn("Upcast dice sides mismatch; skipping increment.", inc);
        return;
      }
      totalDiceSpec.count += addCount;
      applied = true;
    });
    const dice = totalDiceSpec ? formatDiceSpec(totalDiceSpec) : baseDice;
    let defaultDamage = baseDefaultDamage;
    if (applied){
      const defaultDamageDice = parseDiceSpec(baseDefaultDamage);
      if (defaultDamageDice || baseDefaultDamage === null || baseDefaultDamage === ""){
        defaultDamage = dice;
      }
    }
    return {dice, defaultDamage};
  };

  const castDamageTypes = new Set();
  let castDurationTurns = null;
  let castOverTime = null;
  let castMovePerTurnFt = null;
  let castTriggerOnStartOrEnter = null;
  let castPersistent = null;
  let castPinnedDefault = null;
  let castUpcastConfig = null;
  let castBaseDice = null;
  let castBaseDefaultDamage = null;
  const setCastDamageTypes = (types) => {
    castDamageTypes.clear();
    if (Array.isArray(types)){
      types.forEach((entry) => {
        const dtype = String(entry || "").trim();
        if (dtype){
          castDamageTypes.add(dtype);
        }
      });
    }
    renderCastDamageTypes();
  };
  const renderCastDamageTypes = () => {
    if (!castDamageTypeList) return;
    castDamageTypeList.textContent = "";
    for (const dtype of castDamageTypes){
      const chip = document.createElement("span");
      chip.className = "chip damage-type-chip";
      const label = document.createElement("span");
      label.textContent = dtype;
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.setAttribute("aria-label", `Remove ${dtype}`);
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", () => {
        castDamageTypes.delete(dtype);
        renderCastDamageTypes();
      });
      chip.appendChild(label);
      chip.appendChild(removeBtn);
      castDamageTypeList.appendChild(chip);
    }
  };
  const addCastDamageType = (value) => {
    const dtype = String(value || "").trim();
    if (!dtype){
      localToast("Choose a damage type first, matey.");
      return;
    }
    if (castDamageTypes.has(dtype)){
      localToast("That damage type be added already.");
      return;
    }
    castDamageTypes.add(dtype);
    renderCastDamageTypes();
  };

  const applySpellPreset = (preset) => {
    if (!preset || typeof preset !== "object") return;
    if (castNameInput && preset.name){
      castNameInput.value = String(preset.name || "");
    }
    if (castShapeInput){
      castShapeInput.value = preset.shape ? String(preset.shape || "").toLowerCase() : "";
    }
    updateCastShapeFields();
    if (castRadiusInput){
      castRadiusInput.value = Number.isFinite(Number(preset.radius_ft)) ? Number(preset.radius_ft) : "";
    }
    if (castSideInput){
      castSideInput.value = Number.isFinite(Number(preset.side_ft)) ? Number(preset.side_ft) : "";
    }
    if (castLengthInput){
      castLengthInput.value = Number.isFinite(Number(preset.length_ft)) ? Number(preset.length_ft) : "";
    }
    if (castWidthInput){
      castWidthInput.value = Number.isFinite(Number(preset.width_ft)) ? Number(preset.width_ft) : "";
    }
    if (castAngleInput){
      castAngleInput.value = Number.isFinite(Number(preset.angle_deg)) ? Number(preset.angle_deg) : "";
    }
    if (castOrientInput){
      castOrientInput.value = preset.orient ? String(preset.orient || "").toLowerCase() : "vertical";
    }
    if (castThicknessInput){
      castThicknessInput.value = Number.isFinite(Number(preset.thickness_ft)) ? Number(preset.thickness_ft) : "";
    }
    if (castHeightInput){
      castHeightInput.value = Number.isFinite(Number(preset.height_ft)) ? Number(preset.height_ft) : "";
    }
    if (castDcTypeInput){
      castDcTypeInput.value = preset.save_type ? String(preset.save_type || "").toLowerCase() : "";
    }
    if (castDcValueInput){
      castDcValueInput.value = Number.isFinite(Number(preset.save_dc)) ? Number(preset.save_dc) : "";
    }
    if (castDefaultDamageInput){
      const defaultDamage = preset.default_damage;
      castDefaultDamageInput.value = defaultDamage !== undefined && defaultDamage !== null ? String(defaultDamage) : "";
      castBaseDefaultDamage = defaultDamage !== undefined && defaultDamage !== null ? String(defaultDamage) : "";
    }
    if (castDiceInput){
      const dice = preset.dice;
      castDiceInput.value = dice !== undefined && dice !== null ? String(dice) : "";
      castBaseDice = dice !== undefined && dice !== null ? String(dice) : "";
    }
    if (castColorInput && preset.color){
      castColorInput.value = String(preset.color || "");
    }
    setCastDamageTypes(preset.damage_types);
    if (Number.isFinite(Number(preset.duration_turns))){
      castDurationTurns = Number(preset.duration_turns);
    } else {
      castDurationTurns = null;
    }
    if (typeof preset.over_time === "boolean"){
      castOverTime = preset.over_time;
    } else {
      castOverTime = null;
    }
    const movePerTurn = Number(preset.move_per_turn_ft);
    if (Number.isFinite(movePerTurn)){
      castMovePerTurnFt = movePerTurn;
    } else {
      castMovePerTurnFt = null;
    }
    if (preset.trigger_on_start_or_enter){
      castTriggerOnStartOrEnter = String(preset.trigger_on_start_or_enter || "").toLowerCase();
    } else {
      castTriggerOnStartOrEnter = null;
    }
    if (typeof preset.persistent === "boolean"){
      castPersistent = preset.persistent;
    } else {
      castPersistent = null;
    }
    if (typeof preset.pinned_default === "boolean"){
      castPinnedDefault = preset.pinned_default;
    } else {
      castPinnedDefault = null;
    }
    castUpcastConfig = normalizeUpcastConfig(preset.upcast);
    if (castSlotLevelInput){
      if (castUpcastConfig){
        castSlotLevelInput.disabled = false;
        castSlotLevelInput.readOnly = false;
        castSlotLevelInput.value = Number.isFinite(Number(castUpcastConfig.base_level))
          ? String(castUpcastConfig.base_level)
          : "";
      } else {
        castSlotLevelInput.value = "";
        castSlotLevelInput.disabled = true;
        castSlotLevelInput.readOnly = true;
      }
    }
    const slotLevelValue = Number(castSlotLevelInput?.value);
    const upcastValues = computeUpcastValues(castBaseDice, castBaseDefaultDamage, castUpcastConfig, slotLevelValue);
    if (castDiceInput && upcastValues.dice !== undefined && upcastValues.dice !== null){
      castDiceInput.value = String(upcastValues.dice || "");
    }
    if (castDefaultDamageInput && upcastValues.defaultDamage !== undefined && upcastValues.defaultDamage !== null){
      castDefaultDamageInput.value = String(upcastValues.defaultDamage || "");
    }
  };

  const updateUpcastFields = () => {
    if (!castUpcastConfig) return;
    const slotLevelValue = Number(castSlotLevelInput?.value);
    const upcastValues = computeUpcastValues(castBaseDice, castBaseDefaultDamage, castUpcastConfig, slotLevelValue);
    if (castDiceInput && upcastValues.dice !== undefined && upcastValues.dice !== null){
      castDiceInput.value = String(upcastValues.dice || "");
    }
    if (castDefaultDamageInput && upcastValues.defaultDamage !== undefined && upcastValues.defaultDamage !== null){
      castDefaultDamageInput.value = String(upcastValues.defaultDamage || "");
    }
  };

  if (castPresetInput){
    castPresetInput.addEventListener("change", () => {
      const name = String(castPresetInput.value || "").trim();
      if (!name){
        castDurationTurns = null;
        castOverTime = null;
        castMovePerTurnFt = null;
        castTriggerOnStartOrEnter = null;
        castPersistent = null;
        castPinnedDefault = null;
        castUpcastConfig = null;
        castBaseDice = null;
        castBaseDefaultDamage = null;
        if (castDefaultDamageInput){
          castDefaultDamageInput.value = "";
        }
        if (castDiceInput){
          castDiceInput.value = "";
        }
        if (castSlotLevelInput){
          castSlotLevelInput.value = "";
          castSlotLevelInput.disabled = true;
          castSlotLevelInput.readOnly = true;
        }
        updateSpellPresetDetails(null);
        return;
      }
      const preset = cachedSpellPresets.find(p => String(p.name || "") === name);
      updateSpellPresetDetails(preset || null);
      applySpellPreset(preset);
    });
  }

  if (castSlotLevelInput){
    castSlotLevelInput.addEventListener("input", () => {
      updateUpcastFields();
    });
  }

  if (castAddDamageTypeBtn){
    castAddDamageTypeBtn.addEventListener("click", () => {
      addCastDamageType(castDamageTypeInput?.value || "");
    });
  }

  if (castForm){
    castForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (!claimedCid){
        localToast("Claim a character first, matey.");
        return;
      }
      if (!state || !gridReady()){
        localToast("Map not ready yet, matey.");
        return;
      }
      const shape = String(castShapeInput?.value || "").toLowerCase();
      if (!shape){
        localToast("Pick a spell shape first, matey.");
        return;
      }
      const parsePositive = (value) => {
        const num = parseFloat(value || "");
        return Number.isFinite(num) && num > 0 ? num : null;
      };
      const parseNonnegative = (value) => {
        const num = parseFloat(value || "");
        return Number.isFinite(num) && num >= 0 ? num : null;
      };
      const radiusFt = parsePositive(castRadiusInput?.value);
      const sideFt = parsePositive(castSideInput?.value);
      const lengthFt = parsePositive(castLengthInput?.value);
      const widthFt = parsePositive(castWidthInput?.value);
      const angleRaw = String(castAngleInput?.value || "").trim();
      const angleDeg = angleRaw ? parseNonnegative(castAngleInput?.value) : null;
      const widthRaw = String(castWidthInput?.value || "").trim();
      const thicknessFt = parsePositive(castThicknessInput?.value);
      const thicknessRaw = String(castThicknessInput?.value || "").trim();
      const heightFt = parsePositive(castHeightInput?.value);
      const heightRaw = String(castHeightInput?.value || "").trim();
      const orientValue = String(castOrientInput?.value || "vertical").toLowerCase();
      const orient = orientValue === "horizontal" ? "horizontal" : "vertical";
      if (shape === "circle" && radiusFt === null){
        localToast("Enter a valid radius, matey.");
        return;
      }
      if ((shape === "sphere" || shape === "cylinder") && radiusFt === null){
        localToast("Enter a valid radius, matey.");
        return;
      }
      if (shape === "cylinder" && heightRaw && heightFt === null){
        localToast("Enter a valid height, matey.");
        return;
      }
      if (shape === "square" && sideFt === null){
        localToast("Enter a valid side length, matey.");
        return;
      }
      if (shape === "cube" && sideFt === null){
        localToast("Enter a valid side length, matey.");
        return;
      }
      if (shape === "line" && (lengthFt === null || widthFt === null)){
        localToast("Enter a valid line size, matey.");
        return;
      }
      if (shape === "cone" && lengthFt === null){
        localToast("Enter a valid cone length, matey.");
        return;
      }
      if (shape === "cone" && angleRaw && (angleDeg === null || angleDeg <= 0)){
        localToast("Enter a valid cone angle, matey.");
        return;
      }
      if ((shape === "line" || shape === "wall") && angleRaw && angleDeg === null){
        localToast("Enter a valid angle, matey.");
        return;
      }
      if (shape === "wall" && widthRaw && widthFt === null){
        localToast("Enter a valid wall width, matey.");
        return;
      }
      if (shape === "wall" && thicknessRaw && thicknessFt === null){
        localToast("Enter a valid wall thickness, matey.");
        return;
      }
      if (shape === "wall" && heightRaw && heightFt === null){
        localToast("Enter a valid wall height, matey.");
        return;
      }
      if (shape === "wall"){
        if (lengthFt === null){
          localToast("Enter a valid wall length, matey.");
          return;
        }
        if (widthFt === null && (thicknessFt === null || heightFt === null)){
          localToast("Enter a valid wall thickness and height (or width), matey.");
          return;
        }
      }
      const dcType = String(castDcTypeInput?.value || "").trim().toLowerCase();
      const dcValue = parseInt(castDcValueInput?.value || "", 10);
      const damageTypes = Array.from(castDamageTypes);
      if (!damageTypes.length){
        const fallbackType = String(castDamageTypeInput?.value || "").trim();
        if (fallbackType){
          damageTypes.push(fallbackType);
        }
      }
      const damageType = damageTypes.length === 1 ? damageTypes[0] : "";
      const name = String(castNameInput?.value || "").trim();
      const color = normalizeHexColor(castColorInput?.value || "") || null;
      let defaultDamage = String(castDefaultDamageInput?.value || "").trim();
      let dice = String(castDiceInput?.value || "").trim();
      if (castUpcastConfig){
        const slotLevelValue = Number(castSlotLevelInput?.value);
        const upcastValues = computeUpcastValues(
          castBaseDice || dice,
          castBaseDefaultDamage || defaultDamage,
          castUpcastConfig,
          slotLevelValue
        );
        if (upcastValues.dice !== undefined && upcastValues.dice !== null){
          dice = String(upcastValues.dice || "");
        }
        if (upcastValues.defaultDamage !== undefined && upcastValues.defaultDamage !== null){
          defaultDamage = String(upcastValues.defaultDamage || "");
        }
      }
      const center = defaultAoeCenter();
      if (shape !== "line"){
        const caster = getClaimedUnit();
        if (caster && caster.pos){
          const start = {col: Number(caster.pos.col), row: Number(caster.pos.row)};
          const end = {col: Number(center.cx), row: Number(center.cy)};
          const blocked = isLineOfSightBlocked(start, end);
          setLosPreview(start, end, blocked);
          if (blocked){
            localToast("No line of sight to spell center.");
            return;
          }
        }
      }
      const payload = {
        shape,
        dc: Number.isFinite(dcValue) ? dcValue : null,
        save_type: dcType || null,
        damage_type: damageType || null,
        damage_types: damageTypes,
        name: name || null,
        color,
        cx: center.cx,
        cy: center.cy,
      };
      if (defaultDamage){
        payload.default_damage = defaultDamage;
      }
      if (dice){
        payload.dice = dice;
      }
      if (Number.isFinite(Number(castDurationTurns)) && Number(castDurationTurns) >= 0){
        payload.duration_turns = Number(castDurationTurns);
      }
      if (typeof castOverTime === "boolean"){
        payload.over_time = castOverTime;
      }
      if (Number.isFinite(Number(castMovePerTurnFt)) && Number(castMovePerTurnFt) >= 0){
        payload.move_per_turn_ft = Number(castMovePerTurnFt);
      }
      if (castTriggerOnStartOrEnter){
        payload.trigger_on_start_or_enter = castTriggerOnStartOrEnter;
      }
      if (typeof castPersistent === "boolean"){
        payload.persistent = castPersistent;
      }
      if (typeof castPinnedDefault === "boolean"){
        payload.pinned_default = castPinnedDefault;
      }
      if (shape === "circle"){
        payload.radius_ft = radiusFt;
      } else if (shape === "sphere" || shape === "cylinder"){
        payload.radius_ft = radiusFt;
        if (heightFt !== null){
          payload.height_ft = heightFt;
        }
      } else if (shape === "square" || shape === "cube"){
        payload.side_ft = sideFt;
      } else if (shape === "line"){
        payload.length_ft = lengthFt;
        payload.width_ft = widthFt;
        payload.orient = orient;
        if (angleDeg !== null){
          payload.angle_deg = angleDeg;
        }
      } else if (shape === "cone"){
        payload.length_ft = lengthFt;
        payload.angle_deg = angleDeg !== null ? angleDeg : 90;
        payload.orient = orient;
      } else if (shape === "wall"){
        payload.length_ft = lengthFt;
        payload.orient = orient;
        if (widthFt !== null){
          payload.width_ft = widthFt;
        }
        if (thicknessFt !== null){
          payload.thickness_ft = thicknessFt;
        }
        if (heightFt !== null){
          payload.height_ft = heightFt;
        }
        if (angleDeg !== null){
          payload.angle_deg = angleDeg;
        }
      }
      send({type: "cast_aoe", payload});
    });
  }

  if (dashBtn){
    dashBtn.addEventListener("click", () => {
      if (!claimedCid) return;
      showDashModal();
    });
  }
  if (dashActionBtn){
    dashActionBtn.addEventListener("click", () => {
      if (!claimedCid) return;
      send({type:"dash", cid: Number(claimedCid), spend:"action"});
      hideDashModal();
    });
  }
  if (dashBonusActionBtn){
    dashBonusActionBtn.addEventListener("click", () => {
      if (!claimedCid) return;
      send({type:"dash", cid: Number(claimedCid), spend:"bonus"});
      hideDashModal();
    });
  }
  if (dashCancelBtn){
    dashCancelBtn.addEventListener("click", () => {
      hideDashModal();
    });
  }
  if (battleLogBtn){
    battleLogBtn.addEventListener("click", () => {
      requestBattleLog();
      showLogModal();
    });
  }
  if (logRefreshBtn){
    logRefreshBtn.addEventListener("click", () => {
      requestBattleLog();
    });
  }
  if (logCloseBtn){
    logCloseBtn.addEventListener("click", () => {
      hideLogModal();
    });
  }
  if (configBtn){
    configBtn.addEventListener("click", () => {
      if (!configModal) return;
      if (configModal.classList.contains("show")){
        hideConfigModal();
        return;
      }
      showConfigModal();
    });
  }
  if (configCloseBtn){
    configCloseBtn.addEventListener("click", () => {
      hideConfigModal();
    });
  }
  if (configModal){
    configModal.addEventListener("click", (event) => {
      if (event.target === configModal){
        hideConfigModal();
      }
    });
  }
  if (adminMenuBtn && adminMenuPopover){
    adminMenuBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = adminMenuPopover.classList.contains("show");
      setAdminMenu(!isOpen);
    });
  }
  if (adminMenuOpenBtn){
    adminMenuOpenBtn.addEventListener("click", async () => {
      closeAdminMenu();
      try {
        await requestAdminLogin();
      } catch (err){
        return;
      }
      showAdminModal();
      fetchAdminSessions();
    });
  }
  if (adminMenuRefreshBtn){
    adminMenuRefreshBtn.addEventListener("click", async () => {
      closeAdminMenu();
      try {
        await requestAdminLogin();
      } catch (err){
        return;
      }
      fetchAdminSessions();
    });
  }
  if (adminRefreshBtn){
    adminRefreshBtn.addEventListener("click", () => {
      fetchAdminSessions();
    });
  }
  if (adminCloseBtn){
    adminCloseBtn.addEventListener("click", () => {
      hideAdminModal();
    });
  }
  if (adminModal){
    adminModal.addEventListener("click", (event) => {
      if (event.target === adminModal){
        hideAdminModal();
      }
    });
  }
  if (adminLoginSubmit){
    adminLoginSubmit.addEventListener("click", () => {
      submitAdminLogin();
    });
  }
  if (adminLoginCancel){
    adminLoginCancel.addEventListener("click", () => {
      hideAdminLoginModal();
      finalizeAdminLogin(false);
    });
  }
  if (adminLoginModal){
    adminLoginModal.addEventListener("click", (event) => {
      if (event.target === adminLoginModal){
        hideAdminLoginModal();
        finalizeAdminLogin(false);
      }
    });
  }
  if (adminPasswordInput){
    adminPasswordInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter"){
        event.preventDefault();
        submitAdminLogin();
      }
    });
  }
  if (presetSaveBtn){
    presetSaveBtn.addEventListener("click", () => {
      const preset = buildGuiPreset();
      persistLocalPreset(preset);
      send({type: "save_preset", preset});
    });
  }
  if (presetLoadBtn){
    presetLoadBtn.addEventListener("click", () => {
      send({type: "load_preset"});
    });
  }
  if (enableNotificationsBtn){
    enableNotificationsBtn.addEventListener("click", async () => {
      if (!("Notification" in window)){
        setNotificationStatus("Notifications are not supported.");
        return;
      }
      try {
        if (!swRegistration){
          swRegistration = await navigator.serviceWorker.ready;
        }
      } catch (err){
        console.warn("Service worker not ready.", err);
        setNotificationStatus("Service worker not ready.");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted"){
        setNotificationStatus("Notifications blocked.");
        return;
      }
      if (!("PushManager" in window)){
        setNotificationStatus("Push is not supported.");
        return;
      }
      try {
        const existing = await swRegistration.pushManager.getSubscription();
        if (existing){
          setNotificationStatus("Notifications already enabled.");
          return;
        }
        if (!pushPublicKey){
          setNotificationStatus("Missing push public key.");
          return;
        }
        const subscription = await swRegistration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(pushPublicKey),
        });
        console.log("Push subscription:", JSON.stringify(subscription));
        setNotificationStatus("Notifications enabled.");
      } catch (err){
        console.warn("Push subscription failed.", err);
        setNotificationStatus("Failed to enable notifications.");
      }
    });
  }
  if (enableTurnAlertsBtn){
    enableTurnAlertsBtn.addEventListener("click", async () => {
      try {
        const identity = getTurnAlertIdentity();
        await ensurePushSubscribed({
          vapidPublicKey: pushPublicKey,
          playerId: identity.playerId,
        });
        localToast("Turn alerts enabled.");
      } catch (err){
        const message = err?.message ? String(err.message) : "Failed to enable alerts.";
        setTurnAlertStatus(message);
        localToast(message);
      }
    });
  }
  if (hideTurnAlertsBtn && turnAlertsPanel){
    hideTurnAlertsBtn.addEventListener("click", () => {
      localStorage.setItem(turnAlertHideKey, "1");
      turnAlertsPanel.classList.add("hidden");
    });
  }
  if (castOverlayOpenBtn){
    castOverlayOpenBtn.addEventListener("click", () => {
      setCastOverlayOpen(true);
    });
  }
  if (castOverlayBackBtn){
    castOverlayBackBtn.addEventListener("click", () => {
      setCastOverlayOpen(false);
    });
  }
  if (spellPreparedOpenBtn){
    spellPreparedOpenBtn.addEventListener("click", () => {
      if (!claimedCid){
        localToast("Claim a character first.");
        return;
      }
      setSpellSelectContext("prepared");
      setSpellSelectMode(true);
      setSpellSelectOverlayOpen(true);
    });
  }
  if (spellSelectBackBtn){
    spellSelectBackBtn.addEventListener("click", () => {
      setSpellSelectOverlayOpen(false);
    });
  }
  if (spellSelectCloseBtn){
    spellSelectCloseBtn.addEventListener("click", () => {
      setSpellSelectOverlayOpen(false);
    });
  }
  if (spellSelectModeBtn){
    spellSelectModeBtn.addEventListener("click", () => {
      setSpellSelectMode(!spellSelectMode);
    });
  }
  if (spellSelectSaveBtn){
    spellSelectSaveBtn.addEventListener("click", async () => {
      if (!claimedCid){
        localToast("Claim a character first.");
        return;
      }
      if (!spellSelectMode){
        localToast(
          spellSelectContext === "prepared"
            ? "Enable selection mode to save prepared spells."
            : "Enable selection mode to save known spells."
        );
        return;
      }
      const playerName = getClaimedPlayerName();
      if (!playerName){
        localToast("Unable to resolve player name.");
        return;
      }
      const currentConfig = getPlayerSpellConfig(playerName);
      const preparedConfig = getPlayerPreparedSpellConfig(playerName);
      if (spellSelectContext === "prepared"){
        const names = getSelectedSpellNames(selectedPreparedSpellKeys);
        const saved = await persistPlayerSpellConfig(playerName, {
          cantrips: currentConfig.cantrips,
          spells: currentConfig.spells,
          names: currentConfig.names,
          prepared: names,
          preparedMaxFormula: preparedConfig.maxFormula,
        });
        if (!saved) return;
        localToast("Prepared spells saved.");
        selectedPreparedSpellKeys = new Set(names.map(getSpellKey));
        renderSpellSelectTable(cachedSpellPresets);
        return;
      }
      const names = getSelectedSpellNames(selectedKnownSpellKeys);
      const saved = await persistPlayerSpellConfig(playerName, {
        cantrips: currentConfig.cantrips,
        spells: currentConfig.spells,
        names,
        prepared: preparedConfig.prepared,
        preparedMaxFormula: preparedConfig.maxFormula,
      });
      if (!saved) return;
      localToast("Known spells saved.");
      selectedKnownSpellKeys = new Set(names.map(getSpellKey));
      refreshSpellPresetOptions();
      renderSpellSelectTable(cachedSpellPresets);
    });
  }
  if (spellConfigOpenBtn){
    spellConfigOpenBtn.addEventListener("click", () => {
      setSpellConfigOpen(true);
    });
  }
  if (spellConfigCancelBtn){
    spellConfigCancelBtn.addEventListener("click", () => {
      setSpellConfigOpen(false);
    });
  }
  if (spellConfigSaveBtn){
    spellConfigSaveBtn.addEventListener("click", async () => {
      if (!claimedCid){
        localToast("Claim a character first.");
        return;
      }
      const playerName = getClaimedPlayerName();
      if (!playerName){
        localToast("Unable to resolve player name.");
        return;
      }
      const currentConfig = getPlayerSpellConfig(playerName);
      const preparedConfig = getPlayerPreparedSpellConfig(playerName);
      const saved = await persistPlayerSpellConfig(playerName, {
        cantrips: spellConfigCantripsInput?.value,
        spells: spellConfigSpellsInput?.value,
        names: currentConfig.names,
        prepared: preparedConfig.prepared,
        preparedMaxFormula: preparedConfig.maxFormula,
      });
      if (!saved) return;
      setSpellConfigOpen(false);
      updateSpellSelectSummary();
      localToast("Known spells saved.");
    });
  }
  if (spellConfigForm){
    spellConfigForm.addEventListener("submit", (event) => {
      event.preventDefault();
      spellConfigSaveBtn?.click();
    });
  }
  if (connEl && connPopoverEl){
    connEl.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = connPopoverEl.classList.contains("show");
      setConnPopover(!isOpen);
    });
  }
  if (connReconnectBtn){
    connReconnectBtn.addEventListener("click", () => {
      softReconnect();
    });
  }
  document.addEventListener("click", (event) => {
    if (!connPopoverEl || !connEl) return;
    if (connPopoverEl.contains(event.target) || connEl.contains(event.target)) return;
    closeConnPopover();
  });
  document.addEventListener("click", (event) => {
    if (!adminMenuPopover || !adminMenuBtn) return;
    if (adminMenuPopover.contains(event.target) || adminMenuBtn.contains(event.target)) return;
    closeAdminMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape"){
      if (spellConfigModal?.classList.contains("show")){
        setSpellConfigOpen(false);
        return;
      }
      if (castOverlay?.classList.contains("show")){
        setCastOverlayOpen(false);
        return;
      }
      closeConnPopover();
      closeAdminMenu();
      hideAdminModal();
    }
  });
  if (toggleTopbarTitle){
    toggleTopbarTitle.addEventListener("change", (event) => {
      showTopbarTitle = !!event.target.checked;
      persistToggle(uiToggleKeys.topbarTitle, showTopbarTitle);
      applyUiConfig();
    });
  }
  if (toggleConnIndicator){
    toggleConnIndicator.addEventListener("change", (event) => {
      showConnIndicator = !!event.target.checked;
      persistToggle(uiToggleKeys.connIndicator, showConnIndicator);
      applyUiConfig();
    });
  }
  if (connStyleButtons.length){
    connStyleButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const nextStyle = button.dataset.connStyle === "compact" ? "compact" : "full";
        if (connStyle === nextStyle) return;
        connStyle = nextStyle;
        persistChoice(uiSelectKeys.connStyle, connStyle);
        applyUiConfig();
      });
    });
  }
  if (toggleLockMap){
    toggleLockMap.addEventListener("change", (event) => {
      showLockMap = !!event.target.checked;
      persistToggle(uiToggleKeys.lockMap, showLockMap);
      applyUiConfig();
    });
  }
  if (toggleCenterMap){
    toggleCenterMap.addEventListener("change", (event) => {
      showCenterMap = !!event.target.checked;
      persistToggle(uiToggleKeys.centerMap, showCenterMap);
      applyUiConfig();
    });
  }
  if (toggleMeasure){
    toggleMeasure.addEventListener("change", (event) => {
      showMeasure = !!event.target.checked;
      persistToggle(uiToggleKeys.measure, showMeasure);
      applyUiConfig();
    });
  }
  if (toggleMeasureClear){
    toggleMeasureClear.addEventListener("change", (event) => {
      showMeasureClear = !!event.target.checked;
      persistToggle(uiToggleKeys.measureClear, showMeasureClear);
      applyUiConfig();
    });
  }
  if (toggleZoomIn){
    toggleZoomIn.addEventListener("change", (event) => {
      showZoomIn = !!event.target.checked;
      persistToggle(uiToggleKeys.zoomIn, showZoomIn);
      applyUiConfig();
    });
  }
  if (toggleZoomOut){
    toggleZoomOut.addEventListener("change", (event) => {
      showZoomOut = !!event.target.checked;
      persistToggle(uiToggleKeys.zoomOut, showZoomOut);
      applyUiConfig();
    });
  }
  if (toggleBattleLog){
    toggleBattleLog.addEventListener("change", (event) => {
      showBattleLog = !!event.target.checked;
      persistToggle(uiToggleKeys.battleLog, showBattleLog);
      applyUiConfig();
    });
  }
  if (initiativeStyleSelect){
    initiativeStyleSelect.addEventListener("change", (event) => {
      const value = event.target.value;
      initiativeStyle = ["full", "compact", "hidden"].includes(value) ? value : "full";
      persistChoice(uiSelectKeys.initiativeStyle, initiativeStyle);
      applyUiConfig();
    });
  }
  if (toggleUseAction){
    toggleUseAction.addEventListener("change", (event) => {
      showUseAction = !!event.target.checked;
      persistToggle(uiToggleKeys.useAction, showUseAction);
      applyUiConfig();
    });
  }
  if (toggleUseBonusAction){
    toggleUseBonusAction.addEventListener("change", (event) => {
      showUseBonusAction = !!event.target.checked;
      persistToggle(uiToggleKeys.useBonusAction, showUseBonusAction);
      applyUiConfig();
    });
  }
  if (toggleDash){
    toggleDash.addEventListener("change", (event) => {
      showDash = !!event.target.checked;
      persistToggle(uiToggleKeys.dash, showDash);
      applyUiConfig();
    });
  }
  if (toggleStandUp){
    toggleStandUp.addEventListener("change", (event) => {
      showStandUp = !!event.target.checked;
      persistToggle(uiToggleKeys.standUp, showStandUp);
      applyUiConfig();
    });
  }
  if (toggleResetTurn){
    toggleResetTurn.addEventListener("change", (event) => {
      showResetTurn = !!event.target.checked;
      persistToggle(uiToggleKeys.resetTurn, showResetTurn);
      applyUiConfig();
    });
  }
  if (toggleSpellMenu){
    toggleSpellMenu.addEventListener("change", (event) => {
      hideSpellMenu = !!event.target.checked;
      persistToggle(uiToggleKeys.hideSpellMenu, hideSpellMenu);
      applyUiConfig();
    });
  }
  if (toggleLockMenus){
    toggleLockMenus.addEventListener("change", (event) => {
      menusLocked = !!event.target.checked;
      persistToggle(uiToggleKeys.lockMenus, menusLocked);
      applyUiConfig();
    });
  }
  Object.entries(hotkeyConfig).forEach(([action, config]) => {
    if (!config || !config.input) return;
    config.input.addEventListener("keydown", (event) => {
      event.preventDefault();
      if (event.key === "Escape"){
        config.input.blur();
        return;
      }
      if (event.key === "Backspace" || event.key === "Delete"){
        setHotkey(action, "");
        return;
      }
      const combo = normalizeHotkeyEvent(event);
      if (!combo) return;
      setHotkey(action, combo);
    });
    config.input.addEventListener("focus", () => {
      config.input.select();
    });
  });
  useActionBtn.addEventListener("click", () => {
    if (!claimedCid) return;
    send({type:"use_action", cid: Number(claimedCid)});
  });
  useBonusActionBtn.addEventListener("click", () => {
    if (!claimedCid) return;
    send({type:"use_bonus_action", cid: Number(claimedCid)});
  });
  if (standUpBtn){
    standUpBtn.addEventListener("click", () => {
      if (!claimedCid) return;
      send({type:"stand_up", cid: Number(claimedCid)});
    });
  }
  if (resetTurnBtn){
    resetTurnBtn.addEventListener("click", () => {
      if (!claimedCid) return;
      send({type:"reset_turn", cid: Number(claimedCid)});
    });
  }
  document.getElementById("endTurn").addEventListener("click", () => {
    if (!claimedCid) return;
    send({type:"end_turn", cid: Number(claimedCid)});
  });
  if (turnModalOk){
    turnModalOk.addEventListener("click", () => {
      handleUserGesture();
      hideTurnModal();
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    if (isTypingTarget(event.target)) return;
    const combo = normalizeHotkeyEvent(event);
    if (!combo) return;
    const action = hotkeyBindings.get(combo);
    if (!action) return;
    event.preventDefault();
    const config = hotkeyConfig[action];
    if (config && typeof config.action === "function"){
      config.action();
    }
  });
  document.addEventListener("pointerdown", handleUserGesture, {passive: true});
  document.addEventListener("keydown", handleUserGesture);

  const mapWrap = document.querySelector(".mapWrap");
  if (mapWrap && window.ResizeObserver){
    const ro = new ResizeObserver(() => resize());
    ro.observe(mapWrap);
  }
  resize();
  updateMeasurementControls();
  updateWaitingOverlay();
  connect();
})();
</script>
</body>
</html>
"""

SERVICE_WORKER_JS = r"""self.addEventListener("push", (event) => {
  let payload = {};
  if (event.data){
    try {
      payload = event.data.json();
    } catch (err){
      try {
        payload = { body: event.data.text() };
      } catch (parseErr){
        payload = {};
      }
    }
  }
  const title = payload.title || "InitTracker LAN";
  const body = payload.body || "You have a new alert.";
  const url = payload.url || "/";
  const options = {
    body,
    data: { url },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification && event.notification.data && event.notification.data.url) ? event.notification.data.url : "/";
  event.waitUntil((async () => {
    const clientList = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of clientList){
      client.postMessage({ type: "deep-link", url });
      if ("focus" in client){
        await client.focus();
        return;
      }
    }
    if (clients.openWindow){
      await clients.openWindow(url);
    }
  })());
});
"""

HTML_INDEX = HTML_INDEX.replace("__DAMAGE_TYPE_OPTIONS__", DAMAGE_TYPE_OPTIONS)

# ----------------------------- LAN plumbing -----------------------------

@dataclass
class LanConfig:
    host: str = "0.0.0.0"
    port: int = 8787
    vapid_public_key: Optional[str] = None
    vapid_private_key: Optional[str] = None
    vapid_subject: str = "mailto:dm@example.com"
    allowlist: List[str] = field(default_factory=list)
    denylist: List[str] = field(default_factory=list)
    access_file: Optional[str] = None
    admin_password: Optional[str] = None

    def __post_init__(self) -> None:
        env_public = os.getenv("INITTRACKER_VAPID_PUBLIC_KEY")
        env_private = os.getenv("INITTRACKER_VAPID_PRIVATE_KEY")
        env_subject = os.getenv("INITTRACKER_VAPID_SUBJECT")
        env_allowlist = os.getenv("INITTRACKER_LAN_ALLOWLIST")
        env_denylist = os.getenv("INITTRACKER_LAN_DENYLIST")
        env_access_file = os.getenv("INITTRACKER_LAN_ACCESS_FILE")
        env_admin_password = os.getenv("INITTRACKER_ADMIN_PASSWORD")
        if env_public:
            self.vapid_public_key = env_public.strip()
        if env_private:
            self.vapid_private_key = env_private.strip()
        if env_subject:
            self.vapid_subject = env_subject.strip()
        if env_access_file:
            self.access_file = env_access_file.strip()
        file_config = self._load_access_file(self.access_file)
        if file_config:
            self.allowlist.extend(file_config.get("allowlist", []))
            self.denylist.extend(file_config.get("denylist", []))
            file_admin_password = str(file_config.get("admin_password") or "").strip()
            if file_admin_password:
                self.admin_password = file_admin_password
        if env_admin_password:
            self.admin_password = env_admin_password.strip()
        self.allowlist.extend(self._parse_access_entries(env_allowlist))
        self.denylist.extend(self._parse_access_entries(env_denylist))
        self.allowlist = self._normalize_access_entries(self.allowlist)
        self.denylist = self._normalize_access_entries(self.denylist)

    @staticmethod
    def _normalize_access_entries(entries: List[str]) -> List[str]:
        seen = set()
        normalized: List[str] = []
        for entry in entries:
            cleaned = str(entry or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    @staticmethod
    def _parse_access_entries(value: Optional[str]) -> List[str]:
        if not value:
            return []
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") or raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [str(entry).strip() for entry in parsed if str(entry).strip()]
        parts = re.split(r"[,\s]+", raw)
        return [part for part in (p.strip() for p in parts) if part]

    @staticmethod
    def _load_access_file(path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {}
        file_path = Path(path)
        if not file_path.exists():
            return {}
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return {}
        parsed: Any = None
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = None
        if parsed is None:
            yaml_spec = importlib.util.find_spec("yaml")
            if yaml_spec is not None:
                yaml = importlib.import_module("yaml")
                try:
                    parsed = yaml.safe_load(content)
                except Exception:
                    parsed = None
        if isinstance(parsed, list):
            return {"allowlist": [str(entry).strip() for entry in parsed if str(entry).strip()]}
        if isinstance(parsed, dict):
            allowlist = parsed.get("allowlist", []) if isinstance(parsed.get("allowlist", []), list) else []
            denylist = parsed.get("denylist", []) if isinstance(parsed.get("denylist", []), list) else []
            admin_password = parsed.get("admin_password")
            return {
                "allowlist": [str(entry).strip() for entry in allowlist if str(entry).strip()],
                "denylist": [str(entry).strip() for entry in denylist if str(entry).strip()],
                "admin_password": admin_password,
            }
        return {}


@dataclass
class MonsterSpec:
    filename: str
    name: str
    mtype: str
    cr: Optional[float]
    hp: Optional[int]
    speed: Optional[int]
    swim_speed: Optional[int]
    dex: Optional[int]
    init_mod: Optional[int]
    saving_throws: Dict[str, int]
    ability_mods: Dict[str, int]
    raw_data: Dict[str, Any]


@dataclass
class PlayerProfile:
    name: str
    format_version: int = 0
    identity: Dict[str, Any] = field(default_factory=dict)
    leveling: Dict[str, Any] = field(default_factory=dict)
    abilities: Dict[str, Any] = field(default_factory=dict)
    defenses: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    spellcasting: Dict[str, Any] = field(default_factory=dict)
    inventory: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "format_version": self.format_version,
            "identity": dict(self.identity),
            "leveling": dict(self.leveling),
            "abilities": dict(self.abilities),
            "defenses": dict(self.defenses),
            "resources": dict(self.resources),
            "spellcasting": dict(self.spellcasting),
            "inventory": dict(self.inventory),
        }


class LanController:
    """Runs a FastAPI+WebSocket server in a background thread and bridges actions into the Tk thread."""

    def __init__(self, app: "InitiativeTracker") -> None:
        self.app = app
        self.cfg = LanConfig()
        self._server_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._uvicorn_server = None
        self._admin_password_hash: Optional[bytes] = None
        self._admin_password_salt: Optional[bytes] = None
        self._admin_tokens: Dict[str, float] = {}
        self._admin_token_ttl_seconds: int = 15 * 60

        self._clients_lock = threading.Lock()
        self._clients: Dict[int, Any] = {}  # id(websocket) -> websocket
        self._clients_meta: Dict[int, Dict[str, Any]] = {}  # id(websocket) -> {host,port,ua,connected_at}
        self._client_hosts: Dict[int, str] = {}  # id(websocket) -> host
        self._claims: Dict[int, int] = {}   # id(websocket) -> cid
        self._cid_to_ws: Dict[int, int] = {}  # cid -> id(websocket) (1 owner at a time)
        self._cid_to_host: Dict[int, str] = {}  # cid -> host (active claim)
        self._host_assignments: Dict[str, int] = self._load_host_assignments()  # host -> cid (persistent)
        self._yaml_host_assignments: Dict[str, Dict[str, Any]] = {}
        self._host_presets: Dict[str, Dict[str, Any]] = {}
        self._cid_push_subscriptions: Dict[int, List[Dict[str, Any]]] = {}

        self._actions: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._last_state_json: Optional[str] = None
        self._polling: bool = False
        self._grid_version: int = 0
        self._grid_pending: Dict[int, Tuple[int, float]] = {}
        self._grid_resend_seconds: float = 1.5
        self._grid_last_sent: Optional[Tuple[Optional[int], Optional[int]]] = None
        self._ko_round_num: Optional[int] = None
        self._ko_played: bool = False
        self._cached_snapshot: Dict[str, Any] = {
            "grid": None,
            "obstacles": [],
            "units": [],
            "active_cid": None,
            "round_num": 0,
        }
        self._cached_pcs: List[Dict[str, Any]] = []
        self._init_admin_auth()

    # ---------- Tk thread API ----------

    def _resolve_reverse_dns(self, host: str) -> Optional[str]:
        host = str(host or "").strip()
        if not host:
            return None
        try:
            resolved, _, _ = socket.gethostbyaddr(host)
        except Exception:
            return None
        resolved = str(resolved or "").strip()
        return resolved or None

    def _host_matches_entry(self, host: str, entry: str) -> bool:
        host = str(host or "").strip()
        entry = str(entry or "").strip()
        if not host or not entry:
            return False
        if entry == "*":
            return True
        if "*" in entry:
            return fnmatch.fnmatch(host, entry)
        host_ip: Optional[ipaddress._BaseAddress]
        try:
            host_ip = ipaddress.ip_address(host)
        except ValueError:
            host_ip = None
        if host_ip is not None:
            try:
                network = ipaddress.ip_network(entry, strict=False)
                return host_ip in network
            except ValueError:
                pass
        return host == entry

    def _is_host_allowed(self, host: str) -> bool:
        host = str(host or "").strip()
        if not host:
            return False if self.cfg.allowlist else True
        for entry in self.cfg.denylist:
            if self._host_matches_entry(host, entry):
                return False
        if not self.cfg.allowlist:
            return True
        return any(self._host_matches_entry(host, entry) for entry in self.cfg.allowlist)

    def _init_admin_auth(self) -> None:
        password = str(self.cfg.admin_password or "").strip()
        if not password:
            return
        salt = os.urandom(16)
        self._admin_password_salt = salt
        self._admin_password_hash = self._derive_admin_password_hash(password, salt)
        self.cfg.admin_password = None

    @staticmethod
    def _derive_admin_password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)

    def _admin_password_matches(self, password: str) -> bool:
        if not self._admin_password_hash or not self._admin_password_salt:
            return False
        candidate = self._derive_admin_password_hash(password, self._admin_password_salt)
        return hmac.compare_digest(candidate, self._admin_password_hash)

    def _issue_admin_token(self) -> str:
        token = secrets.token_urlsafe(32)
        self._admin_tokens[token] = time.time() + float(self._admin_token_ttl_seconds)
        return token

    def _is_admin_token_valid(self, token: str) -> bool:
        token = str(token or "").strip()
        if not token:
            return False
        expires = self._admin_tokens.get(token)
        if not expires:
            return False
        now = time.time()
        if expires <= now:
            self._admin_tokens.pop(token, None)
            return False
        return True

    def _require_admin(self, request: "Request") -> None:
        from fastapi import HTTPException

        if not self._admin_password_hash:
            raise HTTPException(status_code=403, detail="Admin password is not configured.")
        header = request.headers.get("authorization", "")
        token = ""
        if header.lower().startswith("bearer "):
            token = header.split(" ", 1)[1].strip()
        if not self._is_admin_token_valid(token):
            raise HTTPException(status_code=401, detail="Unauthorized.")

    def admin_disconnect_session(self, ws_id: int, reason: str = "Disconnected by the DM.") -> None:
        if not self._loop:
            return
        coro = self._disconnect_session_async(int(ws_id), reason)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    @staticmethod
    def _normalize_push_subscription(subscription: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(subscription, dict):
            return None
        endpoint = str(subscription.get("endpoint", "") or "").strip()
        keys = subscription.get("keys")
        if not endpoint or not isinstance(keys, dict):
            return None
        p256dh = str(keys.get("p256dh", "") or "").strip()
        auth = str(keys.get("auth", "") or "").strip()
        if not p256dh or not auth:
            return None
        return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}

    def _save_push_subscription(self, cid: int, subscription: Dict[str, Any]) -> bool:
        sub = self._normalize_push_subscription(subscription)
        if not sub:
            return False
        with self._clients_lock:
            existing = self._cid_push_subscriptions.setdefault(int(cid), [])
            for entry in existing:
                if entry.get("endpoint") == sub["endpoint"]:
                    entry["keys"] = sub["keys"]
                    return True
            existing.append(sub)
        return True

    def _subscriptions_for_cid(self, cid: int) -> List[Dict[str, Any]]:
        with self._clients_lock:
            subs = self._cid_push_subscriptions.get(int(cid), [])
            return [dict(entry) for entry in subs]

    def _remove_push_subscription(self, cid: int, endpoint: str) -> None:
        endpoint = str(endpoint).strip()
        if not endpoint:
            return
        with self._clients_lock:
            subs = self._cid_push_subscriptions.get(int(cid), [])
            self._cid_push_subscriptions[int(cid)] = [
                entry for entry in subs if str(entry.get("endpoint", "")) != endpoint
            ]

    def _host_assignments_path(self) -> Path:
        return _ensure_logs_dir() / "lan_assignments.json"

    def _load_host_assignments(self) -> Dict[str, int]:
        data = _read_index_file(self._host_assignments_path())
        raw = data.get("assignments") if isinstance(data, dict) else None
        assignments: Dict[str, int] = {}
        if isinstance(raw, dict):
            for host, cid in raw.items():
                key = str(host or "").strip()
                if not key:
                    continue
                try:
                    cid_int = int(cid)
                except Exception:
                    continue
                assignments[key] = cid_int
        return assignments

    def _save_host_assignments(self) -> None:
        payload = {"version": 1, "assignments": dict(self._host_assignments)}
        _write_index_file(self._host_assignments_path(), payload)

    def _set_host_assignment(self, host: str, cid: Optional[int]) -> None:
        host = str(host or "").strip()
        if not host:
            return
        with self._clients_lock:
            if cid is None:
                self._host_assignments.pop(host, None)
            else:
                self._host_assignments[host] = int(cid)
        self._save_host_assignments()

    def _assigned_cid_for_host(self, host: str) -> Optional[int]:
        host = str(host or "").strip()
        if not host:
            return None
        with self._clients_lock:
            cid = self._host_assignments.get(host)
        return int(cid) if isinstance(cid, int) else None

    def _sync_yaml_host_assignments(self, profiles: Dict[str, Dict[str, Any]]) -> None:
        if not isinstance(profiles, dict):
            profiles = {}
        name_to_cid: Dict[str, int] = {}
        pcs = list(self._cached_pcs)
        if not pcs:
            try:
                pcs = list(
                    self.app._lan_pcs() if hasattr(self.app, "_lan_pcs") else self.app._lan_claimable()
                )
            except Exception:
                pcs = []
        for pc in pcs:
            if not isinstance(pc, dict):
                continue
            name = str(pc.get("name") or "").strip()
            cid = pc.get("cid")
            if name and isinstance(cid, int):
                name_to_cid[name.lower()] = int(cid)

        host_map: Dict[str, Dict[str, Any]] = {}
        conflicts: List[Tuple[str, str, str]] = []
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            identity = profile.get("identity")
            if not isinstance(identity, dict):
                continue
            host = str(identity.get("ip") or "").strip()
            if not host:
                continue
            if host in host_map:
                conflicts.append((host, host_map[host]["name"], str(name)))
                continue
            cid = name_to_cid.get(str(name).lower())
            host_map[host] = {"name": str(name), "cid": cid}

        with self._clients_lock:
            self._yaml_host_assignments = host_map

        for host, left, right in conflicts:
            self.app._oplog(
                f"LAN YAML assignment conflict: {host} is listed for {left} and {right}.",
                level="warning",
            )

        for host, info in host_map.items():
            cid = info.get("cid")
            if cid is None:
                self.app._oplog(
                    f"LAN YAML assignment skipped: {info.get('name')} has host {host} but no matching cid.",
                    level="warning",
                )
                continue
            existing = self._assigned_cid_for_host(host)
            if existing is not None and existing != cid:
                self.app._oplog(
                    f"LAN YAML assignment for {host} -> {info.get('name')} (cid {cid})"
                    f" conflicts with existing assignment cid {existing}.",
                    level="warning",
                )
                continue
            if existing == cid:
                continue
            self._set_host_assignment(host, int(cid))

    def start(self, quiet: bool = False) -> None:
        if self._server_thread and self._server_thread.is_alive():
            self.app._oplog("LAN server already runnin'.")
            return

        # Lazy imports so the base app still works without these deps installed.
        try:
            from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
            from fastapi.responses import HTMLResponse, Response
            from fastapi.staticfiles import StaticFiles
            import uvicorn
            # Expose these in module globals so FastAPI's type resolver can see 'em even from nested defs.
            globals()["WebSocket"] = WebSocket
            globals()["WebSocketDisconnect"] = WebSocketDisconnect
            globals()["Request"] = Request
        except Exception as e:
            if quiet:
                self.app._oplog(f"LAN server needs fastapi + uvicorn (missing): {e}")
                return
            messagebox.showerror(
                "LAN Server missing deps",
                f"Arrr, LAN server needs fastapi + uvicorn.\n\nError: {e}",
            )
            return

        app = FastAPI()
        assets_dir = Path(__file__).parent / "assets"
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        for asset_name in ("alert.wav", "ko.wav"):
            if not (assets_dir / asset_name).exists():
                self.app._oplog(
                    f"LAN assets missing {asset_name} at {assets_dir / asset_name} (check assets_dir path).",
                    level="warning",
                )

        @app.get("/")
        async def index():
            push_key = self.cfg.vapid_public_key
            push_key_value = json.dumps(push_key) if push_key else "undefined"
            return HTMLResponse(HTML_INDEX.replace("__PUSH_PUBLIC_KEY__", push_key_value))

        @app.get("/sw.js")
        async def service_worker():
            return Response(SERVICE_WORKER_JS, media_type="application/javascript")

        @app.post("/api/push/subscribe")
        async def push_subscribe(payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            subscription = payload.get("subscription")
            if subscription is None and "endpoint" in payload:
                subscription = payload
            if not isinstance(subscription, dict):
                raise HTTPException(status_code=400, detail="Invalid subscription.")
            player_id = payload.get("playerId")
            try:
                player_id = int(player_id)
            except Exception:
                player_id = None
            if player_id is None:
                raise HTTPException(status_code=404, detail="Unable to resolve player.")
            ok = self._save_push_subscription(player_id, subscription)
            if not ok:
                raise HTTPException(status_code=400, detail="Invalid subscription payload.")
            return {"ok": True, "playerId": player_id}

        @app.post("/api/admin/login")
        async def admin_login(payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            password = str(payload.get("password") or "")
            if not password:
                raise HTTPException(status_code=400, detail="Missing password.")
            if not self._admin_password_hash:
                raise HTTPException(status_code=403, detail="Admin password is not configured.")
            if not self._admin_password_matches(password):
                raise HTTPException(status_code=401, detail="Invalid password.")
            token = self._issue_admin_token()
            return {"token": token, "expires_in": self._admin_token_ttl_seconds}

        @app.get("/api/admin/sessions")
        async def admin_sessions(request: Request):
            self._require_admin(request)
            return self._admin_sessions_payload()

        @app.post("/api/admin/assign_ip")
        async def admin_assign_ip(request: Request, payload: Dict[str, Any] = Body(...)):
            self._require_admin(request)
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            host = str(payload.get("ip") or "").strip()
            if not host:
                raise HTTPException(status_code=400, detail="Missing IP address.")
            cid_raw = payload.get("cid")
            cid: Optional[int]
            if cid_raw is None or cid_raw == "":
                cid = None
            else:
                try:
                    cid = int(cid_raw)
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid character id.")
                if not self._pc_exists(cid):
                    raise HTTPException(status_code=404, detail="Unknown character id.")
            self._set_host_assignment(host, cid)
            await self._apply_host_assignment_async(host, cid, note="Assigned by the DM.")
            return {"ok": True, "ip": host, "cid": cid}

        @app.post("/api/players/{name}/spells")
        async def update_player_spells(name: str, payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            player_name = str(name or "").strip()
            if not player_name:
                raise HTTPException(status_code=400, detail="Missing player name.")
            try:
                normalized = self.app._save_player_spell_config(player_name, payload)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except RuntimeError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            except Exception:
                raise HTTPException(status_code=500, detail="Failed to save player spells.")
            return {"ok": True, "player": {"name": player_name, **normalized}}

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            try:
                host = getattr(getattr(ws, "client", None), "host", "?")
                port = getattr(getattr(ws, "client", None), "port", "")
                ua = ""
                try:
                    ua = ws.headers.get("user-agent", "")
                except Exception:
                    ua = ""
                connected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                host, port, ua, connected_at = "?", "", "", ""
            if not self._is_host_allowed(host):
                await ws.accept()
                await ws.close(code=1008, reason="Unauthorized IP.")
                self.app._oplog(f"LAN session rejected host={host}:{port} ua={ua}", level="warning")
                return

            await ws.accept()
            ws_id = id(ws)
            reverse_dns = self._resolve_reverse_dns(host)

            with self._clients_lock:
                self._clients[ws_id] = ws
                self._clients_meta[ws_id] = {
                    "host": host,
                    "port": port,
                    "ua": ua,
                    "connected_at": connected_at,
                    "last_seen": connected_at,
                    "reverse_dns": reverse_dns,
                }
                self._client_hosts[ws_id] = host
            self.app._oplog(f"LAN session connected ws_id={ws_id} host={host}:{port} ua={ua}")
            try:
                await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                # Immediately send snapshot + claimable list
                await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
                await self._auto_assign_host(ws_id, host)
                while True:
                    raw = await ws.receive_text()
                    try:
                        with self._clients_lock:
                            if ws_id in self._clients_meta:
                                self._clients_meta[ws_id]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    typ = str(msg.get("type") or "")
                    if typ == "save_preset":
                        preset = msg.get("preset")
                        if preset is not None and not isinstance(preset, dict):
                            await ws.send_text(json.dumps({"type": "preset_error", "error": "Invalid preset payload."}))
                            continue
                        host_key = self._client_hosts.get(ws_id) or f"ws:{ws_id}"
                        if preset is None:
                            self._host_presets.pop(host_key, None)
                        else:
                            self._host_presets[host_key] = preset
                        await ws.send_text(json.dumps({"type": "preset_saved"}))
                    elif typ == "load_preset":
                        host_key = self._client_hosts.get(ws_id) or f"ws:{ws_id}"
                        preset = self._host_presets.get(host_key)
                        await ws.send_text(json.dumps({"type": "preset", "preset": preset}))
                    elif typ == "grid_request":
                        await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                    elif typ == "grid_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._grid_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._grid_pending.pop(ws_id, None)
                    elif typ == "log_request":
                        try:
                            lines = self.app._lan_battle_log_lines()
                        except Exception:
                            lines = []
                        await ws.send_text(json.dumps({"type": "battle_log", "lines": lines}))
                    elif typ in (
                        "move",
                        "dash",
                        "end_turn",
                        "use_action",
                        "use_bonus_action",
                        "set_color",
                        "reset_turn",
                        "cast_aoe",
                        "aoe_move",
                        "aoe_remove",
                    ):
                        # enqueue for Tk thread
                        with self._clients_lock:
                            claimed_cid = self._claims.get(ws_id)
                        msg["_claimed_cid"] = claimed_cid
                        msg["_ws_id"] = ws_id
                        self._actions.put(msg)
                    elif typ == "toast":
                        # Client wants a toast? ignore
                        pass
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
            finally:
                with self._clients_lock:
                    self._clients.pop(ws_id, None)
                    self._clients_meta.pop(ws_id, None)
                    self._client_hosts.pop(ws_id, None)
                    old = self._claims.pop(ws_id, None)
                    if old is not None:
                        self._cid_to_ws.pop(int(old), None)
                        self._cid_to_host.pop(int(old), None)
                    self._grid_pending.pop(ws_id, None)
                if old is not None:
                    name = self._pc_name_for(int(old))
                    self.app._oplog(f"LAN session disconnected ws_id={ws_id} (claimed {name})")
                else:
                    self.app._oplog(f"LAN session disconnected ws_id={ws_id}")

        # Start uvicorn server in a thread (with its own event loop).
        try:
            self._cached_snapshot = self.app._lan_snapshot()
            self._cached_pcs = list(
                self.app._lan_pcs() if hasattr(self.app, "_lan_pcs") else self.app._lan_claimable()
            )
        except Exception:
            pass
        try:
            profiles = self.app._player_profiles_payload() if hasattr(self.app, "_player_profiles_payload") else {}
            self._sync_yaml_host_assignments(profiles)
        except Exception:
            pass

        def run_server():
            # Create fresh loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            config = uvicorn.Config(app, host=self.cfg.host, port=self.cfg.port, log_level="warning", access_log=False)
            server = uvicorn.Server(config)
            self._uvicorn_server = server
            loop.run_until_complete(server.serve())

        self._server_thread = threading.Thread(target=run_server, name="InitTrackerLAN", daemon=True)
        self._server_thread.start()

        # Start Tk polling for actions and state broadcasts
        if not self._polling:
            self._polling = True
            self.app.after(60, self._tick)

        url = self._best_lan_url()
        self.app._oplog(f"LAN server hoisted at {url}  (open on yer phone, matey)")

    def stop(self) -> None:
        # Ask uvicorn to stop
        if self._uvicorn_server is not None:
            try:
                self._uvicorn_server.should_exit = True
            except Exception:
                pass
        self.app._oplog("LAN server be lowerin' sails (stoppin').")

    def notify_turn_start(self, cid: int, round_num: int, turn_num: int) -> None:
        """Send push notification for the newly active combatant (if subscribed)."""
        try:
            cid = int(cid)
        except Exception:
            return
        worker = threading.Thread(
            target=self._dispatch_turn_notification,
            args=(cid, int(round_num), int(turn_num)),
            daemon=True,
        )
        worker.start()

    def _dispatch_turn_notification(self, cid: int, round_num: int, turn_num: int) -> None:
        subscriptions = self._subscriptions_for_cid(cid)
        if not subscriptions:
            return
        name = self._pc_name_for(cid)
        payload = {
            "title": "Your turn!",
            "body": f"{name} is up (round {round_num}, turn {turn_num}).",
            "url": "/",
        }
        invalid = self._send_push_notifications(subscriptions, payload)
        for endpoint in invalid:
            self._remove_push_subscription(cid, endpoint)

    def _send_push_notifications(self, subscriptions: List[Dict[str, Any]], payload: Dict[str, Any]) -> List[str]:
        if not subscriptions:
            return []
        try:
            from pywebpush import webpush, WebPushException  # type: ignore
        except Exception as exc:
            self.app._oplog(f"Push notifications unavailable (pywebpush missing): {exc}", level="warning")
            return []
        if not self.cfg.vapid_private_key or not self.cfg.vapid_public_key:
            self.app._oplog(
                "Push notifications skipped (missing VAPID keys). Set INITTRACKER_VAPID_PUBLIC_KEY/PRIVATE_KEY.",
                level="warning",
            )
            return []
        invalid: List[str] = []
        data = json.dumps(payload)
        for sub in subscriptions:
            endpoint = str(sub.get("endpoint", "") or "").strip()
            keys = sub.get("keys") if isinstance(sub, dict) else None
            if not endpoint or not isinstance(keys, dict):
                continue
            p256dh = str(keys.get("p256dh", "") or "").strip()
            auth = str(keys.get("auth", "") or "").strip()
            if not p256dh or not auth:
                continue
            subscription_info = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
            try:
                webpush(
                    subscription_info,
                    data=data,
                    vapid_private_key=self.cfg.vapid_private_key,
                    vapid_claims={"sub": self.cfg.vapid_subject},
                )
            except WebPushException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in (404, 410):
                    invalid.append(endpoint)
                else:
                    self.app._oplog(f"Push send failed for {endpoint}: {exc}", level="warning")
            except Exception as exc:
                self.app._oplog(f"Push send failed for {endpoint}: {exc}", level="warning")
        return invalid

    async def _auto_assign_host(self, ws_id: int, host: str) -> None:
        host = str(host or "").strip()
        if not host:
            return
        preferred = self._assigned_cid_for_host(host)
        if preferred is None:
            return
        if not self._pc_exists(preferred):
            return
        await self._claim_ws_async(ws_id, int(preferred), note="Assigned.", allow_override=True)

    # ---------- Sessions / Claims (Tk thread safe) ----------

    def sessions_snapshot(self) -> List[Dict[str, Any]]:
        """Return a best-effort list of connected clients + who they claim."""
        out: List[Dict[str, Any]] = []
        with self._clients_lock:
            for ws_id, ws in list(self._clients.items()):
                meta = dict(self._clients_meta.get(ws_id, {}))
                cid = self._claims.get(ws_id)
                host = meta.get("host", "?")
                reverse_dns = meta.get("reverse_dns")
                if reverse_dns is None and host not in ("", "?"):
                    reverse_dns = self._resolve_reverse_dns(host)
                    if ws_id in self._clients_meta:
                        self._clients_meta[ws_id]["reverse_dns"] = reverse_dns
                assigned_cid = self._host_assignments.get(host)
                assigned_name = self._pc_name_for(int(assigned_cid)) if isinstance(assigned_cid, int) else None
                out.append(
                    {
                        "ws_id": int(ws_id),
                        "cid": int(cid) if cid is not None else None,
                        "host": host,
                        "port": meta.get("port", ""),
                        "user_agent": meta.get("ua", ""),
                        "connected_at": meta.get("connected_at", ""),
                        "last_seen": meta.get("last_seen", meta.get("connected_at", "")),
                        "reverse_dns": reverse_dns,
                        "assigned_cid": int(assigned_cid) if assigned_cid is not None else None,
                        "assigned_name": assigned_name,
                        "status": "connected",
                    }
                )
        out.sort(key=lambda s: int(s.get("ws_id", 0)))
        return out

    def _pc_exists(self, cid: int) -> bool:
        try:
            cid = int(cid)
        except Exception:
            return False
        pcs = {int(p.get("cid")) for p in self._cached_pcs if isinstance(p.get("cid"), int)}
        return cid in pcs

    def _admin_sessions_payload(self) -> Dict[str, Any]:
        sessions = self.sessions_snapshot()
        connected_hosts = {str(s.get("host")) for s in sessions if str(s.get("host"))}
        offline_entries: List[Dict[str, Any]] = []
        with self._clients_lock:
            assignments = dict(self._host_assignments)
            yaml_assignments = dict(self._yaml_host_assignments)
        for host, cid in assignments.items():
            if host in connected_hosts:
                continue
            reverse_dns = self._resolve_reverse_dns(host)
            yaml_entry = yaml_assignments.get(host, {})
            offline_entries.append(
                {
                    "ws_id": None,
                    "cid": None,
                    "host": host,
                    "ip": host,
                    "reverse_dns": reverse_dns,
                    "assigned_cid": int(cid),
                    "assigned_name": self._pc_name_for(int(cid)),
                    "yaml_assigned_cid": yaml_entry.get("cid"),
                    "yaml_assigned_name": yaml_entry.get("name"),
                    "status": "offline",
                    "last_seen": "",
                }
            )
        all_sessions = sessions + offline_entries
        for entry in all_sessions:
            if "ip" not in entry:
                entry["ip"] = entry.get("host")
            host = str(entry.get("host") or entry.get("ip") or "").strip()
            yaml_entry = yaml_assignments.get(host, {})
            if yaml_entry:
                entry["yaml_assigned_cid"] = yaml_entry.get("cid")
                entry["yaml_assigned_name"] = yaml_entry.get("name")
        all_sessions.sort(key=lambda s: str(s.get("ip", "")))
        pcs_payload = [
            {"cid": int(p.get("cid")), "name": str(p.get("name", ""))}
            for p in self._cached_pcs
            if isinstance(p.get("cid"), int)
        ]
        pcs_payload.sort(key=lambda p: str(p.get("name", "")).lower())
        yaml_payload = [
            {"host": host, "cid": entry.get("cid"), "name": entry.get("name")}
            for host, entry in sorted(yaml_assignments.items())
        ]
        return {"sessions": all_sessions, "pcs": pcs_payload, "yaml_assignments": yaml_payload}

    def admin_sessions_payload(self) -> Dict[str, Any]:
        """Return admin sessions payload for both web and DM-side tooling."""
        return self._admin_sessions_payload()

    def assign_host(self, host: str, cid: Optional[int], note: str = "Assigned by the DM.") -> None:
        """Assign a PC to all sessions from a host (or clear if cid is None)."""
        host = str(host or "").strip()
        if not host:
            return
        self._set_host_assignment(host, cid)
        if not self._loop:
            return
        coro = self._apply_host_assignment_async(host, cid, note=note)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _apply_host_assignment_async(self, host: str, cid: Optional[int], note: str) -> None:
        host = str(host or "").strip()
        if not host:
            return
        with self._clients_lock:
            ws_ids = [ws_id for ws_id, ws_host in self._client_hosts.items() if ws_host == host]
        if not ws_ids:
            return
        if cid is None:
            for ws_id in ws_ids:
                await self._unclaim_ws_async(ws_id, reason=note, clear_ownership=False)
            return
        for ws_id in ws_ids:
            await self._claim_ws_async(ws_id, int(cid), note=note, allow_override=True)

    def assign_session(self, ws_id: int, cid: Optional[int], note: str = "Assigned by the DM.") -> None:
        """DM assigns a PC to a session (or clears assignment if cid is None)."""
        if not self._loop:
            return
        coro = self._assign_session_async(int(ws_id), cid, note)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _assign_session_async(self, ws_id: int, cid: Optional[int], note: str) -> None:
        with self._clients_lock:
            ws = self._clients.get(ws_id)
            host = self._client_hosts.get(ws_id)
        if not ws:
            return
        if host:
            self._set_host_assignment(host, cid)
        if cid is None:
            # unclaim
            await self._unclaim_ws_async(ws_id, reason=note, clear_ownership=False)
            return
        await self._claim_ws_async(ws_id, int(cid), note=note, allow_override=True)

    async def _disconnect_session_async(self, ws_id: int, reason: str) -> None:
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        try:
            await self._unclaim_ws_async(ws_id, reason=reason, clear_ownership=False)
        except Exception:
            pass
        try:
            await ws.close(code=1000)
        except Exception:
            pass
        try:
            await self._broadcast_state_async(self._cached_snapshot)
        except Exception:
            pass

    def _tick(self) -> None:
        """Runs on Tk thread: process actions and broadcast state when changed."""
        # 1) process queued actions from clients
        processed_any = False
        while True:
            try:
                msg = self._actions.get_nowait()
            except queue.Empty:
                break
            processed_any = True
            self.app._lan_apply_action(msg)

        # 2) broadcast snapshot if changed (polling-based, avoids wiring every hook)
        snap = self.app._lan_snapshot()
        self._cached_snapshot = snap
        try:
            self._cached_pcs = list(
                self.app._lan_pcs() if hasattr(self.app, "_lan_pcs") else self.app._lan_claimable()
            )
        except Exception:
            self._cached_pcs = []
        grid = snap.get("grid", {}) if isinstance(snap, dict) else {}
        if isinstance(grid, dict):
            cols = grid.get("cols")
            rows = grid.get("rows")
            if self._grid_last_sent != (cols, rows):
                self._grid_version += 1
                self._grid_last_sent = (cols, rows)
                self._broadcast_grid_update(grid)
        self._resend_grid_updates()
        snap_json = json.dumps(snap, sort_keys=True, separators=(",", ":"))
        if snap_json != self._last_state_json:
            self._last_state_json = snap_json
            self._broadcast_state(snap)

        # 3) continue polling
        if self._polling:
            self.app.after(120, self._tick)

    def _pcs_payload(self) -> List[Dict[str, Any]]:
        pcs = list(self._cached_pcs)
        with self._clients_lock:
            cid_to_host = dict(self._cid_to_host)
        profiles = self.app._player_profiles_payload() if hasattr(self.app, "_player_profiles_payload") else {}
        out: List[Dict[str, Any]] = []
        for p in pcs:
            pp = dict(p)
            cid = int(pp.get("cid", -1))
            pp["claimed_by"] = cid_to_host.get(cid)
            name = str(pp.get("name") or "")
            if name and isinstance(profiles, dict):
                profile = profiles.get(name)
                if isinstance(profile, dict):
                    pp["player_profile"] = profile
            out.append(pp)
        out.sort(key=lambda d: str(d.get("name", "")))
        return out

    def _can_auto_claim(self, cid: int) -> bool:
        try:
            cid = int(cid)
        except Exception:
            return False
        pcs = {int(p.get("cid")) for p in self._cached_pcs if isinstance(p.get("cid"), int)}
        if cid not in pcs:
            return False
        with self._clients_lock:
            return self._cid_to_ws.get(cid) is None

    # ---------- Server-thread safe broadcast ----------

    def _broadcast_state(self, snap: Dict[str, Any]) -> None:
        if not self._loop:
            return
        coro = self._broadcast_state_async(snap)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _broadcast_state_async(self, snap: Dict[str, Any]) -> None:
        payload = json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()})
        to_drop: List[int] = []
        with self._clients_lock:
            items = list(self._clients.items())
        for ws_id, ws in items:
            try:
                await ws.send_text(payload)
            except Exception:
                to_drop.append(ws_id)
        if to_drop:
            with self._clients_lock:
                for ws_id in to_drop:
                    # cleanup drop
                    old_cid = self._claims.pop(ws_id, None)
                    if old_cid is not None:
                        self._cid_to_ws.pop(int(old_cid), None)
                        self._cid_to_host.pop(int(old_cid), None)
                    self._clients.pop(ws_id, None)
                    self._clients_meta.pop(ws_id, None)
                    self._client_hosts.pop(ws_id, None)

    def _broadcast_grid_update(self, grid: Dict[str, Any]) -> None:
        if not self._loop:
            return
        coro = self._broadcast_grid_update_async(grid)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _broadcast_grid_update_async(self, grid: Dict[str, Any]) -> None:
        payload = json.dumps({"type": "grid_update", "grid": grid, "version": self._grid_version})
        now = time.time()
        with self._clients_lock:
            items = list(self._clients.items())
        for ws_id, ws in items:
            try:
                await ws.send_text(payload)
                with self._clients_lock:
                    self._grid_pending[ws_id] = (self._grid_version, now)
            except Exception:
                with self._clients_lock:
                    self._grid_pending.pop(ws_id, None)

    async def _send_grid_update_async(self, ws_id: int, grid: Dict[str, Any]) -> None:
        payload = json.dumps({"type": "grid_update", "grid": grid, "version": self._grid_version})
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        try:
            await ws.send_text(payload)
            with self._clients_lock:
                self._grid_pending[ws_id] = (self._grid_version, time.time())
        except Exception:
            with self._clients_lock:
                self._grid_pending.pop(ws_id, None)

    def _resend_grid_updates(self) -> None:
        if not self._loop or not self._grid_pending:
            return
        now = time.time()
        with self._clients_lock:
            pending = list(self._grid_pending.items())
            clients = dict(self._clients)
        for ws_id, (ver, last_sent) in pending:
            if ver != self._grid_version:
                with self._clients_lock:
                    self._grid_pending.pop(ws_id, None)
                continue
            if now - last_sent < self._grid_resend_seconds:
                continue
            ws = clients.get(ws_id)
            if not ws:
                with self._clients_lock:
                    self._grid_pending.pop(ws_id, None)
                continue
            payload = {"type": "grid_update", "grid": self._cached_snapshot.get("grid", {}), "version": self._grid_version}
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(json.dumps(payload)), self._loop)
                with self._clients_lock:
                    self._grid_pending[ws_id] = (self._grid_version, now)
            except Exception:
                with self._clients_lock:
                    self._grid_pending.pop(ws_id, None)

    def toast(self, ws_id: Optional[int], text: str) -> None:
        """Send a small toast to one client (best effort)."""
        if ws_id is None or not self._loop:
            return
        coro = self._toast_async(ws_id, text)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    def play_ko(self, attacker_cid: Optional[int]) -> None:
        """Play a KO sound on the attacker's claimed LAN client (once per round)."""
        if not self._loop or attacker_cid is None:
            return
        try:
            attacker_cid = int(attacker_cid)
        except Exception:
            return
        round_num = int(getattr(self.app, "round_num", 0) or 0)
        if self._ko_round_num != round_num:
            self._ko_round_num = round_num
            self._ko_played = False
        if self._ko_played:
            return
        pc_cids = {int(p.get("cid")) for p in self._cached_pcs if isinstance(p.get("cid"), int)}
        if attacker_cid not in pc_cids:
            return
        with self._clients_lock:
            ws_id = self._cid_to_ws.get(attacker_cid)
        if ws_id is None:
            return
        self._ko_played = True
        coro = self._send_async(ws_id, {"type": "play_audio", "audio": "ko", "cid": attacker_cid})
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _toast_async(self, ws_id: int, text: str) -> None:
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        try:
            await ws.send_text(json.dumps({"type": "toast", "text": text}))
        except Exception:
            pass

    async def _send_async(self, ws_id: int, payload: Dict[str, Any]) -> None:
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            pass

    async def _unclaim_ws_async(
        self, ws_id: int, reason: str = "Unclaimed", clear_ownership: bool = False
    ) -> None:
        # Drop claim mapping
        with self._clients_lock:
            old = self._claims.pop(ws_id, None)
            if old is not None:
                self._cid_to_ws.pop(int(old), None)
                self._cid_to_host.pop(int(old), None)
        if old is not None:
            name = self._pc_name_for(int(old))
            self.app._oplog(f"LAN session ws_id={ws_id} unclaimed {name} ({reason})")
        await self._send_async(ws_id, {"type": "force_unclaim", "text": reason, "pcs": self._pcs_payload()})

    async def _claim_ws_async(
        self, ws_id: int, cid: int, note: str = "Claimed", allow_override: bool = False
    ) -> None:
        # Ensure cid is a PC
        pcs = {int(p.get("cid")): p for p in self._cached_pcs}
        if int(cid) not in pcs:
            await self._send_async(ws_id, {"type": "toast", "text": "That character ain't claimable, matey."})
            return

        # Steal/assign with single-owner logic
        steal_from: Optional[int] = None
        prev_owned: Optional[int] = None
        with self._clients_lock:
            host = self._client_hosts.get(ws_id, "")
            # if this ws had old claim, clear reverse map
            prev_owned = self._claims.get(ws_id)
            if prev_owned is not None:
                self._cid_to_ws.pop(int(prev_owned), None)
                if self._cid_to_host.get(int(prev_owned)) == host:
                    self._cid_to_host.pop(int(prev_owned), None)

            # if cid is owned, we'll steal
            steal_from = self._cid_to_ws.get(int(cid))
            if steal_from is not None and steal_from != ws_id:
                if not allow_override:
                    await self._send_async(ws_id, {"type": "toast", "text": "That character be claimed already."})
                    return
                self._claims.pop(steal_from, None)
            # assign
            self._claims[ws_id] = int(cid)
            self._cid_to_ws[int(cid)] = ws_id
            if host:
                self._cid_to_host[int(cid)] = host

        if steal_from is not None and steal_from != ws_id:
            await self._send_async(steal_from, {"type": "force_unclaim", "text": "Yer character got reassigned by the DM.", "pcs": self._pcs_payload()})

        await self._send_async(ws_id, {"type": "force_claim", "cid": int(cid), "text": note})
        name = self._pc_name_for(int(cid))
        self.app._oplog(f"LAN session ws_id={ws_id} claimed {name} ({note})")

    # ---------- helpers ----------

    def _best_lan_url(self) -> str:
        return f"http://{self.cfg.host}:{self.cfg.port}/"

    def _cached_snapshot_payload(self) -> Dict[str, Any]:
        snap = dict(self._cached_snapshot)
        units = snap.get("units")
        if isinstance(units, list):
            with self._clients_lock:
                cid_to_host = dict(self._cid_to_host)
            enriched = []
            for unit in units:
                if not isinstance(unit, dict):
                    enriched.append(unit)
                    continue
                copy_unit = dict(unit)
                try:
                    cid = int(copy_unit.get("cid", -1))
                except Exception:
                    cid = -1
                copy_unit["claimed_by"] = cid_to_host.get(cid)
                enriched.append(copy_unit)
            snap["units"] = enriched
        return snap

    def _pc_name_for(self, cid: int) -> str:
        for pc in self._cached_pcs:
            if int(pc.get("cid", -1)) == int(cid):
                name = pc.get("name")
                if name:
                    return str(name)
        return f"cid:{cid}"


# ----------------------------- Tracker -----------------------------

class InitiativeTracker(base.InitiativeTracker):
    """Tk tracker + LAN proof-of-concept server."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"DnD Initiative Tracker — v{APP_VERSION}")

        # Operations logger (terminal + ./logs/operations.log)
        self._ops_logger = _make_ops_logger()

        self._lan = LanController(self)
        self._install_lan_menu()

        # Monster library (YAML files in ./Monsters)
        self._monster_specs: List[MonsterSpec] = []
        self._monsters_by_name: Dict[str, MonsterSpec] = {}
        self._load_monsters_index()
        # Swap the Name entry for a monster dropdown + library button
        self.after(0, self._install_monster_dropdown_widget)

        # Spell preset cache (YAML files in ./Spells)
        self._spell_presets_cache: Optional[List[Dict[str, Any]]] = None
        self._spell_index_entries: Dict[str, Any] = {}
        self._spell_index_loaded = False
        self._spell_dir_notice: Optional[str] = None
        self._player_yaml_cache_by_path: Dict[Path, Optional[Dict[str, Any]]] = {}
        self._player_yaml_meta_by_path: Dict[Path, Dict[str, object]] = {}
        self._player_yaml_data_by_name: Dict[str, Dict[str, Any]] = {}
        self._player_yaml_name_map: Dict[str, Path] = {}

        # LAN state for when map window isn't open
        self._lan_grid_cols = 20
        self._lan_grid_rows = 20
        self._lan_positions: Dict[int, Tuple[int, int]] = {}  # cid -> (col,row)
        self._lan_obstacles: set[Tuple[int, int]] = set()
        self._lan_aoes: Dict[int, Dict[str, Any]] = {}
        self._lan_next_aoe_id = 1
        self._turn_snapshots: Dict[int, Dict[str, Any]] = {}

        # POC helpers: seed all Player Characters and start the LAN server automatically.
        if POC_AUTO_SEED_PCS:
            self._poc_seed_all_player_characters()
        # Start quietly (log on success; avoid popups if deps missing)
        if POC_AUTO_START_LAN:
            self.after(250, lambda: self._lan.start(quiet=True))

    # --------------------- Spell preset cache ---------------------

    def _spell_index_path(self) -> Path:
        return _ensure_logs_dir() / "spell_index.json"

    def _invalidate_spell_index_cache(self) -> None:
        self._spell_presets_cache = None
        self._spell_index_entries = {}
        self._spell_index_loaded = False

    def _load_spell_index_entries(self) -> Dict[str, Any]:
        if self._spell_index_loaded:
            return self._spell_index_entries
        index_data = _read_index_file(self._spell_index_path())
        entries = index_data.get("entries") if isinstance(index_data.get("entries"), dict) else {}
        self._spell_index_entries = entries if isinstance(entries, dict) else {}
        self._spell_index_loaded = True
        return self._spell_index_entries

    def _refresh_monsters_spells(self) -> None:
        self._invalidate_spell_index_cache()
        super()._refresh_monsters_spells()

    def _load_monsters_and_spells(self) -> None:
        self._load_monsters_index()
        self._spell_presets_payload()

    # --------------------- Logging split: battle vs operations ---------------------

    def _history_file_path(self) -> Path:
        """Battle log file path (used by base _log)."""
        logs = _ensure_logs_dir()
        return logs / "battle.log"

    def _oplog(self, text: str, level: str = "info") -> None:
        """Operations log: terminal + ./logs/operations.log (no UI)."""
        try:
            lg = getattr(self, "_ops_logger", None) or _make_ops_logger()
            fn = getattr(lg, level, lg.info)
            fn(str(text))
        except Exception:
            # fallback
            try:
                print(text)
            except Exception:
                pass

    def _lan_battle_log_lines(self, limit: int = 200) -> List[str]:
        path = self._history_file_path()
        try:
            if not path.exists():
                return []
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []
        if limit > 0:
            return lines[-limit:]
        return lines

    def _resolve_spells_dir(self) -> Optional[Path]:
        base_dir = Path.cwd()
        canonical = base_dir / "Spells"
        fallback = base_dir / "spells"
        if canonical.exists():
            return canonical
        if fallback.exists():
            notice = "Using fallback spell directory './spells/'. Prefer './Spells/'."
            if self._spell_dir_notice != notice:
                self._oplog(notice, "warning")
                self._spell_dir_notice = notice
            return fallback
        notice = f"No spell presets found. Expected './Spells/' under {base_dir}."
        if self._spell_dir_notice != notice:
            self._oplog(notice, "info")
            self._spell_dir_notice = notice
        return None

    def _open_starting_players_dialog(self) -> None:
        """Suppress the startup roster popup during LAN POC, but keep it available later."""
        if POC_AUTO_SEED_PCS:
            return
        try:
            super()._open_starting_players_dialog()
        except Exception:
            pass

    def _process_start_of_turn(self, c: Any) -> Tuple[bool, str, set[str]]:
        skip, msg, dec_skip = super()._process_start_of_turn(c)
        try:
            self._lan_record_turn_snapshot(int(getattr(c, "cid", -1)))
        except Exception:
            pass
        return skip, msg, dec_skip

    def _lan_current_position(self, cid: int) -> Optional[Tuple[int, int]]:
        mw = None
        try:
            mw = getattr(self, "_map_window", None)
            if mw is not None and not mw.winfo_exists():
                mw = None
        except Exception:
            mw = None
        if mw is not None:
            try:
                tok = getattr(mw, "unit_tokens", {}).get(cid)
                if tok:
                    return (int(tok.get("col")), int(tok.get("row")))
            except Exception:
                pass
        return self._lan_positions.get(cid)

    def _lan_record_turn_snapshot(self, cid: int) -> None:
        if cid not in self.combatants:
            return
        pos = self._lan_current_position(cid)
        if pos is None:
            return
        c = self.combatants[cid]
        self._turn_snapshots[cid] = {
            "col": int(pos[0]),
            "row": int(pos[1]),
            "move_remaining": int(getattr(c, "move_remaining", 0) or 0),
            "move_total": int(getattr(c, "move_total", 0) or 0),
            "action_remaining": int(getattr(c, "action_remaining", 0) or 0),
            "bonus_action_remaining": int(getattr(c, "bonus_action_remaining", 0) or 0),
        }

    def _lan_restore_turn_snapshot(self, cid: int) -> bool:
        snap = self._turn_snapshots.get(cid)
        if not snap or cid not in self.combatants:
            return False
        c = self.combatants[cid]
        c.move_remaining = int(snap.get("move_remaining", c.move_remaining))
        c.move_total = int(snap.get("move_total", c.move_total))
        c.action_remaining = int(snap.get("action_remaining", c.action_remaining))
        c.bonus_action_remaining = int(snap.get("bonus_action_remaining", c.bonus_action_remaining))

        col = int(snap.get("col", 0))
        row = int(snap.get("row", 0))
        self._lan_positions[cid] = (col, row)
        mw = getattr(self, "_map_window", None)
        try:
            if mw is not None and mw.winfo_exists():
                tok = getattr(mw, "unit_tokens", {}).get(cid)
                if tok:
                    tok["col"] = col
                    tok["row"] = row
                    mw._layout_unit(cid)
                    mw._update_groups()
                    mw._update_move_highlight()
                    mw._update_included_for_selected()
        except Exception:
            pass
        self._update_turn_ui()
        return True

    def _install_lan_menu(self) -> None:
        try:
            menubar = tk.Menu(self)
            try:
                # preserve any existing menu if base set one
                existing = self["menu"]
                if existing:
                    menubar = existing
            except Exception:
                pass

            lan = tk.Menu(menubar, tearoff=0)
            lan.add_command(label="Start LAN Server", command=self._lan.start)
            lan.add_command(label="Stop LAN Server", command=self._lan.stop)
            lan.add_separator()
            lan.add_command(label="Show LAN URL", command=self._show_lan_url)
            lan.add_command(label="Show QR Code", command=self._show_lan_qr)
            lan.add_separator()
            lan.add_command(label="Sessions…", command=self._open_lan_sessions)
            lan.add_command(label="Admin Assignments…", command=self._open_lan_admin_assignments)
            menubar.add_cascade(label="LAN", menu=lan)
            self.config(menu=menubar)
        except Exception:
            pass

    def _show_lan_url(self) -> None:
        url = self._lan._best_lan_url()
        messagebox.showinfo("LAN URL", f"Open this on yer LAN devices:\n\n{url}")

    def _show_lan_qr(self) -> None:
        url = "https://dnd.3045.network"
        try:
            import qrcode  # type: ignore
        except Exception as e:
            messagebox.showerror("QR Code", f"Arrr, QR code needs the qrcode module.\n\nError: {e}")
            return
        try:
            from PIL import Image, ImageTk  # type: ignore
        except Exception as e:
            messagebox.showerror(
                "QR Code",
                "Arrr, image QR needs Pillow ImageTk. Try: sudo apt install python3-pil.imagetk\n\n" + str(e),
            )
            return

        # Build QR image
        qr = qrcode.QRCode(border=2, box_size=10)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        try:
            img = img.convert("RGB")
        except Exception:
            pass

        # Scale to a comfortable size for phones
        size = 360
        try:
            img = img.resize((size, size), Image.NEAREST)
        except Exception:
            pass

        win = tk.Toplevel(self)
        win.title("LAN QR Code")
        win.geometry("420x520")
        win.transient(self)

        frm = tk.Frame(win)
        frm.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(frm, image=photo)
        lbl.image = photo  # keep alive
        lbl.pack(pady=(0, 10))

        tk.Label(frm, text=url, wraplength=380, justify="center").pack(pady=(0, 8))

        btns = tk.Frame(frm)
        btns.pack()

        def copy_url():
            try:
                self.clipboard_clear()
                self.clipboard_append(url)
            except Exception:
                pass

        tk.Button(btns, text="Copy URL", command=copy_url).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btns, text="Close", command=win.destroy).pack(side=tk.LEFT)

    def _open_lan_sessions(self) -> None:
        """DM utility: see connected LAN clients and (re)assign PCs."""
        win = tk.Toplevel(self)
        win.title("LAN Sessions")
        win.geometry("720x420")
        win.transient(self)

        outer = tk.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Sessions table
        cols = ("ws_id", "host", "claimed")
        tree = ttk.Treeview(outer, columns=cols, show="headings", height=10)
        tree.heading("ws_id", text="Session")
        tree.heading("host", text="Client")
        tree.heading("claimed", text="Claimed")
        tree.column("ws_id", width=90, anchor="center")
        tree.column("host", width=260, anchor="w")
        tree.column("claimed", width=240, anchor="w")
        tree.pack(fill=tk.BOTH, expand=True)

        controls = tk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))

        tk.Label(controls, text="Assign to:").pack(side=tk.LEFT)

        # PC dropdown (name shown, cid used)
        pc_map: Dict[str, Optional[int]] = {"(unassigned)": None}
        try:
            for p in self._lan_pcs():
                nm = str(p.get("name", ""))
                cid = p.get("cid")
                if nm and isinstance(cid, int):
                    pc_map[nm] = int(cid)
        except Exception:
            pass
        pc_names = sorted([k for k in pc_map.keys() if k != "(unassigned)"])
        pc_names.insert(0, "(unassigned)")

        pc_var = tk.StringVar(value="(unassigned)")
        pc_box = ttk.Combobox(controls, textvariable=pc_var, values=pc_names, width=30, state="readonly")
        pc_box.pack(side=tk.LEFT, padx=(6, 10))

        def refresh_sessions() -> None:
            tree.delete(*tree.get_children())
            sessions = self._lan.sessions_snapshot()
            # quick lookup from cid -> name
            cid_to_name: Dict[int, str] = {}
            try:
                for p in self._lan_pcs():
                    if isinstance(p.get("cid"), int):
                        cid_to_name[int(p["cid"])] = str(p.get("name", ""))
            except Exception:
                pass

            for s in sessions:
                ws_id = int(s.get("ws_id"))
                host = str(s.get("host", "?"))
                port = str(s.get("port", ""))
                host_disp = f"{host}:{port}" if port else host
                cid = s.get("cid")
                claimed = ""
                if isinstance(cid, int):
                    claimed = cid_to_name.get(int(cid), f"cid {cid}")
                tree.insert("", "end", iid=str(ws_id), values=(ws_id, host_disp, claimed))

        def get_selected_ws_id() -> Optional[int]:
            sel = tree.selection()
            if not sel:
                return None
            try:
                return int(sel[0])
            except Exception:
                return None

        def do_assign() -> None:
            ws_id = get_selected_ws_id()
            if ws_id is None:
                return
            cid = pc_map.get(pc_var.get())
            self._lan.assign_session(ws_id, cid, note="Assigned by the DM.")
            # refresh shortly after
            self.after(300, refresh_sessions)

        def do_kick() -> None:
            ws_id = get_selected_ws_id()
            if ws_id is None:
                return
            # best-effort: unclaim
            self._lan.assign_session(ws_id, None, note="Unclaimed by the DM.")
            self.after(300, refresh_sessions)

        ttk.Button(controls, text="Refresh", command=refresh_sessions).pack(side=tk.LEFT)
        ttk.Button(controls, text="Assign", command=do_assign).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(controls, text="Unassign", command=do_kick).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="Close", command=win.destroy).pack(side=tk.RIGHT)

        refresh_sessions()

    def _open_lan_admin_assignments(self) -> None:
        """DM utility: assign PCs by host/IP (mirrors web admin)."""
        win = tk.Toplevel(self)
        win.title("LAN Admin Assignments")
        win.geometry("860x460")
        win.transient(self)

        outer = tk.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        cols = ("host", "status", "assigned", "last_seen", "user_agent")
        tree = ttk.Treeview(outer, columns=cols, show="headings", height=12)
        tree.heading("host", text="Host/IP")
        tree.heading("status", text="Status")
        tree.heading("assigned", text="Assigned PC")
        tree.heading("last_seen", text="Last Seen")
        tree.heading("user_agent", text="User Agent")
        tree.column("host", width=200, anchor="w")
        tree.column("status", width=90, anchor="center")
        tree.column("assigned", width=180, anchor="w")
        tree.column("last_seen", width=140, anchor="w")
        tree.column("user_agent", width=230, anchor="w")
        tree.pack(fill=tk.BOTH, expand=True)

        controls = tk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))

        tk.Label(controls, text="Assign to:").pack(side=tk.LEFT)

        pc_var = tk.StringVar(value="(unassigned)")
        pc_box = ttk.Combobox(controls, textvariable=pc_var, width=30, state="readonly")
        pc_box.pack(side=tk.LEFT, padx=(6, 10))

        host_by_iid: Dict[str, str] = {}
        pc_map: Dict[str, Optional[int]] = {"(unassigned)": None}

        def refresh_sessions() -> None:
            tree.delete(*tree.get_children())
            host_by_iid.clear()
            payload = self._lan.admin_sessions_payload()
            sessions = payload.get("sessions") if isinstance(payload, dict) else []
            pcs = payload.get("pcs") if isinstance(payload, dict) else []

            pc_map.clear()
            pc_map["(unassigned)"] = None
            if isinstance(pcs, list):
                for pc in pcs:
                    if not isinstance(pc, dict):
                        continue
                    name = str(pc.get("name", "")).strip()
                    cid = pc.get("cid")
                    if name and isinstance(cid, int):
                        pc_map[name] = int(cid)

            pc_names = sorted([k for k in pc_map.keys() if k != "(unassigned)"])
            pc_names.insert(0, "(unassigned)")
            pc_box["values"] = pc_names
            if pc_var.get() not in pc_names:
                pc_var.set("(unassigned)")

            if not isinstance(sessions, list):
                sessions = []
            for idx, entry in enumerate(sessions):
                if not isinstance(entry, dict):
                    continue
                host = str(entry.get("ip") or entry.get("host") or "").strip()
                port = str(entry.get("port") or "").strip()
                host_disp = f"{host}:{port}" if port else (host or "?")
                reverse_dns = str(entry.get("reverse_dns") or "").strip()
                if reverse_dns:
                    host_disp = f"{host_disp} ({reverse_dns})"
                status = str(entry.get("status") or "").strip() or "unknown"
                assigned_name = entry.get("assigned_name")
                assigned_cid = entry.get("assigned_cid")
                yaml_assigned_name = entry.get("yaml_assigned_name")
                assigned = ""
                if assigned_name:
                    assigned = str(assigned_name)
                elif isinstance(assigned_cid, int):
                    assigned = f"cid {assigned_cid}"
                if yaml_assigned_name:
                    yaml_label = str(yaml_assigned_name)
                    if assigned:
                        assigned = f"{assigned} (YAML: {yaml_label})"
                    else:
                        assigned = f"YAML: {yaml_label}"
                last_seen = str(entry.get("last_seen") or "").strip()
                user_agent = str(entry.get("user_agent") or entry.get("ua") or "").strip()
                iid = f"{idx}"
                tree.insert("", "end", iid=iid, values=(host_disp, status, assigned, last_seen, user_agent))
                if host:
                    host_by_iid[iid] = host

        def get_selected_host() -> Optional[str]:
            sel = tree.selection()
            if not sel:
                return None
            return host_by_iid.get(sel[0])

        def do_assign() -> None:
            host = get_selected_host()
            if not host:
                return
            cid = pc_map.get(pc_var.get())
            self._lan.assign_host(host, cid, note="Assigned by the DM.")
            self.after(300, refresh_sessions)

        def do_unassign() -> None:
            host = get_selected_host()
            if not host:
                return
            self._lan.assign_host(host, None, note="Unclaimed by the DM.")
            self.after(300, refresh_sessions)

        ttk.Button(controls, text="Refresh", command=refresh_sessions).pack(side=tk.LEFT)
        ttk.Button(controls, text="Assign", command=do_assign).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(controls, text="Unassign", command=do_unassign).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="Close", command=win.destroy).pack(side=tk.RIGHT)

        refresh_sessions()
    
    def _poc_seed_all_player_characters(self) -> None:
        """Temporary POC behavior: add all starting roster PCs to initiative and roll initiative.

        This makes remote/LAN testing easy over SSH without clicking through dialogs.
        Safe to call multiple times; it won't duplicate names already in combat.
        """
        try:
            roster = list(self._load_starting_players_roster())
        except Exception:
            roster = []

        if not roster:
            return

        existing = {str(c.name) for c in self.combatants.values()}

        players_dir = None
        try:
            players_dir = Path(__file__).resolve().parent / "players"
        except Exception:
            players_dir = Path.cwd() / "players"

        ymod = getattr(base, "yaml", None)
        cfg_cache: Dict[str, Optional[Dict[str, Any]]] = getattr(
            self, "_player_config_cache", None
        )
        if cfg_cache is None:
            cfg_cache = {}
            self._player_config_cache = cfg_cache
        cfg_paths: Optional[Dict[str, Path]] = getattr(self, "_player_config_paths", None)
        if cfg_paths is None:
            cfg_paths = {}
            try:
                if players_dir.exists():
                    cfg_paths = {
                        path.stem: path
                        for path in players_dir.glob("*.yaml")
                        if path.is_file()
                    }
            except Exception:
                cfg_paths = {}
            self._player_config_paths = cfg_paths

        for name in roster:
            nm = str(name).strip()
            if not nm or nm in existing:
                continue

            # Defaults
            hp = 0
            speed = 30
            swim = 0
            water = False
            actions: List[str] = []
            bonus_actions: List[str] = []

            # Future-facing: per-PC config file players/<Name>.yaml (optional)
            data = cfg_cache.get(nm, None)
            if nm not in cfg_cache:
                try:
                    cfg_path = cfg_paths.get(nm) if cfg_paths is not None else None
                    if cfg_path is not None:
                        raw = cfg_path.read_text(encoding="utf-8")
                        if ymod is not None:
                            data = ymod.safe_load(raw)
                        if not isinstance(data, dict):
                            data = None
                    cfg_cache[nm] = data
                except Exception:
                    cfg_cache[nm] = None
                    data = None
            if isinstance(data, dict):
                def normalize_action_list(value: Any) -> List[str]:
                    if isinstance(value, list):
                        return [str(item).strip() for item in value if str(item).strip()]
                    if isinstance(value, str) and value.strip():
                        return [value.strip()]
                    return []
                profile = self._normalize_player_profile(data, nm)
                resources = profile.get("resources", {}) if isinstance(profile, dict) else {}
                defenses = profile.get("defenses", {}) if isinstance(profile, dict) else {}
                # accept a few key names
                speed = int(
                    resources.get("base_movement", resources.get("speed", speed)) or speed
                )
                swim = int(resources.get("swim_speed", swim) or swim)
                hp = int(defenses.get("hp", hp) or hp)
                actions = normalize_action_list(resources.get("actions"))
                bonus_actions = normalize_action_list(resources.get("bonus_actions"))

            try:
                init_total = random.randint(1, 20)
            except Exception:
                init_total = 10

            try:
                self._create_combatant(
                    name=self._unique_name(nm),
                    hp=int(hp),
                    speed=int(speed),
                    swim_speed=int(swim),
                    water_mode=bool(water),
                    initiative=int(init_total),
                    dex=None,
                    ally=True,
                    is_pc=True,
                    actions=actions,
                    bonus_actions=bonus_actions,
                )
                existing.add(nm)
            except Exception:
                pass

        try:
            self._rebuild_table(scroll_to_current=True)
        except Exception:
            pass

    # --------------------- LAN snapshot + actions ---------------------

    def _lan_claimable(self) -> List[Dict[str, Any]]:
        """Return Player Characters that can be claimed."""
        out: List[Dict[str, Any]] = []
        for c in self.combatants.values():
            role = self._name_role_memory.get(str(c.name), "enemy")
            if role == "pc":
                out.append({"cid": c.cid, "name": str(c.name)})
        # sort stable
        out.sort(key=lambda x: str(x["name"]).lower())
        return out

    def _lan_pcs(self) -> List[Dict[str, Any]]:
        """Alias for LAN client character selection."""
        return self._lan_claimable()

    def _normalize_token_color(self, color: Any) -> Optional[str]:
        if not isinstance(color, str):
            return None
        value = color.strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            return None
        return value

    def _token_color_forbidden(self, color: str) -> bool:
        try:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
        except Exception:
            return True
        if r >= 245 and g >= 245 and b >= 245:
            return True
        if r >= 200 and g <= 80 and b <= 80:
            return True
        return False

    def _token_color_payload(self, c: Any) -> Optional[str]:
        return self._normalize_token_color(getattr(c, "token_color", None))

    def _lan_sync_aoes_to_map(self, mw: Any) -> None:
        store = getattr(self, "_lan_aoes", {}) or {}
        if not store:
            return
        try:
            mw_aoes = getattr(mw, "aoes", None)
            if mw_aoes is None:
                mw_aoes = {}
                setattr(mw, "aoes", mw_aoes)
            changed = False
            for aid, aoe in store.items():
                aid_int = int(aid)
                if aid_int not in mw_aoes:
                    mw_aoes[aid_int] = dict(aoe)
                    if hasattr(mw, "_create_aoe_items"):
                        try:
                            mw._create_aoe_items(aid_int)
                        except Exception:
                            pass
                    changed = True
            if changed and hasattr(mw, "_refresh_aoe_list"):
                try:
                    mw._refresh_aoe_list()
                except Exception:
                    pass
            if mw_aoes:
                max_aid = max(int(a) for a in mw_aoes.keys())
                try:
                    next_aid = int(getattr(mw, "_next_aoe_id", max_aid + 1))
                except Exception:
                    next_aid = max_aid + 1
                if next_aid <= max_aid:
                    setattr(mw, "_next_aoe_id", max_aid + 1)
        except Exception:
            pass

    def _lan_snapshot(self) -> Dict[str, Any]:
        # Prefer map window live state when available
        mw = None
        try:
            mw = getattr(self, "_map_window", None)
            if mw is not None and not mw.winfo_exists():
                mw = None
        except Exception:
            mw = None

        cols = self._lan_grid_cols
        rows = self._lan_grid_rows
        obstacles = set(self._lan_obstacles)
        positions = dict(self._lan_positions)
        map_ready = mw is not None
        aoes: List[Dict[str, Any]] = []
        aoe_source: Dict[int, Dict[str, Any]] = dict(getattr(self, "_lan_aoes", {}) or {})
        rough_terrain: Dict[Tuple[int, int], object] = {}

        if mw is not None:
            try:
                cols = int(getattr(mw, "cols", cols))
                rows = int(getattr(mw, "rows", rows))
            except Exception:
                pass
            try:
                self._lan_sync_aoes_to_map(mw)
                aoe_source = dict(getattr(mw, "aoes", {}) or {})
            except Exception:
                pass
            try:
                obstacles = set(getattr(mw, "obstacles", obstacles) or set())
            except Exception:
                pass
            try:
                rough_terrain = dict(getattr(mw, "rough_terrain", rough_terrain) or {})
            except Exception:
                pass
            try:
                for cid, tok in (getattr(mw, "unit_tokens", {}) or {}).items():
                    positions[int(cid)] = (int(tok.get("col")), int(tok.get("row")))
            except Exception:
                pass
            try:
                self._lan_aoes = dict(aoe_source)
                if aoe_source:
                    max_aid = max(int(aid) for aid in aoe_source.keys())
                    self._lan_next_aoe_id = max(self._lan_next_aoe_id, max_aid + 1)
            except Exception:
                pass

        try:
            for aid, d in sorted((aoe_source or {}).items()):
                kind = str(d.get("kind") or d.get("shape") or "").lower()
                if kind not in ("circle", "square", "line", "sphere", "cube", "cone", "cylinder", "wall"):
                    continue
                payload: Dict[str, Any] = {
                    "aid": int(aid),
                    "kind": kind,
                    "name": str(d.get("name") or f"AoE {aid}"),
                    "color": str(d.get("color") or ""),
                    "cx": float(d.get("cx") or 0.0),
                    "cy": float(d.get("cy") or 0.0),
                    "pinned": bool(d.get("pinned")),
                    "duration_turns": d.get("duration_turns"),
                    "remaining_turns": d.get("remaining_turns"),
                }
                for extra_key in (
                    "dc",
                    "save_type",
                    "damage_type",
                    "half_on_pass",
                    "default_damage",
                    "owner",
                    "owner_cid",
                    "over_time",
                    "move_per_turn_ft",
                    "move_remaining_ft",
                    "trigger_on_start_or_enter",
                    "persistent",
                ):
                    if d.get(extra_key) not in (None, ""):
                        payload[extra_key] = d.get(extra_key)
                if kind in ("circle", "sphere", "cylinder"):
                    payload["radius_sq"] = float(d.get("radius_sq") or 0.0)
                    if d.get("radius_ft") is not None:
                        payload["radius_ft"] = float(d.get("radius_ft") or 0.0)
                    if d.get("height_ft") is not None:
                        payload["height_ft"] = float(d.get("height_ft") or 0.0)
                elif kind in ("line", "wall"):
                    payload["length_sq"] = float(d.get("length_sq") or 0.0)
                    payload["width_sq"] = float(d.get("width_sq") or 0.0)
                    payload["orient"] = str(d.get("orient") or "vertical")
                    if d.get("angle_deg") is not None:
                        payload["angle_deg"] = float(d.get("angle_deg") or 0.0)
                    if d.get("length_ft") is not None:
                        payload["length_ft"] = float(d.get("length_ft") or 0.0)
                    if d.get("width_ft") is not None:
                        payload["width_ft"] = float(d.get("width_ft") or 0.0)
                    if d.get("thickness_ft") is not None:
                        payload["thickness_ft"] = float(d.get("thickness_ft") or 0.0)
                    if d.get("height_ft") is not None:
                        payload["height_ft"] = float(d.get("height_ft") or 0.0)
                elif kind == "cone":
                    payload["length_sq"] = float(d.get("length_sq") or 0.0)
                    payload["orient"] = str(d.get("orient") or "vertical")
                    if d.get("angle_deg") is not None:
                        payload["angle_deg"] = float(d.get("angle_deg") or 0.0)
                    if d.get("length_ft") is not None:
                        payload["length_ft"] = float(d.get("length_ft") or 0.0)
                else:
                    payload["side_sq"] = float(d.get("side_sq") or 0.0)
                    if d.get("side_ft") is not None:
                        payload["side_ft"] = float(d.get("side_ft") or 0.0)
                aoes.append(payload)
        except Exception:
            pass

        # Ensure any combatant has a position (spawn near center in a square spiral)
        if self.combatants and len(positions) < len(self.combatants):
            positions = self._lan_seed_missing_positions(positions, cols, rows)

        units: List[Dict[str, Any]] = []
        for c in sorted(self.combatants.values(), key=lambda x: int(x.cid)):
            role = self._name_role_memory.get(str(c.name), "enemy")
            pos = positions.get(c.cid, (max(0, cols // 2), max(0, rows // 2)))
            marks = self._lan_marks_for(c)
            actions = [str(item).strip() for item in (getattr(c, "actions", []) or []) if str(item).strip()]
            bonus_actions = [
                str(item).strip()
                for item in (getattr(c, "bonus_actions", []) or [])
                if str(item).strip()
            ]
            units.append(
                {
                    "cid": c.cid,
                    "name": str(c.name),
                    "role": role if role in ("pc", "ally", "enemy") else "enemy",
                    "token_color": self._token_color_payload(c),
                    "hp": int(getattr(c, "hp", 0) or 0),
                    "move_remaining": int(getattr(c, "move_remaining", 0) or 0),
                    "move_total": int(getattr(c, "move_total", 0) or 0),
                    "action_remaining": int(getattr(c, "action_remaining", 0) or 0),
                    "bonus_action_remaining": int(getattr(c, "bonus_action_remaining", 0) or 0),
                    "actions": actions,
                    "bonus_actions": bonus_actions,
                    "is_prone": self._has_condition(c, "prone"),
                    "is_spellcaster": bool(getattr(c, "is_spellcaster", False)),
                    "pos": {"col": int(pos[0]), "row": int(pos[1])},
                    "marks": marks,
                }
            )

        # Active creature
        active = self.current_cid if getattr(self, "current_cid", None) is not None else None

        grid_payload = None
        if map_ready:
            grid_payload = {"cols": int(cols), "rows": int(rows), "feet_per_square": 5}
        turn_order: List[int] = []
        try:
            ordered = self._display_order()
            turn_order = [int(c.cid) for c in ordered if getattr(c, "cid", None) is not None]
        except Exception:
            try:
                turn_order = [int(c.cid) for c in sorted(self.combatants.values(), key=lambda x: int(x.cid))]
            except Exception:
                turn_order = []
        rough_payload: List[Dict[str, Any]] = []
        for (c, r), cell in sorted(rough_terrain.items()):
            if isinstance(cell, dict):
                color = str(cell.get("color") or "")
                is_swim = bool(cell.get("is_swim", False))
                is_rough = bool(cell.get("is_rough", False))
            else:
                color = str(cell)
                is_swim = False
                is_rough = True
            rough_payload.append(
                {
                    "col": int(c),
                    "row": int(r),
                    "color": color,
                    "is_swim": is_swim,
                    "is_rough": is_rough,
                }
            )

        snap: Dict[str, Any] = {
            "grid": grid_payload,
            "obstacles": [{"col": int(c), "row": int(r)} for (c, r) in sorted(obstacles)],
            "rough_terrain": rough_payload,
            "aoes": aoes,
            "units": units,
            "active_cid": active,
            "round_num": int(getattr(self, "round_num", 0) or 0),
            "turn_order": turn_order,
            "spell_presets": self._spell_presets_payload(),
            "player_spells": self._player_spell_config_payload(),
            "player_profiles": self._player_profiles_payload(),
        }
        return snap

    def _lan_marks_for(self, c: Any) -> str:
        # Match main-map effect markers (conditions, DoT, star advantage, etc.)
        try:
            text = self._format_effects(c)
        except Exception:
            text = ""
        return (text or "").strip()

    def _spell_presets_payload(self) -> List[Dict[str, Any]]:
        if yaml is None:
            return []
        spells_dir = self._resolve_spells_dir()
        if spells_dir is None:
            return []

        try:
            files = sorted(list(spells_dir.glob("*.yaml")) + list(spells_dir.glob("*.yml")))
        except Exception:
            files = []

        ops = _make_ops_logger()
        if not files:
            self._spell_presets_cache = []
            self._spell_index_entries = {}
            self._spell_index_loaded = True
            _write_index_file(self._spell_index_path(), {"version": 1, "entries": {}})
            return []

        cached_entries = self._load_spell_index_entries()
        cache_keys = set(cached_entries.keys()) if isinstance(cached_entries, dict) else set()
        file_keys = {fp.name for fp in files}
        cache_names_match = cache_keys == file_keys

        def cache_is_valid(entries: Dict[str, Any]) -> bool:
            if not cache_names_match:
                return False
            for fp in files:
                meta = _file_stat_metadata(fp)
                entry = entries.get(fp.name) if isinstance(entries, dict) else None
                if not isinstance(entry, dict):
                    return False
                if not _metadata_matches(entry, meta):
                    return False
                if not isinstance(entry.get("preset"), dict):
                    return False
            return True

        if self._spell_presets_cache is not None and cache_is_valid(cached_entries):
            return list(self._spell_presets_cache)

        presets: List[Dict[str, Any]] = []
        ability_map = {
            "strength": "str",
            "str": "str",
            "dexterity": "dex",
            "dex": "dex",
            "constitution": "con",
            "con": "con",
            "intelligence": "int",
            "int": "int",
            "wisdom": "wis",
            "wis": "wis",
            "charisma": "cha",
            "cha": "cha",
        }

        def parse_number(value: Any) -> Optional[float]:
            if value in (None, ""):
                return None
            try:
                num = float(value)
            except Exception:
                return None
            if not (num == num and abs(num) != float("inf")):
                return None
            return num

        def parse_dice(value: Any) -> Optional[str]:
            if value in (None, ""):
                return None
            raw = str(value).strip().lower()
            match = re.fullmatch(r"(\\d+)d(4|6|8|10|12)", raw)
            if not match:
                return None
            count = int(match.group(1))
            if count <= 0:
                return None
            return f"{count}d{match.group(2)}"

        def normalize_save_type(value: Any) -> Optional[str]:
            if value in (None, ""):
                return None
            raw = str(value).strip().lower()
            return ability_map.get(raw, raw)

        def parse_spell_file(fp: Path) -> Optional[Tuple[Dict[str, Any], str]]:
            try:
                raw = fp.read_text(encoding="utf-8")
            except Exception as exc:
                ops.warning("Failed reading spell YAML %s: %s", fp.name, exc)
                return None
            try:
                parsed = yaml.safe_load(raw)
            except Exception as exc:
                ops.warning("Failed parsing spell YAML %s: %s", fp.name, exc)
                return None
            if not isinstance(parsed, dict):
                ops.warning("Spell YAML %s did not parse to a dict.", fp.name)
                return None

            name = str(parsed.get("name") or "").strip()
            if not name:
                ops.warning("Spell YAML %s missing name; skipping preset.", fp.name)
                return None

            schema = parsed.get("schema")
            spell_id = parsed.get("id")
            level = parsed.get("level")
            school = parsed.get("school")
            tags_raw = parsed.get("tags")
            tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []
            casting_time = parsed.get("casting_time")
            spell_range = parsed.get("range")
            ritual = parsed.get("ritual")
            concentration = parsed.get("concentration")
            lists = parsed.get("lists") if isinstance(parsed.get("lists"), dict) else {}
            mechanics = parsed.get("mechanics") if isinstance(parsed.get("mechanics"), dict) else {}
            automation_raw = str(mechanics.get("automation") or "").strip().lower()
            automation = automation_raw if automation_raw in ("full", "partial", "manual") else "manual"
            errors: List[str] = []
            warnings: List[str] = []
            if not schema:
                errors.append("missing schema")
            if not spell_id:
                errors.append("missing id")
            if level is None:
                errors.append("missing level")
            if not school:
                errors.append("missing school")
            if errors:
                ops.warning("Spell YAML %s has issues: %s", fp.name, ", ".join(errors))

            preset: Dict[str, Any] = {
                "schema": schema,
                "id": spell_id,
                "name": name,
                "level": level,
                "school": school,
                "tags": tags,
                "casting_time": str(casting_time).strip() if casting_time not in (None, "") else None,
                "range": str(spell_range).strip() if spell_range not in (None, "") else None,
                "ritual": ritual if isinstance(ritual, bool) else None,
                "concentration": concentration if isinstance(concentration, bool) else None,
                "lists": lists,
                "mechanics": mechanics,
                "automation": automation,
            }

            targeting = mechanics.get("targeting") if isinstance(mechanics.get("targeting"), dict) else {}
            range_data = targeting.get("range") if isinstance(targeting.get("range"), dict) else {}
            area = targeting.get("area") if isinstance(targeting.get("area"), dict) else {}
            shape_raw = str(area.get("shape") or "").strip().lower()
            shape_map = {
                "circle": "sphere",
                "square": "cube",
            }
            shape = shape_map.get(shape_raw, shape_raw)
            missing_required_fields = False
            if automation in ("full", "partial"):
                if str(range_data.get("kind") or "").strip().lower() == "distance":
                    distance_ft = parse_number(range_data.get("distance_ft"))
                    if distance_ft is None:
                        warnings.append("missing targeting.range.distance_ft")
                        missing_required_fields = True
                if shape and shape not in ("sphere", "cube", "cone", "cylinder", "wall", "line"):
                    warnings.append(f"unsupported area shape '{shape_raw or shape}'")
                    missing_required_fields = True
            if shape in ("sphere", "cube", "cone", "cylinder", "wall", "line"):
                preset["shape"] = shape
                missing_dimensions: List[str] = []
                if shape == "sphere":
                    radius_ft = parse_number(area.get("radius_ft"))
                    if radius_ft is not None:
                        preset["radius_ft"] = radius_ft
                    else:
                        missing_dimensions.append("radius_ft")
                if shape == "cube":
                    side_ft = parse_number(area.get("side_ft"))
                    if side_ft is not None:
                        preset["side_ft"] = side_ft
                    else:
                        missing_dimensions.append("side_ft")
                if shape == "cylinder":
                    radius_ft = parse_number(area.get("radius_ft"))
                    if radius_ft is not None:
                        preset["radius_ft"] = radius_ft
                    else:
                        missing_dimensions.append("radius_ft")
                    height_ft = parse_number(area.get("height_ft"))
                    if height_ft is not None:
                        preset["height_ft"] = height_ft
                    else:
                        missing_dimensions.append("height_ft")
                if shape == "line":
                    length_ft = parse_number(area.get("length_ft"))
                    width_ft = parse_number(area.get("width_ft"))
                    if length_ft is not None:
                        preset["length_ft"] = length_ft
                    else:
                        missing_dimensions.append("length_ft")
                    if width_ft is not None:
                        preset["width_ft"] = width_ft
                    else:
                        missing_dimensions.append("width_ft")
                    angle_deg = parse_number(area.get("angle_deg"))
                    if angle_deg is not None:
                        preset["angle_deg"] = angle_deg
                if shape == "cone":
                    length_ft = parse_number(area.get("length_ft"))
                    if length_ft is not None:
                        preset["length_ft"] = length_ft
                    else:
                        missing_dimensions.append("length_ft")
                    angle_deg = parse_number(area.get("angle_deg"))
                    if angle_deg is not None:
                        preset["angle_deg"] = angle_deg
                if shape == "wall":
                    length_ft = parse_number(area.get("length_ft"))
                    width_ft = parse_number(area.get("width_ft"))
                    height_ft = parse_number(area.get("height_ft"))
                    if length_ft is not None:
                        preset["length_ft"] = length_ft
                    else:
                        missing_dimensions.append("length_ft")
                    if width_ft is not None:
                        preset["width_ft"] = width_ft
                    else:
                        missing_dimensions.append("width_ft")
                    if height_ft is not None:
                        preset["height_ft"] = height_ft
                    else:
                        missing_dimensions.append("height_ft")
                    angle_deg = parse_number(area.get("angle_deg"))
                    if angle_deg is not None:
                        preset["angle_deg"] = angle_deg
                if missing_dimensions:
                    preset["incomplete"] = True
                    preset["incomplete_fields"] = missing_dimensions
                    if automation in ("full", "partial"):
                        warnings.append("missing area dimensions: " + ", ".join(missing_dimensions))
                        missing_required_fields = True

            damage_types: List[str] = []
            dice: Optional[str] = None
            effect_scaling: Optional[Dict[str, Any]] = None
            save_type: Optional[str] = None
            save_dc: Optional[int] = None
            half_on_pass: Optional[bool] = None

            sequence = mechanics.get("sequence") if isinstance(mechanics.get("sequence"), list) else []
            for step in sequence:
                if not isinstance(step, dict):
                    continue
                check = step.get("check") if isinstance(step.get("check"), dict) else {}
                if save_type is None and check.get("kind") == "saving_throw":
                    save_type = normalize_save_type(check.get("ability"))
                    dc_value = check.get("dc")
                    if isinstance(dc_value, (int, float)):
                        save_dc = int(dc_value)
                    elif isinstance(dc_value, str) and dc_value.strip().isdigit():
                        save_dc = int(dc_value.strip())
                outcomes = step.get("outcomes") if isinstance(step.get("outcomes"), dict) else {}
                for outcome_key, outcome_list in outcomes.items():
                    if not isinstance(outcome_list, list):
                        continue
                    for effect in outcome_list:
                        if not isinstance(effect, dict):
                            continue
                        if effect.get("effect") != "damage":
                            continue
                        dtype = str(effect.get("damage_type") or "").strip()
                        if dtype and dtype not in damage_types:
                            damage_types.append(dtype)
                        if dice is None:
                            dice = parse_dice(effect.get("dice"))
                        if effect_scaling is None and isinstance(effect.get("scaling"), dict):
                            effect_scaling = effect.get("scaling")
                        if half_on_pass is None:
                            multiplier = parse_number(effect.get("multiplier"))
                            if multiplier is not None and abs(multiplier - 0.5) < 1e-9:
                                outcome_label = str(outcome_key or "").strip().lower()
                                if outcome_label in ("success", "pass", "save", "saved", "succeed"):
                                    half_on_pass = True

            scaling = mechanics.get("scaling") if isinstance(mechanics.get("scaling"), dict) else None
            if scaling is None:
                scaling = effect_scaling

            if save_type:
                preset["save_type"] = save_type
            if save_dc is not None:
                preset["save_dc"] = save_dc
            if dice:
                preset["dice"] = dice
            if damage_types:
                preset["damage_types"] = damage_types
            if half_on_pass:
                preset["half_on_pass"] = True

            upcast: Optional[Dict[str, Any]] = None
            if isinstance(scaling, dict) and scaling.get("kind") == "slot_level":
                base_slot = scaling.get("base_slot")
                add_per_slot = scaling.get("add_per_slot_above")
                base_level = int(base_slot) if isinstance(base_slot, int) else None
                add_dice = parse_dice(add_per_slot)
                if base_level is None and isinstance(base_slot, str) and base_slot.strip().isdigit():
                    base_level = int(base_slot.strip())
                if base_level is not None and add_dice:
                    upcast = {
                        "base_level": base_level,
                        "add_per_slot_above": add_dice,
                    }
            if isinstance(scaling, dict) and scaling.get("kind") == "character_level":
                thresholds = scaling.get("thresholds") if isinstance(scaling.get("thresholds"), dict) else {}
                increments: List[Dict[str, Any]] = []
                for threshold, data in thresholds.items():
                    if not isinstance(data, dict):
                        continue
                    try:
                        level = int(str(threshold).strip())
                    except ValueError:
                        continue
                    add_dice = parse_dice(data.get("add"))
                    if add_dice:
                        increments.append({"level": level, "add_dice": add_dice})
                if increments:
                    increments.sort(key=lambda entry: entry.get("level", 0))
                    upcast = {
                        "base_level": 1,
                        "increments": increments,
                    }
            if upcast:
                preset["upcast"] = upcast

            if automation == "full":
                if "shape" not in preset:
                    automation = "partial"
                if not dice and not damage_types and not save_type:
                    automation = "partial"
            if not mechanics:
                automation = "manual"
            if missing_required_fields and automation == "full":
                automation = "partial"
            if errors and automation == "full":
                automation = "partial"
            preset["automation"] = automation
            if warnings:
                ops.warning("Spell YAML %s has automation warnings: %s", fp.name, ", ".join(warnings))

            return preset, raw

        new_entries: Dict[str, Any] = {}
        used_cached_only = True
        for fp in files:
            meta = _file_stat_metadata(fp)
            entry = cached_entries.get(fp.name) if isinstance(cached_entries, dict) else None
            if isinstance(entry, dict) and _metadata_matches(entry, meta):
                preset = entry.get("preset")
                if isinstance(preset, dict):
                    presets.append(preset)
                    new_entry = dict(entry)
                    new_entry["mtime_ns"] = meta.get("mtime_ns")
                    new_entry["size"] = meta.get("size")
                    new_entries[fp.name] = new_entry
                    continue
            used_cached_only = False
            parsed = parse_spell_file(fp)
            if parsed is None:
                continue
            preset, raw = parsed
            presets.append(preset)
            new_entries[fp.name] = {
                "mtime_ns": meta.get("mtime_ns"),
                "size": meta.get("size"),
                "hash": _hash_text(raw),
                "preset": preset,
            }

        self._spell_presets_cache = presets
        self._spell_index_entries = new_entries
        self._spell_index_loaded = True
        if not used_cached_only or not cache_names_match:
            _write_index_file(self._spell_index_path(), {"version": 1, "entries": new_entries})

        return presets

    def _players_dir(self) -> Path:
        try:
            return Path(__file__).resolve().parent / "players"
        except Exception:
            return Path.cwd() / "players"

    @staticmethod
    def _sanitize_player_filename(name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "").strip())
        slug = slug.strip("-._")
        return slug or "player"

    @staticmethod
    def _normalize_player_section(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _normalize_identity_host(self, value: Any) -> Optional[str]:
        host = str(value or "").strip()
        if not host:
            return None
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass
        if len(host) > 253:
            return None
        labels = host.split(".")
        for label in labels:
            if not label or len(label) > 63:
                return None
            if label.startswith("-") or label.endswith("-"):
                return None
            if not re.match(r"^[A-Za-z0-9-]+$", label):
                return None
        return host

    def _normalize_player_profile(self, data: Dict[str, Any], fallback_name: str) -> Dict[str, Any]:
        def normalize_name(value: Any) -> Optional[str]:
            text = str(value or "").strip()
            return text or None

        fmt_raw = data.get("format_version")
        try:
            fmt = int(fmt_raw)
        except Exception:
            fmt = 0
        if fmt != 1:
            fmt = 0

        identity = self._normalize_player_section(data.get("identity"))
        leveling = self._normalize_player_section(data.get("leveling"))
        abilities = self._normalize_player_section(data.get("abilities"))
        defenses = self._normalize_player_section(data.get("defenses"))
        resources = self._normalize_player_section(data.get("resources"))
        spellcasting = self._normalize_player_section(data.get("spellcasting"))
        inventory = self._normalize_player_section(data.get("inventory"))

        name = (
            normalize_name(data.get("name"))
            or normalize_name(identity.get("name"))
            or normalize_name(identity.get("character_name"))
            or normalize_name(identity.get("player_name"))
            or normalize_name(fallback_name)
        )
        if name is None:
            name = fallback_name

        if "name" not in identity and name:
            identity["name"] = name

        raw_ip = identity.get("ip")
        normalized_ip = self._normalize_identity_host(raw_ip)
        if normalized_ip:
            identity["ip"] = normalized_ip
        else:
            if raw_ip:
                self._oplog(f"Player YAML {name}: invalid identity.ip '{raw_ip}'.", level="warning")
            identity.pop("ip", None)

        if fmt == 0:
            if "base_movement" in data and "base_movement" not in resources:
                resources["base_movement"] = data.get("base_movement")
            if "speed" in data and "base_movement" not in resources:
                resources["base_movement"] = data.get("speed")
            if "swim_speed" in data and "swim_speed" not in resources:
                resources["swim_speed"] = data.get("swim_speed")
            if "hp" in data and "hp" not in defenses:
                defenses["hp"] = data.get("hp")
            if "actions" in data and "actions" not in resources:
                resources["actions"] = data.get("actions")
            if "bonus_actions" in data and "bonus_actions" not in resources:
                resources["bonus_actions"] = data.get("bonus_actions")

        for key in ("known_cantrips", "known_spells", "known_spell_names"):
            if key not in spellcasting and key in data:
                spellcasting[key] = data.get(key)
        if "prepared_spells" not in spellcasting and "prepared_spells" in data:
            spellcasting["prepared_spells"] = data.get("prepared_spells")

        profile = PlayerProfile(
            name=name,
            format_version=fmt,
            identity=identity,
            leveling=leveling,
            abilities=abilities,
            defenses=defenses,
            resources=resources,
            spellcasting=spellcasting,
            inventory=inventory,
        )
        return profile.to_dict()

    def _normalize_player_spell_config(
        self,
        data: Dict[str, Any],
        include_missing_prepared: bool = True,
    ) -> Dict[str, Any]:
        def normalize_limit(value: Any, fallback: int) -> int:
            try:
                num = int(value)
            except Exception:
                return fallback
            return max(0, num)

        def normalize_name(value: Any) -> Optional[str]:
            text = str(value or "").strip()
            return text or None

        source = data
        if isinstance(data.get("spellcasting"), dict):
            source = data.get("spellcasting", {})
        known_cantrips = normalize_limit(source.get("known_cantrips"), 0)
        known_spells = normalize_limit(source.get("known_spells"), 15)
        raw_names = source.get("known_spell_names")
        names: List[str] = []
        if isinstance(raw_names, list):
            names = [name for item in raw_names if (name := normalize_name(item))]
        elif isinstance(raw_names, str):
            name = normalize_name(raw_names)
            names = [name] if name else []
        prepared_payload: Dict[str, Any] = {}
        prepared_spells = source.get("prepared_spells")
        if isinstance(prepared_spells, dict):
            raw_prepared = prepared_spells.get("prepared")
            prepared_names: List[str] = []
            if isinstance(raw_prepared, list):
                prepared_names = [
                    name for item in raw_prepared if (name := normalize_name(item))
                ]
            elif isinstance(raw_prepared, str):
                name = normalize_name(raw_prepared)
                prepared_names = [name] if name else []
            prepared_payload["prepared"] = prepared_names
            max_formula = prepared_spells.get("max_formula")
            if isinstance(max_formula, str) and max_formula.strip():
                prepared_payload["max_formula"] = max_formula.strip()
            if "max" in prepared_spells:
                prepared_payload["max"] = normalize_limit(prepared_spells.get("max"), 0)
            if "max_spells" in prepared_spells:
                prepared_payload["max_spells"] = normalize_limit(
                    prepared_spells.get("max_spells"), 0
                )
            if "max_prepared" in prepared_spells:
                prepared_payload["max_prepared"] = normalize_limit(
                    prepared_spells.get("max_prepared"), 0
                )
        elif include_missing_prepared:
            prepared_payload["prepared"] = []
        payload = {
            "known_cantrips": known_cantrips,
            "known_spells": known_spells,
            "known_spell_names": names,
        }
        if prepared_payload:
            payload["prepared_spells"] = prepared_payload
        return payload

    def _load_player_yaml_cache(self) -> None:
        if yaml is None:
            self._player_yaml_cache_by_path = {}
            self._player_yaml_meta_by_path = {}
            self._player_yaml_data_by_name = {}
            self._player_yaml_name_map = {}
            return

        players_dir = self._players_dir()
        if not players_dir.exists():
            self._player_yaml_cache_by_path = {}
            self._player_yaml_meta_by_path = {}
            self._player_yaml_data_by_name = {}
            self._player_yaml_name_map = {}
            return

        try:
            files = sorted(list(players_dir.glob("*.yaml")) + list(players_dir.glob("*.yml")))
        except Exception:
            files = []

        data_by_path = dict(self._player_yaml_cache_by_path)
        meta_by_path = dict(self._player_yaml_meta_by_path)

        valid_paths = set(files)
        for cached_path in list(data_by_path.keys()):
            if cached_path not in valid_paths:
                data_by_path.pop(cached_path, None)
                meta_by_path.pop(cached_path, None)

        for path in files:
            meta = _file_stat_metadata(path)
            cached_meta = meta_by_path.get(path)
            if cached_meta and _metadata_matches(cached_meta, meta):
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                parsed = yaml.safe_load(raw)
            except Exception:
                parsed = None
            data_by_path[path] = parsed if isinstance(parsed, dict) else None
            meta_by_path[path] = meta

        name_map: Dict[str, Path] = {}
        data_by_name: Dict[str, Dict[str, Any]] = {}
        for path, data in data_by_path.items():
            if not isinstance(data, dict):
                continue
            profile = self._normalize_player_profile(data, path.stem)
            name = str(profile.get("name") or path.stem).strip() or path.stem
            data_by_name[name] = profile
            name_map[name.lower()] = path
            name_map[path.stem.lower()] = path

        self._player_yaml_cache_by_path = data_by_path
        self._player_yaml_meta_by_path = meta_by_path
        self._player_yaml_data_by_name = data_by_name
        self._player_yaml_name_map = name_map
        try:
            self._lan._sync_yaml_host_assignments(self._player_yaml_data_by_name)
        except Exception:
            pass

    def _player_spell_config_payload(self) -> Dict[str, Dict[str, Any]]:
        self._load_player_yaml_cache()
        payload: Dict[str, Dict[str, Any]] = {}
        for name, data in self._player_yaml_data_by_name.items():
            if not isinstance(data, dict):
                continue
            payload[name] = self._normalize_player_spell_config(data)
        return payload

    def _player_profiles_payload(self) -> Dict[str, Dict[str, Any]]:
        self._load_player_yaml_cache()
        payload: Dict[str, Dict[str, Any]] = {}
        for name, data in self._player_yaml_data_by_name.items():
            if not isinstance(data, dict):
                continue
            payload[name] = dict(data)
        return payload

    def _save_player_spell_config(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if yaml is None:
            raise RuntimeError("PyYAML is required for spell persistence.")
        player_name = str(name or "").strip()
        if not player_name:
            raise ValueError("Player name is required.")
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a dictionary.")
        self._load_player_yaml_cache()
        key = player_name.lower()
        path = self._player_yaml_name_map.get(key)
        if path is None:
            players_dir = self._players_dir()
            players_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{self._sanitize_player_filename(player_name)}.yaml"
            path = players_dir / filename

        existing = self._player_yaml_cache_by_path.get(path) or {}
        if not isinstance(existing, dict):
            existing = {}

        normalized = self._normalize_player_spell_config(payload, include_missing_prepared=False)
        prepared_payload = normalized.get("prepared_spells")
        normalized_known = {k: v for k, v in normalized.items() if k != "prepared_spells"}

        if int(existing.get("format_version") or 0) == 1:
            spellcasting = existing.get("spellcasting")
            if not isinstance(spellcasting, dict):
                spellcasting = {}
            spellcasting.update(normalized_known)
            if prepared_payload is not None:
                existing_prepared = spellcasting.get("prepared_spells")
                if not isinstance(existing_prepared, dict):
                    existing_prepared = {}
                existing_prepared.update(prepared_payload)
                spellcasting["prepared_spells"] = existing_prepared
            existing["spellcasting"] = spellcasting
            identity = existing.get("identity")
            if not isinstance(identity, dict):
                identity = {}
            if "name" not in identity:
                identity["name"] = player_name
            existing["identity"] = identity
        else:
            if "name" not in existing:
                existing["name"] = player_name
            existing.update(normalized_known)
            if prepared_payload is not None:
                existing_prepared = existing.get("prepared_spells")
                if not isinstance(existing_prepared, dict):
                    existing_prepared = {}
                existing_prepared.update(prepared_payload)
                existing["prepared_spells"] = existing_prepared

        yaml_text = yaml.safe_dump(existing, sort_keys=False)
        path.write_text(yaml_text, encoding="utf-8")

        meta = _file_stat_metadata(path)
        self._player_yaml_cache_by_path[path] = existing
        self._player_yaml_meta_by_path[path] = meta
        profile = self._normalize_player_profile(existing, path.stem)
        profile_name = profile.get("name", player_name)
        self._player_yaml_data_by_name[profile_name] = profile
        self._player_yaml_name_map[player_name.lower()] = path
        self._player_yaml_name_map[path.stem.lower()] = path

        return normalized

    def _lan_seed_missing_positions(self, positions: Dict[int, Tuple[int, int]], cols: int, rows: int) -> Dict[int, Tuple[int, int]]:
        # place missing near center in a simple spiral, one square apart
        cx, cy = max(0, cols // 2), max(0, rows // 2)
        used = set(positions.values())
        def spiral_cells():
            yield (cx, cy)
            step = 1
            x, y = cx, cy
            while step < max(cols, rows) * 3:
                for _ in range(step):
                    x += 1
                    yield (x, y)
                for _ in range(step):
                    y += 1
                    yield (x, y)
                step += 1
                for _ in range(step):
                    x -= 1
                    yield (x, y)
                for _ in range(step):
                    y -= 1
                    yield (x, y)
                step += 1
        for c in self.combatants.values():
            if c.cid in positions:
                continue
            for (x, y) in spiral_cells():
                if not (0 <= x < cols and 0 <= y < rows):
                    continue
                if (x, y) in used:
                    continue
                positions[c.cid] = (x, y)
                used.add((x, y))
                break
        # persist
        self._lan_positions = dict(positions)
        return positions

    def _lan_apply_action(self, msg: Dict[str, Any]) -> None:
        """Apply client actions on the Tk thread."""
        typ = str(msg.get("type") or "")
        ws_id = msg.get("_ws_id")
        claimed = msg.get("_claimed_cid")
        admin_token = str(msg.get("admin_token") or "").strip()
        is_admin = bool(admin_token and self._is_admin_token_valid(admin_token))

        # Basic sanity: claimed cid must match the action cid (if provided)
        cid = msg.get("cid")
        if isinstance(cid, int):
            if not is_admin and claimed is not None and cid != claimed:
                self._lan.toast(ws_id, "Arrr, that token ain’t yers.")
                return
        else:
            cid = claimed

        if cid is None and not is_admin:
            self._lan.toast(ws_id, "Claim a character first, matey.")
            return

        # Must exist
        if cid is not None and cid not in self.combatants:
            self._lan.toast(ws_id, "That scallywag ain’t in combat no more.")
            return

        if typ == "set_color":
            color = self._normalize_token_color(msg.get("color"))
            if not color:
                self._lan.toast(ws_id, "Pick a valid hex color, matey.")
                return
            if self._token_color_forbidden(color):
                self._lan.toast(ws_id, "No red or white, matey.")
                return
            c = self.combatants.get(cid)
            if not c:
                return
            setattr(c, "token_color", color)
            mw = getattr(self, "_map_window", None)
            if mw is not None and hasattr(mw, "update_unit_token_colors"):
                try:
                    if mw.winfo_exists():
                        mw.update_unit_token_colors()
                except Exception:
                    pass
            return

        # Only allow controlling on your turn (POC)
        if not is_admin and typ not in ("cast_aoe", "aoe_move", "aoe_remove"):
            if self.current_cid is None or int(self.current_cid) != int(cid):
                self._lan.toast(ws_id, "Not yer turn yet, matey.")
                return

        if typ == "cast_aoe":
            payload = msg.get("payload") or {}
            shape = str(payload.get("shape") or payload.get("kind") or "").strip().lower()
            if shape not in ("circle", "square", "line", "sphere", "cube", "cone", "cylinder", "wall"):
                self._lan.toast(ws_id, "Pick a valid spell shape, matey.")
                return
            def parse_positive_float(value: Any) -> Optional[float]:
                try:
                    num = float(value)
                except Exception:
                    return None
                if num <= 0:
                    return None
                return num

            def parse_nonnegative_float(value: Any) -> Optional[float]:
                try:
                    num = float(value)
                except Exception:
                    return None
                if num < 0:
                    return None
                return num

            def parse_bool(value: Any) -> Optional[bool]:
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    raw = value.strip().lower()
                    if raw in ("true", "yes", "y", "1"):
                        return True
                    if raw in ("false", "no", "n", "0"):
                        return False
                return None

            def parse_trigger(value: Any) -> Optional[str]:
                if not isinstance(value, str):
                    return None
                raw = value.strip().lower()
                if raw in ("start", "enter"):
                    return raw
                if raw in ("start_or_enter", "start-or-enter", "start/enter"):
                    return "start_or_enter"
                return None

            def parse_default_damage(value: Any) -> Optional[str]:
                if value in (None, ""):
                    return None
                if isinstance(value, (int, float)):
                    return str(int(value))
                if isinstance(value, str):
                    raw = value.strip()
                    return raw or None
                return None

            def parse_dice(value: Any) -> Optional[str]:
                if not isinstance(value, str):
                    return None
                raw = value.strip().lower()
                match = re.fullmatch(r"(\\d+)d(4|6|8|10|12)", raw)
                if not match:
                    return None
                count = int(match.group(1))
                if count <= 0:
                    return None
                return f"{count}d{match.group(2)}"

            size = parse_positive_float(payload.get("size"))
            radius_ft = parse_positive_float(payload.get("radius_ft"))
            side_ft = parse_positive_float(payload.get("side_ft"))
            length_ft = parse_positive_float(payload.get("length_ft"))
            width_ft = parse_positive_float(payload.get("width_ft"))
            thickness_ft = parse_positive_float(payload.get("thickness_ft"))
            height_ft = parse_positive_float(payload.get("height_ft"))
            angle_deg = parse_nonnegative_float(payload.get("angle_deg"))
            duration_turns = payload.get("duration_turns")
            over_time = parse_bool(payload.get("over_time"))
            move_per_turn_ft = parse_nonnegative_float(payload.get("move_per_turn_ft"))
            trigger_on_start_or_enter = parse_trigger(payload.get("trigger_on_start_or_enter"))
            persistent = parse_bool(payload.get("persistent"))
            pinned_default = parse_bool(payload.get("pinned_default"))
            color = self._normalize_token_color(payload.get("color")) or ""
            name = str(payload.get("name") or "").strip()
            save_type = str(payload.get("save_type") or "").strip().lower()
            damage_type = str(payload.get("damage_type") or "").strip()
            raw_damage_types = payload.get("damage_types")
            damage_types: List[str] = []
            if isinstance(raw_damage_types, (list, tuple)):
                for entry in raw_damage_types:
                    dtype = str(entry or "").strip()
                    if dtype:
                        damage_types.append(dtype)
            if damage_types and not damage_type:
                damage_type = damage_types[0]
            half_on_pass = payload.get("half_on_pass")
            default_damage = parse_default_damage(payload.get("default_damage"))
            dice = parse_dice(payload.get("dice"))
            try:
                dc_val = int(payload.get("dc"))
            except Exception:
                dc_val = None
            over_time_flag = bool(over_time) if over_time is not None else False
            persistent_flag = bool(persistent) if persistent is not None else over_time_flag
            pinned_flag = bool(pinned_default) if pinned_default is not None else False
            duration_turns_val: Optional[int]
            if duration_turns in (None, ""):
                duration_turns_val = None
            else:
                try:
                    duration_turns_val = int(duration_turns)
                except Exception:
                    duration_turns_val = None
                if duration_turns_val is not None and duration_turns_val < 0:
                    duration_turns_val = None
            mw = getattr(self, "_map_window", None)
            map_ready = mw is not None and mw.winfo_exists()
            if map_ready:
                try:
                    self._lan_sync_aoes_to_map(mw)
                except Exception:
                    pass
            try:
                feet_per_square = float(getattr(mw, "feet_per_square", 5.0) or 5.0) if map_ready else 5.0
            except Exception:
                feet_per_square = 5.0
            if feet_per_square <= 0:
                feet_per_square = 5.0
            try:
                if map_ready:
                    cols = int(getattr(mw, "cols", 0))
                    rows = int(getattr(mw, "rows", 0))
                else:
                    cols = int(self._lan_grid_cols)
                    rows = int(self._lan_grid_rows)
            except Exception:
                cols = 0
                rows = 0
            try:
                cx = float(payload.get("cx"))
                cy = float(payload.get("cy"))
            except Exception:
                cx = None
                cy = None
            if cx is None or cy is None:
                _, _, _, positions = self._lan_live_map_data()
                if cid in positions:
                    cx = float(positions[cid][0])
                    cy = float(positions[cid][1])
                else:
                    cx = max(0.0, (cols - 1) / 2.0) if cols else 0.0
                    cy = max(0.0, (rows - 1) / 2.0) if rows else 0.0
            if cols and rows:
                cx = max(0.0, min(cx, cols - 1))
                cy = max(0.0, min(cy, rows - 1))
            if map_ready:
                aid = int(getattr(mw, "_next_aoe_id", 1))
                setattr(mw, "_next_aoe_id", aid + 1)
            else:
                aid = int(getattr(self, "_lan_next_aoe_id", 1))
                store = getattr(self, "_lan_aoes", {}) or {}
                if store:
                    max_aid = max(int(a) for a in store.keys())
                    if aid <= max_aid:
                        aid = max_aid + 1
                self._lan_next_aoe_id = aid + 1
            if cid is not None and cid in self.combatants:
                owner = str(self.combatants[cid].name)
                owner_cid = int(cid)
            else:
                owner = "DM"
                owner_cid = None
            aoe: Dict[str, Any] = {
                "kind": shape,
                "cx": float(cx),
                "cy": float(cy),
                "pinned": pinned_flag,
                "color": color
                or (
                    mw._aoe_default_color(shape)
                    if map_ready and hasattr(mw, "_aoe_default_color")
                    else ""
                ),
                "name": name or f"AoE {aid}",
                "shape": None,
                "label": None,
                "owner": owner,
                "owner_cid": owner_cid,
                "duration_turns": duration_turns_val,
                "remaining_turns": duration_turns_val if (duration_turns_val or 0) > 0 else None,
            }
            if over_time_flag:
                aoe["over_time"] = True
            if persistent_flag:
                aoe["persistent"] = True
            if trigger_on_start_or_enter:
                aoe["trigger_on_start_or_enter"] = trigger_on_start_or_enter
            if move_per_turn_ft is not None:
                aoe["move_per_turn_ft"] = move_per_turn_ft
                aoe["move_remaining_ft"] = move_per_turn_ft
            if dc_val is not None:
                aoe["dc"] = int(dc_val)
            if save_type:
                aoe["save_type"] = save_type
            if damage_types:
                aoe["damage_types"] = list(damage_types)
            if damage_type:
                aoe["damage_type"] = damage_type
            if half_on_pass is not None:
                aoe["half_on_pass"] = bool(half_on_pass)
            if dice:
                aoe["dice"] = dice
                if default_damage is None:
                    default_damage = dice
            if default_damage is not None:
                aoe["default_damage"] = default_damage
            if shape == "circle":
                if radius_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell radius, matey.")
                    return
                if radius_ft is not None:
                    aoe["radius_sq"] = max(0.5, float(radius_ft) / feet_per_square)
                    aoe["radius_ft"] = float(radius_ft)
                else:
                    aoe["radius_sq"] = float(size)
            elif shape in ("sphere", "cylinder"):
                if radius_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell radius, matey.")
                    return
                if radius_ft is not None:
                    aoe["radius_sq"] = max(0.5, float(radius_ft) / feet_per_square)
                    aoe["radius_ft"] = float(radius_ft)
                else:
                    aoe["radius_sq"] = float(size)
                if height_ft is not None:
                    aoe["height_ft"] = float(height_ft)
            elif shape == "square":
                if side_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell side length, matey.")
                    return
                if side_ft is not None:
                    aoe["side_sq"] = max(1.0, float(side_ft) / feet_per_square)
                    aoe["side_ft"] = float(side_ft)
                else:
                    aoe["side_sq"] = float(size)
            elif shape == "cube":
                if side_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell side length, matey.")
                    return
                if side_ft is not None:
                    aoe["side_sq"] = max(1.0, float(side_ft) / feet_per_square)
                    aoe["side_ft"] = float(side_ft)
                else:
                    aoe["side_sq"] = float(size)
            elif shape == "cone":
                if length_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell length, matey.")
                    return
                if angle_deg is None or angle_deg <= 0:
                    self._lan.toast(ws_id, "Pick a valid spell cone angle, matey.")
                    return
                if length_ft is not None:
                    aoe["length_sq"] = max(1.0, float(length_ft) / feet_per_square)
                    aoe["length_ft"] = float(length_ft)
                else:
                    aoe["length_sq"] = float(size)
                aoe["angle_deg"] = float(angle_deg)
                aoe["orient"] = str(payload.get("orient") or "vertical")
                aoe["ax"] = float(cx)
                aoe["ay"] = float(cy)
            elif shape == "wall":
                if length_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell length, matey.")
                    return
                if length_ft is not None:
                    aoe["length_sq"] = max(1.0, float(length_ft) / feet_per_square)
                    aoe["length_ft"] = float(length_ft)
                else:
                    aoe["length_sq"] = float(size)
                if width_ft is not None:
                    aoe["width_sq"] = max(1.0, float(width_ft) / feet_per_square)
                    aoe["width_ft"] = float(width_ft)
                    if height_ft is not None:
                        aoe["height_ft"] = float(height_ft)
                elif thickness_ft is not None and height_ft is not None:
                    aoe["width_sq"] = max(1.0, float(thickness_ft) / feet_per_square)
                    aoe["thickness_ft"] = float(thickness_ft)
                    aoe["height_ft"] = float(height_ft)
                else:
                    self._lan.toast(ws_id, "Pick a valid wall thickness and height, matey.")
                    return
                aoe["orient"] = str(payload.get("orient") or "vertical")
                if angle_deg is not None:
                    aoe["angle_deg"] = float(angle_deg)
                aoe["ax"] = float(cx)
                aoe["ay"] = float(cy)
            else:
                if length_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell length, matey.")
                    return
                if length_ft is not None:
                    aoe["length_sq"] = max(1.0, float(length_ft) / feet_per_square)
                    aoe["length_ft"] = float(length_ft)
                else:
                    aoe["length_sq"] = float(size)
                if width_ft is not None:
                    aoe["width_sq"] = max(1.0, float(width_ft) / feet_per_square)
                    aoe["width_ft"] = float(width_ft)
                else:
                    width = parse_positive_float(payload.get("width")) or 1.0
                    aoe["width_sq"] = max(1.0, float(width))
                aoe["orient"] = str(payload.get("orient") or "vertical")
                if angle_deg is not None:
                    aoe["angle_deg"] = float(angle_deg)
                aoe["ax"] = float(cx)
                aoe["ay"] = float(cy)
            if map_ready:
                mw.aoes[aid] = aoe
                try:
                    if hasattr(mw, "_create_aoe_items"):
                        mw._create_aoe_items(aid)
                    if hasattr(mw, "_refresh_aoe_list"):
                        mw._refresh_aoe_list(select=aid)
                except Exception:
                    pass
                try:
                    self._lan_aoes = dict(getattr(mw, "aoes", {}) or {})
                    self._lan_next_aoe_id = max(self._lan_next_aoe_id, aid + 1)
                except Exception:
                    pass
            else:
                store = getattr(self, "_lan_aoes", {}) or {}
                store[int(aid)] = aoe
                self._lan_aoes = store
            self._lan.toast(ws_id, f"Casted {aoe['name']}.")
            return
        elif typ == "aoe_move":
            aid = msg.get("aid")
            to = msg.get("to") or {}
            if not isinstance(aid, int):
                self._lan.toast(ws_id, "Pick a spell first, matey.")
                return
            try:
                cx = float(to.get("cx"))
                cy = float(to.get("cy"))
            except Exception:
                return
            mw = getattr(self, "_map_window", None)
            if mw is None or not mw.winfo_exists():
                self._lan.toast(ws_id, "Map window not open, matey.")
                return
            d = (getattr(mw, "aoes", {}) or {}).get(aid)
            if not d:
                return
            if bool(d.get("pinned")) and not is_admin:
                self._lan.toast(ws_id, "That spell be pinned.")
                return
            owner_cid = d.get("owner_cid")
            if owner_cid is not None and int(owner_cid) != int(cid) and not is_admin:
                self._lan.toast(ws_id, "That spell be not yers.")
                return
            move_per_turn_ft = d.get("move_per_turn_ft")
            move_remaining_ft = d.get("move_remaining_ft")
            if not is_admin and move_per_turn_ft not in (None, ""):
                if self.current_cid is None or int(self.current_cid) != int(cid):
                    self._lan.toast(ws_id, "Not yer turn yet, matey.")
                    return
                try:
                    move_limit = float(move_per_turn_ft)
                except Exception:
                    move_limit = None
                if move_limit is None or move_limit <= 0:
                    self._lan.toast(ws_id, "That spell can't move this turn.")
                    return
                try:
                    remaining = float(move_remaining_ft)
                except Exception:
                    remaining = move_limit
                try:
                    feet_per_square = float(getattr(mw, "feet_per_square", 5.0) or 5.0)
                except Exception:
                    feet_per_square = 5.0
                if feet_per_square <= 0:
                    feet_per_square = 5.0
                dx = float(cx) - float(d.get("cx") or 0.0)
                dy = float(cy) - float(d.get("cy") or 0.0)
                dist_ft = (dx * dx + dy * dy) ** 0.5 * feet_per_square
                if dist_ft > remaining + 0.01:
                    self._lan.toast(ws_id, f"That spell can only move {remaining:.1f} ft this turn.")
                    return
                d["move_remaining_ft"] = max(0.0, float(remaining) - dist_ft)
            try:
                cols = int(getattr(mw, "cols", 0))
                rows = int(getattr(mw, "rows", 0))
            except Exception:
                cols = 0
                rows = 0
            if cols and rows:
                cx = max(0.0, min(cx, cols - 1))
                cy = max(0.0, min(cy, rows - 1))
            d["cx"] = float(cx)
            d["cy"] = float(cy)
            try:
                if hasattr(mw, "_layout_aoe"):
                    mw._layout_aoe(aid)
            except Exception:
                pass
            return
        elif typ == "aoe_remove":
            aid = msg.get("aid")
            if not isinstance(aid, int):
                self._lan.toast(ws_id, "Pick a spell first, matey.")
                return
            mw = getattr(self, "_map_window", None)
            map_ready = mw is not None and mw.winfo_exists()
            aoe_store = getattr(mw, "aoes", {}) if map_ready else (getattr(self, "_lan_aoes", {}) or {})
            d = (aoe_store or {}).get(aid)
            if not d and map_ready:
                d = (getattr(self, "_lan_aoes", {}) or {}).get(aid)
            if not d:
                return
            if bool(d.get("pinned")) and not is_admin:
                self._lan.toast(ws_id, "That spell be pinned.")
                return
            owner_cid = d.get("owner_cid")
            if (
                owner_cid is not None
                and cid is not None
                and int(owner_cid) != int(cid)
                and not is_admin
            ):
                self._lan.toast(ws_id, "That spell be not yers.")
                return
            if owner_cid is not None and cid is None and not is_admin:
                self._lan.toast(ws_id, "That spell be not yers.")
                return
            if map_ready:
                try:
                    if hasattr(mw, "aoes") and isinstance(mw.aoes, dict):
                        mw.aoes.pop(aid, None)
                    if hasattr(mw, "_refresh_aoe_list"):
                        mw._refresh_aoe_list()
                except Exception:
                    pass
                try:
                    self._lan_aoes = dict(getattr(mw, "aoes", {}) or {})
                except Exception:
                    pass
            else:
                store = getattr(self, "_lan_aoes", {}) or {}
                store.pop(aid, None)
                self._lan_aoes = store
            return

        if typ == "move":
            to = msg.get("to") or {}
            try:
                col = int(to.get("col"))
                row = int(to.get("row"))
            except Exception:
                return

            ok, reason, cost = self._lan_try_move(cid, col, row)
            if not ok:
                self._lan.toast(ws_id, reason or "Can’t move there.")
            else:
                self._lan.toast(ws_id, f"Moved ({cost} ft).")
        elif typ == "dash":
            c = self.combatants.get(cid)
            if not c:
                return
            spend = str(msg.get("spend") or "").lower()
            if spend not in ("action", "bonus"):
                self._lan.toast(ws_id, "Choose action or bonus action, matey.")
                return
            if spend == "action":
                if not self._use_action(c):
                    self._lan.toast(ws_id, "No actions left, matey.")
                    return
                spend_label = "action"
            else:
                if not self._use_bonus_action(c):
                    self._lan.toast(ws_id, "No bonus actions left, matey.")
                    return
                spend_label = "bonus action"
            try:
                base_speed = int(self._mode_speed(c))
            except Exception:
                base_speed = int(getattr(c, "speed", 30) or 30)
            try:
                # Match map dash logic: add 30 to both numerator/denominator
                total = int(getattr(c, "move_total", 0) or 0)
                rem = int(getattr(c, "move_remaining", 0) or 0)
                setattr(c, "move_total", total + base_speed)
                setattr(c, "move_remaining", rem + base_speed)
                self._log(f"{c.name} dashed (move {rem}/{total} -> {c.move_remaining}/{c.move_total})", cid=cid)
                self._lan.toast(ws_id, f"Dashed ({spend_label}).")
                self._rebuild_table(scroll_to_current=True)
            except Exception:
                pass
        elif typ == "use_action":
            c = self.combatants.get(cid)
            if not c:
                return
            if not self._use_action(c):
                self._lan.toast(ws_id, "No actions left, matey.")
                return
            self._lan.toast(ws_id, "Action used.")
            self._rebuild_table(scroll_to_current=True)
        elif typ == "use_bonus_action":
            c = self.combatants.get(cid)
            if not c:
                return
            if not self._use_bonus_action(c):
                self._lan.toast(ws_id, "No bonus actions left, matey.")
                return
            self._lan.toast(ws_id, "Bonus action used.")
            self._rebuild_table(scroll_to_current=True)
        elif typ == "stand_up":
            c = self.combatants.get(cid)
            if not c:
                return
            if not self._has_condition(c, "prone"):
                return
            eff = self._effective_speed(c)
            if eff <= 0:
                self._lan.toast(ws_id, "Can't stand up right now (speed is 0).")
                return
            cost = max(0, eff // 2)
            if c.move_remaining < cost:
                self._lan.toast(ws_id, f"Not enough movement to stand (need {cost} ft).")
                return
            c.move_remaining -= cost
            self._remove_condition_type(c, "prone")
            self._log(f"stood up (spent {cost} ft, prone removed)", cid=c.cid)
            self._lan.toast(ws_id, "Stood up.")
            self._rebuild_table(scroll_to_current=True)
        elif typ == "reset_turn":
            if self._lan_restore_turn_snapshot(cid):
                c = self.combatants.get(cid)
                if c:
                    self._log(f"{c.name} reset their turn snapshot.", cid=cid)
                self._lan.toast(ws_id, "Turn reset.")
                self._rebuild_table(scroll_to_current=True)
            else:
                self._lan.toast(ws_id, "No turn snapshot yet, matey.")
        elif typ == "end_turn":
            # Let player end their own turn.
            try:
                self._next_turn()
            except Exception:
                pass

    def _lan_try_move(self, cid: int, col: int, row: int) -> Tuple[bool, str, int]:
        # Boundaries
        cols, rows, obstacles, positions = self._lan_live_map_data()
        if not (0 <= col < cols and 0 <= row < rows):
            return (False, "Off the map, matey.", 0)
        if (col, row) in obstacles:
            return (False, "That square be blocked.", 0)

        c = self.combatants.get(cid)
        if not c:
            return (False, "No such unit.", 0)

        origin = positions.get(cid)
        if origin is None:
            # seed at center
            origin = (max(0, cols // 2), max(0, rows // 2))
            self._lan_positions[cid] = origin

        max_ft = int(getattr(c, "move_remaining", 0) or 0)
        if max_ft <= 0:
            return (False, "No movement left, matey.", 0)

        cost = self._lan_shortest_cost(origin, (col, row), obstacles, cols, rows, max_ft)
        if cost is None:
            return (False, "Can’t reach that square (blocked).", 0)
        if cost > max_ft:
            return (False, f"Ye need {cost} ft but only {max_ft} ft be left.", 0)

        # Apply
        try:
            setattr(c, "move_remaining", max(0, max_ft - cost))
        except Exception:
            pass
        self._lan_positions[cid] = (col, row)

        # Update live map window token if open
        mw = getattr(self, "_map_window", None)
        try:
            if mw is not None and mw.winfo_exists():
                # place by cell -> pixel
                x, y = mw._grid_to_pixel(col, row)
                mw._place_unit_at_pixel(cid, x, y)
        except Exception:
            pass

        self._log(f"moved to ({col},{row}) (spent {cost} ft; {c.move_remaining}/{c.move_total} left)", cid=cid)
        self._rebuild_table(scroll_to_current=True)
        return (True, "", int(cost))

    def _lan_live_map_data(self) -> Tuple[int, int, set[Tuple[int, int]], Dict[int, Tuple[int, int]]]:
        cols = int(self._lan_grid_cols)
        rows = int(self._lan_grid_rows)
        obstacles = set(self._lan_obstacles)
        positions = dict(self._lan_positions)

        mw = getattr(self, "_map_window", None)
        try:
            if mw is not None and mw.winfo_exists():
                cols = int(getattr(mw, "cols", cols))
                rows = int(getattr(mw, "rows", rows))
                obstacles = set(getattr(mw, "obstacles", obstacles) or set())
                for cid, tok in (getattr(mw, "unit_tokens", {}) or {}).items():
                    try:
                        positions[int(cid)] = (int(tok.get("col")), int(tok.get("row")))
                    except Exception:
                        pass
        except Exception:
            pass
        return cols, rows, obstacles, positions

    def _lan_shortest_cost(
        self,
        origin: Tuple[int, int],
        dest: Tuple[int, int],
        obstacles: set[Tuple[int, int]],
        cols: int,
        rows: int,
        max_ft: int,
    ) -> Optional[int]:
        """Dijkstra over (col,row,diagParity) to match 5/10 diagonal rule.

        diagParity toggles when you take a diagonal step; first diagonal costs 5, second costs 10, then 5, etc.
        Orthogonal steps always cost 5 and do not change parity.
        """
        if origin == dest:
            return 0

        import heapq

        def in_bounds(c: int, r: int) -> bool:
            return 0 <= c < cols and 0 <= r < rows

        # (cost, col, row, parity)
        pq: List[Tuple[int, int, int, int]] = [(0, origin[0], origin[1], 0)]
        best: Dict[Tuple[int, int, int], int] = {(origin[0], origin[1], 0): 0}

        while pq:
            cost, c, r, parity = heapq.heappop(pq)
            if cost != best.get((c, r, parity), 10**9):
                continue
            if cost > max_ft:
                continue
            if (c, r) == dest:
                return cost

            # neighbors 8-dir
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    if dc == 0 and dr == 0:
                        continue
                    nc, nr = c + dc, r + dr
                    if not in_bounds(nc, nr):
                        continue
                    if (nc, nr) in obstacles:
                        continue

                    diag = (dc != 0 and dr != 0)
                    if diag:
                        step = 5 if parity == 0 else 10
                        npar = 1 - parity
                    else:
                        step = 5
                        npar = parity

                    ncost = cost + step
                    key = (nc, nr, npar)
                    if ncost < best.get(key, 10**9) and ncost <= max_ft:
                        best[key] = ncost
                        heapq.heappush(pq, (ncost, nc, nr, npar))

        return None



    # --------------------- Monsters (YAML library) ---------------------
    def _monsters_dir_path(self) -> Path:
        return Path.cwd() / "Monsters"

    def _load_monsters_index(self) -> None:
        """Load ./Monsters/*.yml|*.yaml and build a small index for the add dropdown."""
        self._monster_specs = []
        self._monsters_by_name = {}

        mdir = self._monsters_dir_path()
        try:
            mdir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        files: List[Path] = []
        try:
            files = sorted(list(mdir.glob("*.yml")) + list(mdir.glob("*.yaml")))
        except Exception:
            files = []

        index_path = _ensure_logs_dir() / "monster_index.json"
        index_data = _read_index_file(index_path)
        cached_entries = index_data.get("entries") if isinstance(index_data.get("entries"), dict) else {}
        new_entries: Dict[str, Any] = {}
        yaml_missing_logged = False

        if not files:
            _write_index_file(index_path, {"version": 1, "entries": {}})
            return

        for fp in files:
            meta = _file_stat_metadata(fp)
            entry = cached_entries.get(fp.name) if isinstance(cached_entries, dict) else None
            if isinstance(entry, dict) and _metadata_matches(entry, meta):
                summary = entry.get("summary")
                if isinstance(summary, dict):
                    name = str(summary.get("name") or "").strip()
                    if name:
                        spec = MonsterSpec(
                            filename=str(fp.name),
                            name=name,
                            mtype=str(summary.get("mtype") or "unknown").strip() or "unknown",
                            cr=summary.get("cr"),
                            hp=summary.get("hp"),
                            speed=summary.get("speed"),
                            swim_speed=summary.get("swim_speed"),
                            dex=summary.get("dex"),
                            init_mod=summary.get("init_mod"),
                            saving_throws=summary.get("saving_throws") if isinstance(summary.get("saving_throws"), dict) else {},
                            ability_mods=summary.get("ability_mods") if isinstance(summary.get("ability_mods"), dict) else {},
                            raw_data=summary.get("raw_data") if isinstance(summary.get("raw_data"), dict) else {},
                        )
                        if name not in self._monsters_by_name:
                            self._monsters_by_name[name] = spec
                        self._monster_specs.append(spec)

                        new_entry = dict(entry)
                        new_entry["mtime_ns"] = meta.get("mtime_ns")
                        new_entry["size"] = meta.get("size")
                        if not new_entry.get("hash"):
                            try:
                                raw = fp.read_text(encoding="utf-8")
                                new_entry["hash"] = _hash_text(raw)
                            except Exception:
                                pass
                        new_entries[fp.name] = new_entry
                        continue

            if yaml is None:
                if not yaml_missing_logged:
                    # Monster files are complex; be explicit so the user knows what to install.
                    try:
                        self._log("Monster YAML support requires PyYAML. Install: sudo apt install python3-yaml")
                    except Exception:
                        pass
                    yaml_missing_logged = True
                continue

            try:
                raw = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            try:
                data = yaml.safe_load(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            legacy_mon = data.get("monster")
            is_legacy = "monster" in data
            if is_legacy:
                if not isinstance(legacy_mon, dict):
                    continue
                mon = legacy_mon
            else:
                mon = data

            raw_data: Dict[str, Any] = {}
            abilities: Dict[str, Any] = {}
            if not is_legacy:
                for key in (
                    "name",
                    "size",
                    "type",
                    "alignment",
                    "initiative",
                    "challenge_rating",
                    "ac",
                    "hp",
                    "speed",
                    "traits",
                    "actions",
                    "legendary_actions",
                    "description",
                    "habitat",
                    "treasure",
                ):
                    if key in mon:
                        raw_data[key] = mon.get(key)
                ab = mon.get("abilities")
                if isinstance(ab, dict):
                    for key, val in ab.items():
                        if not isinstance(key, str):
                            continue
                        abilities[key.strip().lower()] = val
                    if abilities:
                        raw_data["abilities"] = abilities
            else:
                ab = mon.get("abilities")
                if isinstance(ab, dict):
                    for key, val in ab.items():
                        if not isinstance(key, str):
                            continue
                        abilities[key.strip().lower()] = val

            name = str(mon.get("name") or (fp.stem if is_legacy else "")).strip()
            if not name:
                continue

            mtype = str(mon.get("type") or "unknown").strip() or "unknown"

            cr_val = None
            try:
                if is_legacy:
                    ch = mon.get("challenge") or {}
                    if isinstance(ch, dict) and "cr" in ch:
                        cr_val = ch.get("cr")
                else:
                    cr_val = mon.get("challenge_rating")
            except Exception:
                cr_val = None
            cr: Optional[float] = None
            try:
                if isinstance(cr_val, (int, float)):
                    cr = float(cr_val)
                elif isinstance(cr_val, str) and cr_val.strip():
                    cr = float(cr_val.strip())
            except Exception:
                cr = None

            hp = None
            try:
                if is_legacy:
                    defs = mon.get("defenses") or {}
                    if isinstance(defs, dict):
                        hp_block = defs.get("hit_points") or {}
                        if isinstance(hp_block, dict):
                            avg = hp_block.get("average")
                            if isinstance(avg, int):
                                hp = int(avg)
                            elif isinstance(avg, str) and avg.strip().isdigit():
                                hp = int(avg.strip())
                else:
                    hp_val = mon.get("hp")
                    if isinstance(hp_val, int):
                        hp = int(hp_val)
                    elif isinstance(hp_val, str):
                        match = re.match(r"^\s*(\d+)", hp_val)
                        if match:
                            hp = int(match.group(1))
            except Exception:
                hp = None

            speed = None
            swim_speed = None
            try:
                if is_legacy:
                    sp = mon.get("speed") or {}
                    if isinstance(sp, dict):
                        wf = sp.get("walk_ft")
                        sf = sp.get("swim_ft")
                        if isinstance(wf, int):
                            speed = int(wf)
                        elif isinstance(wf, str) and wf.strip().isdigit():
                            speed = int(wf.strip())
                        if isinstance(sf, int):
                            swim_speed = int(sf)
                        elif isinstance(sf, str) and sf.strip().isdigit():
                            swim_speed = int(sf.strip())
                else:
                    sp = mon.get("speed")
                    if isinstance(sp, int):
                        speed = int(sp)
                    elif isinstance(sp, str) and sp.strip().lstrip("-").isdigit():
                        speed = int(sp.strip())
            except Exception:
                speed = None
                swim_speed = None

            dex = None
            try:
                ab = abilities if abilities else (mon.get("abilities") or {})
                if isinstance(ab, dict):
                    dv = ab.get("dex")
                    if isinstance(dv, int):
                        dex = int(dv)
                    elif isinstance(dv, str) and dv.strip().lstrip("-").isdigit():
                        dex = int(dv.strip())
            except Exception:
                dex = None

            init_mod = None
            try:
                ini = mon.get("initiative") or {}
                if isinstance(ini, dict):
                    mv = ini.get("modifier")
                    if isinstance(mv, int):
                        init_mod = int(mv)
                    elif isinstance(mv, str) and mv.strip().lstrip("-").isdigit():
                        init_mod = int(mv.strip())
            except Exception:
                init_mod = None

            saving_throws: Dict[str, int] = {}
            try:
                saves = mon.get("saving_throws") or {}
                if isinstance(saves, dict):
                    for key, val in saves.items():
                        if not isinstance(key, str):
                            continue
                        ability = key.strip().lower()
                        if ability not in {"str", "dex", "con", "int", "wis", "cha"}:
                            continue
                        if isinstance(val, int):
                            saving_throws[ability] = int(val)
                        elif isinstance(val, str):
                            raw = val.strip()
                            if raw.startswith("+"):
                                raw = raw[1:]
                            if raw.lstrip("-").isdigit():
                                saving_throws[ability] = int(raw)
            except Exception:
                saving_throws = {}

            ability_mods: Dict[str, int] = {}
            try:
                ab = abilities if abilities else (mon.get("abilities") or {})
                if isinstance(ab, dict):
                    for key, val in ab.items():
                        if not isinstance(key, str):
                            continue
                        ability = key.strip().lower()
                        if ability not in {"str", "dex", "con", "int", "wis", "cha"}:
                            continue
                        score = None
                        if isinstance(val, int):
                            score = int(val)
                        elif isinstance(val, str):
                            raw = val.strip()
                            if raw.lstrip("-").isdigit():
                                score = int(raw)
                        if score is None:
                            continue
                        ability_mods[ability] = (score - 10) // 2
            except Exception:
                ability_mods = {}

            spec = MonsterSpec(
                filename=str(fp.name),
                name=name,
                mtype=mtype,
                cr=cr,
                hp=hp,
                speed=speed,
                swim_speed=swim_speed,
                dex=dex,
                init_mod=init_mod,
                saving_throws=saving_throws,
                ability_mods=ability_mods,
                raw_data=raw_data,
            )

            if name not in self._monsters_by_name:
                self._monsters_by_name[name] = spec
            self._monster_specs.append(spec)

            new_entries[fp.name] = {
                "mtime_ns": meta.get("mtime_ns"),
                "size": meta.get("size"),
                "hash": _hash_text(raw),
                "summary": {
                    "name": name,
                    "mtype": mtype,
                    "cr": cr,
                    "hp": hp,
                    "speed": speed,
                    "swim_speed": swim_speed,
                    "dex": dex,
                    "init_mod": init_mod,
                    "saving_throws": saving_throws,
                    "ability_mods": ability_mods,
                    "raw_data": raw_data,
                },
            }

        self._monster_specs.sort(key=lambda s: s.name.lower())
        _write_index_file(index_path, {"version": 1, "entries": new_entries})

    def _monster_names_sorted(self) -> List[str]:
        return [s.name for s in self._monster_specs]

    def _install_monster_dropdown_widget(self) -> None:
        """Replace the Name Entry with a Combobox listing ./Monsters YAML files."""
        try:
            add_frame = None

            def walk(w):
                nonlocal add_frame
                try:
                    if isinstance(w, ttk.Labelframe) and str(w.cget("text")) == "Add Combatant":
                        add_frame = w
                        return
                except Exception:
                    pass
                for ch in w.winfo_children():
                    walk(ch)

            walk(self)
            if add_frame is None:
                return

            target = None
            for ch in add_frame.winfo_children():
                try:
                    gi = ch.grid_info()
                    if int(gi.get("row", -1)) == 1 and int(gi.get("column", -1)) == 0:
                        target = ch
                        break
                except Exception:
                    continue

            if target is not None:
                try:
                    target.destroy()
                except Exception:
                    pass

            holder = ttk.Frame(add_frame)
            holder.grid(row=1, column=0, padx=(0, 8), sticky="w")

            values = self._monster_names_sorted()
            combo = ttk.Combobox(holder, textvariable=self.name_var, values=values, width=22)
            combo.pack(side="left")
            combo.bind("<<ComboboxSelected>>", lambda e: self._on_monster_selected())

            btn = ttk.Button(holder, text="📜", width=3, command=self._open_monster_library)
            btn.pack(side="left", padx=(4, 0))

            info_btn = ttk.Button(holder, text="Info", width=5, command=self._open_monster_stat_block)
            info_btn.pack(side="left", padx=(4, 0))

            self._monster_combo = combo  # type: ignore[attr-defined]

            if values and not self.name_var.get().strip():
                self.name_var.set(values[0])
                self._on_monster_selected()
        except Exception:
            return

    def _monster_int_from_value(self, value: object) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("+"):
                raw = raw[1:]
            if raw.lstrip("-").isdigit():
                return int(raw)
        return None

    def _format_monster_simple_value(self, value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _format_monster_modifier(self, value: object) -> str:
        mod = self._monster_int_from_value(value)
        if mod is None:
            return self._format_monster_simple_value(value)
        return f"{mod:+d}"

    def _format_monster_initiative(self, value: object) -> str:
        if isinstance(value, dict):
            if "modifier" in value:
                return self._format_monster_modifier(value.get("modifier"))
            return self._format_monster_simple_value(value)
        return self._format_monster_modifier(value)

    def _format_monster_ac(self, value: object) -> str:
        if isinstance(value, dict):
            for key in ("value", "ac"):
                if key in value:
                    return self._format_monster_simple_value(value.get(key))
        return self._format_monster_simple_value(value)

    def _format_monster_hp(self, value: object) -> str:
        if isinstance(value, dict):
            if "average" in value:
                return self._format_monster_simple_value(value.get("average"))
        return self._format_monster_simple_value(value)

    def _format_monster_speed(self, value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, dict):
            parts = []
            for key, val in value.items():
                label = str(key).replace("_", " ")
                parts.append(f"{label} {self._format_monster_simple_value(val)}")
            return ", ".join(parts) if parts else "—"
        return self._format_monster_simple_value(value)

    def _format_monster_text_block(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts = []
            for entry in value:
                text = self._format_monster_text_block(entry)
                if text:
                    parts.append(text)
            return "; ".join(parts)
        if isinstance(value, dict):
            parts = []
            for key, entry in value.items():
                text = self._format_monster_text_block(entry)
                if text:
                    parts.append(f"{key}: {text}")
            return ", ".join(parts)
        return str(value)

    def _format_monster_feature_lines(self, value: object) -> List[str]:
        lines: List[str] = []
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    name = entry.get("name") or entry.get("title")
                    desc = entry.get("desc") or entry.get("description") or entry.get("text")
                    if name and desc:
                        lines.append(f"- {name}: {self._format_monster_text_block(desc)}")
                    elif name:
                        lines.append(f"- {name}")
                    elif desc:
                        lines.append(f"- {self._format_monster_text_block(desc)}")
                elif isinstance(entry, str):
                    text = entry.strip()
                    if text:
                        lines.append(f"- {text}")
        elif isinstance(value, dict):
            for key, entry in value.items():
                text = self._format_monster_text_block(entry)
                if text:
                    lines.append(f"- {key}: {text}")
        elif isinstance(value, str):
            text = value.strip()
            if text:
                lines.append(text)
        return lines

    def _monster_stat_block_text(self, spec: MonsterSpec) -> str:
        raw = spec.raw_data or {}
        lines: List[str] = []
        lines.append(spec.name)
        lines.append("")
        lines.append("Identity")
        lines.append(f"Name: {spec.name}")
        lines.append(f"Size: {self._format_monster_simple_value(raw.get('size'))}")
        lines.append(f"Type: {self._format_monster_simple_value(raw.get('type') or spec.mtype)}")
        lines.append(f"Alignment: {self._format_monster_simple_value(raw.get('alignment'))}")
        lines.append(f"Initiative: {self._format_monster_initiative(raw.get('initiative'))}")
        lines.append(f"AC: {self._format_monster_ac(raw.get('ac'))}")
        lines.append(f"HP: {self._format_monster_hp(raw.get('hp'))}")
        lines.append(f"Speed: {self._format_monster_speed(raw.get('speed'))}")
        lines.append("")
        lines.append("Ability Scores")
        abilities = raw.get("abilities")
        ability_lines = []
        if isinstance(abilities, dict):
            for ab in ("str", "dex", "con", "int", "wis", "cha"):
                if ab not in abilities:
                    continue
                score = self._monster_int_from_value(abilities.get(ab))
                if score is None:
                    continue
                mod = (score - 10) // 2
                ability_lines.append(f"{ab.upper()} {score} ({mod:+d})")
        if ability_lines:
            lines.append("  " + " | ".join(ability_lines))
        else:
            lines.append("  No ability scores available.")

        def add_section(title: str, value: object) -> None:
            lines.append("")
            lines.append(title)
            entries = self._format_monster_feature_lines(value)
            if entries:
                lines.extend(entries)
            else:
                lines.append(f"No {title.lower()} available.")

        add_section("Traits", raw.get("traits"))
        add_section("Actions", raw.get("actions"))
        add_section("Legendary Actions", raw.get("legendary_actions"))

        def add_single_line_section(title: str, value: object) -> None:
            text = self._format_monster_text_block(value)
            lines.append("")
            lines.append(title)
            if text:
                lines.append(text)
            else:
                lines.append(f"No {title.lower()} available.")

        add_single_line_section("Description", raw.get("description"))
        add_single_line_section("Habitat", raw.get("habitat"))
        add_single_line_section("Treasure", raw.get("treasure"))
        return "\n".join(lines)

    def _open_monster_stat_block(self, spec: Optional[MonsterSpec] = None) -> None:
        if spec is None:
            nm = self.name_var.get().strip()
            spec = self._monsters_by_name.get(nm)

        win = tk.Toplevel(self)
        title = f"{spec.name} Stat Block" if spec else "Monster Info"
        win.title(title)
        win.geometry("560x680")
        win.transient(self)
        win.after(0, win.grab_set)

        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)

        if not spec or not spec.raw_data:
            ttk.Label(
                body,
                text="No stat block available for this monster.",
                wraplength=520,
                justify="left",
            ).pack(anchor="w")
            return

        text = tk.Text(body, wrap="word")
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        text.insert("1.0", self._monster_stat_block_text(spec))
        text.configure(state="disabled")

    def _on_monster_selected(self) -> None:
        nm = self.name_var.get().strip()
        spec = self._monsters_by_name.get(nm)
        if not spec:
            return

        try:
            if spec.hp is not None:
                self.hp_var.set(str(spec.hp))
            if spec.speed is not None:
                self.speed_var.set(str(spec.speed))
            if spec.swim_speed is not None and spec.swim_speed > 0:
                self.swim_var.set(str(spec.swim_speed))
            else:
                self.swim_var.set("")
            if spec.dex is not None:
                try:
                    dex_mod = (int(spec.dex) - 10) // 2
                except Exception:
                    dex_mod = None
                if dex_mod is not None:
                    self.dex_var.set(str(dex_mod))
        except Exception:
            pass

        mod = spec.init_mod
        if mod is None and spec.dex is not None:
            try:
                mod = (int(spec.dex) - 10) // 2
            except Exception:
                mod = None
        if mod is not None:
            r = random.randint(1, 20)
            self.init_var.set(str(r + int(mod)))

    def _open_monster_library(self) -> None:
        win = tk.Toplevel(self)
        win.title("Monster Library")
        win.geometry("720x560")
        win.transient(self)
        win.after(0, win.lift)

        top = ttk.Frame(win, padding=10)
        top.pack(fill="both", expand=True)

        ctrl = ttk.Frame(top)
        ctrl.pack(fill="x", pady=(0, 8))

        ttk.Label(ctrl, text="Filter type").pack(side="left")
        type_var = tk.StringVar(value="All")
        types = sorted({s.mtype for s in self._monster_specs})
        type_box = ttk.Combobox(ctrl, textvariable=type_var, values=["All"] + types, width=18, state="readonly")
        type_box.pack(side="left", padx=(6, 12))

        ttk.Label(ctrl, text="Sort").pack(side="left")
        sort_var = tk.StringVar(value="Name")
        sort_box = ttk.Combobox(ctrl, textvariable=sort_var, values=["Name", "Type", "CR"], width=10, state="readonly")
        sort_box.pack(side="left", padx=(6, 12))

        ttk.Button(ctrl, text="Reload", command=lambda: self._monster_library_reload(win)).pack(side="right")
        ttk.Button(ctrl, text="Info", command=lambda: open_info()).pack(side="right", padx=(0, 8))

        search_row = ttk.Frame(top)
        search_row.pack(fill="x", pady=(0, 8))

        ttk.Label(search_row, text="Search").pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_row, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

        cols = ("name", "type", "cr", "file")
        tree_frame = ttk.Frame(top)
        tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=18)
        tree.heading("name", text="Name")
        tree.heading("type", text="Type")
        tree.heading("cr", text="CR")
        tree.heading("file", text="File")

        tree.column("name", width=240, anchor="w")
        tree.column("type", width=160, anchor="w")
        tree.column("cr", width=70, anchor="center")
        tree.column("file", width=200, anchor="w")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def get_filtered() -> List[MonsterSpec]:
            tsel = type_var.get()
            specs = self._monster_specs
            if tsel and tsel != "All":
                specs = [s for s in specs if s.mtype == tsel]
            query = search_var.get().strip().lower()
            if query:
                specs = [s for s in specs if query in s.name.lower()]
            sm = sort_var.get()
            if sm == "Type":
                return sorted(specs, key=lambda s: (s.mtype.lower(), s.name.lower()))
            if sm == "CR":
                return sorted(specs, key=lambda s: (s.cr is None, s.cr if s.cr is not None else 9999.0, s.name.lower()))
            return sorted(specs, key=lambda s: s.name.lower())

        def refresh():
            tree.delete(*tree.get_children())
            for s in get_filtered():
                cr_txt = "" if s.cr is None else (str(int(s.cr)) if float(s.cr).is_integer() else str(s.cr))
                tree.insert("", "end", iid=f"{s.filename}:{s.name}", values=(s.name, s.mtype, cr_txt, s.filename))

        def on_select(event=None):
            sel = tree.selection()
            if not sel:
                return
            iid = sel[0]
            try:
                _fn, nm = iid.split(":", 1)
            except Exception:
                nm = tree.item(iid, "values")[0]
            self.name_var.set(nm)
            self._on_monster_selected()
            try:
                win.destroy()
            except Exception:
                pass

        def open_info():
            sel = tree.selection()
            if not sel:
                return
            iid = sel[0]
            try:
                _fn, nm = iid.split(":", 1)
            except Exception:
                nm = tree.item(iid, "values")[0]
            spec = self._monsters_by_name.get(nm)
            self._open_monster_stat_block(spec)

        def on_keypress(event):
            ch = (event.char or "").lower()
            if len(ch) != 1 or ch < "a" or ch > "z":
                return
            for iid in tree.get_children():
                values = tree.item(iid, "values")
                if values and values[0].lower().startswith(ch):
                    tree.selection_set(iid)
                    tree.focus(iid)
                    tree.see(iid)
                    break

        tree.bind("<Double-1>", on_select)
        tree.bind("<KeyPress>", on_keypress)
        type_box.bind("<<ComboboxSelected>>", lambda e: refresh())
        sort_box.bind("<<ComboboxSelected>>", lambda e: refresh())
        search_var.trace_add("write", lambda *_: refresh())

        refresh()

    def _monster_library_reload(self, libwin: tk.Toplevel) -> None:
        self._load_monsters_index()
        try:
            combo = getattr(self, "_monster_combo", None)
            if combo is not None:
                combo["values"] = self._monster_names_sorted()
        except Exception:
            pass

        try:
            libwin.destroy()
        except Exception:
            pass
        self._open_monster_library()



def main() -> None:
    app = InitiativeTracker()
    app.mainloop()


if __name__ == "__main__":
    main()
