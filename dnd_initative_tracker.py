#!/usr/bin/env python3
"""
DnD Initiative Tracker (v41) — LAN Proof-of-Concept

This edition layers a small LAN/mobile web client on top of the Tk app without rewriting it.
- DM runs the Tk app.
- LAN server starts automatically (and can be stopped/restarted from the "LAN" menu).
- Players open the LAN URL on mobile and claim any Player Character, then can move their token (on their turn).
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
import json
import queue
import socket
import threading
import time
import logging
import re
from datetime import datetime
from dataclasses import dataclass
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


class LanAccountStore:
    """Persist LAN accounts + ownership into a simple JSON file."""

    def __init__(self, path: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        self._path = path or (_ensure_logs_dir() / "lan_accounts.json")
        self._logger = logger
        self._data: Dict[str, Any] = {"accounts": {}}
        self._ownership: Dict[int, str] = {}
        self.load()

    def load(self) -> None:
        try:
            if not self._path.exists():
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        accounts_raw = raw.get("accounts", {})
        accounts: Dict[str, Dict[str, Any]] = {}
        if isinstance(accounts_raw, dict):
            candidates = list(accounts_raw.values())
        elif isinstance(accounts_raw, list):
            candidates = accounts_raw
        else:
            candidates = []
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            username = str(entry.get("username", "")).strip()
            if not username:
                continue
            created_at = str(entry.get("created_at", "")).strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preset = entry.get("preset")
            if not isinstance(preset, dict):
                preset = None
            owned_raw = entry.get("owned_cids", [])
            owned: List[int] = []
            if isinstance(owned_raw, list):
                for cid in owned_raw:
                    try:
                        owned.append(int(cid))
                    except Exception:
                        continue
            account: Dict[str, Any] = {"username": username, "created_at": created_at, "owned_cids": owned}
            if preset is not None:
                account["preset"] = preset
            accounts[username] = account
        self._data["accounts"] = accounts
        self._rebuild_ownership()

    def save(self) -> None:
        try:
            payload = {"accounts": list(self._data.get("accounts", {}).values())}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            if self._logger:
                self._logger.warning("Failed to save LAN accounts: %s", exc)

    def ensure_account(self, username: str) -> Dict[str, Any]:
        username = str(username).strip()
        if not username:
            raise ValueError("Username required.")
        accounts = self._data.setdefault("accounts", {})
        account = accounts.get(username)
        if account:
            return account
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        account = {"username": username, "created_at": created_at, "owned_cids": []}
        accounts[username] = account
        self.save()
        return account

    def preset_for(self, username: str) -> Optional[Dict[str, Any]]:
        username = str(username).strip()
        if not username:
            return None
        account = self._data.get("accounts", {}).get(username)
        if not isinstance(account, dict):
            return None
        preset = account.get("preset")
        if isinstance(preset, dict):
            try:
                return json.loads(json.dumps(preset))
            except Exception:
                return dict(preset)
        return None

    def set_preset(self, username: str, preset: Optional[Dict[str, Any]]) -> bool:
        username = str(username).strip()
        if not username:
            return False
        if preset is not None and not isinstance(preset, dict):
            return False
        account = self.ensure_account(username)
        if preset is None:
            account.pop("preset", None)
        else:
            account["preset"] = preset
        self.save()
        return True

    def owner_for(self, cid: int) -> Optional[str]:
        try:
            cid = int(cid)
        except Exception:
            return None
        return self._ownership.get(cid)

    def claim(self, cid: int, username: str, force: bool = False) -> bool:
        try:
            cid = int(cid)
        except Exception:
            return False
        username = str(username).strip()
        if not username:
            return False
        owner = self._ownership.get(cid)
        if owner and owner != username and not force:
            return False
        if owner and owner != username and force:
            old_account = self._data.get("accounts", {}).get(owner)
            if old_account:
                old_account["owned_cids"] = [c for c in old_account.get("owned_cids", []) if int(c) != cid]
        account = self.ensure_account(username)
        if cid not in account.get("owned_cids", []):
            account["owned_cids"].append(cid)
        self._ownership[cid] = username
        self.save()
        return True

    def clear_owner(self, cid: int) -> bool:
        try:
            cid = int(cid)
        except Exception:
            return False
        owner = self._ownership.get(cid)
        if not owner:
            return False
        account = self._data.get("accounts", {}).get(owner)
        if account:
            account["owned_cids"] = [c for c in account.get("owned_cids", []) if int(c) != cid]
        self._ownership.pop(cid, None)
        self.save()
        return True

    def accounts_snapshot(self) -> List[Dict[str, Any]]:
        accounts = self._data.get("accounts", {})
        if not isinstance(accounts, dict):
            return []
        return [dict(account) for account in accounts.values() if isinstance(account, dict)]

    def ownership_snapshot(self) -> Dict[int, str]:
        return dict(self._ownership)

    def _rebuild_ownership(self) -> None:
        self._ownership = {}
        accounts = self._data.get("accounts", {})
        if not isinstance(accounts, dict):
            return
        for username, account in accounts.items():
            if not isinstance(account, dict):
                continue
            for cid in account.get("owned_cids", []):
                try:
                    self._ownership[int(cid)] = str(username)
                except Exception:
                    continue


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
    .cast-panel summary{
      cursor:pointer;
      font-weight:700;
      list-style:none;
    }
    .cast-panel summary::-webkit-details-marker{display:none;}
    .cast-panel[open] summary{margin-bottom:8px;}
    .form-grid{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap:8px;
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
      position:absolute; inset:0; background: rgba(0,0,0,0.55);
      display:none; align-items:center; justify-content:center; padding: 20px 14px;
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
      max-height: calc(100vh - var(--safeInsetTop) - var(--safeInsetBottom) - 40px);
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
    .login-screen{
      position:fixed;
      inset:0;
      display:none;
      align-items:center;
      justify-content:center;
      background: radial-gradient(circle at top, rgba(20,25,35,0.95), rgba(10,12,18,0.98));
      padding: 20px;
      z-index: 40;
    }
    .login-card{
      width: min(360px, 100%);
      background: rgba(20,25,35,0.95);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 16px;
      padding: 18px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.45);
      display:flex;
      flex-direction:column;
      gap:12px;
    }
    .login-card h2{margin:0; font-size: 18px;}
    .login-card p{margin:0; color: var(--muted); font-size: 13px;}
    .login-actions{
      display:flex;
      justify-content:flex-end;
      margin-top: 4px;
    }
    .login-error{
      color: var(--danger);
      font-size: 12px;
      min-height: 16px;
    }
    body.login-required .app{display:none;}
    body.login-required .login-screen{display:flex;}
    @media (max-width: 720px), (max-height: 720px){
      .btn{padding: 6px 8px; font-size: 12px;}
      .topbar{gap:8px; padding: calc(8px + var(--safeInsetTop)) 10px 8px 10px;}
      .sheet{padding: 8px 10px calc(10px + var(--safeInsetBottom)) 10px;}
    }
  </style>
</head>
<body>
<div class="login-screen" id="loginScreen" aria-live="polite">
  <form class="login-card" id="loginForm">
    <h2>Join the table</h2>
    <p>Enter a username to connect to the initiative tracker.</p>
    <div class="form-field">
      <label for="loginName">Username</label>
      <input id="loginName" type="text" autocomplete="name" maxlength="32" placeholder="E.g. Captain Rook" required />
    </div>
    <div class="login-error" id="loginError"></div>
    <div class="login-actions">
      <button class="btn accent" type="submit">Enter</button>
    </div>
  </form>
</div>
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
    <div class="spacer"></div>
    <button class="btn" id="configBtn">Config</button>
    <div class="topbar-controls">
      <button class="btn" id="lockMap">Lock Map</button>
      <button class="btn" id="centerMap">Center on Me</button>
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
      <div class="card">
        <h2>Battle Log</h2>
        <div class="log-content" id="logContent">Loading…</div>
        <div class="modal-actions">
          <button class="btn accent" id="logRefresh">Refresh</button>
          <button class="btn" id="logClose">Close</button>
        </div>
      </div>
    </div>
    <div class="modal" id="configModal" aria-hidden="true">
      <div class="card">
        <h2>Config</h2>
        <details class="config-section" open>
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
        <div class="modal-actions">
          <button class="btn" id="configClose">Close</button>
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
      <details class="cast-panel" id="castPanel">
        <summary>Cast Spell</summary>
        <form id="castForm">
          <div class="form-grid">
            <div class="form-field">
              <label for="castPreset">Preset</label>
              <select id="castPreset">
                <option value="" selected>Custom</option>
              </select>
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
          <div class="form-actions">
            <button class="btn accent" type="submit">Cast</button>
          </div>
        </form>
      </details>
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
  let swRegistration = null;

  function setNotificationStatus(message){
    if (!notificationStatus) return;
    notificationStatus.textContent = message;
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
  const configModal = document.getElementById("configModal");
  const configCloseBtn = document.getElementById("configClose");
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
  const resetTurnBtn = document.getElementById("resetTurn");
  const standUpBtn = document.getElementById("standUp");
  const showAllNamesEl = document.getElementById("showAllNames");
  const castPanel = document.getElementById("castPanel");
  const castForm = document.getElementById("castForm");
  const castPresetInput = document.getElementById("castPreset");
  const castNameInput = document.getElementById("castName");
  const castShapeInput = document.getElementById("castShape");
  const castRadiusField = document.getElementById("castRadiusField");
  const castSideField = document.getElementById("castSideField");
  const castLengthField = document.getElementById("castLengthField");
  const castWidthField = document.getElementById("castWidthField");
  const castRadiusInput = document.getElementById("castRadius");
  const castSideInput = document.getElementById("castSide");
  const castLengthInput = document.getElementById("castLength");
  const castWidthInput = document.getElementById("castWidth");
  const castDcTypeInput = document.getElementById("castDcType");
  const castDcValueInput = document.getElementById("castDcValue");
  const castDefaultDamageInput = document.getElementById("castDefaultDamage");
  const castDiceInput = document.getElementById("castDice");
  const castSlotLevelInput = document.getElementById("castSlotLevel");
  const castDamageTypeInput = document.getElementById("castDamageType");
  const castDamageTypeList = document.getElementById("castDamageTypeList");
  const castAddDamageTypeBtn = document.getElementById("castAddDamageType");
  const castColorInput = document.getElementById("castColor");
  const loginScreen = document.getElementById("loginScreen");
  const loginForm = document.getElementById("loginForm");
  const loginNameInput = document.getElementById("loginName");
  const loginError = document.getElementById("loginError");
  const sheetWrap = document.getElementById("sheetWrap");
  const sheetHandle = document.getElementById("sheetHandle");
  const turnAlertAudio = new Audio("/assets/alert.wav");
  turnAlertAudio.preload = "auto";
  const koAlertAudio = new Audio("/assets/ko.wav");
  koAlertAudio.preload = "auto";
  let audioUnlocked = false;
  let pendingTurnAlert = false;
  let pendingVibrate = false;
  let lastVibrateSupported = canVibrate;
  let userHasInteracted = navigator.userActivation?.hasBeenActive ?? false;

  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");

  let ws = null;
  let state = null;
  let reconnectTimer = null;
  let reconnecting = false;
  const clientId = (() => {
    const key = "inittracker_clientId";
    let value = localStorage.getItem(key);
    if (!value){
      if (crypto && typeof crypto.randomUUID === "function"){
        value = crypto.randomUUID();
      } else {
        const rand = Math.random().toString(36).slice(2, 10);
        value = `${Date.now().toString(36)}-${rand}`;
      }
      localStorage.setItem(key, value);
    }
    return value;
  })();
  const usernameKey = "inittracker_username";
  let storedUsername = localStorage.getItem(usernameKey) || "";
  let claimedCid = null;
  let shownNoOwnedToast = false;
  let pendingClaim = null;
  let lastPcList = [];
  let lastActiveCid = null;
  let lastTurnRound = null;
  let selectedTurnCid = null;
  let loggedIn = false;

  // view transform
  let zoom = 32; // px per square
  let panX = 0, panY = 0;
  let dragging = null; // {cid, startX, startY, origCol, origRow}
  let draggingAoe = null; // {aid, cx, cy}
  const aoeDragOverrides = new Map(); // aid -> {cx, cy}
  let panning = null;  // {x,y, panX, panY}
  let centeredCid = null;
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
  if (loginNameInput){
    loginNameInput.value = storedUsername;
  }
  setLoginState(false);
  if (iosInstallHint){
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    const isSafariEngine = /AppleWebKit/.test(navigator.userAgent);
    const isAltBrowser = /CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
    const isStandalone = window.navigator.standalone === true;
    const showHint = isIOS && isSafariEngine && !isAltBrowser && !isStandalone;
    iosInstallHint.classList.toggle("hidden", !showHint);
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
  }

  function hideConfigModal(){
    if (!configModal) return;
    configModal.classList.remove("show");
    configModal.setAttribute("aria-hidden", "true");
  }

  function send(msg){
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify(msg));
  }

  function setLoginState(isLoggedIn){
    loggedIn = isLoggedIn;
    document.body.classList.toggle("login-required", !isLoggedIn);
    if (isLoggedIn && loginError){
      loginError.textContent = "";
    }
  }

  function setLoginError(text){
    if (!loginError) return;
    loginError.textContent = text || "";
  }

  function sendHello(){
    if (!loginNameInput) return;
    const username = loginNameInput.value.trim();
    if (!username){
      setLoginError("Username required.");
      return;
    }
    if (!ws || ws.readyState !== 1){
      setLoginError("Not connected yet. Try again in a moment.");
      return;
    }
    send({
      type: "hello",
      username,
      claimed: claimedCid ? Number(claimedCid) : null,
      client_id: clientId,
    });
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
    pendingClaim = unit || null;
    let preferred = normalizeHexColor(unit?.token_color)
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
    if (!loggedIn) return;
    const me = (storedUsername || "").trim();
    if (!me) return;
    const list = Array.isArray(pcs) ? pcs : [];
    const ownedByMe = list.some(u => String(u.owned_by || "") === me);
    if (ownedByMe) return;
    localToast("No owned PCs found. Ask the DM to assign yer character.");
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
      if (a.kind === "circle"){
        const r = Math.max(0, Number(a.radius_sq || 0)) * zoom;
        if (dx * dx + dy * dy <= r * r){
          return a;
        }
      } else if (a.kind === "square"){
        const half = Math.max(0, Number(a.side_sq || 0)) * zoom / 2;
        if (Math.abs(dx) <= half && Math.abs(dy) <= half){
          return a;
        }
      } else if (a.kind === "line"){
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
        const remainingTurns = Number(a.remaining_turns);
        if (Number.isFinite(remainingTurns) && remainingTurns <= 0){
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
        if (a.kind === "circle"){
          const r = Math.max(0, Number(a.radius_sq || 0)) * zoom;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, 0.28) : "rgba(168,197,255,0.32)";
          ctx.strokeStyle = colorHex || "rgba(45,79,138,0.85)";
          ctx.fill();
          ctx.stroke();
        } else if (a.kind === "line"){
          const lengthPx = Math.max(0, Number(a.length_sq || 0)) * zoom;
          const widthPx = Math.max(0, Number(a.width_sq || 0)) * zoom;
          const angleDeg = Number.isFinite(Number(a.angle_deg)) ? Number(a.angle_deg) : null;
          const orient = a.orient === "horizontal" ? "horizontal" : "vertical";
          const halfW = orient === "horizontal" ? lengthPx / 2 : widthPx / 2;
          const halfH = orient === "horizontal" ? widthPx / 2 : lengthPx / 2;
          ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, 0.28) : "rgba(183,255,224,0.32)";
          ctx.strokeStyle = colorHex || "rgba(45,138,87,0.85)";
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
        } else if (a.kind === "square"){
          const sidePx = Math.max(0, Number(a.side_sq || 0)) * zoom;
          const half = sidePx / 2;
          ctx.beginPath();
          ctx.rect(x - half, y - half, sidePx, sidePx);
          ctx.fillStyle = colorHex ? rgbaFromHex(colorHex, 0.28) : "rgba(226,182,255,0.32)";
          ctx.strokeStyle = colorHex || "rgba(107,61,138,0.85)";
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

  function centerOnClaimed(){
    if (!state || !state.units || !claimedCid) return;
    if (!gridReady()) return;
    const me = state.units.find(u => Number(u.cid) === Number(claimedCid));
    if (!me) return;
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;
    const cols = state.grid.cols, rows = state.grid.rows;
    const desiredX = (w / 2) - (me.pos.col + 0.5) * zoom;
    const desiredY = (h / 2) - (me.pos.row + 0.5) * zoom;
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
    centeredCid = String(claimedCid);
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
      chip.setAttribute("aria-label", `Turn ${idx + 1}: ${unitName}`);
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
      nameEl.textContent = unitName;
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
      turnOrderEl.appendChild(chip);
      chipByCid.set(Number(cid), chip);
    });
    const setSelectedTurnCid = (cid) => {
      selectedTurnCid = cid;
      chipByCid.forEach((chip, key) => {
        chip.classList.toggle("selected", Number(key) === Number(cid));
      });
      showTurnOrderBubble(chipByCid.get(Number(cid)), unitsByCid.get(Number(cid)));
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
        if (standUpBtn){
          standUpBtn.disabled = !(myTurn && me.is_prone);
        }
      } else {
        actionEl.textContent = "Action: —";
        bonusActionEl.textContent = "Bonus Action: —";
        useActionBtn.disabled = true;
        useBonusActionBtn.disabled = true;
        if (standUpBtn){
          standUpBtn.disabled = true;
        }
      }
    } else {
      actionEl.textContent = "Action: —";
      bonusActionEl.textContent = "Bonus Action: —";
      useActionBtn.disabled = true;
      useBonusActionBtn.disabled = true;
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
      if (loginNameInput && loginNameInput.value.trim()){
        sendHello();
      } else {
        setLoginState(false);
      }
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
      if (msg.type === "login_ok"){
        const username = String(msg.username || "").trim();
        if (username){
          localStorage.setItem(usernameKey, username);
          if (loginNameInput){
            loginNameInput.value = username;
          }
          storedUsername = username;
        }
        setLoginState(true);
        shownNoOwnedToast = false;
      } else if (msg.type === "login_error"){
        setLoginState(false);
        setLoginError(msg.error || "Username required.");
      } else if (msg.type === "preset"){
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
        state = msg.state;
        updateSpellPresetOptions(state?.spell_presets);
        aoeDragOverrides.clear();
        lastPcList = msg.pcs || msg.claimable || [];
        updateWaitingOverlay();
        draw();
        updateHud();
        maybeShowTurnAlert();
        if (claimedCid && clientId && state && Array.isArray(state.units)){
          const me = state.units.find(u => Number(u.cid) === Number(claimedCid));
          const serverOwner = me ? (me.claimed_by ?? null) : null;
          if (me && serverOwner !== clientId){
            claimedCid = null;
            meEl.textContent = "(unclaimed)";
            shownNoOwnedToast = false;
            updateHud();
          }
        }
        if (!claimedCid){
          showNoOwnedPcToast(msg.pcs || msg.claimable || []);
        } else {
          const exists = (state.units || []).some(u => Number(u.cid) === Number(claimedCid));
          if (!exists){
            claimedCid = null;
            meEl.textContent = "(unclaimed)";
            shownNoOwnedToast = false;
            showNoOwnedPcToast(msg.pcs || msg.claimable || []);
          }
        }
      } else if (msg.type === "force_claim"){
        if (msg.cid !== null && msg.cid !== undefined){
          claimedCid = String(msg.cid);
          shownNoOwnedToast = false;
        }
        noteEl.textContent = msg.text || "Assigned by the DM.";
        setTimeout(() => noteEl.textContent = "Tip: drag yer token", 2500);
      } else if (msg.type === "force_unclaim"){
        claimedCid = null;
        meEl.textContent = "(unclaimed)";
        shownNoOwnedToast = false;
        showNoOwnedPcToast(msg.pcs || lastPcList || []);
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

  if (loginForm){
    loginForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      sendHello();
    });
  }

  // input
  function pointerPos(ev){
    const r = canvas.getBoundingClientRect();
    return {x: ev.clientX - r.left, y: ev.clientY - r.top};
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
    if (state && state.units){
      let hit = null;
      for (let i=state.units.length-1; i>=0; i--){
        const u = state.units[i];
        const {x,y} = gridToScreen(u.pos.col,u.pos.row);
        const r = Math.max(12, zoom*0.45);
        const dx = p.x - x, dy = p.y - y;
        if (dx*dx + dy*dy <= r*r){
          hit = u; break;
        }
      }
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
    }
    const aoeHit = hitTestAoe(p);
    if (aoeHit){
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
    // else pan (if map not locked)
    if (!lockMap){
      panning = {x: p.x, y: p.y, panX, panY};
    }
  });

  canvas.addEventListener("pointermove", (ev) => {
    const p = pointerPos(ev);
    if (activePointers.has(ev.pointerId)){
      activePointers.set(ev.pointerId, p);
    }
    if (pinchState && activePointers.size >= 2){
      updatePinch();
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
    } else if (draggingAoe){
      const g = screenToGridFloat(p.x, p.y);
      draggingAoe.cx = g.col;
      draggingAoe.cy = g.row;
      aoeDragOverrides.set(Number(draggingAoe.aid), {cx: g.col, cy: g.row});
      draw();
    } else if (panning){
      panX = panning.panX + (p.x - panning.x);
      panY = panning.panY + (p.y - panning.y);
      draw();
    }
  });

  canvas.addEventListener("pointerup", (ev) => {
    const p = pointerPos(ev);
    activePointers.delete(ev.pointerId);
    if (activePointers.size < 2){
      pinchState = null;
    }
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
    activePointers.delete(ev.pointerId);
    if (activePointers.size < 2){
      pinchState = null;
    }
    if (draggingAoe){
      aoeDragOverrides.delete(Number(draggingAoe.aid));
      draggingAoe = null;
      draw();
    }
  });

  canvas.addEventListener("wheel", (ev) => {
    if (pinchState) return;
    ev.preventDefault();
    const p = pointerPos(ev);
    const delta = ev.deltaY || 0;
    const factor = delta > 0 ? 0.9 : 1.1;
    zoomAt(zoom * factor, p.x, p.y);
  }, {passive: false});

  if (zoomInBtn){
    zoomInBtn.addEventListener("click", () => {
      const r = canvas.getBoundingClientRect();
      zoomAt(zoom + 4, r.width / 2, r.height / 2);
    });
  }
  if (zoomOutBtn){
    zoomOutBtn.addEventListener("click", () => {
      const r = canvas.getBoundingClientRect();
      zoomAt(zoom - 4, r.width / 2, r.height / 2);
    });
  }
  if (lockMapBtn){
    lockMapBtn.addEventListener("click", (ev) => {
      lockMap = !lockMap;
      ev.target.textContent = lockMap ? "Unlock Map" : "Lock Map";
    });
  }
  if (centerMapBtn){
    centerMapBtn.addEventListener("click", () => {
      centerOnClaimed();
      draw();
    });
  }
  if (measureToggle){
    measureToggle.addEventListener("click", () => {
      measurementMode = !measurementMode;
      updateMeasurementControls();
    });
  }
  if (measureClear){
    measureClear.addEventListener("click", () => {
      clearMeasurement();
    });
  }

  if (tokenColorInput){
    tokenColorInput.addEventListener("input", (ev) => {
      updateTokenColorSwatch(ev.target.value);
    });
  }
  if (tokenColorConfirm){
    tokenColorConfirm.addEventListener("click", () => {
      if (!pendingClaim){
        closeColorModal();
        return;
      }
      const color = validateTokenColor(tokenColorInput ? tokenColorInput.value : "");
      if (!color) return;
      claimedCid = String(pendingClaim.cid);
      shownNoOwnedToast = false;
      localStorage.setItem("inittracker_tokenColor", color);
      send({type:"claim", cid: Number(pendingClaim.cid)});
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
  const normalizeSpellPresets = (presets) => Array.isArray(presets) ? presets.filter(p => p && typeof p === "object") : [];
  const updateSpellPresetOptions = (presets) => {
    if (!castPresetInput) return;
    const list = normalizeSpellPresets(presets);
    const signature = JSON.stringify(list.map(p => String(p.name || "")));
    if (signature === lastSpellPresetSignature){
      return;
    }
    lastSpellPresetSignature = signature;
    const currentValue = String(castPresetInput.value || "");
    castPresetInput.textContent = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Custom";
    castPresetInput.appendChild(blank);
    list.forEach(preset => {
      const name = String(preset.name || "").trim();
      if (!name) return;
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      castPresetInput.appendChild(opt);
    });
    if (currentValue && list.some(p => String(p.name || "") === currentValue)){
      castPresetInput.value = currentValue;
    } else {
      castPresetInput.value = "";
    }
  };

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
    const isCircle = shape === "circle";
    const isSquare = shape === "square";
    const isLine = shape === "line";
    setCastFieldVisible(castRadiusField, isCircle);
    setCastFieldVisible(castSideField, isSquare);
    setCastFieldVisible(castLengthField, isLine);
    setCastFieldVisible(castWidthField, isLine);
    setCastFieldEnabled(castRadiusInput, isCircle);
    setCastFieldEnabled(castSideInput, isSquare);
    setCastFieldEnabled(castLengthInput, isLine);
    setCastFieldEnabled(castWidthInput, isLine);
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
    rawIncrements.forEach((entry) => {
      if (!entry || typeof entry !== "object"){
        console.warn("Invalid upcast increment entry; skipping.", entry);
        return;
      }
      const levelsPer = Number(entry.levels_per_increment);
      const addDice = typeof entry.add_dice === "string" ? entry.add_dice : "";
      if (!Number.isFinite(levelsPer) || levelsPer <= 0){
        console.warn("Invalid upcast levels_per_increment; skipping.", entry);
        return;
      }
      if (!parseDiceSpec(addDice)){
        console.warn("Invalid upcast add_dice; skipping.", entry);
        return;
      }
      increments.push({
        levels_per_increment: levelsPer,
        add_dice: addDice,
      });
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
      const levelsPer = Number(inc.levels_per_increment);
      const addDiceSpec = parseDiceSpec(inc.add_dice);
      if (!Number.isFinite(levelsPer) || !addDiceSpec) return;
      const steps = Math.floor(deltaLevels / levelsPer);
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
    if (castShapeInput && preset.shape){
      castShapeInput.value = String(preset.shape || "").toLowerCase();
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
        return;
      }
      const presets = normalizeSpellPresets(state?.spell_presets);
      const preset = presets.find(p => String(p.name || "") === name);
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
      const radiusFt = parsePositive(castRadiusInput?.value);
      const sideFt = parsePositive(castSideInput?.value);
      const lengthFt = parsePositive(castLengthInput?.value);
      const widthFt = parsePositive(castWidthInput?.value);
      if (shape === "circle" && radiusFt === null){
        localToast("Enter a valid radius, matey.");
        return;
      }
      if (shape === "square" && sideFt === null){
        localToast("Enter a valid side length, matey.");
        return;
      }
      if (shape === "line" && (lengthFt === null || widthFt === null)){
        localToast("Enter a valid line size, matey.");
        return;
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
      } else if (shape === "square"){
        payload.side_ft = sideFt;
      } else if (shape === "line"){
        payload.length_ft = lengthFt;
        payload.width_ft = widthFt;
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
  if (presetSaveBtn){
    presetSaveBtn.addEventListener("click", () => {
      const preset = buildGuiPreset();
      persistLocalPreset(preset);
      if (!loggedIn){
        setPresetStatus("Login required.");
        return;
      }
      send({type: "save_preset", preset});
    });
  }
  if (presetLoadBtn){
    presetLoadBtn.addEventListener("click", () => {
      if (!loggedIn){
        setPresetStatus("Login required.");
        return;
      }
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
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape"){
      closeConnPopover();
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

class LanController:
    """Runs a FastAPI+WebSocket server in a background thread and bridges actions into the Tk thread."""

    def __init__(self, app: "InitiativeTracker") -> None:
        self.app = app
        self.cfg = LanConfig()
        self._server_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._uvicorn_server = None
        self._account_store = LanAccountStore(logger=self.app._ops_logger)
        self._store_lock = threading.Lock()

        self._clients_lock = threading.Lock()
        self._clients: Dict[int, Any] = {}  # id(websocket) -> websocket
        self._clients_meta: Dict[int, Dict[str, Any]] = {}  # id(websocket) -> {host,port,ua,connected_at}
        self._claims: Dict[int, int] = {}   # id(websocket) -> cid
        self._cid_to_ws: Dict[int, int] = {}  # cid -> id(websocket) (1 owner at a time)
        self._client_ids: Dict[int, str] = {}  # id(websocket) -> client_id
        self._client_claims: Dict[str, int] = {}  # client_id -> cid (last known claim)
        self._cid_to_client: Dict[int, str] = {}  # cid -> client_id (active claim)
        self._client_usernames: Dict[int, str] = {}  # id(websocket) -> username

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

    # ---------- Tk thread API ----------

    def _ensure_account(self, username: str) -> None:
        with self._store_lock:
            self._account_store.ensure_account(username)

    def _owner_for(self, cid: int) -> Optional[str]:
        with self._store_lock:
            return self._account_store.owner_for(cid)

    def _claim_owner(self, cid: int, username: str, allow_override: bool = False) -> bool:
        with self._store_lock:
            return self._account_store.claim(cid, username, force=allow_override)

    def _clear_owner(self, cid: int) -> bool:
        with self._store_lock:
            return self._account_store.clear_owner(cid)

    def _preset_for_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._store_lock:
            return self._account_store.preset_for(username)

    def _save_preset_for_username(self, username: str, preset: Optional[Dict[str, Any]]) -> bool:
        with self._store_lock:
            return self._account_store.set_preset(username, preset)

    def accounts_snapshot(self) -> List[Dict[str, Any]]:
        with self._store_lock:
            accounts = self._account_store.accounts_snapshot()
        accounts.sort(key=lambda a: str(a.get("username", "")).lower())
        return accounts

    def ownership_snapshot(self) -> Dict[int, str]:
        with self._store_lock:
            return self._account_store.ownership_snapshot()

    def admin_assign_owner(self, cid: int, username: str) -> bool:
        with self._store_lock:
            ok = self._account_store.claim(cid, username, force=True)
        if ok:
            self._broadcast_state(self._cached_snapshot)
        return ok

    def admin_clear_owner(self, cid: int) -> bool:
        with self._store_lock:
            ok = self._account_store.clear_owner(cid)
        if ok:
            self._broadcast_state(self._cached_snapshot)
        return ok

    def admin_disconnect_session(self, ws_id: int, reason: str = "Disconnected by the DM.") -> None:
        if not self._loop:
            return
        coro = self._disconnect_session_async(int(ws_id), reason)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    def start(self, quiet: bool = False) -> None:
        if self._server_thread and self._server_thread.is_alive():
            self.app._oplog("LAN server already runnin'.")
            return

        # Lazy imports so the base app still works without these deps installed.
        try:
            from fastapi import FastAPI, WebSocket, WebSocketDisconnect
            from fastapi.responses import HTMLResponse, Response
            from fastapi.staticfiles import StaticFiles
            import uvicorn
            # Expose these in module globals so FastAPI's type resolver can see 'em even from nested defs.
            globals()["WebSocket"] = WebSocket
            globals()["WebSocketDisconnect"] = WebSocketDisconnect
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
            return HTMLResponse(HTML_INDEX)

        @app.get("/sw.js")
        async def service_worker():
            return Response(SERVICE_WORKER_JS, media_type="application/javascript")

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            ws_id = id(ws)
            # record client meta
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

            with self._clients_lock:
                self._clients[ws_id] = ws
                self._clients_meta[ws_id] = {
                    "host": host,
                    "port": port,
                    "ua": ua,
                    "connected_at": connected_at,
                    "last_seen": connected_at,
                }
            self.app._oplog(f"LAN session connected ws_id={ws_id} host={host}:{port} ua={ua}")
            try:
                await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                # Immediately send snapshot + claimable list
                await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
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
                    if typ == "hello":
                        # If client sends previous claim, remember it (optional).
                        claimed = msg.get("claimed")
                        client_id = msg.get("client_id")
                        username = msg.get("username")
                        if isinstance(client_id, str):
                            client_id = client_id.strip()
                        else:
                            client_id = None
                        if isinstance(username, str):
                            username = username.strip()
                        else:
                            username = None
                        if not username:
                            await ws.send_text(json.dumps({"type": "login_error", "error": "Username required."}))
                            continue
                        with self._clients_lock:
                            self._client_usernames[ws_id] = username
                        try:
                            self._ensure_account(username)
                        except Exception:
                            pass
                        await ws.send_text(json.dumps({"type": "login_ok", "username": username}))
                        preset = self._preset_for_username(username)
                        if preset is not None:
                            await ws.send_text(json.dumps({"type": "preset", "preset": preset}))
                        if client_id:
                            with self._clients_lock:
                                self._client_ids[ws_id] = client_id
                            known_claim = self._client_claims.get(client_id)
                            if known_claim is not None and self._can_auto_claim(int(known_claim), username):
                                await self._claim_ws_async(ws_id, int(known_claim), note="Reconnected.")
                            elif isinstance(claimed, int) and self._can_auto_claim(int(claimed), username):
                                await self._claim_ws_async(ws_id, int(claimed), note="Reconnected.")
                        elif isinstance(claimed, int) and self._can_auto_claim(int(claimed), username):
                            await self._claim_ws_async(ws_id, int(claimed), note="Reconnected.")
                        await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
                    elif typ == "save_preset":
                        with self._clients_lock:
                            username = self._client_usernames.get(ws_id)
                        if not username:
                            await ws.send_text(json.dumps({"type": "login_error", "error": "Login required before saving presets."}))
                            continue
                        preset = msg.get("preset")
                        if preset is not None and not isinstance(preset, dict):
                            await ws.send_text(json.dumps({"type": "preset_error", "error": "Invalid preset payload."}))
                            continue
                        ok = self._save_preset_for_username(username, preset)
                        if ok:
                            await ws.send_text(json.dumps({"type": "preset_saved"}))
                        else:
                            await ws.send_text(json.dumps({"type": "preset_error", "error": "Unable to save preset."}))
                    elif typ == "load_preset":
                        with self._clients_lock:
                            username = self._client_usernames.get(ws_id)
                        if not username:
                            await ws.send_text(json.dumps({"type": "login_error", "error": "Login required before loading presets."}))
                            continue
                        preset = self._preset_for_username(username)
                        await ws.send_text(json.dumps({"type": "preset", "preset": preset}))
                    elif typ == "grid_request":
                        await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                    elif typ == "grid_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._grid_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._grid_pending.pop(ws_id, None)
                    elif typ == "claim":
                        with self._clients_lock:
                            username = self._client_usernames.get(ws_id)
                        if not username:
                            await ws.send_text(json.dumps({"type": "login_error", "error": "Login required before claiming."}))
                            continue
                        cid = msg.get("cid")
                        if isinstance(cid, int):
                            owner = self._owner_for(cid)
                            if owner and owner != username:
                                await self._send_async(ws_id, {"type": "toast", "text": f"{self._pc_name_for(cid)} belongs to {owner}."})
                                continue
                            await self._claim_ws_async(ws_id, cid, note="Claimed. Drag yer token, matey.")
                            await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
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
                    ):
                        with self._clients_lock:
                            username = self._client_usernames.get(ws_id)
                        if not username:
                            await ws.send_text(json.dumps({"type": "login_error", "error": "Login required before actions."}))
                            continue
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
                    old = self._claims.pop(ws_id, None)
                    if old is not None:
                        self._cid_to_ws.pop(int(old), None)
                        self._cid_to_client.pop(int(old), None)
                    self._client_ids.pop(ws_id, None)
                    self._client_usernames.pop(ws_id, None)
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

    # ---------- Sessions / Claims (Tk thread safe) ----------

    def sessions_snapshot(self) -> List[Dict[str, Any]]:
        """Return a best-effort list of connected clients + who they claim."""
        out: List[Dict[str, Any]] = []
        with self._clients_lock:
            for ws_id, ws in list(self._clients.items()):
                meta = dict(self._clients_meta.get(ws_id, {}))
                cid = self._claims.get(ws_id)
                username = self._client_usernames.get(ws_id)
                out.append(
                    {
                        "ws_id": int(ws_id),
                        "cid": int(cid) if cid is not None else None,
                        "username": username,
                        "host": meta.get("host", "?"),
                        "port": meta.get("port", ""),
                        "user_agent": meta.get("ua", ""),
                        "connected_at": meta.get("connected_at", ""),
                        "last_seen": meta.get("last_seen", meta.get("connected_at", "")),
                    }
                )
        out.sort(key=lambda s: int(s.get("ws_id", 0)))
        return out

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
        if not ws:
            return
        if cid is None:
            # unclaim
            await self._unclaim_ws_async(ws_id, reason=note, clear_ownership=True)
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
            cid_to_client = dict(self._cid_to_client)
        out: List[Dict[str, Any]] = []
        for p in pcs:
            pp = dict(p)
            cid = int(pp.get("cid", -1))
            pp["claimed_by"] = cid_to_client.get(cid)
            pp["owned_by"] = self._owner_for(cid)
            out.append(pp)
        out.sort(key=lambda d: str(d.get("name", "")))
        return out

    def _can_auto_claim(self, cid: int, username: Optional[str] = None) -> bool:
        try:
            cid = int(cid)
        except Exception:
            return False
        pcs = {int(p.get("cid")) for p in self._cached_pcs if isinstance(p.get("cid"), int)}
        if cid not in pcs:
            return False
        if username:
            owner = self._owner_for(cid)
            if owner and owner != username:
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
                        self._cid_to_client.pop(int(old_cid), None)
                    self._clients.pop(ws_id, None)
                    self._clients_meta.pop(ws_id, None)
                    self._client_ids.pop(ws_id, None)

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
                self._cid_to_client.pop(int(old), None)
            client_id = self._client_ids.get(ws_id)
            if client_id:
                self._client_claims.pop(client_id, None)
        if old is not None and clear_ownership:
            self._clear_owner(int(old))
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
        with self._clients_lock:
            username = self._client_usernames.get(ws_id)
        if username:
            owner = self._owner_for(cid)
            if owner and owner != username and not allow_override:
                await self._send_async(ws_id, {"type": "toast", "text": f"{self._pc_name_for(cid)} belongs to {owner}."})
                return

        # Steal/assign with single-owner logic
        steal_from: Optional[int] = None
        prev_owned: Optional[int] = None
        client_id: Optional[str] = None
        steal_client_id: Optional[str] = None
        with self._clients_lock:
            # if this ws had old claim, clear reverse map
            prev_owned = self._claims.get(ws_id)
            if prev_owned is not None:
                self._cid_to_ws.pop(int(prev_owned), None)
                self._cid_to_client.pop(int(prev_owned), None)

            # if cid is owned, we'll steal
            steal_from = self._cid_to_ws.get(int(cid))
            if steal_from is not None and steal_from != ws_id:
                self._claims.pop(steal_from, None)
            # assign
            self._claims[ws_id] = int(cid)
            self._cid_to_ws[int(cid)] = ws_id
            client_id = self._client_ids.get(ws_id)
            if client_id:
                self._client_claims[client_id] = int(cid)
                self._cid_to_client[int(cid)] = client_id
            else:
                self._cid_to_client.pop(int(cid), None)
            if steal_from is not None and steal_from != ws_id:
                steal_client_id = self._client_ids.get(steal_from)
                if steal_client_id:
                    self._client_claims.pop(steal_client_id, None)
                    if client_id:
                        self._cid_to_client[int(cid)] = client_id
                    else:
                        self._cid_to_client.pop(int(cid), None)

        if username:
            self._claim_owner(int(cid), username, allow_override=allow_override)

        if steal_from is not None and steal_from != ws_id:
            await self._send_async(steal_from, {"type": "force_unclaim", "text": "Yer character got reassigned by the DM.", "pcs": self._pcs_payload()})

        await self._send_async(ws_id, {"type": "force_claim", "cid": int(cid), "text": note})
        name = self._pc_name_for(int(cid))
        self.app._oplog(f"LAN session ws_id={ws_id} claimed {name} ({note})")

    # ---------- helpers ----------

    def _best_lan_url(self) -> str:
        ip = "127.0.0.1"
        try:
            # Try common LAN interfaces
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "127.0.0.1"
        return f"http://{ip}:{self.cfg.port}/"

    def _cached_snapshot_payload(self) -> Dict[str, Any]:
        snap = dict(self._cached_snapshot)
        units = snap.get("units")
        if isinstance(units, list):
            with self._clients_lock:
                cid_to_client = dict(self._cid_to_client)
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
                copy_unit["claimed_by"] = cid_to_client.get(cid)
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
            menubar.add_cascade(label="LAN", menu=lan)
            self.config(menu=menubar)
        except Exception:
            pass

    def _show_lan_url(self) -> None:
        url = self._lan._best_lan_url()
        messagebox.showinfo("LAN URL", f"Open this on yer LAN devices:\n\n{url}")

    def _show_lan_qr(self) -> None:
        url = self._lan._best_lan_url()
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
        ttk.Button(controls, text="LAN Admin…", command=self._open_lan_admin).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(controls, text="Assign", command=do_assign).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(controls, text="Unassign", command=do_kick).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="Close", command=win.destroy).pack(side=tk.RIGHT)

        refresh_sessions()

    def _open_lan_admin(self) -> None:
        """DM utility: manage LAN accounts, ownership, and sessions."""
        win = tk.Toplevel(self)
        win.title("LAN Admin")
        win.geometry("960x680")
        win.transient(self)

        outer = tk.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        summary_frame = tk.LabelFrame(outer, text="Session Summary")
        summary_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))

        summary_cols = ("ws_id", "username", "claimed", "last_seen", "client")
        summary_tree = ttk.Treeview(summary_frame, columns=summary_cols, show="headings", height=6)
        summary_tree.heading("ws_id", text="Session")
        summary_tree.heading("username", text="Username")
        summary_tree.heading("claimed", text="Claimed PC")
        summary_tree.heading("last_seen", text="Last Seen")
        summary_tree.heading("client", text="Client")
        summary_tree.column("ws_id", width=90, anchor="center")
        summary_tree.column("username", width=160, anchor="w")
        summary_tree.column("claimed", width=200, anchor="w")
        summary_tree.column("last_seen", width=160, anchor="w")
        summary_tree.column("client", width=280, anchor="w")
        summary_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tables = tk.Frame(outer)
        tables.pack(fill=tk.BOTH, expand=True)

        accounts_frame = tk.LabelFrame(tables, text="Known Accounts")
        accounts_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        accounts_cols = ("username", "owned", "created_at")
        accounts_tree = ttk.Treeview(accounts_frame, columns=accounts_cols, show="headings", height=8)
        accounts_tree.heading("username", text="Username")
        accounts_tree.heading("owned", text="Owned PCs")
        accounts_tree.heading("created_at", text="Created")
        accounts_tree.column("username", width=160, anchor="w")
        accounts_tree.column("owned", width=220, anchor="w")
        accounts_tree.column("created_at", width=140, anchor="w")
        accounts_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        ownership_frame = tk.LabelFrame(tables, text="PC Ownership")
        ownership_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        ownership_cols = ("pc", "owner")
        ownership_tree = ttk.Treeview(ownership_frame, columns=ownership_cols, show="headings", height=8)
        ownership_tree.heading("pc", text="Player Character")
        ownership_tree.heading("owner", text="Owner")
        ownership_tree.column("pc", width=220, anchor="w")
        ownership_tree.column("owner", width=180, anchor="w")
        ownership_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        actions = tk.LabelFrame(outer, text="Admin Actions")
        actions.pack(fill=tk.X, pady=(10, 0))

        pc_map: Dict[str, Optional[int]] = {}
        pc_var = tk.StringVar()
        pc_box = ttk.Combobox(actions, textvariable=pc_var, values=[], width=28, state="readonly")
        pc_box.grid(row=0, column=1, padx=(6, 16), pady=6, sticky="w")
        tk.Label(actions, text="PC:").grid(row=0, column=0, padx=(6, 0), pady=6, sticky="w")

        tk.Label(actions, text="Username:").grid(row=0, column=2, padx=(6, 0), pady=6, sticky="w")
        user_var = tk.StringVar()
        user_entry = ttk.Combobox(actions, textvariable=user_var, values=[], width=22)
        user_entry.grid(row=0, column=3, padx=(6, 16), pady=6, sticky="w")

        def refresh_admin() -> None:
            summary_tree.delete(*summary_tree.get_children())
            accounts_tree.delete(*accounts_tree.get_children())
            ownership_tree.delete(*ownership_tree.get_children())

            cid_to_name: Dict[int, str] = {}
            try:
                for p in self._lan_pcs():
                    if isinstance(p.get("cid"), int):
                        cid_to_name[int(p["cid"])] = str(p.get("name", ""))
            except Exception:
                pass

            sessions = self._lan.sessions_snapshot()
            for s in sessions:
                ws_id = int(s.get("ws_id"))
                username = s.get("username") or ""
                cid = s.get("cid")
                claimed = ""
                if isinstance(cid, int):
                    claimed = cid_to_name.get(int(cid), f"cid {cid}")
                last_seen = s.get("last_seen", "") or s.get("connected_at", "")
                host = str(s.get("host", "?"))
                port = str(s.get("port", ""))
                client = f"{host}:{port}" if port else host
                summary_tree.insert("", "end", iid=str(ws_id), values=(ws_id, username, claimed, last_seen, client))

            accounts = self._lan.accounts_snapshot()
            for account in accounts:
                username = str(account.get("username", ""))
                created_at = str(account.get("created_at", ""))
                owned_names = []
                for cid in account.get("owned_cids", []) or []:
                    try:
                        owned_names.append(cid_to_name.get(int(cid), f"cid {cid}"))
                    except Exception:
                        continue
                owned_text = ", ".join(owned_names)
                accounts_tree.insert("", "end", iid=username, values=(username, owned_text, created_at))

            ownership = self._lan.ownership_snapshot()
            for cid, name in cid_to_name.items():
                owner = ownership.get(int(cid), "")
                ownership_tree.insert("", "end", iid=str(cid), values=(name, owner))

            pc_map.clear()
            for cid, name in cid_to_name.items():
                pc_map[name] = int(cid)
            pc_names = sorted(pc_map.keys())
            pc_box["values"] = pc_names
            if pc_names:
                pc_var.set(pc_names[0])
            usernames = [str(a.get("username", "")) for a in accounts if a.get("username")]
            user_entry["values"] = usernames

        def selected_ws_id() -> Optional[int]:
            sel = summary_tree.selection()
            if not sel:
                return None
            try:
                return int(sel[0])
            except Exception:
                return None

        def selected_cid() -> Optional[int]:
            name = pc_var.get()
            cid = pc_map.get(name)
            if isinstance(cid, int):
                return cid
            return None

        def do_clear_owner() -> None:
            cid = selected_cid()
            if cid is None:
                return
            self._lan.admin_clear_owner(cid)
            self.after(300, refresh_admin)

        def do_assign_owner() -> None:
            cid = selected_cid()
            username = user_var.get().strip()
            if cid is None or not username:
                return
            self._lan.admin_assign_owner(cid, username)
            self.after(300, refresh_admin)

        def do_disconnect() -> None:
            ws_id = selected_ws_id()
            if ws_id is None:
                return
            self._lan.admin_disconnect_session(ws_id)
            self.after(500, refresh_admin)

        ttk.Button(actions, text="Clear Ownership", command=do_clear_owner).grid(row=0, column=4, padx=(0, 6), pady=6)
        ttk.Button(actions, text="Assign Owner", command=do_assign_owner).grid(row=0, column=5, padx=(0, 6), pady=6)
        ttk.Button(actions, text="Disconnect Session", command=do_disconnect).grid(row=0, column=6, padx=(0, 6), pady=6)
        ttk.Button(actions, text="Refresh", command=refresh_admin).grid(row=0, column=7, padx=(0, 6), pady=6)
        ttk.Button(actions, text="Close", command=win.destroy).grid(row=0, column=8, padx=(0, 6), pady=6)

        refresh_admin()


    
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

        for name in roster:
            nm = str(name).strip()
            if not nm or nm in existing:
                continue

            # Defaults
            hp = 0
            speed = 30
            swim = 0
            water = False

            # Future-facing: per-PC config file players/<Name>.yaml (optional)
            try:
                cfg_path = players_dir / f"{nm}.yaml"
                if cfg_path.exists():
                    raw = cfg_path.read_text(encoding="utf-8")
                    data = None
                    if ymod is not None:
                        data = ymod.safe_load(raw)
                    if isinstance(data, dict):
                        # accept a few key names
                        speed = int(data.get("base_movement", data.get("speed", speed)) or speed)
                        swim = int(data.get("swim_speed", swim) or swim)
                        hp = int(data.get("hp", hp) or hp)
            except Exception:
                pass

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
                if kind not in ("circle", "square", "line"):
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
                if kind == "circle":
                    payload["radius_sq"] = float(d.get("radius_sq") or 0.0)
                elif kind == "line":
                    payload["length_sq"] = float(d.get("length_sq") or 0.0)
                    payload["width_sq"] = float(d.get("width_sq") or 0.0)
                    payload["orient"] = str(d.get("orient") or "vertical")
                    if d.get("angle_deg") is not None:
                        payload["angle_deg"] = float(d.get("angle_deg") or 0.0)
                else:
                    payload["side_sq"] = float(d.get("side_sq") or 0.0)
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
        presets: List[Dict[str, Any]] = []
        for preset in getattr(self, "_spell_presets", []) or []:
            presets.append(
                {
                    "name": str(preset.name),
                    "shape": str(preset.shape),
                    "radius_ft": preset.radius_ft,
                    "side_ft": preset.side_ft,
                    "length_ft": preset.length_ft,
                    "width_ft": preset.width_ft,
                    "save_type": preset.save_type,
                    "save_dc": preset.save_dc,
                    "default_damage": getattr(preset, "default_damage", None),
                    "dice": getattr(preset, "dice", None),
                    "damage_types": list(preset.damage_types or []),
                    "color": preset.color,
                    "duration_turns": getattr(preset, "duration_turns", None),
                    "over_time": getattr(preset, "over_time", None),
                    "move_per_turn_ft": getattr(preset, "move_per_turn_ft", None),
                    "trigger_on_start_or_enter": getattr(preset, "trigger_on_start_or_enter", None),
                    "persistent": getattr(preset, "persistent", None),
                    "pinned_default": getattr(preset, "pinned_default", None),
                    "upcast": getattr(preset, "upcast", None),
                }
            )
        return presets

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

        # Basic sanity: claimed cid must match the action cid (if provided)
        cid = msg.get("cid")
        if isinstance(cid, int):
            if claimed is not None and cid != claimed:
                self._lan.toast(ws_id, "Arrr, that token ain’t yers.")
                return
        else:
            cid = claimed

        if cid is None:
            self._lan.toast(ws_id, "Claim a character first, matey.")
            return

        # Must exist
        if cid not in self.combatants:
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
        if typ not in ("cast_aoe", "aoe_move"):
            if self.current_cid is None or int(self.current_cid) != int(cid):
                self._lan.toast(ws_id, "Not yer turn yet, matey.")
                return

        if typ == "cast_aoe":
            payload = msg.get("payload") or {}
            shape = str(payload.get("shape") or payload.get("kind") or "").strip().lower()
            if shape not in ("circle", "square", "line"):
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
            owner = str(self.combatants[cid].name)
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
                "owner_cid": int(cid),
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
                else:
                    aoe["radius_sq"] = float(size)
            elif shape == "square":
                if side_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell side length, matey.")
                    return
                if side_ft is not None:
                    aoe["side_sq"] = max(1.0, float(side_ft) / feet_per_square)
                else:
                    aoe["side_sq"] = float(size)
            else:
                if length_ft is None and size is None:
                    self._lan.toast(ws_id, "Pick a valid spell length, matey.")
                    return
                if length_ft is not None:
                    aoe["length_sq"] = max(1.0, float(length_ft) / feet_per_square)
                else:
                    aoe["length_sq"] = float(size)
                if width_ft is not None:
                    aoe["width_sq"] = max(1.0, float(width_ft) / feet_per_square)
                else:
                    width = parse_positive_float(payload.get("width")) or 1.0
                    aoe["width_sq"] = max(1.0, float(width))
                aoe["orient"] = str(payload.get("orient") or "vertical")
                aoe["angle_deg"] = float(payload.get("angle_deg") or 90.0)
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
            if bool(d.get("pinned")):
                self._lan.toast(ws_id, "That spell be pinned.")
                return
            owner_cid = d.get("owner_cid")
            if owner_cid is not None and int(owner_cid) != int(cid):
                self._lan.toast(ws_id, "That spell be not yers.")
                return
            move_per_turn_ft = d.get("move_per_turn_ft")
            move_remaining_ft = d.get("move_remaining_ft")
            if move_per_turn_ft not in (None, ""):
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

        if not files:
            return

        if yaml is None:
            # Monster files are complex; be explicit so the user knows what to install.
            try:
                self._log("Monster YAML support requires PyYAML. Install: sudo apt install python3-yaml")
            except Exception:
                pass
            return

        for fp in files:
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
                    elif isinstance(hp_val, str) and hp_val.strip().lstrip("-").isdigit():
                        hp = int(hp_val.strip())
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

        self._monster_specs.sort(key=lambda s: s.name.lower())

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

        cols = ("name", "type", "cr", "file")
        tree = ttk.Treeview(top, columns=cols, show="headings", height=18)
        tree.heading("name", text="Name")
        tree.heading("type", text="Type")
        tree.heading("cr", text="CR")
        tree.heading("file", text="File")

        tree.column("name", width=240, anchor="w")
        tree.column("type", width=160, anchor="w")
        tree.column("cr", width=70, anchor="center")
        tree.column("file", width=200, anchor="w")

        tree.pack(fill="both", expand=True)

        def get_filtered() -> List[MonsterSpec]:
            tsel = type_var.get()
            specs = self._monster_specs
            if tsel and tsel != "All":
                specs = [s for s in specs if s.mtype == tsel]
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

        tree.bind("<Double-1>", on_select)
        type_box.bind("<<ComboboxSelected>>", lambda e: refresh())
        sort_box.bind("<<ComboboxSelected>>", lambda e: refresh())

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
