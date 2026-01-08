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


# --- App metadata ---
APP_VERSION = "41"

# --- LAN POC switches ---
POC_AUTO_START_LAN = True
POC_AUTO_SEED_PCS = True  # auto-add Player Characters from startingplayers.yaml (useful over SSH testing)

# ----------------------------- LAN Server -----------------------------

HTML_INDEX = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
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

    .mapWrap{flex:1; min-height:0; position:relative; overflow:hidden; background:#0a0c12;}
    canvas{position:absolute; inset:0; width:100%; height:100%; touch-action:none;}
    .waiting{
      position:absolute; inset:0; display:none; align-items:center; justify-content:center;
      background: rgba(10,12,18,0.82); color: var(--muted); font-size: 16px; letter-spacing: 0.4px;
      text-transform: lowercase;
    }
    .waiting.show{display:flex;}

    .sheet{
      padding: 10px 12px calc(12px + var(--safeInsetBottom)) 12px;
      background: rgba(20,25,35,0.92);
      border-top: 1px solid rgba(255,255,255,0.08);
      backdrop-filter: blur(10px);
      position:sticky; bottom:0; z-index:20;
    }
    .row{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
    .row + .row{margin-top:10px;}
    .label{font-size:12px; color:var(--muted);}
    .value{font-size:14px; font-weight:700;}
    .chip{font-size:12px; padding:6px 10px; border-radius:999px; border:1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05);}
    .chip input{margin-right:6px;}
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
    .modal-actions{display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;}
    .modal-actions .btn{flex:1; min-width:120px;}
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
    }
    .turn-card h2{margin:0 0 12px 0; font-size:18px;}
    .log-content{
      max-height: 55vh;
      overflow:auto;
      padding: 10px;
      border:1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      background: rgba(8,10,16,0.65);
      font-size: 12px;
      white-space: pre-wrap;
      line-height: 1.4;
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
    <h1>InitTracker LAN</h1>
    <div class="pill" id="conn">Connecting…</div>
    <div class="spacer"></div>
    <button class="btn" id="changeChar">Change</button>
    <button class="btn" id="lockMap">Lock Map</button>
    <button class="btn" id="centerMap">Center on Me</button>
    <button class="btn accent" id="zoomIn">Zoom +</button>
    <button class="btn accent" id="zoomOut">Zoom −</button>
    <button class="btn" id="battleLog">Battle Log</button>
  </div>

  <div class="mapWrap">
    <canvas id="c"></canvas>
    <div class="waiting" id="waitingOverlay">(waiting for combat...)</div>

    <div class="modal" id="claimModal">
      <div class="card">
        <h2>Choose yer character</h2>
        <div class="list" id="claimList"></div>
        <div class="hint">
          This be a LAN proof-o’-concept. Ye can drag <b>only yer own token</b>, and only <b>on yer turn</b>.<br/>
          If the list be empty, tell the DM to mark ye as a Player Character or add ye from the starting roster.
        </div>
      </div>
    </div>
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
  </div>

  <div class="sheet">
    <div class="row">
      <div class="label">Ye be:</div>
      <div class="value" id="me">(unclaimed)</div>
      <div class="spacer"></div>
      <button class="btn" id="useAction">Use Action</button>
      <button class="btn" id="useBonusAction">Use Bonus Action</button>
      <button class="btn" id="dash">Dash</button>
      <button class="btn" id="resetTurn">Reset Turn</button>
      <button class="btn danger" id="endTurn">End Turn</button>
    </div>
    <div class="row">
      <div class="chip" id="move">Move: —</div>
      <div class="chip" id="action">Action: —</div>
      <div class="chip" id="bonusAction">Bonus Action: —</div>
      <div class="chip" id="turn">Turn: —</div>
      <div class="chip" id="note">Tip: drag yer token</div>
      <label class="chip"><input type="checkbox" id="showAllNames">Show All Names</label>
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
  const canVibrate = "vibrate" in navigator;
  function vibrate(pattern){
    if (!canVibrate) return false;
    return navigator.vibrate(pattern);
  }

  const qs = new URLSearchParams(location.search);
  const wsProto = (location.protocol === "https:") ? "wss" : "ws";
  const wsUrl = `${wsProto}://${location.host}/ws`;

  const connEl = document.getElementById("conn");
  const meEl = document.getElementById("me");
  const moveEl = document.getElementById("move");
  const actionEl = document.getElementById("action");
  const bonusActionEl = document.getElementById("bonusAction");
  const turnEl = document.getElementById("turn");
  const noteEl = document.getElementById("note");
  const claimModal = document.getElementById("claimModal");
  const claimList = document.getElementById("claimList");
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
  const showAllNamesEl = document.getElementById("showAllNames");
  const turnAlertAudio = new Audio("/assets/alert.wav");
  turnAlertAudio.preload = "auto";
  let audioUnlocked = false;
  let pendingTurnAlert = false;
  let pendingVibrate = false;
  let lastVibrateSupported = canVibrate;
  let userHasInteracted = navigator.userActivation?.hasBeenActive ?? false;

  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");

  let ws = null;
  let state = null;
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
  let claimedCid = localStorage.getItem("inittracker_claimedCid") || null;
  let pendingClaim = null;
  let lastPcList = [];
  let lastActiveCid = null;
  let lastTurnRound = null;

  // view transform
  let zoom = 32; // px per square
  let panX = 0, panY = 0;
  let dragging = null; // {cid, startX, startY, origCol, origRow}
  let panning = null;  // {x,y, panX, panY}
  let centeredCid = null;
  let lockMap = false;
  let lastGrid = {cols: null, rows: null};
  let lastGridVersion = null;
  let fittedToGrid = false;
  let showAllNames = localStorage.getItem("inittracker_showAllNames") === "1";
  if (showAllNamesEl){
    showAllNamesEl.checked = showAllNames;
    showAllNamesEl.addEventListener("change", (ev) => {
      showAllNames = !!ev.target.checked;
      localStorage.setItem("inittracker_showAllNames", showAllNames ? "1" : "0");
      draw();
    });
  }

  function setConn(ok, txt){
    connEl.textContent = txt;
    connEl.style.borderColor = ok ? "rgba(106,169,255,0.35)" : "rgba(255,91,91,0.35)";
    connEl.style.background = ok ? "rgba(106,169,255,0.14)" : "rgba(255,91,91,0.14)";
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

  function showClaim(list){
    claimList.innerHTML = "";
    list.forEach(u => {
      const div = document.createElement("div");
      div.className = "item";
      const taken = (u.claimed_by !== null && u.claimed_by !== undefined);
      const meta = taken ? `Claimed` : `Unclaimed`;
      const btnTxt = taken ? "Take" : "Claim";
      div.innerHTML = `<div style="flex:1"><div class="name">${u.name}</div><div class="meta">Player Character • ${meta}</div></div><button class="btn accent">${btnTxt}</button>`;
      div.querySelector("button").addEventListener("click", () => {
        claimModal.classList.remove("show");
        openColorModal(u);
      });
      claimList.appendChild(div);
    });
    claimModal.classList.add("show");
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

  function gridReady(){
    if (!state || !state.grid) return false;
    if (state.grid.ready === false) return false;
    return Number.isFinite(state.grid.cols) && Number.isFinite(state.grid.rows);
  }

  function updateWaitingOverlay(){
    if (!waitingOverlay) return;
    waitingOverlay.classList.toggle("show", !gridReady());
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
        const cx = Number(a.cx ?? 0);
        const cy = Number(a.cy ?? 0);
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
        if (a.name){
          ctx.font = `700 ${Math.max(10, Math.floor(zoom*0.32))}px system-ui`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "rgba(20,25,35,0.9)";
          ctx.fillText(String(a.name), x + 1, y + 1);
          ctx.fillStyle = "rgba(232,238,247,0.95)";
          ctx.fillText(String(a.name), x, y);
        }
        ctx.restore();
      });
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
      } else {
        actionEl.textContent = "Action: —";
        bonusActionEl.textContent = "Bonus Action: —";
        useActionBtn.disabled = true;
        useBonusActionBtn.disabled = true;
      }
    } else {
      actionEl.textContent = "Action: —";
      bonusActionEl.textContent = "Bonus Action: —";
      useActionBtn.disabled = true;
      useBonusActionBtn.disabled = true;
    }
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
      setConn(true, "Connected");
      send({type:"grid_request"});
      send({type:"hello", claimed: claimedCid ? Number(claimedCid) : null, client_id: clientId});
    });
    ws.addEventListener("close", () => {
      setConn(false, "Disconnected");
      setTimeout(connect, 1000);
    });
    ws.addEventListener("message", (ev) => {
      let msg = null;
      try { msg = JSON.parse(ev.data); } catch(e){ return; }
      if (msg.type === "state"){
        state = msg.state;
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
            localStorage.removeItem("inittracker_claimedCid");
            meEl.textContent = "(unclaimed)";
            updateHud();
          }
        }
        // show claim if needed
        if (!claimedCid){
          const pcs = (msg.pcs || msg.claimable || []);
          if (pcs && pcs.length){
            showClaim(pcs);
          }
        } else {
          // if our cid no longer exists, clear
          const exists = (state.units || []).some(u => Number(u.cid) === Number(claimedCid));
          if (!exists){
            claimedCid = null;
            localStorage.removeItem("inittracker_claimedCid");
            meEl.textContent = "(unclaimed)";
            const pcs = (msg.pcs || msg.claimable || []);
            if (pcs && pcs.length){
              showClaim(pcs);
            }
          }
        }
      } else if (msg.type === "force_claim"){
        if (msg.cid !== null && msg.cid !== undefined){
          claimedCid = String(msg.cid);
          localStorage.setItem("inittracker_claimedCid", claimedCid);
        }
        claimModal.classList.remove("show");
        noteEl.textContent = msg.text || "Assigned by the DM.";
        setTimeout(() => noteEl.textContent = "Tip: drag yer token", 2500);
      } else if (msg.type === "force_unclaim"){
        claimedCid = null;
        localStorage.removeItem("inittracker_claimedCid");
        meEl.textContent = "(unclaimed)";
        const pcs = (msg.pcs || lastPcList || []);
        if (pcs && pcs.length){
          showClaim(pcs);
        } else {
          claimModal.classList.add("show");
        }
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
      }
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
      panning = null;
      startPinch();
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
    panning = null;
  });

  canvas.addEventListener("pointercancel", (ev) => {
    activePointers.delete(ev.pointerId);
    if (activePointers.size < 2){
      pinchState = null;
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

  document.getElementById("zoomIn").addEventListener("click", () => {
    const r = canvas.getBoundingClientRect();
    zoomAt(zoom + 4, r.width / 2, r.height / 2);
  });
  document.getElementById("zoomOut").addEventListener("click", () => {
    const r = canvas.getBoundingClientRect();
    zoomAt(zoom - 4, r.width / 2, r.height / 2);
  });
  document.getElementById("lockMap").addEventListener("click", (ev) => {
    lockMap = !lockMap;
    ev.target.textContent = lockMap ? "Unlock Map" : "Lock Map";
  });
  document.getElementById("centerMap").addEventListener("click", () => {
    centerOnClaimed();
    draw();
  });

  document.getElementById("changeChar").addEventListener("click", () => {
    const pcs = lastPcList || [];
    if (pcs && pcs.length){
      showClaim(pcs);
    } else {
      claimModal.classList.add("show");
    }
  });

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
      localStorage.setItem("inittracker_claimedCid", claimedCid);
      localStorage.setItem("inittracker_tokenColor", color);
      send({type:"claim", cid: Number(pendingClaim.cid)});
      send({type:"set_color", cid: Number(pendingClaim.cid), color});
      meEl.textContent = pendingClaim.name;
      closeColorModal();
      claimModal.classList.remove("show");
    });
  }
  if (tokenColorCancel){
    tokenColorCancel.addEventListener("click", () => {
      closeColorModal();
      const pcs = lastPcList || [];
      if (pcs && pcs.length){
        showClaim(pcs);
      } else {
        claimModal.classList.add("show");
      }
    });
  }

  document.getElementById("dash").addEventListener("click", () => {
    if (!claimedCid) return;
    showDashModal();
  });
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
  useActionBtn.addEventListener("click", () => {
    if (!claimedCid) return;
    send({type:"use_action", cid: Number(claimedCid)});
  });
  useBonusActionBtn.addEventListener("click", () => {
    if (!claimedCid) return;
    send({type:"use_bonus_action", cid: Number(claimedCid)});
  });
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

  document.addEventListener("pointerdown", handleUserGesture, {passive: true});
  document.addEventListener("keydown", handleUserGesture);

  const mapWrap = document.querySelector(".mapWrap");
  if (mapWrap && window.ResizeObserver){
    const ro = new ResizeObserver(() => resize());
    ro.observe(mapWrap);
  }
  resize();
  updateWaitingOverlay();
  connect();
})();
</script>
</body>
</html>
"""

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

class LanController:
    """Runs a FastAPI+WebSocket server in a background thread and bridges actions into the Tk thread."""

    def __init__(self, app: "InitiativeTracker") -> None:
        self.app = app
        self.cfg = LanConfig()
        self._server_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._uvicorn_server = None

        self._clients_lock = threading.Lock()
        self._clients: Dict[int, Any] = {}  # id(websocket) -> websocket
        self._clients_meta: Dict[int, Dict[str, Any]] = {}  # id(websocket) -> {host,port,ua,connected_at}
        self._claims: Dict[int, int] = {}   # id(websocket) -> cid
        self._cid_to_ws: Dict[int, int] = {}  # cid -> id(websocket) (1 owner at a time)
        self._client_ids: Dict[int, str] = {}  # id(websocket) -> client_id
        self._client_claims: Dict[str, int] = {}  # client_id -> cid (last known claim)
        self._cid_to_client: Dict[int, str] = {}  # cid -> client_id (active claim)

        self._actions: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._last_state_json: Optional[str] = None
        self._polling: bool = False
        self._grid_version: int = 0
        self._grid_pending: Dict[int, Tuple[int, float]] = {}
        self._grid_resend_seconds: float = 1.5
        self._grid_last_sent: Optional[Tuple[Optional[int], Optional[int]]] = None
        self._cached_snapshot: Dict[str, Any] = {
            "grid": None,
            "obstacles": [],
            "units": [],
            "active_cid": None,
            "round_num": 0,
        }
        self._cached_pcs: List[Dict[str, Any]] = []

    # ---------- Tk thread API ----------

    def start(self, quiet: bool = False) -> None:
        if self._server_thread and self._server_thread.is_alive():
            self.app._oplog("LAN server already runnin'.")
            return

        # Lazy imports so the base app still works without these deps installed.
        try:
            from fastapi import FastAPI, WebSocket, WebSocketDisconnect
            from fastapi.responses import HTMLResponse
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
        if not (assets_dir / "alert.wav").exists():
            self.app._oplog(
                f"LAN assets missing alert.wav at {assets_dir / 'alert.wav'} (check assets_dir path).",
                level="warning",
            )

        @app.get("/")
        async def index():
            return HTMLResponse(HTML_INDEX)

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
                self._clients_meta[ws_id] = {"host": host, "port": port, "ua": ua, "connected_at": connected_at}
            self.app._oplog(f"LAN session connected ws_id={ws_id} host={host}:{port} ua={ua}")
            try:
                await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                # Immediately send snapshot + claimable list
                await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
                while True:
                    raw = await ws.receive_text()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    typ = str(msg.get("type") or "")
                    if typ == "hello":
                        # If client sends previous claim, remember it (optional).
                        claimed = msg.get("claimed")
                        client_id = msg.get("client_id")
                        if isinstance(client_id, str):
                            client_id = client_id.strip()
                        else:
                            client_id = None
                        if client_id:
                            with self._clients_lock:
                                self._client_ids[ws_id] = client_id
                            known_claim = self._client_claims.get(client_id)
                            if known_claim is not None and self._can_auto_claim(int(known_claim)):
                                await self._claim_ws_async(ws_id, int(known_claim), note="Reconnected.")
                            elif isinstance(claimed, int) and self._can_auto_claim(int(claimed)):
                                await self._claim_ws_async(ws_id, int(claimed), note="Reconnected.")
                        elif isinstance(claimed, int) and self._can_auto_claim(int(claimed)):
                            await self._claim_ws_async(ws_id, int(claimed), note="Reconnected.")
                        await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
                    elif typ == "grid_request":
                        await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                    elif typ == "grid_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._grid_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._grid_pending.pop(ws_id, None)
                    elif typ == "claim":
                        cid = msg.get("cid")
                        if isinstance(cid, int):
                            await self._claim_ws_async(ws_id, cid, note="Claimed. Drag yer token, matey.")
                            await ws.send_text(json.dumps({"type": "state", "state": self._cached_snapshot_payload(), "pcs": self._pcs_payload()}))
                    elif typ == "log_request":
                        try:
                            lines = self.app._lan_battle_log_lines()
                        except Exception:
                            lines = []
                        await ws.send_text(json.dumps({"type": "battle_log", "lines": lines}))
                    elif typ in ("move", "dash", "end_turn", "use_action", "use_bonus_action", "set_color", "reset_turn"):
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
                out.append(
                    {
                        "ws_id": int(ws_id),
                        "cid": int(cid) if cid is not None else None,
                        "host": meta.get("host", "?"),
                        "port": meta.get("port", ""),
                        "user_agent": meta.get("ua", ""),
                        "connected_at": meta.get("connected_at", ""),
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
            await self._unclaim_ws_async(ws_id, reason=note)
            return
        await self._claim_ws_async(ws_id, int(cid), note=note)

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
            pp["claimed_by"] = cid_to_client.get(int(pp.get("cid", -1)))
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

    async def _unclaim_ws_async(self, ws_id: int, reason: str = "Unclaimed") -> None:
        # Drop claim mapping
        with self._clients_lock:
            old = self._claims.pop(ws_id, None)
            if old is not None:
                self._cid_to_ws.pop(int(old), None)
                self._cid_to_client.pop(int(old), None)
            client_id = self._client_ids.get(ws_id)
            if client_id:
                self._client_claims.pop(client_id, None)
        if old is not None:
            name = self._pc_name_for(int(old))
            self.app._oplog(f"LAN session ws_id={ws_id} unclaimed {name} ({reason})")
        await self._send_async(ws_id, {"type": "force_unclaim", "text": reason, "pcs": self._pcs_payload()})

    async def _claim_ws_async(self, ws_id: int, cid: int, note: str = "Claimed") -> None:
        # Ensure cid is a PC
        pcs = {int(p.get("cid")): p for p in self._cached_pcs}
        if int(cid) not in pcs:
            await self._send_async(ws_id, {"type": "toast", "text": "That character ain't claimable, matey."})
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
        ttk.Button(controls, text="Assign", command=do_assign).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(controls, text="Unassign", command=do_kick).pack(side=tk.LEFT, padx=(6, 0))
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

        if mw is not None:
            try:
                cols = int(getattr(mw, "cols", cols))
                rows = int(getattr(mw, "rows", rows))
            except Exception:
                pass
            try:
                for aid, d in sorted((getattr(mw, "aoes", {}) or {}).items()):
                    kind = str(d.get("kind") or "")
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
                    }
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
            try:
                obstacles = set(getattr(mw, "obstacles", obstacles) or set())
            except Exception:
                pass
            try:
                for cid, tok in (getattr(mw, "unit_tokens", {}) or {}).items():
                    positions[int(cid)] = (int(tok.get("col")), int(tok.get("row")))
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
                    "pos": {"col": int(pos[0]), "row": int(pos[1])},
                    "marks": marks,
                }
            )

        # Active creature
        active = self.current_cid if getattr(self, "current_cid", None) is not None else None

        grid_payload = None
        if map_ready:
            grid_payload = {"cols": int(cols), "rows": int(rows), "feet_per_square": 5}
        snap: Dict[str, Any] = {
            "grid": grid_payload,
            "obstacles": [{"col": int(c), "row": int(r)} for (c, r) in sorted(obstacles)],
            "aoes": aoes,
            "units": units,
            "active_cid": active,
            "round_num": int(getattr(self, "round_num", 0) or 0),
        }
        return snap

    def _lan_marks_for(self, c: Any) -> str:
        # Match main-map effect markers (conditions, DoT, star advantage, etc.)
        try:
            text = self._format_effects(c)
        except Exception:
            text = ""
        return (text or "").strip()

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
        if self.current_cid is None or int(self.current_cid) != int(cid):
            self._lan.toast(ws_id, "Not yer turn yet, matey.")
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
        elif typ == "reset_turn":
            if self._lan_restore_turn_snapshot(cid):
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
            mon = data.get("monster")
            if not isinstance(mon, dict):
                continue

            name = str(mon.get("name") or fp.stem).strip()
            if not name:
                continue

            mtype = str(mon.get("type") or "unknown").strip() or "unknown"

            cr_val = None
            try:
                ch = mon.get("challenge") or {}
                if isinstance(ch, dict) and "cr" in ch:
                    cr_val = ch.get("cr")
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
                defs = mon.get("defenses") or {}
                if isinstance(defs, dict):
                    hp_block = defs.get("hit_points") or {}
                    if isinstance(hp_block, dict):
                        avg = hp_block.get("average")
                        if isinstance(avg, int):
                            hp = int(avg)
                        elif isinstance(avg, str) and avg.strip().isdigit():
                            hp = int(avg.strip())
            except Exception:
                hp = None

            speed = None
            swim_speed = None
            try:
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
            except Exception:
                speed = None
                swim_speed = None

            dex = None
            try:
                ab = mon.get("abilities") or {}
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

            self._monster_combo = combo  # type: ignore[attr-defined]

            if values and not self.name_var.get().strip():
                self.name_var.set(values[0])
                self._on_monster_selected()
        except Exception:
            return

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
