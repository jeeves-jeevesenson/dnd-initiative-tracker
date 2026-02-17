#!/usr/bin/env python3
"""
DnD Initiative Tracker

Run:
  python3 dnd_initative_tracker.py

Features:
- Initiative order with configurable "Start Here" rotation
- Turn tracker (current creature, round count, turn count) + loops
- HP + Speed (movement) per creature
- Damage tool (calculator-style) with auto-remove only when damage drops HP to 0
- Heal tool (simple HP add with optional attacker logging)
- Damage-over-time conditions (Burn/Poison/Necrotic) that roll at start of creature's turn
- Conditions (2024 Basic Rules list) with stackable durations, auto-skip for certain conditions
- Prone: Stand Up button spends half movement to remove Prone
- Star Advantage condition: expires at start of creature's turn
- Ally name text in green, enemies in red
- Persistent log with history file
- Conditions tick down at end of each creature's turn (non-stacking, Exhaustion excepted)
"""

from __future__ import annotations

import random
import math
import os
import sys
import shutil
import ast
import re
import json
import hashlib
import threading
from pathlib import Path
from datetime import datetime

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Set, Union
from tkinter import messagebox, ttk, simpledialog, filedialog

PIL_IMAGE_IMPORT_ERROR: Optional[str] = None
PIL_IMAGETK_IMPORT_ERROR: Optional[str] = None
USER_YAML_DIRNAME = "Dnd-Init-Yamls"

try:
    from PIL import Image  # type: ignore
except Exception as e:  # pragma: no cover
    Image = None
    PIL_IMAGE_IMPORT_ERROR = str(e)

try:
    from PIL import ImageTk  # type: ignore
except Exception as e:  # pragma: no cover
    ImageTk = None
    PIL_IMAGETK_IMPORT_ERROR = str(e)


def _app_base_dir() -> Path:
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
    except Exception:
        pass
    try:
        return Path(__file__).resolve().parent
    except Exception:
        try:
            return Path.cwd()
        except Exception:
            return Path(".")


def _app_data_dir() -> Path:
    override = os.getenv("INITTRACKER_DATA_DIR")
    if override:
        try:
            return Path(override).expanduser()
        except Exception:
            pass
    try:
        docs_dir = Path.home() / "Documents"
        return docs_dir / USER_YAML_DIRNAME
    except Exception:
        pass
    return _app_base_dir()


def _seed_user_players_dir() -> None:
    _seed_user_items_dir()
    user_dir = _app_data_dir() / "players"
    base_dir = _app_base_dir() / "players"
    if not base_dir.exists():
        return
    try:
        if user_dir.exists():
            if any(user_dir.glob("*.y*ml")):
                return
    except Exception:
        return
    try:
        user_dir.mkdir(parents=True, exist_ok=True)
        for path in list(base_dir.glob("*.y*ml")):
            dest = user_dir / path.name
            if not dest.exists():
                shutil.copy2(path, dest)
    except Exception:
        pass


def _seed_user_monsters_dir() -> Path:
    user_dir = _app_data_dir() / "Monsters"
    base_dir = _app_base_dir() / "Monsters"
    try:
        user_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return base_dir
    if not base_dir.exists():
        return user_dir
    try:
        for path in base_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            rel = path.relative_to(base_dir)
            dest = user_dir / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    except Exception:
        pass
    return user_dir


def _seed_user_items_dir() -> Path:
    user_dir = _app_data_dir() / "Items"
    base_dir = _app_base_dir() / "Items"
    try:
        (user_dir / "Weapons").mkdir(parents=True, exist_ok=True)
        (user_dir / "Armor").mkdir(parents=True, exist_ok=True)
    except Exception:
        return base_dir
    if not base_dir.exists():
        return user_dir
    try:
        for path in base_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            rel = path.relative_to(base_dir)
            dest = user_dir / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    except Exception:
        pass
    return user_dir


# --- 2024 Basic Rules (conditions list) ---
# Roll20's Free Basic Rules (2024) index includes:
# Blinded, Charmed, Deafened, Exhaustion, Frightened, Grappled, Incapacitated,
# Invisible, Paralyzed, Petrified, Poisoned, Prone, Restrained, Stunned, Unconscious.

CONDITIONS_META: Dict[str, Dict[str, object]] = {
    "blinded": {"label": "Blinded", "icon": "🙈", "skip": False, "immobile": False},
    "charmed": {"label": "Charmed", "icon": "💖", "skip": False, "immobile": False},
    "deafened": {"label": "Deafened", "icon": "🔇", "skip": False, "immobile": False},
    "exhaustion": {"label": "Exhaustion", "icon": "🥱", "skip": False, "immobile": False},  # tracked as level
    "frightened": {"label": "Frightened", "icon": "😱", "skip": False, "immobile": False},
    "grappled": {"label": "Grappled", "icon": "🤼", "skip": False, "immobile": True},
    "incapacitated": {"label": "Incapacitated", "icon": "⛔", "skip": True, "immobile": False},
    "invisible": {"label": "Invisible", "icon": "🫥", "skip": False, "immobile": False},
    "paralyzed": {"label": "Paralyzed", "icon": "🧊", "skip": True, "immobile": True},
    "petrified": {"label": "Petrified", "icon": "🪨", "skip": True, "immobile": True},
    "poisoned": {"label": "Poisoned", "icon": "🤢", "skip": False, "immobile": False},
    "prone": {"label": "Prone", "icon": "🛌", "skip": False, "immobile": False},
    "restrained": {"label": "Restrained", "icon": "⛓", "skip": False, "immobile": True},
    "stunned": {"label": "Stunned", "icon": "💫", "skip": True, "immobile": True},
    "unconscious": {"label": "Unconscious", "icon": "😴", "skip": True, "immobile": True},
    "star_advantage": {"label": "Star Advantage", "icon": "⭐", "skip": False, "immobile": False},
    "dot": {"label": "Damage over Time", "icon": "🩸", "skip": False, "immobile": False},
}

DOT_META = {
    "burn": {"label": "Burn", "icon": "🔥"},
    "poison": {"label": "Poison", "icon": "☠"},
    "necrotic": {"label": "Necrotic", "icon": "💀"},

}
AOE_COLOR_PRESETS = [
    ("Blue", "#2d4f8a"),
    ("Green", "#2d8a57"),
    ("Purple", "#6b3d8a"),
    ("Red", "#8a2d2d"),
    ("Orange", "#c2651a"),
    ("Yellow", "#b59a00"),
    ("Gray", "#5c5c5c"),
    ("Black", "#111111"),
]
DEFAULT_ROUGH_TERRAIN_PRESETS = [
    {"label": "Mud", "color": "#8d6e63", "movement_type": "ground", "is_swim": False, "is_rough": True},
    {"label": "Water", "color": "#4aa3df", "movement_type": "water", "is_swim": True, "is_rough": False},
    {"label": "Grass", "color": "#6ab04c", "movement_type": "ground", "is_swim": False, "is_rough": True},
    {"label": "Stone", "color": "#9e9e9e", "movement_type": "ground", "is_swim": False, "is_rough": True},
    {"label": "Sand", "color": "#d4a373", "movement_type": "ground", "is_swim": False, "is_rough": True},
    {"label": "Magic", "color": "#8e44ad", "movement_type": "ground", "is_swim": False, "is_rough": True},
    {"label": "Shadow", "color": "#4b4b4b", "movement_type": "ground", "is_swim": False, "is_rough": True},
]
DEFAULT_STARTING_PLAYERS = [
    "John Twilight",
    "стихия",
    "Thibble Wobblepop",
    "Throat Goat",
    "Dorian Vandergraff",
    "Old Man",
    "Fred Figglehorn",
    "Malagrou Thunderclopper",
    "Johnny Morris",
]

DAMAGE_TYPES = [
    "",
    "Acid",
    "Bludgeoning",
    "Cold",
    "Fire",
    "Force",
    "Lightning",
    "Necrotic",
    "Piercing",
    "Poison",
    "Psychic",
    "Radiant",
    "Slashing",
    "Thunder",
]

MOVEMENT_MODES = ("normal", "swim", "burrow", "fly")
MOVEMENT_MODE_LABELS = {
    "normal": "Normal",
    "swim": "Swim",
    "burrow": "Burrow",
    "fly": "Fly",
}
# Climb mode is deferred until elevation support lands.


def _apply_dialog_geometry(dlg: tk.Toplevel, width: int, height: int, min_w: int, min_h: int) -> None:
    dlg.geometry(f"{width}x{height}")
    dlg.minsize(min_w, min_h)
    dlg.update_idletasks()
    req_w = max(dlg.winfo_reqwidth(), min_w)
    req_h = max(dlg.winfo_reqheight(), min_h)
    dlg.minsize(req_w, req_h)
    if dlg.winfo_width() < req_w or dlg.winfo_height() < req_h:
        dlg.geometry(f"{max(dlg.winfo_width(), req_w)}x{max(dlg.winfo_height(), req_h)}")




@dataclass
class ConditionStack:
    sid: int
    ctype: str  # key in CONDITIONS_META (except exhaustion, which is level-based)
    remaining_turns: Optional[int]  # None = indefinite
    dot_type: Optional[str] = None
    dice: Optional[Dict[int, int]] = None


@dataclass
class Combatant:
    cid: int
    name: str
    hp: int
    speed: int
    swim_speed: int
    fly_speed: int
    burrow_speed: int
    climb_speed: int
    movement_mode: str
    move_remaining: int
    initiative: int
    dex: Optional[int] = None
    roll: Optional[int] = None
    nat20: bool = False
    ally: bool = False
    is_pc: bool = False
    is_spellcaster: bool = False
    token_color: Optional[str] = None
    move_total: int = 0
    temp_move_bonus: int = 0
    temp_move_turns_remaining: int = 0
    action_remaining: int = 1
    attack_resource_remaining: int = 0
    bonus_action_remaining: int = 1
    reaction_remaining: int = 1
    spell_cast_remaining: int = 1
    actions: List[Dict[str, Any]] = field(default_factory=list)
    bonus_actions: List[Dict[str, Any]] = field(default_factory=list)
    extra_action_pool: int = 0
    extra_bonus_pool: int = 0
    saving_throws: Dict[str, int] = field(default_factory=dict)
    ability_mods: Dict[str, int] = field(default_factory=dict)
    monster_spec: Optional[MonsterSpec] = None

    # Mount state
    mounted_by_cid: Optional[int] = None  # rider riding this mount
    rider_cid: Optional[int] = None  # mount this rider is using
    mount_shared_turn: bool = False
    mount_controller_mode: str = "independent"  # rider|independent|summon_auto
    has_mounted_this_turn: bool = False
    can_be_mounted: bool = False


    # Effects / statuses
    condition_stacks: List[ConditionStack] = field(default_factory=list)
    exhaustion_level: int = 0  # 0-6
    concentrating: bool = False
    concentration_spell_level: Optional[int] = None
    concentration_started_turn: Optional[Tuple[int, int]] = None
    concentration_aoe_ids: List[int] = field(default_factory=list)


@dataclass
class MonsterSpec:
    filename: str
    name: str
    mtype: str
    cr: Optional[float]
    hp: Optional[int]
    speed: Optional[int]
    swim_speed: Optional[int]
    fly_speed: Optional[int]
    burrow_speed: Optional[int]
    climb_speed: Optional[int]
    dex: Optional[int]
    init_mod: Optional[int]
    saving_throws: Dict[str, int]
    ability_mods: Dict[str, int]
    raw_data: Dict[str, Any]


@dataclass(frozen=True)
class TerrainPreset:
    label: str
    color: str
    movement_type: str
    is_swim: bool
    is_rough: bool


def _normalize_hex_color_value(color: object) -> Optional[str]:
    if not isinstance(color, str):
        return None
    value = color.strip().lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        return None
    return value


def _normalize_movement_type(value: object, is_swim: bool = False) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"water", "ground"}:
            return lowered
        if lowered in {"swim", "waterborne"}:
            return "water"
        if lowered in {"land", "normal", "burrow", "earth"}:
            return "ground"
    return "water" if is_swim else "ground"


def _parse_speed_number(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return None
    return None


def _normalize_speed_key(key: object) -> str:
    if not isinstance(key, str):
        return ""
    text = key.strip().lower().replace("_", " ").replace("-", " ")
    text = text.replace("ft", "").strip()
    return " ".join(text.split())


def _parse_speed_string(text: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for part in re.split(r"[;,]", text):
        chunk = part.strip()
        if not chunk:
            continue
        value = _parse_speed_number(chunk)
        if value is None:
            continue
        lowered = chunk.lower()
        label = None
        for key in ("fly", "swim", "burrow", "climb", "walk", "land", "normal"):
            if key in lowered:
                label = key
                break
        if label is None:
            label = "normal"
        if label not in result:
            result[label] = value
    return result


def _parse_speed_data(value: object) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]:
    speeds: Dict[str, Optional[int]] = {
        "normal": None,
        "swim": None,
        "fly": None,
        "burrow": None,
        "climb": None,
    }

    def set_speed(kind: str, speed_val: Optional[int]) -> None:
        if speed_val is None:
            return
        if speeds.get(kind) is None:
            speeds[kind] = speed_val

    def apply_label(label: str, speed_val: Optional[int]) -> None:
        if speed_val is None:
            return
        normalized = _normalize_speed_key(label)
        if normalized in {"normal", "walk", "land", "ground", "base", "speed"}:
            set_speed("normal", speed_val)
        elif normalized in {"swim", "fly", "burrow", "climb"}:
            set_speed(normalized, speed_val)
        else:
            set_speed("normal", speed_val)

    if isinstance(value, dict):
        for key, entry in value.items():
            if isinstance(entry, str):
                parsed = _parse_speed_string(entry)
                if parsed:
                    for label, spd in parsed.items():
                        apply_label(label, spd)
                    continue
            apply_label(str(key), _parse_speed_number(entry))
    elif isinstance(value, str):
        parsed = _parse_speed_string(value)
        for label, spd in parsed.items():
            apply_label(label, spd)
    else:
        apply_label("normal", _parse_speed_number(value))

    return (
        speeds["normal"],
        speeds["swim"],
        speeds["fly"],
        speeds["burrow"],
        speeds["climb"],
    )


def _terrain_preset_from_entry(entry: object) -> Optional[TerrainPreset]:
    if not isinstance(entry, dict):
        return None
    label = str(entry.get("label") or "").strip()
    color = _normalize_hex_color_value(entry.get("color"))
    is_swim = bool(entry.get("is_swim", False))
    movement_type = _normalize_movement_type(entry.get("movement_type"), is_swim=is_swim)
    if movement_type == "water":
        is_swim = True
    is_rough = bool(entry.get("is_rough", False))
    if not label:
        label = color or "Terrain"
    if not color:
        return None
    return TerrainPreset(
        label=label,
        color=color,
        movement_type=movement_type,
        is_swim=is_swim,
        is_rough=is_rough,
    )


def _load_rough_terrain_presets() -> List[TerrainPreset]:
    preset_dir = Path(__file__).resolve().parent / "presets" / "rough_terrain"
    presets: List[TerrainPreset] = []
    if preset_dir.exists():
        for path in sorted(preset_dir.iterdir()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in (".json", ".yml", ".yaml"):
                continue
            data: object = None
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    if suffix == ".json":
                        data = json.load(handle)
                    elif yaml is not None:
                        data = yaml.safe_load(handle)
            except Exception:
                continue
            entries: List[object] = []
            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict):
                raw_entries = data.get("terrains")
                if isinstance(raw_entries, list):
                    entries = raw_entries
            for entry in entries:
                preset = _terrain_preset_from_entry(entry)
                if preset is None:
                    continue
                presets.append(preset)
    if presets:
        return presets
    fallback: List[TerrainPreset] = []
    for entry in DEFAULT_ROUGH_TERRAIN_PRESETS:
        preset = _terrain_preset_from_entry(entry)
        if preset is not None:
            fallback.append(preset)
    return fallback


class InitiativeTracker(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DnD Initiative Tracker")
        self.geometry("1120x720")
        icon_path = Path(__file__).resolve().parent / "assets" / "graphic-512.png"
        try:
            if icon_path.exists():
                photo = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, photo)
                self._app_icon = photo
        except Exception:
            pass

        self._next_id = 1
        self._next_stack_id = 1
        self.combatants: Dict[int, Combatant] = {}
        self._monster_specs: List[MonsterSpec] = []
        self._monsters_by_name: Dict[str, MonsterSpec] = {}
        self._monster_index_cache: Optional[Dict[str, object]] = None
        self._monster_detail_cache: Dict[str, Dict[str, Any]] = {}
        self._monster_library_refreshers: List[Callable[[], None]] = []
        self.rough_terrain_presets: List[TerrainPreset] = _load_rough_terrain_presets()
        self._index_loading = False
        self._index_loading_callbacks: List[Callable[[], None]] = []

        # Remember roles for name-based log styling (pc/ally/enemy)
        self._name_role_memory: Dict[str, str] = {}
        try:
            for _nm in self._load_starting_players_roster():
                self._name_role_memory[str(_nm)] = "pc"
        except Exception:
            pass

        self.start_cid: Optional[int] = None

        # Turn tracker state
        self.current_cid: Optional[int] = None
        self.round_num: int = 1
        self.turn_num: int = 0
        self._concentration_save_state: Dict[Tuple[int, Tuple[int, int]], Dict[str, object]] = {}

        self._build_ui()
        self._load_indexes_async(self._refresh_monster_library)
        self._load_history_into_log()
        self._log("=== Session started ===")
        self._open_starting_players_dialog()
        self._rebuild_table()

    # -------------------------- UI --------------------------
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("DnD.TLabelframe", padding=8)
        style.configure("DnD.Treeview", rowheight=24)

        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Add frame
        add_frame = ttk.LabelFrame(container, text="Add Combatant", style="DnD.TLabelframe")
        add_frame.pack(fill=tk.X, pady=(0, 8))

        left_controls = ttk.Frame(add_frame)
        left_controls.grid(row=0, column=0, sticky="w")

        ttk.Button(left_controls, text="Bulk Add…", command=self._open_bulk_dialog).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Remove Selected", command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Damage…", command=self._open_damage_tool).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Heal…", command=self._open_heal_tool).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Conditions…", command=self._open_condition_tool).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Set Start Here", command=self._set_start_here).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Clear Start", command=self._clear_start).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left_controls, text="Refresh monsters/spells", command=self._refresh_monsters_spells).pack(side=tk.LEFT, padx=(8, 0))

        library_frame = ttk.LabelFrame(add_frame, text="Creature Library (view-only)")
        library_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        library_frame.columnconfigure(0, weight=1)

        library_top = ttk.Frame(library_frame)
        library_top.grid(row=0, column=0, sticky="ew")
        library_top.columnconfigure(0, weight=1)

        self.monster_library_filter_var = tk.StringVar()
        ttk.Label(library_top, text="Search").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(library_top, textvariable=self.monster_library_filter_var, width=26)
        search_entry.grid(row=1, column=0, sticky="w", padx=(0, 8))

        sort_label = ttk.Label(library_top, text="Sort by")
        sort_label.grid(row=0, column=1, sticky="w")
        self.monster_library_sort_var = tk.StringVar(value="Name")
        sort_combo = ttk.Combobox(
            library_top,
            textvariable=self.monster_library_sort_var,
            values=["Name", "Type", "CR", "HP", "Speed"],
            state="readonly",
            width=12,
        )
        sort_combo.grid(row=1, column=1, sticky="w", padx=(0, 8))

        info_btn = ttk.Button(library_top, text="Info", command=self._open_selected_library_monster_info)
        info_btn.grid(row=1, column=2, sticky="w")

        library_list = tk.Listbox(library_frame, height=6, exportselection=False)
        library_scroll = ttk.Scrollbar(library_frame, orient="vertical", command=library_list.yview)
        library_list.configure(yscrollcommand=library_scroll.set)
        library_list.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        library_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        self._monster_library_listbox = library_list
        self._monster_library_sort_combo = sort_combo
        self._monster_library_filter_entry = search_entry
        self._monster_library_info_btn = info_btn

        def _refresh_library() -> None:
            self._refresh_monster_library_list()

        self.monster_library_filter_var.trace_add("write", lambda *_args: _refresh_library())
        self.monster_library_sort_var.trace_add("write", lambda *_args: _refresh_library())
        self._monster_library_refreshers.append(_refresh_library)
        _refresh_library()

        # Turn frame
        turn_frame = ttk.LabelFrame(container, text="Turn Tracker", style="DnD.TLabelframe")
        turn_frame.pack(fill=tk.X, pady=(0, 8))

        self.turn_current_var = tk.StringVar(value="(not started)")
        self.turn_round_var = tk.StringVar(value="1")
        self.turn_count_var = tk.StringVar(value="0")
        self.turn_move_var = tk.StringVar(value="—")
        self.start_last_var = tk.StringVar(value="")

        ttk.Label(turn_frame, text="Current:").grid(row=0, column=0, sticky="w")
        ttk.Label(turn_frame, textvariable=self.turn_current_var).grid(row=0, column=1, sticky="w", padx=(0, 20))

        ttk.Label(turn_frame, text="Round:").grid(row=0, column=2, sticky="w")
        ttk.Label(turn_frame, textvariable=self.turn_round_var, width=6).grid(row=0, column=3, sticky="w", padx=(0, 20))

        ttk.Label(turn_frame, text="Turn:").grid(row=0, column=4, sticky="w")
        ttk.Label(turn_frame, textvariable=self.turn_count_var, width=8).grid(row=0, column=5, sticky="w", padx=(0, 20))

        ttk.Label(turn_frame, text="Move:").grid(row=0, column=6, sticky="w")
        ttk.Label(turn_frame, textvariable=self.turn_move_var, width=12).grid(row=0, column=7, sticky="w")

        btn_row = ttk.Frame(turn_frame)
        btn_row.grid(row=1, column=0, columnspan=8, sticky="w", pady=(6, 0))

        ttk.Button(btn_row, text="Start/Reset", command=self._start_turns).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Set Turn Here", command=self._set_turn_here).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Prev Turn", command=self._prev_turn).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Next Turn", command=self._next_turn).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Stand Up", command=self._stand_up_current).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Move…", command=self._open_move_tool).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Dash", command=self._dash_current).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Temp Move…", command=self._grant_temp_move_bonus).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Give Action", command=self._give_action).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Give Bonus Action", command=self._give_bonus_action).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(btn_row, text="Mode").pack(side=tk.LEFT, padx=(0, 4))
        self.move_mode_var = tk.StringVar(value=MOVEMENT_MODE_LABELS["normal"])
        self.move_mode_combo = ttk.Combobox(
            btn_row,
            textvariable=self.move_mode_var,
            values=[MOVEMENT_MODE_LABELS[mode] for mode in MOVEMENT_MODES],
            state="readonly",
            width=9,
        )
        self.move_mode_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.move_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_selected_movement_mode())
        ttk.Button(btn_row, text="Map Mode…", command=self._open_map_mode).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="LAN Admin…", command=self._open_lan_admin).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Roll LAN Initiative", command=self._roll_lan_initiative_for_claimed_pcs).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Long Rest…", command=self._confirm_long_rest).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Clear", command=self._clear_turns).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(
            btn_row, text="Shortcuts: Space=Next, Shift+Space=Prev, C=Conditions, D=Damage, H=Heal, M=Move, W=Mode, P=Map"
        ).pack(
            side=tk.LEFT, padx=(14, 0)
        )

        ttk.Label(turn_frame, text="Start-of-turn log:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(turn_frame, textvariable=self.start_last_var, wraplength=1000).grid(
            row=2, column=1, columnspan=7, sticky="w", pady=(6, 0)
        )


        # Table + Log (split pane)
        paned = ttk.PanedWindow(container, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        table_frame = ttk.LabelFrame(paned, text="Initiative Order", style="DnD.TLabelframe")
        log_frame = ttk.LabelFrame(paned, text="Log", style="DnD.TLabelframe")
        paned.add(table_frame, weight=4)
        paned.add(log_frame, weight=1)

        columns = ("name", "side", "hp", "temp_hp", "ac", "walk", "swim", "fly", "effects", "init")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="extended", style="DnD.Treeview"
        )

        self.tree.heading("name", text="Name", anchor="w")
        self.tree.heading("side", text="Side", anchor="center")
        self.tree.heading("hp", text="HP", anchor="center")
        self.tree.heading("temp_hp", text="Temp HP", anchor="center")
        self.tree.heading("ac", text="AC", anchor="center")
        self.tree.heading("walk", text="Walk", anchor="center")
        self.tree.heading("swim", text="Swim", anchor="center")
        self.tree.heading("fly", text="Fly", anchor="center")
        self.tree.heading("effects", text="Conditions", anchor="center")
        self.tree.heading("init", text="Initiative", anchor="center")

        self.tree.column("name", width=320, anchor=tk.W)
        self.tree.column("side", width=70, anchor=tk.CENTER)
        self.tree.column("hp", width=60, anchor=tk.CENTER)
        self.tree.column("temp_hp", width=70, anchor=tk.CENTER)
        self.tree.column("ac", width=60, anchor=tk.CENTER)
        self.tree.column("walk", width=60, anchor=tk.CENTER)
        self.tree.column("swim", width=60, anchor=tk.CENTER)
        self.tree.column("fly", width=60, anchor=tk.CENTER)
        self.tree.column("effects", width=260, anchor=tk.CENTER)
        self.tree.column("init", width=90, anchor=tk.CENTER)

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Log box
        log_top = ttk.Frame(log_frame)
        log_top.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.show_timestamps_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_top, text="Timestamp", variable=self.show_timestamps_var, command=self._toggle_log_timestamps).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(log_top, text="Clear Log", command=self._clear_log).pack(side=tk.RIGHT)

        log_body = ttk.Frame(log_frame)
        log_body.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.log_text = tk.Text(log_body, height=10, wrap="word")
        self.log_text.configure(state="disabled")
        log_scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._init_log_styles()

        # row tags
        self.tree.tag_configure("odd", background="#f7f1df")
        self.tree.tag_configure("even", background="#fbf7eb")
        self.tree.tag_configure("ally", foreground="#1b7f2a")
        self.tree.tag_configure("enemy", foreground="#b02a2a")
        self.tree.tag_configure("current", background="#fff2b2")
        self.tree.tag_configure("start", background="#cfe8ff")

        # bindings
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_move_mode_selector())
        self.bind("<space>", lambda e: self._next_turn())
        self.bind("<Shift-space>", lambda e: self._prev_turn())
        self.bind("<KeyPress-d>", lambda e: self._open_damage_tool())
        self.bind("<KeyPress-h>", lambda e: self._open_heal_tool())
        self.bind("<KeyPress-c>", lambda e: self._open_condition_tool())
        self.bind("<KeyPress-t>", lambda e: self._open_dot_tool())
        self.bind("<KeyPress-m>", lambda e: self._open_move_tool())
        self.bind("<KeyPress-w>", lambda e: self._cycle_movement_mode_selected())
        self.bind("<KeyPress-p>", lambda e: self._open_map_mode())

        self._tree_context_menu = tk.Menu(self, tearoff=0)
        self._tree_context_menu.add_command(
            label="View Monster Info",
            command=self._open_selected_monster_info,
            state=tk.DISABLED,
        )

    def _confirm_long_rest(self) -> None:
        if not messagebox.askyesno("Long Rest", "Are you sure?", parent=self):
            return
        if not hasattr(self, "_reset_player_character_resources"):
            messagebox.showerror("Long Rest", "Long rest support is not available in this build.", parent=self)
            return
        try:
            updated = self._reset_player_character_resources()
        except Exception as exc:
            messagebox.showerror("Long Rest", f"Failed to reset player resources.\n\n{exc}", parent=self)
            return
        if updated:
            for c in self.combatants.values():
                role = self._name_role_memory.get(str(c.name), "enemy")
                if not getattr(c, "is_pc", False) and role != "pc":
                    continue
                key = str(c.name or "").strip().lower()
                if key in updated:
                    try:
                        c.hp = int(updated[key])
                    except Exception:
                        pass
        try:
            self._rebuild_table(scroll_to_current=True)
        except Exception:
            pass
        if hasattr(self, "_lan_force_state_broadcast"):
            try:
                self._lan_force_state_broadcast()
            except Exception:
                pass
        try:
            self._log("Long rest applied to player characters.")
        except Exception:
            pass
        messagebox.showinfo("Long Rest", "Player characters restored.", parent=self)

    def _roll_lan_initiative_for_claimed_pcs(self) -> None:
        messagebox.showinfo(
            "Roll LAN Initiative",
            "LAN initiative prompting is not available in this build.",
            parent=self,
        )

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
            nm = self._selected_library_name()
            spec = self._monsters_by_name.get(nm) if nm else None
        if spec is not None:
            spec = self._load_monster_details(spec.name) or spec

        win = tk.Toplevel(self)
        title = f"{spec.name} Stat Block" if spec else "Monster Info"
        win.title(title)
        win.geometry("560x680")
        win.transient(self)

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

    def _selected_library_name(self) -> str:
        listbox = getattr(self, "_monster_library_listbox", None)
        if listbox is not None:
            try:
                selection = listbox.curselection()
                if selection:
                    raw = str(listbox.get(selection[0]))
                    return raw.split(" | ")[0].strip()
            except Exception:
                pass
        return ""

    def _open_selected_library_monster_info(self) -> None:
        name = self._selected_library_name()
        if not name:
            messagebox.showinfo("Monster Info", "Select a creature from the library first.")
            return
        spec = self._monsters_by_name.get(name)
        if spec is None:
            messagebox.showinfo("Monster Info", f"No stat block available for {name}.")
            return
        spec = self._load_monster_details(spec.name) or spec
        self._open_monster_stat_block(spec)

    def _refresh_monster_library_list(self) -> None:
        listbox = getattr(self, "_monster_library_listbox", None)
        if listbox is None:
            return
        filter_txt = str(getattr(self, "monster_library_filter_var", tk.StringVar()).get()).strip().lower()
        sort_by = str(getattr(self, "monster_library_sort_var", tk.StringVar()).get()).strip().lower()
        specs = list(self._monster_specs)
        if filter_txt:
            def matches(spec: MonsterSpec) -> bool:
                name = spec.name.lower()
                mtype = spec.mtype.lower() if spec.mtype else ""
                return filter_txt in name or filter_txt in mtype

            specs = [s for s in specs if matches(s)]
        if sort_by == "type":
            specs.sort(key=lambda s: (s.mtype.lower() if s.mtype else "", s.name.lower()))
        elif sort_by == "cr":
            specs.sort(key=lambda s: (s.cr is None, float(s.cr or 0), s.name.lower()))
        elif sort_by == "hp":
            specs.sort(key=lambda s: (s.hp is None, int(s.hp or 0), s.name.lower()))
        elif sort_by == "speed":
            specs.sort(key=lambda s: (s.speed is None, int(s.speed or 0), s.name.lower()))
        else:
            specs.sort(key=lambda s: s.name.lower())

        listbox.delete(0, tk.END)
        for spec in specs:
            cr_txt = self._monster_cr_display(spec)
            hp_txt = "?" if spec.hp is None else str(spec.hp)
            spd_txt = "?" if spec.speed is None else str(spec.speed)
            item = f"{spec.name} | {spec.mtype} | CR {cr_txt} | HP {hp_txt} | Spd {spd_txt}"
            listbox.insert(tk.END, item)


    # --------------------- Map Mode ---------------------
    def _open_map_mode(self) -> None:
        """Open the battle map window (Map Mode)."""
        try:
            if self._map_window is not None and self._map_window.winfo_exists():
                try:
                    self._map_window.refresh_spell_overlays()
                except Exception as exc:
                    self._log(f"Map spell overlay refresh failed: {exc}")
                self._map_window.refresh_units()
                self._map_window.lift()
                self._map_window.focus_force()
                return
        except Exception:
            pass

        self._map_window = BattleMapWindow(self)
        try:
            # Highlight active combatant (if any) on open
            if self.current_cid is not None:
                self._map_window.set_active(self.current_cid)
            try:
                self._map_window.refresh_spell_overlays()
            except Exception as exc:
                self._log(f"Map spell overlay refresh failed: {exc}")
        except Exception:
            pass

    # --------------------- Startup players ---------------------
    def _players_file_path(self) -> Path:
        _seed_user_players_dir()
        return _app_data_dir() / "players"

    def _player_name_from_filename(self, path: Path) -> Optional[str]:
        stem = path.stem.strip()
        if not stem:
            return None
        name = stem.replace("-", " ").replace("_", " ")
        name = " ".join(name.split())
        return name or None

    def _player_filename_from_name(self, name: str) -> str:
        base = " ".join(str(name).strip().split())
        if not base:
            return ""
        base = re.sub(r"[\\/]+", "-", base)
        base = re.sub(r"\s+", "-", base)
        return f"{base}.yaml"


    # --------------------- History / Log ---------------------
    def _history_file_path(self) -> Path:
        return self._logs_dir_path() / "dnd_initative_tracker_history.log"

    def _init_log_styles(self) -> None:
        """Configure log widget tags (timestamp toggle + name styling)."""
        if not hasattr(self, "log_text"):
            return

        # Tab stop after the timestamp column.
        try:
            self.log_text.configure(tabs=(160,))
        except Exception:
            pass

        base = tkfont.nametofont("TkDefaultFont")
        self._log_font_bold = tkfont.Font(self, font=base)
        self._log_font_bold.configure(weight="bold")
        self._log_font_bold_italic = tkfont.Font(self, font=base)
        self._log_font_bold_italic.configure(weight="bold", slant="italic")
        self._log_font_bold_underline = tkfont.Font(self, font=base)
        self._log_font_bold_underline.configure(weight="bold", underline=1)

        # Timestamp tag (can be elided)
        self.log_text.tag_configure("ts", foreground="#555555")
        self._toggle_log_timestamps()

        # Name tags
        self.log_text.tag_configure("nm_ally", font=self._log_font_bold)
        self.log_text.tag_configure("nm_enemy", font=self._log_font_bold_italic)
        self.log_text.tag_configure("nm_pc", font=self._log_font_bold_underline)

    def _toggle_log_timestamps(self) -> None:
        if not hasattr(self, "log_text"):
            return
        show = True
        if hasattr(self, "show_timestamps_var"):
            show = bool(self.show_timestamps_var.get())
        try:
            self.log_text.tag_configure("ts", elide=(not show))
        except Exception:
            # Older Tk builds may not support elide; fall back to leaving them visible.
            pass

    def _remember_role(self, c: Combatant) -> None:
        """Persist role memory for name-based styling in the log."""
        if getattr(c, "is_pc", False):
            role = "pc"
        elif bool(getattr(c, "ally", False)):
            role = "ally"
        else:
            role = "enemy"
        self._name_role_memory[str(c.name)] = role

    def _role_for_name(self, name: str) -> Optional[str]:
        # Prefer current combatant state when present
        for c in self.combatants.values():
            if c.name == name:
                if getattr(c, "is_pc", False):
                    return "pc"
                if c.ally:
                    return "ally"
                return "enemy"
        return self._name_role_memory.get(name)

    def _tag_for_name(self, name: str) -> Optional[str]:
        role = self._role_for_name(name)
        if role == "pc":
            return "nm_pc"
        if role == "enemy":
            return "nm_enemy"
        if role == "ally":
            return "nm_ally"
        return None

    def _apply_name_tags_in_range(self, start: str, end: str) -> None:
        """Bold/italic/underline known names in a given text range."""
        if not hasattr(self, "log_text"):
            return
        # Build a de-duplicated name list (memory + current combatants)
        names = set(self._name_role_memory.keys())
        for c in self.combatants.values():
            names.add(c.name)
            # keep memory warm
            self._remember_role(c)

        # Longest names first to reduce partial overlaps.
        ordered = sorted(names, key=lambda s: (-len(s), s))
        for nm in ordered:
            if not nm:
                continue
            tag = self._tag_for_name(nm)
            if not tag:
                continue
            idx = start
            while True:
                try:
                    pos = self.log_text.search(nm, idx, stopindex=end)
                except Exception:
                    break
                if not pos:
                    break
                match_end = f"{pos}+{len(nm)}c"
                try:
                    self.log_text.tag_add(tag, pos, match_end)
                except Exception:
                    pass
                idx = match_end

    def _append_log_line(self, stamp: str, content: str, write_file: bool) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        # Timestamp column
        self.log_text.insert(tk.END, stamp + "\t", ("ts",))
        # Content column
        content_start = self.log_text.index(tk.END)
        self.log_text.insert(tk.END, content)
        content_end = self.log_text.index(tk.END)
        self.log_text.insert(tk.END, "\n")
        self._apply_name_tags_in_range(content_start, content_end)
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

        if write_file:
            try:
                with self._history_file_path().open("a", encoding="utf-8") as f:
                    f.write(stamp + "\t" + content + "\n")
            except Exception:
                pass

    def _load_history_into_log(self, max_lines: int = 2000) -> None:
        """Load existing history file into the Log box."""
        if not hasattr(self, "log_text"):
            return
        p = self._history_file_path()
        if not p.exists():
            return
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > max_lines:
                lines = lines[-max_lines:]

            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", tk.END)
            self.log_text.configure(state="disabled")

            for line in lines:
                if not line.strip():
                    continue
                # Skip old redundant "next up" lines if present
                if " - next up" in line:
                    continue
                stamp = ""
                content = line

                if "\t" in line:
                    stamp, content = line.split("\t", 1)
                elif line.startswith("[") and "]" in line:
                    # Legacy format: [timestamp] ... - msg
                    try:
                        stamp = line.split("]", 1)[0].lstrip("[")
                        content = line.split("]", 1)[1].strip()
                    except Exception:
                        stamp = ""
                        content = line

                if not stamp:
                    stamp = "[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "]"

                self._append_log_line(stamp, content, write_file=False)
        except Exception:
            pass

    def _log(self, msg: str, cid: Optional[int] = None) -> None:
        """Append a line to the on-screen log and the history file."""
        stamp = "[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "]"

        content = msg
        if cid is not None and cid in self.combatants:
            # Prefix with the creature name for generic events
            nm = self.combatants[cid].name
            content = f"{nm}: {msg}"

        self._append_log_line(stamp, content, write_file=True)

    def _death_flavor_line(self, attacker_name: Optional[str], amount: int, dtype: str, target_name: str) -> str:
        """Return a flavorful log line for a creature killed by damage."""
        attacker = (attacker_name or "").strip() or "Something"
        dt = (dtype or "").strip().lower()

        # Generic templates that include type (dtype). Use only if we have a dtype.
        generic_with_type = [
            "{attacker} deals a final blow of {amount} {dtype} damage to {target}. That’ll leave a mark! (Dead)",
            "{attacker} deals a final blow of {amount} {dtype} damage to {target}. Lights out, pal. (Dead)",
            "{attacker} deals a final blow of {amount} {dtype} damage to {target}. That’s not gonna buff out. (Dead)",
            "{attacker} deals a final blow of {amount} {dtype} damage to {target}. Should’ve zigged. (Dead)",
            "{attacker} deals a final blow of {amount} {dtype} damage to {target}. And there it goes! (Dead)",
            "{attacker} deals a final blow of {amount} {dtype} damage to {target}. Thanks for playin’. (Dead)",
            "{attacker} deals {amount} {dtype} to {target}. Now with 100% less menace. (Dead)",
            "{attacker} deals {amount} {dtype} to {target}. Reduced to loot. (Dead)",
        ]

        # Templates that do not require a type (fallback when dtype is blank)
        generic_no_type = [
            "{attacker} drops {target} with {amount} damage. That’ll leave a mark! (Dead)",
            "{attacker} drops {target} with {amount} damage. Lights out, pal. (Dead)",
            "{attacker} drops {target} with {amount} damage. Thanks for playin’. (Dead)",
            "{attacker} drops {target} with {amount} damage. Reduced to loot. (Dead)",
        ]

        typed = {
            "fire": [
                "{attacker} deals {amount} fire to {target}. Extra crispy. (Dead)",
                "{attacker} deals {amount} fire to {target}. Smells like victory. And smoke. (Dead)",
            ],
            "acid": [
                "{attacker} deals a final blow of {amount} acid damage to {target}. Now in soup form. (Dead)",
                "{attacker} deals a final blow of {amount} acid damage to {target}. Dissolved: mostly. (Dead)",
            ],
            "cold": [
                "{attacker} deals a final blow of {amount} cold damage to {target}. Put on ice. (Dead)",
                "{attacker} deals {amount} cold to {target}. Put on ice. (Dead)",
            ],
            "lightning": [
                "{attacker} deals {amount} lightning to {target}. Performed an impromptu reboot. (Dead)",
            ],
            "force": [
                "{attacker} deals {amount} force to {target}. Became a fun physics example. (Dead)",
                "{attacker} deals {amount} force to {target}. Gravity sends its regards. (Dead)",
            ],
            "psychic": [
                "{attacker} deals {amount} psychic to {target}. Out-thought. Out-fought. (Dead)",
                "{target} thought a forbidden thought. (Dead)",
            ],
        }

        pool: list[str] = []
        if dt and dt in typed:
            pool.extend(typed[dt])
        if dt:
            pool.extend(generic_with_type)
        else:
            pool.extend(generic_no_type)

        if not pool:
            pool = generic_no_type

        tmpl = random.choice(pool)
        if "{dtype}" in tmpl:
            return tmpl.format(attacker=attacker, amount=amount, dtype=dt, target=target_name)
        return tmpl.format(attacker=attacker, amount=amount, target=target_name)
    def _clear_log(self) -> None:
        """Archive the current history log to ./old logs/<timestamp>.log and start fresh."""
        # 1) Archive existing history file on disk
        p = self._history_file_path()
        try:
            base = p.parent
            old_dir = base / "old logs"
            old_dir.mkdir(parents=True, exist_ok=True)

            if p.exists():
                # Rename to timestamp (and keep .log extension)
                stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                dest = old_dir / f"{stamp}.log"
                # Avoid collisions if user clears multiple times quickly
                n = 1
                while dest.exists():
                    dest = old_dir / f"{stamp}_{n}.log"
                    n += 1
                shutil.move(str(p), str(dest))

            # Recreate a fresh empty history file
            p.write_text("", encoding="utf-8")
        except Exception:
            # Best effort: at least try to truncate the current log
            try:
                p.write_text("", encoding="utf-8")
            except Exception:
                pass

        # 2) Clear on-screen log
        if hasattr(self, "log_text"):
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", tk.END)
            self.log_text.configure(state="disabled")

    def _load_starting_players_roster(self) -> List[str]:
        players_dir = self._players_file_path()
        if players_dir.exists():
            try:
                out: List[str] = []
                for path in sorted(players_dir.glob("*.yaml")):
                    if not path.is_file():
                        continue
                    nm = self._player_name_from_filename(path)
                    if nm and nm not in out:
                        out.append(nm)
                if out:
                    return out
            except Exception:
                pass

        # If missing or unreadable, seed with defaults.
        self._save_starting_players_roster(list(DEFAULT_STARTING_PLAYERS))
        return list(DEFAULT_STARTING_PLAYERS)

    def _save_starting_players_roster(self, roster: List[str]) -> None:
        players_dir = self._players_file_path()
        uniq: List[str] = []
        for n in roster:
            n = str(n).strip()
            if n and n not in uniq:
                uniq.append(n)
        try:
            players_dir.mkdir(parents=True, exist_ok=True)
            desired_files = {}
            for nm in uniq:
                filename = self._player_filename_from_name(nm)
                if filename:
                    desired_files[filename] = nm
            existing_files = {
                path.name: path
                for path in players_dir.glob("*.yaml")
                if path.is_file()
            }
            for filename, nm in desired_files.items():
                path = players_dir / filename
                if not path.exists():
                    content = f"name: {nm}\n"
                    path.write_text(content, encoding="utf-8")
            for filename, path in existing_files.items():
                if filename not in desired_files:
                    path.unlink()
        except Exception:
            # Non-fatal: app still works, just won't persist roster edits.
            pass

    def _unique_name(self, base: str) -> str:
        base = base.strip() or "Creature"
        existing = {c.name for c in self.combatants.values()}
        if base not in existing:
            return base
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    def _open_starting_players_dialog(self) -> None:
        roster = self._load_starting_players_roster()

        win = tk.Toplevel(self)
        win.title("Starting Players")
        win.geometry("640x560")
        win.transient(self)

        ttk.Label(
            win,
            text="Pick who be startin’ this scrap (allies). Roll initiative per sailor, or type the total.",
        ).pack(anchor="w", padx=12, pady=(12, 6))

        # Scrollable roster list
        outer = ttk.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scroll(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _sync_scroll)

        def _sync_width(evt):
            canvas.itemconfigure(inner_id, width=evt.width)

        canvas.bind("<Configure>", _sync_width)

        rows: List[Dict[str, object]] = []

        def rebuild_rows() -> None:
            nonlocal rows
            for child in inner.winfo_children():
                child.destroy()
            rows = []

            ttk.Label(inner, text="Use").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 6))
            ttk.Label(inner, text="Name").grid(row=0, column=1, sticky="w", padx=(0, 6), pady=(0, 6))
            ttk.Label(inner, text="Roll?").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=(0, 6))
            ttk.Label(inner, text="Init total").grid(row=0, column=3, sticky="w", padx=(0, 6), pady=(0, 6))
            ttk.Label(inner, text="Roster").grid(row=0, column=4, sticky="w", padx=(0, 6), pady=(0, 6))

            for i, name in enumerate(roster, start=1):
                use_var = tk.BooleanVar(value=True)
                roll_var = tk.BooleanVar(value=True)
                init_var = tk.StringVar(value="")

                ttk.Checkbutton(inner, variable=use_var).grid(row=i, column=0, sticky="w", padx=(0, 6))
                ttk.Label(inner, text=name).grid(row=i, column=1, sticky="w", padx=(0, 6))
                ttk.Checkbutton(inner, variable=roll_var).grid(row=i, column=2, sticky="w", padx=(0, 6))

                ent_init = ttk.Entry(inner, textvariable=init_var, width=10)
                ent_init.grid(row=i, column=3, sticky="w", padx=(0, 6))
                ent_init.state(["disabled"])

                def on_roll_change(*_a, rv=roll_var, ent=ent_init):
                    if rv.get():
                        ent.state(["disabled"])
                    else:
                        ent.state(["!disabled"])

                roll_var.trace_add("write", on_roll_change)

                def remove_name(nm=name):
                    nonlocal roster
                    if messagebox.askyesno("Remove player", f"Remove '{nm}' from roster?", parent=win):
                        roster = [x for x in roster if x != nm]
                        self._save_starting_players_roster(roster)
                        rebuild_rows()

                ttk.Button(inner, text="Remove", command=remove_name).grid(row=i, column=4, sticky="w")

                rows.append({"name": name, "use": use_var, "roll": roll_var, "init": init_var})

        rebuild_rows()

        # Add new player controls
        add_bar = ttk.Frame(win)
        add_bar.pack(fill=tk.X, padx=12, pady=(0, 8))
        new_name = tk.StringVar()
        ttk.Label(add_bar, text="New player").pack(side=tk.LEFT)
        ttk.Entry(add_bar, textvariable=new_name, width=26).pack(side=tk.LEFT, padx=(8, 8))

        def add_player():
            nm = new_name.get().strip()
            if not nm:
                return
            if nm in roster:
                messagebox.showinfo("Roster", "That name be already in yer roster.", parent=win)
                return
            roster.append(nm)
            self._save_starting_players_roster(roster)
            new_name.set("")
            rebuild_rows()

        ttk.Button(add_bar, text="Add to roster", command=add_player).pack(side=tk.LEFT)

        # Bottom controls
        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=12, pady=(0, 12))

        def select_all(val: bool):
            for r in rows:
                v = r.get("use")
                if isinstance(v, tk.BooleanVar):
                    v.set(val)

        ttk.Button(btns, text="Select All", command=lambda: select_all(True)).pack(side=tk.LEFT)
        ttk.Button(btns, text="Select None", command=lambda: select_all(False)).pack(side=tk.LEFT, padx=(8, 0))

        def roll_all(val: bool):
            for r in rows:
                v = r.get("roll")
                if isinstance(v, tk.BooleanVar):
                    v.set(val)

        ttk.Button(btns, text="Roll All", command=lambda: roll_all(True)).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(btns, text="No Roll", command=lambda: roll_all(False)).pack(side=tk.LEFT, padx=(8, 0))

        def do_start():
            any_added = False
            for r in rows:
                name = str(r.get("name", "")).strip()
                use_var = r.get("use")
                roll_var = r.get("roll")
                init_var = r.get("init")
                if not name or not isinstance(use_var, tk.BooleanVar) or not isinstance(roll_var, tk.BooleanVar) or not isinstance(init_var, tk.StringVar):
                    continue
                if not use_var.get():
                    continue

                if roll_var.get():
                    nat = random.randint(1, 20)
                    init_total = nat
                    nat20 = (nat == 20)
                    roll_val = nat
                else:
                    txt = init_var.get().strip()
                    try:
                        init_total = int(txt)
                    except ValueError:
                        messagebox.showerror("Input error", f"Init total must be a number for '{name}'.", parent=win)
                        return
                    nat20 = False
                    roll_val = None

                cname = self._unique_name(name)
                cid = self._create_combatant(name=cname, hp=0, speed=30, initiative=init_total, dex=None, ally=True, is_pc=True)
                c = self.combatants.get(cid)
                if c is not None:
                    c.nat20 = nat20
                    c.roll = roll_val
                any_added = True

            if any_added:
                self.current_cid = None
                self.round_num = 1
                self.turn_num = 0
                self.start_cid = None

            win.destroy()

        ttk.Button(btns, text="Start Combat", command=do_start).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Skip", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self.wait_window(win)

    # -------------------------- Data helpers --------------------------
    def _safe_int(self, s: str, default: int = 0) -> int:
        s = (s or "").strip()
        if s == "":
            return default
        return int(s)

    
    def _parse_int_expr(self, expr: str) -> int:
        """Parse a small math expression into an int (supports + - * / // and parentheses)."""
        expr = (expr or "").strip()
        if expr == "":
            raise ValueError("empty")

        tree = ast.parse(expr, mode="eval")

        def _eval(n):
            if isinstance(n, ast.Expression):
                return _eval(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
                v = _eval(n.operand)
                return +v if isinstance(n.op, ast.UAdd) else -v
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)):
                a = _eval(n.left)
                b = _eval(n.right)
                if isinstance(n.op, ast.Add):
                    return a + b
                if isinstance(n.op, ast.Sub):
                    return a - b
                if isinstance(n.op, ast.Mult):
                    return a * b
                if isinstance(n.op, ast.Div):
                    return a / b
                if isinstance(n.op, ast.FloorDiv):
                    return a // b
                if isinstance(n.op, ast.Mod):
                    return a % b
            raise ValueError("unsupported expression")

        val = _eval(tree)
        return int(val)

    def _sorted_combatants(self) -> List[Combatant]:
        ordered = list(self.combatants.values())

        def key(c: Combatant) -> Tuple[int, int, int, str]:
            # initiative desc, nat20 first, dex desc, name
            return (-int(c.initiative), -(1 if c.nat20 else 0), -(int(c.dex or 0)), c.name.lower())

        ordered.sort(key=key)
        return ordered

    def _display_order(self) -> List[Combatant]:
        ordered = self._sorted_combatants()
        if self.start_cid is None:
            return ordered
        try:
            idx = next(i for i, c in enumerate(ordered) if c.cid == self.start_cid)
        except StopIteration:
            return ordered
        return ordered[idx:] + ordered[:idx]

    def _label_for(self, c: Combatant) -> str:
        return f"{c.name} [#{c.cid}]"

    def _cid_from_label(self, lbl: str) -> Optional[int]:
        """Parse a combobox label like 'Goblin [#12]' back into a cid.

        If the user typed a raw name, we try an exact (case-insensitive) match.
        """
        lbl = (lbl or "").strip()
        if not lbl:
            return None

        # Raw cid
        if lbl.isdigit():
            try:
                return int(lbl)
            except Exception:
                return None

        # Standard label: Name [#123]
        if "[#" in lbl:
            try:
                tail = lbl.split("[#", 1)[1]
                num = tail.split("]", 1)[0]
                return int(num)
            except Exception:
                return None

        # Fallback: exact name match (case-insensitive) in display order
        low = lbl.lower()
        for c in self._display_order():
            if c.name.lower() == low:
                return c.cid
        return None

    def _target_labels(self) -> List[str]:
        """Labels for all combatants, in current displayed order."""
        return [self._label_for(c) for c in self._display_order()]

    def _roll_dice_dict(self, dice: Dict[int, int]) -> int:
        """Roll a dice dict like {6:1, 4:2} -> 1d6 + 2d4."""
        total = 0
        for die, cnt in (dice or {}).items():
            try:
                d = int(die)
                n = int(cnt)
            except Exception:
                continue
            if d <= 0 or n <= 0:
                continue
            for _ in range(n):
                total += random.randint(1, d)
        return int(total)

    def _normalize_movement_mode(self, value: object) -> str:
        if isinstance(value, bool):
            return "swim" if value else "normal"
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in MOVEMENT_MODES:
                return lowered
            if lowered in {"land", "ground"}:
                return "normal"
            if lowered == "water":
                return "swim"
            for key, label in MOVEMENT_MODE_LABELS.items():
                if lowered == label.lower():
                    return key
        return "normal"

    def _normalize_movement_type(self, value: object, is_swim: bool = False) -> str:
        return _normalize_movement_type(value, is_swim=is_swim)

    def _movement_mode_label(self, mode: str) -> str:
        return MOVEMENT_MODE_LABELS.get(self._normalize_movement_mode(mode), "Normal")

    def _mode_speed_value(self, mode: str, speed: int, swim: int, fly: int, burrow: int) -> int:
        mode_key = self._normalize_movement_mode(mode)
        if mode_key == "swim":
            if swim > 0:
                return int(swim)
            return max(0, int(speed // 2))
        if mode_key == "fly":
            return max(0, int(fly))
        if mode_key == "burrow":
            return max(0, int(burrow))
        return max(0, int(speed))

    def _mode_speed(self, c: Combatant) -> int:
        """Base movement speed for the creature's current mode."""
        speed = max(0, int(getattr(c, "speed", 0)))
        swim = max(0, int(getattr(c, "swim_speed", 0)))
        fly = max(0, int(getattr(c, "fly_speed", 0)))
        burrow = max(0, int(getattr(c, "burrow_speed", 0)))
        mode = self._normalize_movement_mode(getattr(c, "movement_mode", "normal"))
        return self._mode_speed_value(mode, speed, swim, fly, burrow)

    def _effective_speed(self, c: Combatant) -> int:
        """Effective movement for THIS TURN (mode speed, but immobilizing conditions force 0)."""
        # immobilizing conditions set movement to 0 for the turn
        for st in c.condition_stacks:
            meta = CONDITIONS_META.get(st.ctype, {})
            if bool(meta.get("immobile")):
                return 0
        bonus = int(getattr(c, "temp_move_bonus", 0) or 0)
        turns_left = int(getattr(c, "temp_move_turns_remaining", 0) or 0)
        if bonus > 0 and turns_left > 0:
            return self._mode_speed(c) + bonus
        return self._mode_speed(c)


    def _has_condition(self, c: Combatant, ctype: str) -> bool:
        return any(st.ctype == ctype for st in c.condition_stacks)

    def _remove_condition_type(self, c: Combatant, ctype: str) -> None:
        c.condition_stacks = [st for st in c.condition_stacks if st.ctype != ctype]

    @staticmethod
    def _normalize_action_entries(value: Any, default_type: str) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if isinstance(value, dict):
            value = [value]
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return entries
        for item in value:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                entries.append({"name": name, "description": "", "type": default_type})
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            description = str(item.get("description") or "").strip()
            action_type = str(item.get("type") or default_type).strip().lower() or default_type
            entries.append(
                {
                    "name": name,
                    "description": description,
                    "type": action_type,
                }
            )
        return entries

    # -------------------------- Add / remove --------------------------
    def _create_combatant(
        self,
        name: str,
        hp: int,
        speed: int,
        initiative: int,
        dex: Optional[int],
        ally: bool,
        swim_speed: int = 0,
        fly_speed: Optional[int] = None,
        burrow_speed: Optional[int] = None,
        climb_speed: Optional[int] = None,
        movement_mode: Optional[str] = None,
        is_pc: bool = False,
        is_spellcaster: Optional[bool] = None,
        saving_throws: Optional[Dict[str, int]] = None,
        ability_mods: Optional[Dict[str, int]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        bonus_actions: Optional[List[Dict[str, Any]]] = None,
        monster_spec: Optional[MonsterSpec] = None,
    ) -> int:
        cid = self._next_id
        self._next_id += 1
        spd = max(0, int(speed))
        swim = max(0, int(swim_speed))
        if fly_speed is None and monster_spec is not None:
            fly_speed = monster_spec.fly_speed
        if burrow_speed is None and monster_spec is not None:
            burrow_speed = monster_spec.burrow_speed
        if climb_speed is None and monster_spec is not None:
            climb_speed = monster_spec.climb_speed
        fly = max(0, int(fly_speed or 0))
        burrow = max(0, int(burrow_speed or 0))
        climb = max(0, int(climb_speed or 0))
        mode = self._normalize_movement_mode(movement_mode)

        base = self._mode_speed_value(mode, spd, swim, fly, burrow)
        inferred_spellcaster = None
        raw_spec = getattr(monster_spec, "raw_data", None)
        if isinstance(raw_spec, dict):
            for key in ("is_spellcaster", "spellcaster", "spellcasting"):
                if key in raw_spec:
                    inferred_spellcaster = bool(raw_spec.get(key))
                    break
        if inferred_spellcaster is None:
            inferred_spellcaster = bool(is_pc)
        if is_spellcaster is None:
            is_spellcaster = inferred_spellcaster
        normalized_actions = self._normalize_action_entries(actions, "action")
        normalized_bonus_actions = self._normalize_action_entries(bonus_actions, "bonus_action")

        c = Combatant(
            cid=cid,
            name=name,
            hp=int(hp),
            speed=spd,
            swim_speed=swim,
            fly_speed=fly,
            burrow_speed=burrow,
            climb_speed=climb,
            movement_mode=mode,
            move_remaining=base,
            move_total=base,
            initiative=int(initiative),
            dex=dex,
            nat20=False,
            roll=None,
            ally=ally,
            is_pc=bool(is_pc),
            is_spellcaster=bool(is_spellcaster),
            saving_throws=dict(saving_throws or {}),
            ability_mods=dict(ability_mods or {}),
            actions=normalized_actions,
            bonus_actions=normalized_bonus_actions,
            monster_spec=monster_spec,
        )
        self.combatants[cid] = c
        self._remember_role(c)
        return cid

    def _remove_selected(self) -> None:
        items = self.tree.selection()
        if not items:
            return
        to_remove: List[int] = []
        for it in items:
            try:
                cid = int(it)
            except ValueError:
                continue
            if cid in self.combatants:
                to_remove.append(cid)

        if not to_remove:
            return

        names = [self.combatants[cid].name for cid in to_remove if cid in self.combatants]
        prompt_lines = [f"Remove {len(to_remove)} selected combatant(s)?"]
        if names:
            preview = ", ".join(names[:5])
            if len(names) > 5:
                preview = f"{preview}, ..."
            prompt_lines.append("")
            prompt_lines.append(f"Names: {preview}")
        if not messagebox.askyesno("Confirm Removal", "\n".join(prompt_lines)):
            return

        for cid in to_remove:
            self.combatants.pop(cid, None)

        if self.start_cid in to_remove:
            self.start_cid = None

        self._retarget_current_after_removal(to_remove)
        self._rebuild_table(scroll_to_current=True)

    def _retarget_current_after_removal(self, removed: List[int], pre_order: Optional[List[int]] = None) -> None:
        if self.current_cid is None:
            return
        if self.current_cid not in removed:
            return

        ordered_now = self._display_order()
        if not ordered_now:
            self.current_cid = None
            self.turn_num = 0
            self.round_num = 1
            return

        if pre_order is None:
            pre_order = [c.cid for c in ordered_now]

        # Try to move to the next cid after the removed current cid, based on prior order
        try:
            old_idx = pre_order.index(self.current_cid)
        except ValueError:
            self.current_cid = ordered_now[0].cid
            return

        for step in range(1, len(pre_order) + 1):
            cand = pre_order[(old_idx + step) % len(pre_order)]
            if cand in self.combatants:
                self.current_cid = cand
                return

        self.current_cid = ordered_now[0].cid

    # -------------------------- Start list rotation --------------------------
    def _set_start_here(self) -> None:
        items = self.tree.selection()
        if not items:
            messagebox.showinfo("Start", "Select a combatant row first.")
            return
        try:
            cid = int(items[0])
        except ValueError:
            return
        if cid not in self.combatants:
            return
        self.start_cid = cid
        self._rebuild_table()

    def _clear_start(self) -> None:
        self.start_cid = None
        self._rebuild_table()

    # -------------------------- Turn tracker --------------------------
    def _update_turn_ui(self) -> None:
        if self.current_cid is None or self.current_cid not in self.combatants:
            self.turn_current_var.set("(not started)")
            self.turn_move_var.set("—")
        else:
            c = self.combatants[self.current_cid]
            self.turn_current_var.set(self._label_for(c))
            eff = self._effective_speed(c)
            if eff <= 0:
                self.turn_move_var.set("0")
            else:
                mode = self._movement_mode_label(getattr(c, "movement_mode", "normal"))
                self.turn_move_var.set(f"{c.move_remaining}/{eff} {mode}")

        self.turn_round_var.set(str(max(1, int(self.round_num))))
        # In D&D terms, each creature's "turn number" matches the round.
        self.turn_count_var.set(str(max(1, int(self.round_num))))

    
    def _log_turn_start(self, cid: int) -> None:
        c = self.combatants.get(cid)
        if c is None:
            return
        self._log(f"START R{self.round_num} {c.name}")

    def _log_turn_end(self, cid: int, note: str = "") -> None:
        c = self.combatants.get(cid)
        name = c.name if c is not None else f"#{cid}"
        extra = f" ({note})" if note else ""
        self._log(f"END R{self.round_num} {name}{extra}")
    def _start_turns(self) -> None:
        ordered = self._display_order()
        if not ordered:
            messagebox.showinfo("Turn Tracker", "No combatants in the list yet.")
            return
        self.current_cid = ordered[0].cid
        self.round_num = 1
        self.turn_num = 1
        self._log("--- COMBAT STARTED ---")
        self._log("--- ROUND 1 ---")
        self._enter_turn_with_auto_skip(starting=True)
        self._rebuild_table(scroll_to_current=True)

    def _clear_turns(self) -> None:
        self.current_cid = None
        self.round_num = 1
        self.turn_num = 0
        self.start_last_var.set("")
        self._rebuild_table(scroll_to_current=True)

    def _set_turn_here(self) -> None:
        items = self.tree.selection()
        if not items:
            messagebox.showinfo("Turn Tracker", "Select a combatant row first.")
            return
        try:
            cid = int(items[0])
        except ValueError:
            return
        if cid not in self.combatants:
            return
        self.current_cid = cid
        if self.turn_num <= 0:
            self.turn_num = 1
        self._enter_turn_with_auto_skip(starting=True)
        self._rebuild_table(scroll_to_current=True)

    def _prev_turn(self) -> None:
        ordered = self._display_order()
        if not ordered:
            return

        if self.current_cid is None or self.current_cid not in {c.cid for c in ordered}:
            self.current_cid = ordered[0].cid
            self.round_num = max(1, self.round_num)
            self.turn_num = max(1, self.turn_num)
            self._rebuild_table(scroll_to_current=True)
            return

        ids = [c.cid for c in ordered]
        idx = ids.index(self.current_cid)
        prv = idx - 1
        wrapped = False
        if prv < 0:
            prv = len(ids) - 1
            wrapped = True

        self.current_cid = ids[prv]
        if self.turn_num > 0:
            self.turn_num = max(0, self.turn_num - 1)
        if wrapped and self.round_num > 1:
            self.round_num -= 1

        # Going backwards should not re-apply start-of-turn effects.
        self.start_last_var.set("")
        self._rebuild_table(scroll_to_current=True)

    def _end_turn_cleanup(self, cid: Optional[int], skip_decrement_types: Optional[set[str]] = None) -> None:
        """End-of-turn: reset movement and tick down timed conditions."""
        if cid is None or cid not in self.combatants:
            return
        c = self.combatants[cid]

        # Tick down timed conditions at the END of the creature's turn.
        expired: List[str] = []
        for st in list(c.condition_stacks):
            if st.remaining_turns is None:
                continue
            if skip_decrement_types and st.ctype in skip_decrement_types:
                continue
            if st.remaining_turns > 0:
                st.remaining_turns -= 1
            if st.remaining_turns <= 0:
                expired.append(st.ctype)
                try:
                    c.condition_stacks.remove(st)
                except ValueError:
                    pass

        # Reset movement at end of each turn (start-of-turn will set effective movement).
        turns_left = int(getattr(c, "temp_move_turns_remaining", 0) or 0)
        if turns_left > 0:
            turns_left -= 1
            c.temp_move_turns_remaining = turns_left
            if turns_left <= 0:
                c.temp_move_turns_remaining = 0
                c.temp_move_bonus = 0
                self._log("temporary movement bonus ended", cid=cid)

        base_spd = self._effective_speed(c)
        c.move_total = int(base_spd)
        c.move_remaining = int(base_spd)

        self._tick_aoe_durations()

        if expired:
            labs = ", ".join(str(CONDITIONS_META.get(k, {}).get("label", k)) for k in expired)
            self._log(f"conditions ended: {labs}", cid=cid)

    def _tick_aoe_durations(self) -> None:
        mw = getattr(self, "_map_window", None)
        if mw is None or not getattr(mw, "winfo_exists", lambda: False)():
            return
        aoes = getattr(mw, "aoes", None)
        if not isinstance(aoes, dict) or not aoes:
            return
        expired: List[int] = []
        changed = False
        for aid, data in list(aoes.items()):
            if not bool(data.get("pinned")):
                continue
            remaining = data.get("remaining_turns")
            if remaining is None:
                continue
            try:
                turns = int(remaining)
            except Exception:
                continue
            if turns > 0:
                turns -= 1
            data["remaining_turns"] = turns
            changed = True
            if turns <= 0:
                expired.append(aid)
        for aid in expired:
            try:
                mw._remove_aoe_by_id(aid)
            except Exception:
                pass
        if changed and not expired:
            try:
                mw._refresh_aoe_list(select=getattr(mw, "_selected_aoe", None))
            except Exception:
                pass


    def _next_turn(self) -> None:
        ordered = self._display_order()
        if not ordered:
            return

        if self.current_cid is None or self.current_cid not in {c.cid for c in ordered}:
            # not started -> jump to top
            self.current_cid = ordered[0].cid
            self.round_num = max(1, self.round_num)
            self.turn_num = max(1, self.turn_num)
            self._enter_turn_with_auto_skip(starting=True)
            self._rebuild_table(scroll_to_current=True)
            return

        # end current creature turn
        ended_cid = self.current_cid
        self._end_turn_cleanup(self.current_cid)
        if ended_cid is not None:
            self._log_turn_end(ended_cid)

        ids = [c.cid for c in ordered]
        idx = ids.index(self.current_cid)
        nxt = (idx + 1) % len(ids)
        wrapped = nxt == 0

        self.current_cid = ids[nxt]
        self.turn_num += 1
        if wrapped:
            self.round_num += 1
            self._log(f"--- ROUND {self.round_num} ---")

        self._enter_turn_with_auto_skip(starting=False)
        self._rebuild_table(scroll_to_current=True)
    def _enter_turn_with_auto_skip(self, starting: bool) -> None:
        """Enter the current creature's turn.

        Applies start-of-turn effects (DoT, star advantage expiry, condition skip checks).
        If the creature's turn is skipped (Stunned/Paralyzed/etc), the turn ends immediately and we advance.
        """
        logs: List[str] = []
        safety = 0

        while safety < 200:
            safety += 1
            if self.current_cid is None or self.current_cid not in self.combatants:
                break

            cid_before = self.current_cid
            c = self.combatants[self.current_cid]

            # Update map highlight (if map is open)
            try:
                if self._map_window is not None and self._map_window.winfo_exists():
                    self._map_window.set_active(c.cid, auto_center=True)
            except Exception:
                pass

            # Always log a turn start for the current creature.
            self._log_turn_start(c.cid)

            skip, msg, dec_skip = self._process_start_of_turn(c)
            if msg:
                logs.append(f"{c.name}: {msg}")
                self._log(msg, cid=c.cid)

            # if creature died/removed during start-of-turn, current may have changed
            if cid_before not in self.combatants:
                continue

            if not skip:
                break

            # skipped: end the turn immediately (tick other conditions at end-of-turn, but don't double-tick skip cond)
            self._end_turn_cleanup(self.current_cid, skip_decrement_types=dec_skip)
            self._log_turn_end(c.cid, note="skipped")

            ordered = self._display_order()
            if not ordered:
                self.current_cid = None
                break

            ids = [x.cid for x in ordered]
            if self.current_cid not in ids:
                # already retargeted
                continue

            idx = ids.index(self.current_cid)
            nxt = (idx + 1) % len(ids)
            wrapped = nxt == 0

            self.current_cid = ids[nxt]
            self.turn_num += 1
            if wrapped:
                self.round_num += 1
                self._log(f"--- ROUND {self.round_num} ---")

            if safety >= len(ids) + 10:
                # likely stuck in a skip loop; stop so we don't spin forever
                break

        if self.current_cid is not None and self.current_cid in self.combatants:
            lan = getattr(self, "_lan", None)
            if lan and hasattr(lan, "notify_turn_start"):
                try:
                    lan.notify_turn_start(self.current_cid, self.round_num, self.turn_num)
                except Exception:
                    pass

        self.start_last_var.set(" | ".join(logs))
        self._update_turn_ui()

    def _process_start_of_turn(self, c: Combatant) -> Tuple[bool, str, set[str]]:
        """Start-of-turn processing.

        Returns (skip_turn, message, decremented_skip_types).

        Rules for condition durations:
        - Most timed conditions tick down at the END of the creature's turn.
        - Conditions that skip a turn (Stunned/Paralyzed/etc) tick down by 1 at the START of the creature's turn,
          then the turn ends immediately.
        """
        msgs: List[str] = []
        decremented_skip: set[str] = set()

        # reset movement at start (effective, taking immobile conditions into account)
        eff = self._effective_speed(c)
        c.move_total = eff
        c.move_remaining = eff
        c.action_remaining = 1 + max(0, int(getattr(c, "extra_action_pool", 0) or 0))
        c.attack_resource_remaining = 0
        c.bonus_action_remaining = 1 + max(0, int(getattr(c, "extra_bonus_pool", 0) or 0))
        c.reaction_remaining = 1
        c.spell_cast_remaining = 1
        c.extra_action_pool = 0
        c.extra_bonus_pool = 0
        self._reset_concentration_prompt_state(c)

        # expire star advantage at start of creature's turn
        star_stacks = [st for st in list(c.condition_stacks) if st.ctype == "star_advantage"]
        if star_stacks:
            for st in star_stacks:
                try:
                    c.condition_stacks.remove(st)
                except ValueError:
                    pass
            msgs.append("⭐ advantage ended")

        # DoT stacks roll at start (even if the turn will be skipped)
        dot_stacks = [st for st in list(c.condition_stacks) if st.ctype == "dot"]
        if dot_stacks:
            total_dmg = 0
            details: List[str] = []
            for st in dot_stacks:
                dice = st.dice or {}
                if not dice:
                    continue
                roll = self._roll_dice_dict(dice)
                total_dmg += roll
                dot_type = st.dot_type or "dot"
                details.append(f"{DOT_META.get(dot_type, {}).get('icon','•')}{roll}")
                if st.remaining_turns is not None:
                    st.remaining_turns -= 1
                    if st.remaining_turns <= 0:
                        try:
                            c.condition_stacks.remove(st)
                        except ValueError:
                            pass

            if total_dmg > 0:
                old_hp = c.hp
                c.hp = max(0, int(c.hp) - int(total_dmg))
                msgs.append(f"DoT {total_dmg} ({', '.join(details)})")
                if int(c.hp) < int(old_hp):
                    self._queue_concentration_save(c, "dot")

                # auto-remove ONLY if they were >0 and this drop made them 0
                if old_hp > 0 and c.hp == 0:
                    pre_order = [x.cid for x in self._display_order()]
                    dead_id = c.cid
                    self.combatants.pop(dead_id, None)
                    if self.start_cid == dead_id:
                        self.start_cid = None
                    self._retarget_current_after_removal([dead_id], pre_order=pre_order)
                    msgs.append("dropped to 0 -> removed")
                    return False, "; ".join(msgs), decremented_skip

        mw = getattr(self, "_map_window", None)
        if mw is not None and getattr(mw, "winfo_exists", None) and mw.winfo_exists():
            try:
                aoes = dict(getattr(mw, "aoes", {}) or {})
            except Exception:
                aoes = {}
            if aoes:
                for aid, d in aoes.items():
                    try:
                        owner_cid = d.get("owner_cid")
                        move_per_turn_ft = d.get("move_per_turn_ft")
                        if owner_cid is None or int(owner_cid) != int(c.cid):
                            continue
                        if move_per_turn_ft in (None, ""):
                            continue
                        move_val = float(move_per_turn_ft)
                    except Exception:
                        continue
                    if move_val > 0:
                        d["move_remaining_ft"] = move_val
                for aid, d in aoes.items():
                    if not d.get("over_time"):
                        continue
                    trigger = str(d.get("trigger_on_start_or_enter") or "").strip().lower()
                    if trigger in {"enter"}:
                        continue
                    remaining_turns = d.get("remaining_turns")
                    if isinstance(remaining_turns, (int, float)) and remaining_turns <= 0:
                        continue
                    try:
                        included = mw._compute_included_units(aid)
                    except Exception:
                        included = []
                    if c.cid not in included:
                        continue
                    try:
                        mw._open_aoe_damage(aid=aid, included_override=[c.cid])
                    except Exception:
                        pass

        # Check for skip-turn conditions
        skip_types_present: List[str] = []
        for st in list(c.condition_stacks):
            meta = CONDITIONS_META.get(st.ctype, {})
            if bool(meta.get("skip")):
                # Treat as active if indefinite or remaining > 0
                if st.remaining_turns is None or st.remaining_turns > 0:
                    skip_types_present.append(st.ctype)

        skip = bool(skip_types_present)

        # If skipping: tick down the skip condition(s) NOW (once), then turn will auto-end.
        if skip:
            for st in list(c.condition_stacks):
                if st.ctype in skip_types_present and st.remaining_turns is not None:
                    st.remaining_turns -= 1
                    decremented_skip.add(st.ctype)
                    if st.remaining_turns <= 0:
                        try:
                            c.condition_stacks.remove(st)
                        except ValueError:
                            pass

        # summarize conditions (after any skip decrement)
        shown: List[str] = []
        for st in sorted(c.condition_stacks, key=lambda x: x.ctype):
            if st.ctype in {"dot", "star_advantage"}:
                continue
            icon = str(CONDITIONS_META.get(st.ctype, {}).get("icon", "•"))
            if st.remaining_turns is None:
                shown.append(icon)
            else:
                shown.append(f"{icon}({st.remaining_turns})")
        if shown:
            msgs.append("cond " + " ".join(shown))
        if c.exhaustion_level > 0:
            msgs.append(f"exh {c.exhaustion_level}")

        if skip:
            # mention which condition caused it (best-effort)
            labels = []
            for k in skip_types_present:
                labels.append(str(CONDITIONS_META.get(k, {}).get("label", k)))
            if labels:
                msgs.append("skip: " + ", ".join(sorted(set(labels))))
            msgs.append("turn skipped")

        return skip, "; ".join(msgs), decremented_skip


    def _reset_concentration_prompt_state(self, c: Combatant) -> None:
        if not getattr(c, "concentrating", False):
            return
        state_map = getattr(self, "_concentration_save_state", {})
        if not state_map:
            return
        to_clear = [key for key in state_map if key[0] == c.cid]
        for key in to_clear:
            state = state_map.pop(key, {})
            win = state.get("window")
            if isinstance(win, tk.Toplevel) and win.winfo_exists():
                try:
                    win.destroy()
                except Exception:
                    pass

    def _update_concentration_prompt_text(self, state: Dict[str, object]) -> None:
        label = state.get("label")
        if not isinstance(label, ttk.Label):
            return
        remaining = int(state.get("remaining_saves", 0) or 0)
        dc = int(state.get("dc", 10) or 10)
        if remaining <= 1:
            text = f"Please make a concentration saving throw. You need to get a {dc} or higher."
        else:
            text = (
                f"Please make {remaining} concentration saving throws. "
                f"You need to get a {dc} or higher {remaining} times."
            )
        label.config(text=text)

    def _end_concentration(self, c: Combatant) -> None:
        if not getattr(c, "concentrating", False):
            return
        spell_name = str(getattr(c, "concentration_spell", "") or "").replace("-", " ").strip().title() or "their spell"
        c.concentrating = False
        c.concentration_spell = ""
        c.concentration_spell_level = None
        c.concentration_started_turn = None
        aoe_ids = list(getattr(c, "concentration_aoe_ids", []) or [])
        c.concentration_aoe_ids = []
        state_map = getattr(self, "_concentration_save_state", {})
        if state_map:
            to_clear = [key for key in state_map if key[0] == c.cid]
            for key in to_clear:
                state = state_map.pop(key, {})
                win = state.get("window")
                if isinstance(win, tk.Toplevel) and win.winfo_exists():
                    try:
                        win.destroy()
                    except Exception:
                        pass
        mw = getattr(self, "_map_window", None)
        if mw is not None and getattr(mw, "winfo_exists", None) and mw.winfo_exists():
            for aid in aoe_ids:
                try:
                    mw._remove_aoe_by_id(aid)
                except Exception:
                    pass
        else:
            lan_store = getattr(self, "_lan_aoes", None)
            if isinstance(lan_store, dict) and aoe_ids:
                changed = False
                for aid in aoe_ids:
                    aoe = lan_store.get(aid)
                    if aoe and aoe.get("concentration_bound"):
                        lan_store.pop(aid, None)
                        changed = True
                if changed:
                    self._lan_aoes = lan_store
        self._log(f"{c.name} loses concentration on {spell_name}.")

    def _queue_concentration_save(self, c: Combatant, source: str) -> None:
        if not getattr(c, "concentrating", False):
            return
        if int(getattr(c, "hp", 0) or 0) <= 0:
            self._end_concentration(c)
            return
        try:
            level = int(getattr(c, "concentration_spell_level", 0) or 0)
        except Exception:
            level = 0
        if level < 0:
            level = 0
        dc = 10 + level
        turn_id = (int(self.round_num), int(self.turn_num))
        key = (int(c.cid), turn_id)
        state = self._concentration_save_state.get(key)
        if state is None:
            state = {
                "required_saves_this_turn": 0,
                "remaining_saves": 0,
                "dc": dc,
                "window": None,
                "label": None,
            }
            self._concentration_save_state[key] = state
        state["required_saves_this_turn"] = int(state.get("required_saves_this_turn", 0) or 0) + 1
        state["remaining_saves"] = int(state.get("remaining_saves", 0) or 0) + 1
        state["dc"] = dc

        win = state.get("window")
        if not isinstance(win, tk.Toplevel) or not win.winfo_exists():
            win = tk.Toplevel(self)
            win.title("Concentration Save")
            win.transient(self)

            frm = ttk.Frame(win, padding=12)
            frm.pack(fill=tk.BOTH, expand=True)
            label = ttk.Label(frm, text="", wraplength=340, justify="left")
            label.pack(fill=tk.X, padx=4, pady=(0, 12))

            btn_row = ttk.Frame(frm)
            btn_row.pack(fill=tk.X)

            def on_pass() -> None:
                state["remaining_saves"] = max(0, int(state.get("remaining_saves", 0) or 0) - 1)
                spell_name = str(getattr(c, "concentration_spell", "") or "").replace("-", " ").strip().title() or "their spell"
                self._log(f"{c.name} maintains concentration on {spell_name}.")
                if int(state.get("remaining_saves", 0) or 0) <= 0:
                    if win.winfo_exists():
                        win.destroy()
                    state["window"] = None
                    state["label"] = None
                else:
                    self._update_concentration_prompt_text(state)

            def on_fail() -> None:
                self._end_concentration(c)
                if win.winfo_exists():
                    win.destroy()
                state["window"] = None
                state["label"] = None
                self._concentration_save_state.pop(key, None)

            ttk.Button(btn_row, text="Passed save", command=on_pass).pack(side=tk.LEFT)
            tk.Button(btn_row, text="Failed throw", command=on_fail, bg="#8b1e1e", fg="white").pack(side=tk.LEFT, padx=(8, 0))

            def on_close() -> None:
                if win.winfo_exists():
                    win.destroy()
                state["window"] = None
                state["label"] = None

            win.protocol("WM_DELETE_WINDOW", on_close)
            _apply_dialog_geometry(win, 420, 200, 360, 180)
            state["window"] = win
            state["label"] = label

        self._update_concentration_prompt_text(state)


    # -------------------------- Action usage --------------------------
    def _use_action(self, c: Combatant, log_message: Optional[str] = None) -> bool:
        if c.action_remaining <= 0:
            return False
        c.action_remaining -= 1
        self._log(log_message or f"{c.name} used an action", cid=c.cid)
        return True

    def _use_bonus_action(self, c: Combatant, log_message: Optional[str] = None) -> bool:
        if c.bonus_action_remaining <= 0:
            return False
        c.bonus_action_remaining -= 1
        self._log(log_message or f"{c.name} used a bonus action", cid=c.cid)
        return True

    def _use_reaction(self, c: Combatant, log_message: Optional[str] = None) -> bool:
        if c.reaction_remaining <= 0:
            return False
        c.reaction_remaining -= 1
        self._log(log_message or f"{c.name} used a reaction", cid=c.cid)
        return True

    def _grant_action_targets(self) -> List[Combatant]:
        selected = self._selected_cids()
        targets: List[Combatant] = []
        if selected:
            for cid in selected:
                if cid in self.combatants:
                    targets.append(self.combatants[cid])
            return targets
        if self.current_cid is not None and self.current_cid in self.combatants:
            return [self.combatants[self.current_cid]]
        return []

    def _give_action(self) -> None:
        targets = self._grant_action_targets()
        if not targets:
            messagebox.showinfo("Turn Tracker", "Select a combatant row first.")
            return
        for c in targets:
            if self.current_cid == c.cid:
                c.action_remaining += 1
                note = "extra action granted"
            else:
                c.extra_action_pool = int(getattr(c, "extra_action_pool", 0) or 0) + 1
                note = "extra action queued"
            self._log(note, cid=c.cid)
        self._rebuild_table(scroll_to_current=True)

    def _give_bonus_action(self) -> None:
        targets = self._grant_action_targets()
        if not targets:
            messagebox.showinfo("Turn Tracker", "Select a combatant row first.")
            return
        for c in targets:
            if self.current_cid == c.cid:
                c.bonus_action_remaining += 1
                note = "extra bonus action granted"
            else:
                c.extra_bonus_pool = int(getattr(c, "extra_bonus_pool", 0) or 0) + 1
                note = "extra bonus action queued"
            self._log(note, cid=c.cid)
        self._rebuild_table(scroll_to_current=True)


    # -------------------------- Movement actions --------------------------
    def _stand_up_current(self) -> None:
        if self.current_cid is None or self.current_cid not in self.combatants:
            return
        c = self.combatants[self.current_cid]
        if not self._has_condition(c, "prone"):
            return

        eff = self._effective_speed(c)
        if eff <= 0:
            messagebox.showinfo("Stand Up", "Can't stand up right now (speed is 0).")
            return

        cost = max(0, eff // 2)
        if c.move_remaining < cost:
            messagebox.showinfo("Stand Up", f"Not enough movement to stand (need {cost} ft).")
            return

        c.move_remaining -= cost
        self._remove_condition_type(c, "prone")
        self.start_last_var.set(f"{c.name}: stood up (-{cost} ft)")
        self._log(f"stood up (spent {cost} ft, prone removed)", cid=c.cid)
        self._rebuild_table(scroll_to_current=True)


    def _open_move_tool(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Spend Movement")
        dlg.geometry("540x380")
        dlg.minsize(480, 320)
        dlg.transient(self)

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Target").grid(row=0, column=0, sticky="w")
        targets = self._target_labels()
        target_var = tk.StringVar(value=(targets[0] if targets else ""))
        target_combo = ttk.Combobox(frm, textvariable=target_var, values=targets, state="readonly", width=36)
        target_combo.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 8))
        frm.columnconfigure(0, weight=1)

        ttk.Label(frm, text="Move (ft)").grid(row=2, column=0, sticky="w")
        amt_var = tk.StringVar()
        amt_entry = ttk.Entry(frm, textvariable=amt_var, width=12)
        amt_entry.grid(row=3, column=0, sticky="w")

        difficult_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Difficult terrain (double cost)", variable=difficult_var).grid(
            row=3, column=1, sticky="w", padx=(12, 0)
        )

        apply_selected = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Apply to selected rows", variable=apply_selected).grid(
            row=4, column=0, sticky="w", pady=(6, 0)
        )

        mode_var = tk.StringVar(value=MOVEMENT_MODE_LABELS["normal"])
        ttk.Label(frm, text="Mode").grid(row=4, column=1, sticky="w", padx=(12, 0), pady=(6, 0))
        mode_combo = ttk.Combobox(
            frm,
            textvariable=mode_var,
            values=[MOVEMENT_MODE_LABELS[mode] for mode in MOVEMENT_MODES],
            state="readonly",
            width=12,
        )
        mode_combo.grid(row=5, column=1, sticky="w", padx=(12, 0))

        # Auto-pick selected row if any
        sel = self.tree.selection()
        if sel:
            try:
                scid = int(sel[0])
                if scid in self.combatants:
                    target_var.set(self._label_for(self.combatants[scid]))
                    mode_var.set(self._movement_mode_label(self.combatants[scid].movement_mode))
            except ValueError:
                pass
        elif self.current_cid is not None and self.current_cid in self.combatants:
            target_var.set(self._label_for(self.combatants[self.current_cid]))
            mode_var.set(self._movement_mode_label(self.combatants[self.current_cid].movement_mode))

        def refresh_targets(keep: str = ""):
            vals = self._target_labels()
            target_combo.configure(values=vals)
            if keep in vals:
                target_var.set(keep)
            elif vals:
                target_var.set(vals[0])
            else:
                target_var.set("")

        def apply(_evt=None):
            expr = amt_var.get().strip()
            try:
                feet = self._parse_int_expr(expr)
            except Exception:
                messagebox.showerror("Move", "Move must be a number (you can use simple math like 10+5).")
                return
            if feet < 0:
                messagebox.showerror("Move", "Move can't be negative.")
                return

            cost = feet * (2 if difficult_var.get() else 1)

            # Determine targets
            cids: List[int] = []
            if apply_selected.get():
                for it in self.tree.selection():
                    try:
                        cid = int(it)
                    except ValueError:
                        continue
                    if cid in self.combatants:
                        cids.append(cid)
                if not cids:
                    messagebox.showinfo("Move", "No selected rows to apply to.")
                    return
            else:
                lbl = target_var.get().strip()
                cid = self._cid_from_label(lbl)
                if cid is None or cid not in self.combatants:
                    messagebox.showerror("Move", "Pick a valid target.")
                    return
                cids = [cid]

            for cid in cids:
                # Apply movement mode first (only logs if it actually changes)
                self._set_movement_mode(cid, mode_var.get())
                c = self.combatants.get(cid)
                if c is None:
                    continue

                old = int(c.move_remaining)
                c.move_remaining = max(0, old - int(cost))
                note = f"moved {feet} ft"
                note += f" (difficult: -{cost})" if difficult_var.get() else f" (-{cost})"
                self._log(note + f" (move {old} -> {c.move_remaining})", cid=cid)

            keep_lbl = target_var.get().strip()
            self._rebuild_table(scroll_to_current=True)
            refresh_targets(keep_lbl)

            amt_entry.focus_set()
            amt_entry.selection_range(0, tk.END)

        def cancel(_evt=None):
            dlg.destroy()

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(btn_row, text="Apply", command=apply).pack(side=tk.RIGHT)
        ttk.Button(btn_row, text="Cancel", command=cancel).pack(side=tk.RIGHT, padx=(0, 8))

        dlg.bind("<Return>", apply)
        dlg.bind("<Escape>", cancel)
        amt_entry.focus_set()

    def _open_lan_admin(self) -> None:
        messagebox.showinfo(
            "LAN Admin",
            "LAN admin tools are available in the LAN-enabled app.",
        )

    # -------------------------- Effects formatting --------------------------
    def _format_effects(self, c: Combatant) -> str:
        parts: List[str] = []
        if any(st.ctype == "star_advantage" for st in c.condition_stacks):
            parts.append(str(CONDITIONS_META.get("star_advantage", {}).get("icon", "⭐")))

        # DoT: count per type
        counts: Dict[str, int] = {}
        for st in c.condition_stacks:
            if st.ctype != "dot":
                continue
            dtype = st.dot_type or "dot"
            counts[dtype] = counts.get(dtype, 0) + 1
        for dtype in ["burn", "poison", "necrotic"]:
            n = counts.get(dtype, 0)
            if n <= 0:
                continue
            icon = DOT_META.get(dtype, {}).get("icon", "•")
            parts.append(f"{icon}x{n}" if n > 1 else str(icon))

        # Conditions (non-stacking; Exhaustion handled separately)
        if c.condition_stacks:
            for st in sorted(c.condition_stacks, key=lambda x: x.ctype):
                if st.ctype in {"dot", "star_advantage"}:
                    continue
                icon = str(CONDITIONS_META.get(st.ctype, {}).get("icon", "•"))
                if st.remaining_turns is None:
                    parts.append(icon)
                else:
                    parts.append(f"{icon}({st.remaining_turns})")

        if c.exhaustion_level > 0:
            parts.append(f"{CONDITIONS_META['exhaustion']['icon']}{c.exhaustion_level}")

        return " ".join(parts)

    # -------------------------- Table maintenance --------------------------

    def _move_cell(self, c: Combatant) -> str:
        """Display movement as remaining/total for the current turn."""
        base = int(self._mode_speed(c))
        total = int(getattr(c, "move_total", 0) or 0)
        if total <= 0:
            total = base
        rem = int(getattr(c, "move_remaining", 0) or 0)
        # Clamp
        rem = max(0, min(rem, total))
        return f"{rem}/{total}"

    def _dash_current(self) -> None:
        """Add one more 'speed' worth of movement to the current creature (Dash)."""
        cid = self.current_cid
        if cid is None:
            # fall back to first selected
            try:
                sel = self.tree.selection()
                if sel:
                    cid = int(sel[0])
            except Exception:
                cid = None
        if cid is None or cid not in self.combatants:
            return
        c = self.combatants[cid]
        base = int(self._mode_speed(c))
        total = int(getattr(c, "move_total", 0) or 0)
        if total <= 0:
            total = base
        rem = int(getattr(c, "move_remaining", 0) or 0)

        c.move_total = total + base
        c.move_remaining = rem + base
        self._log(f"{c.name} dashes: move {self._move_cell(c)} ft.", cid=cid)
        self._rebuild_table(scroll_to_current=True)
        try:
            if self._map_window is not None and self._map_window.winfo_exists():
                self._map_window._update_move_highlight()
        except Exception:
            pass

    def _apply_temp_move_bonus(self, cid: int, bonus: int, turns: int) -> bool:
        if cid not in self.combatants:
            return False
        bonus_amt = max(0, int(bonus))
        turns_amt = max(0, int(turns))
        if bonus_amt <= 0 or turns_amt <= 0:
            return False
        c = self.combatants[cid]
        old_eff = self._effective_speed(c)
        c.temp_move_bonus = bonus_amt
        c.temp_move_turns_remaining = turns_amt
        new_eff = self._effective_speed(c)
        delta = new_eff - old_eff
        if self.current_cid == cid:
            total = int(getattr(c, "move_total", 0) or 0)
            if total <= 0:
                total = old_eff
            c.move_total = max(0, total + delta)
            c.move_remaining = max(0, int(getattr(c, "move_remaining", 0) or 0) + delta)
        else:
            c.move_total = int(new_eff)
            c.move_remaining = int(new_eff)
        turns_label = "turn" if turns_amt == 1 else "turns"
        self._log(f"temporary movement +{bonus_amt} ft for {turns_amt} {turns_label}", cid=cid)
        return True

    def _grant_temp_move_bonus(self) -> None:
        targets = [c for c in self._grant_action_targets() if bool(getattr(c, "is_pc", False))]
        if not targets:
            messagebox.showinfo("Turn Tracker", "Select a player character row first.")
            return
        bonus = simpledialog.askinteger(
            "Temporary Movement",
            "Add how much movement (ft)?",
            parent=self,
            minvalue=1,
        )
        if bonus is None:
            return
        turns = simpledialog.askinteger(
            "Temporary Movement",
            "For how many turns?",
            parent=self,
            minvalue=1,
            initialvalue=1,
        )
        if turns is None:
            return
        applied = False
        for c in targets:
            applied = self._apply_temp_move_bonus(c.cid, bonus, turns) or applied
        if not applied:
            return
        self._rebuild_table(scroll_to_current=True)
        try:
            if self._map_window is not None and self._map_window.winfo_exists():
                self._map_window._update_move_highlight()
        except Exception:
            pass

    def _rebuild_table(self, scroll_to_top: bool = False, scroll_to_current: bool = False) -> None:
        # preserve selection
        prev_sel = set(self.tree.selection())
        try:
            prev_y = self.tree.yview()[0]
        except Exception:
            prev_y = 0.0

        self.tree.delete(*self.tree.get_children())

        ordered = self._display_order()
        for i, c in enumerate(ordered):
            side = "Player Character" if getattr(c, "is_pc", False) else ("Ally" if c.ally else "Enemy")
            temp_hp = int(getattr(c, "temp_hp", 0) or 0)
            ac = self._combatant_ac_display(c)
            swim_disp = "" if int(getattr(c, "swim_speed", 0) or 0) == 0 else int(getattr(c, "swim_speed", 0))
            fly_disp = "" if int(getattr(c, "fly_speed", 0) or 0) == 0 else int(getattr(c, "fly_speed", 0))
            init_disp = self._initiative_display(c)
            values = (c.name, side, c.hp, temp_hp, ac, c.speed, swim_disp, fly_disp, self._format_effects(c), init_disp)

            tags: List[str] = []
            tags.append("odd" if i % 2 else "even")
            tags.append("ally" if (c.ally or getattr(c, "is_pc", False)) else "enemy")
            if self.current_cid == c.cid:
                tags.append("current")
            if self.start_cid == c.cid:
                tags.append("start")

            self.tree.insert("", tk.END, iid=str(c.cid), values=values, tags=tuple(tags))

        # restore selection
        for it in prev_sel:
            if it in self.tree.get_children():
                self.tree.selection_add(it)

        if scroll_to_top:
            self.tree.yview_moveto(0.0)
        elif scroll_to_current and self.current_cid is not None:
            try:
                self.tree.see(str(self.current_cid))
            except Exception:
                pass
        else:
            try:
                self.tree.yview_moveto(prev_y)
            except Exception:
                pass

        self._update_turn_ui()
        self._sync_move_mode_selector()

    # -------------------------- Inline editing / clicks --------------------------
    def _selected_enemy_combatant(self) -> Optional[Combatant]:
        items = self.tree.selection()
        if not items:
            return None
        try:
            cid = int(items[0])
        except ValueError:
            return None
        c = self.combatants.get(cid)
        if not c or c.ally:
            return None
        return c

    def _on_tree_right_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
        else:
            self.tree.selection_remove(self.tree.selection())

        can_view = self._selected_enemy_combatant() is not None
        state = tk.NORMAL if can_view else tk.DISABLED
        self._tree_context_menu.entryconfigure("View Monster Info", state=state)
        try:
            self._tree_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._tree_context_menu.grab_release()

    def _open_selected_monster_info(self) -> None:
        c = self._selected_enemy_combatant()
        if not c:
            return
        spec = c.monster_spec or self._monsters_by_name.get(c.name)
        if spec is not None:
            spec = self._load_monster_details(spec.name) or spec
        if not spec:
            messagebox.showinfo("Monster Info", f"No stat block available for {c.name}.")
            return
        self._open_monster_stat_block(spec)

    def _on_tree_double_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item:
            return
        try:
            cid = int(item)
        except ValueError:
            return
        if cid not in self.combatants:
            return

        # Columns:
        # #1 name, #2 side, #3 hp, #4 temp hp, #5 ac, #6 walk, #7 swim, #8 fly, #9 conditions, #10 initiative
        if column == "#1":
            self._inline_edit_cell(item, column, str(self.combatants[cid].name), str, lambda v: self._set_name(cid, v), rebuild=False)
            return
        if column == "#10":
            self._inline_edit_cell(item, column, str(self.combatants[cid].initiative), int, lambda v: self._set_initiative(cid, v))
            return
        if column == "#3":
            self._inline_edit_cell(item, column, str(self.combatants[cid].hp), int, lambda v: self._set_hp(cid, v))
            return
        if column == "#4":
            self._inline_edit_cell(
                item,
                column,
                str(int(getattr(self.combatants[cid], "temp_hp", 0) or 0)),
                int,
                lambda v: self._set_temp_hp(cid, v),
            )
            return
        if column == "#5":
            current_ac = getattr(self.combatants[cid], "ac", "")
            self._inline_edit_cell(item, column, str(current_ac), int, lambda v: self._set_ac(cid, v))
            return
        if column == "#6":
            self._inline_edit_cell(item, column, str(self.combatants[cid].speed), int, lambda v: self._set_speed(cid, v))
            return
        if column == "#7":
            self._inline_edit_cell(item, column, str(self.combatants[cid].swim_speed), int, lambda v: self._set_swim_speed(cid, v))
            return
        if column == "#2":
            c = self.combatants[cid]
            # Cycle Side: Enemy -> Ally -> Player Character -> Enemy
            if getattr(c, "is_pc", False):
                c.is_pc = False
                c.ally = False
            elif c.ally:
                c.is_pc = True
                c.ally = True
            else:
                c.ally = True
                c.is_pc = False
            self._remember_role(c)
            self._rebuild_table(scroll_to_current=True)
            return
        if column == "#9":
            self.tree.selection_set(item)
            self._open_condition_tool()
            return

    def _combatant_ac_display(self, combatant: Combatant) -> str:
        ac_value = None
        for key in ("ac", "armor_class"):
            raw = getattr(combatant, key, None)
            if raw is not None:
                ac_value = raw
                break
        if ac_value is None:
            spec = getattr(combatant, "monster_spec", None)
            raw_data = getattr(spec, "raw_data", None)
            if isinstance(raw_data, dict):
                ac_value = raw_data.get("ac", raw_data.get("armor_class"))
        formatted = self._format_monster_ac(ac_value)
        return "" if formatted == "—" else formatted

    def _initiative_display(self, combatant: Combatant) -> str:
        value = str(int(getattr(combatant, "initiative", 0) or 0))
        return f"{value}★" if bool(getattr(combatant, "nat20", False)) else value

    def _inline_edit_cell(self, item: str, column: str, initial: str, caster, setter, rebuild: bool = True) -> None:
        x, y, w, h = self.tree.bbox(item, column)
        if w == 0 and h == 0:
            return
        entry = ttk.Entry(self.tree)
        entry.insert(0, initial)
        entry.select_range(0, tk.END)
        entry.focus_set()
        entry.place(x=x, y=y, width=w, height=h)

        def commit(_evt=None):
            val = entry.get().strip()
            if val == "":
                entry.destroy()
                return
            try:
                v = caster(val)
            except Exception:
                entry.destroy()
                return
            entry.destroy()
            setter(v)
            if rebuild:
                self._rebuild_table(scroll_to_current=True)

        def cancel(_evt=None):
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    def _set_initiative(self, cid: int, new_init: int) -> None:
        if cid in self.combatants:
            self.combatants[cid].initiative = int(new_init)

    def _set_name(self, cid: int, new_name: str) -> None:
        if cid not in self.combatants:
            return
        name = (new_name or "").strip()
        if not name:
            return
        c = self.combatants[cid]
        old_name = c.name
        unique_name = old_name if name == old_name else self._unique_name(name)
        if old_name != unique_name and old_name in self._name_role_memory:
            del self._name_role_memory[old_name]
        c.name = unique_name
        self._remember_role(c)
        self._rebuild_table(scroll_to_current=True)
        try:
            if self._map_window is not None and self._map_window.winfo_exists():
                self._map_window.refresh_units()
        except Exception:
            pass

    def _set_hp(self, cid: int, new_hp: int) -> None:
        if cid in self.combatants:
            self.combatants[cid].hp = max(0, int(new_hp))

    def _set_temp_hp(self, cid: int, new_temp_hp: int) -> None:
        if cid in self.combatants:
            setattr(self.combatants[cid], "temp_hp", max(0, int(new_temp_hp)))

    def _apply_heal_to_combatant(self, cid: int, amount: int, *, is_temp_hp: bool = False) -> bool:
        c = self.combatants.get(cid)
        if c is None:
            return False
        if is_temp_hp:
            setattr(c, "temp_hp", max(0, int(amount)))
            return True
        c.hp = max(0, int(c.hp) + int(amount))
        return True

    def _set_ac(self, cid: int, new_ac: int) -> None:
        if cid in self.combatants:
            setattr(self.combatants[cid], "ac", max(0, int(new_ac)))

    def _set_speed(self, cid: int, new_spd: int) -> None:
        if cid not in self.combatants:
            return
        c = self.combatants[cid]
        c.speed = max(0, int(new_spd))
        if self.current_cid == cid:
            c.move_remaining = min(c.move_remaining, self._effective_speed(c))
        else:
            base_spd = self._mode_speed(c)
            c.move_total = int(base_spd)
            c.move_remaining = int(base_spd)

    def _set_swim_speed(self, cid: int, new_spd: int) -> None:
        if cid not in self.combatants:
            return
        c = self.combatants[cid]
        c.swim_speed = max(0, int(new_spd))
        if self.current_cid == cid:
            c.move_remaining = min(c.move_remaining, self._effective_speed(c))
        else:
            base_spd = self._mode_speed(c)
            c.move_total = int(base_spd)
            c.move_remaining = int(base_spd)

    def _set_movement_mode(self, cid: int, mode: str, log_change: bool = True) -> None:
        if cid not in self.combatants:
            return
        c = self.combatants[cid]
        old_mode = self._normalize_movement_mode(getattr(c, "movement_mode", "normal"))
        new_mode = self._normalize_movement_mode(mode)
        if old_mode == new_mode:
            return
        c.movement_mode = new_mode
        # Adjust movement bookkeeping
        if self.current_cid == cid:
            c.move_remaining = min(c.move_remaining, self._effective_speed(c))
        else:
            base_spd = self._mode_speed(c)
            c.move_total = int(base_spd)
            c.move_remaining = int(base_spd)
        if log_change:
            self._log(f"movement mode set to {self._movement_mode_label(new_mode)}", cid=cid)
        try:
            if self._map_window is not None and self._map_window.winfo_exists():
                self._map_window._update_move_highlight()
        except Exception:
            pass

    def _cycle_movement_mode_selected(self) -> None:
        items = list(self.tree.selection())
        if not items and self.current_cid is not None:
            items = [str(self.current_cid)]
        if not items:
            return
        for it in items:
            try:
                cid = int(it)
            except ValueError:
                continue
            if cid not in self.combatants:
                continue
            c = self.combatants[cid]
            current = self._normalize_movement_mode(getattr(c, "movement_mode", "normal"))
            idx = MOVEMENT_MODES.index(current) if current in MOVEMENT_MODES else 0
            next_mode = MOVEMENT_MODES[(idx + 1) % len(MOVEMENT_MODES)]
            self._set_movement_mode(cid, next_mode)
        self._sync_move_mode_selector()
        self._rebuild_table(scroll_to_current=True)

    def _apply_selected_movement_mode(self) -> None:
        label = str(self.move_mode_var.get() or "")
        mode = self._normalize_movement_mode(label)
        items = list(self.tree.selection())
        if not items and self.current_cid is not None:
            items = [str(self.current_cid)]
        if not items:
            return
        for it in items:
            try:
                cid = int(it)
            except ValueError:
                continue
            if cid in self.combatants:
                self._set_movement_mode(cid, mode)
        self._rebuild_table(scroll_to_current=True)

    def _sync_move_mode_selector(self) -> None:
        if not hasattr(self, "move_mode_var"):
            return
        cid = None
        sel = self.tree.selection()
        if sel:
            try:
                cid = int(sel[0])
            except ValueError:
                cid = None
        if cid is None:
            cid = self.current_cid
        if cid is not None and cid in self.combatants:
            mode = self._movement_mode_label(getattr(self.combatants[cid], "movement_mode", "normal"))
            self.move_mode_var.set(mode)
        else:
            self.move_mode_var.set(MOVEMENT_MODE_LABELS["normal"])

    # --------------------- Index cache helpers ---------------------
    def _logs_dir_path(self) -> Path:
        base_dir = _app_data_dir()
        logs = base_dir / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return logs

    def _index_file_path(self, name: str) -> Path:
        return self._logs_dir_path() / name

    def _read_index_file(self, path: Path) -> Dict[str, Any]:
        try:
            if not path.exists():
                return {}
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_index_file(self, path: Path, payload: Dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

    def _file_stat_metadata(self, fp: Path) -> Dict[str, object]:
        try:
            stat = fp.stat()
            return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
        except Exception:
            return {"mtime_ns": 0, "size": 0}

    def _metadata_matches(self, entry: Dict[str, object], meta: Dict[str, object]) -> bool:
        return entry.get("mtime_ns") == meta.get("mtime_ns") and entry.get("size") == meta.get("size")

    def _parse_fractional_cr(self, value: str) -> Optional[float]:
        match = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", value)
        if not match:
            return None
        denom = int(match.group(2))
        if denom == 0:
            return None
        return int(match.group(1)) / denom

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _build_dir_cache_signature(self, dir_path: Path, patterns: Tuple[str, ...]) -> Tuple[float, str, List[Path]]:
        files: List[Path] = []
        seen: Set[str] = set()
        for pattern in patterns:
            try:
                for fp in dir_path.glob(pattern):
                    key = str(fp)
                    if key in seen:
                        continue
                    seen.add(key)
                    files.append(fp)
            except Exception:
                continue
        files.sort(key=lambda p: p.name.lower())

        try:
            dir_mtime = dir_path.stat().st_mtime
        except Exception:
            dir_mtime = 0.0

        hasher = hashlib.sha256()
        for fp in files:
            try:
                stat = fp.stat()
                hasher.update(fp.name.encode("utf-8"))
                hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
                hasher.update(str(stat.st_size).encode("utf-8"))
            except Exception:
                hasher.update(fp.name.encode("utf-8"))
        return dir_mtime, hasher.hexdigest(), files

    def _is_index_cache_valid(self, cache: Optional[Dict[str, object]], dir_mtime: float, files_hash: str) -> bool:
        if not cache:
            return False
        return cache.get("dir_mtime") == dir_mtime and cache.get("files_hash") == files_hash

    def _invalidate_monster_index_cache(self) -> None:
        self._monster_index_cache = None
        self._monster_detail_cache = {}

    def ensure_monster_index_loaded(self) -> None:
        self._load_monsters_index()

    def _refresh_monsters_spells(self) -> None:
        self._invalidate_monster_index_cache()
        self._load_indexes_async(self._refresh_monster_library)

    def _refresh_monster_library(self) -> None:
        for refresh in list(self._monster_library_refreshers):
            try:
                refresh()
            except Exception:
                pass

    def _load_indexes_async(self, on_complete: Optional[Callable[[], None]] = None) -> None:
        if on_complete is not None:
            self._index_loading_callbacks.append(on_complete)
        if self._index_loading:
            return
        self._index_loading = True
        worker = threading.Thread(target=self._load_monsters_and_spells, daemon=True)
        worker.start()

        def check_done() -> None:
            if worker.is_alive():
                self.after(50, check_done)
                return
            self._index_loading = False
            callbacks = list(self._index_loading_callbacks)
            self._index_loading_callbacks.clear()
            for callback in callbacks:
                callback()

        self.after(50, check_done)

    def _load_monsters_and_spells(self) -> None:
        self._load_monsters_index()

    # --------------------- Monsters (YAML library) ---------------------
    def _monsters_dir_path(self) -> Path:
        return _seed_user_monsters_dir()

    def _load_monsters_index(self) -> None:
        """Load ./Monsters/*.yml|*.yaml and build a small index for the add dropdown."""
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

        index_path = self._index_file_path("monster_index.json")
        index_data = self._read_index_file(index_path)
        cached_entries = index_data.get("entries") if isinstance(index_data.get("entries"), dict) else {}

        self._monster_specs = []
        self._monsters_by_name = {}
        self._monster_detail_cache = {}

        new_entries: Dict[str, Any] = {}
        yaml_missing_logged = False

        if not files:
            self._write_index_file(index_path, {"version": 1, "entries": {}})
            return

        for fp in files:
            meta = self._file_stat_metadata(fp)
            entry = cached_entries.get(fp.name) if isinstance(cached_entries, dict) else None
            if isinstance(entry, dict) and self._metadata_matches(entry, meta):
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
                            fly_speed=summary.get("fly_speed"),
                            burrow_speed=summary.get("burrow_speed"),
                            climb_speed=summary.get("climb_speed"),
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
                                new_entry["hash"] = self._hash_text(raw)
                            except Exception:
                                pass
                        new_entries[fp.name] = new_entry
                        continue

            if yaml is None:
                if not yaml_missing_logged:
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
            ab = mon.get("abilities")
            if isinstance(ab, dict):
                for key, val in ab.items():
                    if not isinstance(key, str):
                        continue
                    abilities[key.strip().lower()] = val
            if is_legacy:
                try:
                    ch = mon.get("challenge") or {}
                    if isinstance(ch, dict) and "cr" in ch:
                        raw_data["challenge_rating"] = ch.get("cr")
                except Exception:
                    pass
            else:
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
                if abilities:
                    raw_data["abilities"] = abilities

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
                    cr = self._parse_fractional_cr(cr_val)
                    if cr is None:
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
            fly_speed = None
            burrow_speed = None
            climb_speed = None
            try:
                sp = mon.get("speed")
                speed, swim_speed, fly_speed, burrow_speed, climb_speed = _parse_speed_data(sp)
            except Exception:
                speed = None
                swim_speed = None
                fly_speed = None
                burrow_speed = None
                climb_speed = None

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
                ini = mon.get("initiative")
                if isinstance(ini, dict):
                    init_mod = self._monster_int_from_value(ini.get("modifier"))
                else:
                    init_mod = self._monster_int_from_value(ini)
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
                fly_speed=fly_speed,
                burrow_speed=burrow_speed,
                climb_speed=climb_speed,
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
                "hash": self._hash_text(raw),
                "summary": {
                    "name": name,
                    "mtype": mtype,
                    "cr": cr,
                    "hp": hp,
                    "speed": speed,
                    "swim_speed": swim_speed,
                    "fly_speed": fly_speed,
                    "burrow_speed": burrow_speed,
                    "climb_speed": climb_speed,
                    "dex": dex,
                    "init_mod": init_mod,
                    "saving_throws": saving_throws,
                    "ability_mods": ability_mods,
                    "raw_data": raw_data,
                },
            }

        self._monster_specs.sort(key=lambda s: s.name.lower())
        self._write_index_file(index_path, {"version": 1, "entries": new_entries})

    def _load_monster_details(self, name: str) -> Optional[MonsterSpec]:
        spec = self._monsters_by_name.get(name)
        if not spec:
            return None
        filename = spec.filename
        if filename in self._monster_detail_cache:
            spec.raw_data = self._monster_detail_cache[filename]
            return spec
        if spec.raw_data:
            self._monster_detail_cache[filename] = spec.raw_data
            return spec
        if yaml is None:
            return spec
        fp = self._monsters_dir_path() / filename
        try:
            raw = fp.read_text(encoding="utf-8")
        except Exception:
            return spec
        try:
            data = yaml.safe_load(raw)
        except Exception:
            return spec
        if not isinstance(data, dict):
            return spec
        legacy_mon = data.get("monster")
        is_legacy = "monster" in data
        if is_legacy:
            if not isinstance(legacy_mon, dict):
                return spec
            mon = legacy_mon
        else:
            mon = data

        abilities: Dict[str, Any] = {}
        ab = mon.get("abilities")
        if isinstance(ab, dict):
            for key, val in ab.items():
                if not isinstance(key, str):
                    continue
                abilities[key.strip().lower()] = val

        raw_data: Dict[str, Any] = {}
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
            if abilities:
                raw_data["abilities"] = abilities

        self._monster_detail_cache[filename] = raw_data
        spec.raw_data = raw_data
        return spec

    def _monster_names_sorted(self) -> List[str]:
        return [s.name for s in self._monster_specs]

    def _monster_cr_display(self, spec: Optional[MonsterSpec]) -> str:
        if spec is None:
            return "?"
        raw = None
        if isinstance(spec.raw_data, dict):
            raw = spec.raw_data.get("challenge_rating")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, (int, float)):
            return str(int(raw)) if float(raw).is_integer() else str(raw)
        if spec.cr is None:
            return "?"
        return str(int(spec.cr)) if float(spec.cr).is_integer() else str(spec.cr)

    def _open_dm_reference_library(self, from_window: Optional[tk.Misc] = None) -> None:
        """Open the creature reference library while map mode is active."""
        try:
            self._open_bulk_dialog()
        except Exception:
            parent = from_window if from_window is not None else self
            messagebox.showerror("Creature Library", "Unable to open the creature library.", parent=parent)

    # -------------------------- Bulk add --------------------------
    def _open_bulk_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Bulk Add")
        dlg.geometry("980x620")
        dlg.minsize(900, 600)
        dlg.transient(self)

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        left = ttk.Frame(frm)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(3, weight=1)
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Creature Library").grid(row=0, column=0, sticky="w")
        filter_var = tk.StringVar()
        filter_entry = ttk.Entry(left, textvariable=filter_var)
        filter_entry.grid(row=1, column=0, sticky="ew", pady=(4, 6))

        sort_row = ttk.Frame(left)
        sort_row.grid(row=2, column=0, sticky="ew")
        ttk.Label(sort_row, text="Sort by").pack(side=tk.LEFT)
        sort_var = tk.StringVar(value="Name")
        sort_combo = ttk.Combobox(sort_row, textvariable=sort_var, values=["Name", "Type", "CR", "HP", "Speed"], state="readonly", width=12)
        sort_combo.pack(side=tk.LEFT, padx=(6, 0))

        list_frame = ttk.Frame(left)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        library_list = tk.Listbox(list_frame, height=12, exportselection=False)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=library_list.yview)
        library_list.configure(yscrollcommand=list_scroll.set)
        library_list.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")

        info_btn = ttk.Button(left, text="Info")
        info_btn.grid(row=4, column=0, sticky="w", pady=(8, 0))

        right = ttk.Frame(frm)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        ttk.Label(right, text="Group Builder").grid(row=0, column=0, sticky="w")

        base_name_var = tk.StringVar()
        ttk.Label(right, text="Base Name").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(right, textvariable=base_name_var, width=26).grid(row=2, column=0, sticky="w")

        group_frame = ttk.LabelFrame(right, text="Groups")
        group_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        group_frame.columnconfigure(0, weight=1)

        groups_canvas = tk.Canvas(group_frame, highlightthickness=0)
        groups_scroll = ttk.Scrollbar(group_frame, orient="vertical", command=groups_canvas.yview)
        groups_canvas.configure(yscrollcommand=groups_scroll.set)
        groups_canvas.grid(row=0, column=0, sticky="nsew")
        groups_scroll.grid(row=0, column=1, sticky="ns")
        group_frame.rowconfigure(0, weight=1)

        groups_inner = ttk.Frame(groups_canvas)
        groups_inner_id = groups_canvas.create_window((0, 0), window=groups_inner, anchor="nw")

        def _on_groups_inner(_evt=None):
            groups_canvas.configure(scrollregion=groups_canvas.bbox("all"))

        def _on_groups_canvas(evt):
            try:
                groups_canvas.itemconfigure(groups_inner_id, width=evt.width)
            except Exception:
                pass

        groups_inner.bind("<Configure>", _on_groups_inner)
        groups_canvas.bind("<Configure>", _on_groups_canvas)

        group_rows: list[dict] = []

        def apply_monster_defaults(
            spec: Optional[MonsterSpec],
            hp_var: tk.StringVar,
            spd_var: tk.StringVar,
            swim_var: tk.StringVar,
            dex_var: tk.StringVar,
        ) -> None:
            if not spec:
                return
            if spec.hp is not None:
                hp_var.set(str(spec.hp))
            if spec.speed is not None:
                spd_var.set(str(spec.speed))
            if spec.swim_speed is not None and spec.swim_speed > 0:
                swim_var.set(str(spec.swim_speed))
            else:
                swim_var.set("")

            dex_mod = None
            if spec.dex is not None:
                try:
                    dex_mod = (int(spec.dex) - 10) // 2
                except Exception:
                    dex_mod = None
            mod = spec.init_mod
            if mod is None:
                mod = dex_mod
            if mod is not None:
                dex_var.set(str(mod))

        def _regrid_groups() -> None:
            for idx, row in enumerate(group_rows):
                r = idx
                row["frame"].grid(row=r, column=0, sticky="ew", pady=4)
                row["frame"].columnconfigure(0, weight=1)

        def add_group(spec: Optional[MonsterSpec] = None, name: str = "") -> None:
            frame = ttk.Frame(groups_inner)
            name_var = tk.StringVar(value=name or (spec.name if spec else ""))
            count_var = tk.StringVar(value="1")
            dex_var = tk.StringVar()
            hp_var = tk.StringVar()
            spd_var = tk.StringVar(value="30")
            swim_var = tk.StringVar()
            ally_var = tk.BooleanVar(value=False)
            mode_var = tk.StringVar(value=MOVEMENT_MODE_LABELS["normal"])

            top_row = ttk.Frame(frame)
            top_row.grid(row=0, column=0, sticky="ew")
            ttk.Label(top_row, text="Name").pack(side=tk.LEFT)
            ttk.Entry(top_row, textvariable=name_var, width=22).pack(side=tk.LEFT, padx=(6, 8))
            ttk.Label(top_row, text="Count").pack(side=tk.LEFT)
            ttk.Entry(top_row, textvariable=count_var, width=6).pack(side=tk.LEFT, padx=(6, 0))

            stat_row = ttk.Frame(frame)
            stat_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            ttk.Label(stat_row, text="Dex").pack(side=tk.LEFT)
            ttk.Entry(stat_row, textvariable=dex_var, width=6).pack(side=tk.LEFT, padx=(4, 8))
            ttk.Label(stat_row, text="HP").pack(side=tk.LEFT)
            ttk.Entry(stat_row, textvariable=hp_var, width=6).pack(side=tk.LEFT, padx=(4, 8))
            ttk.Label(stat_row, text="Speed").pack(side=tk.LEFT)
            ttk.Entry(stat_row, textvariable=spd_var, width=6).pack(side=tk.LEFT, padx=(4, 8))
            ttk.Label(stat_row, text="Swim").pack(side=tk.LEFT)
            ttk.Entry(stat_row, textvariable=swim_var, width=6).pack(side=tk.LEFT, padx=(4, 8))
            ttk.Checkbutton(stat_row, text="Ally", variable=ally_var).pack(side=tk.LEFT, padx=(6, 4))
            ttk.Label(stat_row, text="Mode").pack(side=tk.LEFT)
            mode_combo = ttk.Combobox(
                stat_row,
                textvariable=mode_var,
                values=[MOVEMENT_MODE_LABELS[mode] for mode in MOVEMENT_MODES],
                state="readonly",
                width=8,
            )
            mode_combo.pack(side=tk.LEFT, padx=(4, 0))

            def remove_group() -> None:
                if len(group_rows) <= 1:
                    name_var.set("")
                    count_var.set("1")
                    dex_var.set("")
                    hp_var.set("")
                    spd_var.set("30")
                    swim_var.set("")
                    ally_var.set(False)
                    mode_var.set(MOVEMENT_MODE_LABELS["normal"])
                    return
                try:
                    group_rows.remove(row)
                except ValueError:
                    pass
                try:
                    frame.destroy()
                except Exception:
                    pass
                _regrid_groups()

            remove_btn = ttk.Button(frame, text="Remove", command=remove_group)
            remove_btn.grid(row=0, column=1, rowspan=2, padx=(8, 0))

            row = dict(
                frame=frame,
                name_var=name_var,
                count_var=count_var,
                dex_var=dex_var,
                hp_var=hp_var,
                spd_var=spd_var,
                swim_var=swim_var,
                ally_var=ally_var,
                mode_var=mode_var,
                spec=spec,
            )
            group_rows.append(row)
            apply_monster_defaults(spec, hp_var, spd_var, swim_var, dex_var)
            _regrid_groups()

        def selected_spec() -> Optional[MonsterSpec]:
            selection = library_list.curselection()
            if not selection:
                return None
            raw = library_list.get(selection[0])
            name = str(raw).split(" | ")[0].strip()
            return self._monsters_by_name.get(name)

        def open_info_for_selected() -> None:
            spec = selected_spec()
            if spec is None:
                messagebox.showinfo("Monster Info", "Select a creature from the list first.")
                return
            spec = self._load_monster_details(spec.name) or spec
            self._open_monster_stat_block(spec)

        info_btn.configure(command=open_info_for_selected)

        def populate_groups_from_selection() -> None:
            spec = selected_spec()
            if spec is None:
                return
            add_group(spec=spec, name=spec.name)

        add_group()

        def set_list_values(values: list[str]) -> None:
            library_list.delete(0, tk.END)
            for value in values:
                library_list.insert(tk.END, value)

        def list_items_for_specs(specs: List[MonsterSpec]) -> List[str]:
            items: List[str] = []
            for spec in specs:
                cr_txt = self._monster_cr_display(spec)
                hp_txt = "?" if spec.hp is None else str(spec.hp)
                spd_txt = "?" if spec.speed is None else str(spec.speed)
                items.append(f"{spec.name} | {spec.mtype} | CR {cr_txt} | HP {hp_txt} | Spd {spd_txt}")
            return items

        def refresh_library_list() -> None:
            specs = list(self._monster_specs)
            search = filter_var.get().strip().lower()
            if search:
                specs = [
                    s
                    for s in specs
                    if search in s.name.lower() or search in (s.mtype.lower() if s.mtype else "")
                ]
            sort_by = sort_var.get().strip().lower()
            if sort_by == "type":
                specs.sort(key=lambda s: (s.mtype.lower() if s.mtype else "", s.name.lower()))
            elif sort_by == "cr":
                specs.sort(key=lambda s: (s.cr is None, float(s.cr or 0), s.name.lower()))
            elif sort_by == "hp":
                specs.sort(key=lambda s: (s.hp is None, int(s.hp or 0), s.name.lower()))
            elif sort_by == "speed":
                specs.sort(key=lambda s: (s.speed is None, int(s.speed or 0), s.name.lower()))
            else:
                specs.sort(key=lambda s: s.name.lower())
            set_list_values(list_items_for_specs(specs))

        filter_var.trace_add("write", lambda *_args: refresh_library_list())
        sort_var.trace_add("write", lambda *_args: refresh_library_list())
        library_list.bind("<Double-1>", lambda _e: populate_groups_from_selection())

        loading_label = ttk.Label(left, text="Loading…")
        loading_label.grid(row=5, column=0, sticky="w", pady=(6, 0))

        def on_indexes_loaded() -> None:
            if not library_list.winfo_exists():
                return
            refresh_library_list()
            if loading_label.winfo_exists():
                loading_label.destroy()

        self._load_indexes_async(on_indexes_loaded)

        add_group_btn = ttk.Button(right, text="Add group", command=add_group)
        add_group_btn.grid(row=4, column=0, sticky="w", pady=(8, 0))

        def on_add():
            base_name = base_name_var.get().strip()
            if not group_rows:
                messagebox.showerror("Input error", "Add at least one group.")
                return
            for row in group_rows:
                base = row["name_var"].get().strip() or base_name
                if not base:
                    messagebox.showerror("Input error", "Each group needs a name (or provide a Base Name).")
                    return
                try:
                    count = int(row["count_var"].get().strip())
                    if count <= 0:
                        raise ValueError()
                except ValueError:
                    messagebox.showerror("Input error", f"Count must be a positive integer for {base}.")
                    return

                dex_txt = row["dex_var"].get().strip()
                if dex_txt == "":
                    dex = 0
                    dex_opt: Optional[int] = None
                else:
                    try:
                        dex = int(dex_txt)
                        dex_opt = dex
                    except ValueError:
                        messagebox.showerror("Input error", f"Dex must be an integer for {base}.")
                        return

                hp_txt = row["hp_var"].get().strip()
                if hp_txt == "":
                    hp = 0
                else:
                    try:
                        hp = int(hp_txt)
                    except ValueError:
                        messagebox.showerror("Input error", f"HP must be an integer for {base}.")
                        return

                spd_txt = row["spd_var"].get().strip()
                if spd_txt == "":
                    speed = 30
                else:
                    try:
                        speed = int(spd_txt)
                    except ValueError:
                        messagebox.showerror("Input error", f"Speed must be an integer for {base}.")
                        return

                swim_txt = row["swim_var"].get().strip()
                if swim_txt == "":
                    swim_speed = 0
                else:
                    try:
                        swim_speed = int(swim_txt)
                    except ValueError:
                        messagebox.showerror("Input error", f"Swim speed must be an integer for {base}.")
                        return

                movement_mode = str(row["mode_var"].get() or MOVEMENT_MODE_LABELS["normal"])
                ally_flag = bool(row["ally_var"].get())
                spec = row.get("spec")
                if spec is not None:
                    spec = self._load_monster_details(spec.name) or spec
                saving_throws = dict(spec.saving_throws) if spec and spec.saving_throws else None
                ability_mods = dict(spec.ability_mods) if spec and spec.ability_mods else None

                for i in range(1, count + 1):
                    roll = random.randint(1, 20)
                    total = roll + dex
                    name = base if count == 1 else f"{base} {i}"
                    cid = self._create_combatant(
                        name=name,
                        hp=hp,
                        speed=speed,
                        swim_speed=swim_speed,
                        movement_mode=movement_mode,
                        initiative=total,
                        dex=dex_opt,
                        ally=ally_flag,
                        saving_throws=saving_throws,
                        ability_mods=ability_mods,
                        monster_spec=spec,
                    )
                    c = self.combatants[cid]
                    c.roll = roll
                    c.nat20 = (roll == 20)

            self._rebuild_table(scroll_to_current=True)
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=6, pady=(10, 0), sticky="e")
        ttk.Button(btns, text="Roll & Add", command=on_add).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT)

    # -------------------------- Damage tool --------------------------

    def _open_damage_tool(
        self,
        attacker_cid: Optional[int] = None,
        target_cid: Optional[int] = None,
    ) -> None:
        """Open the Damage tool.

        This dialog supports:
        - Multiple entries (one per target by default if multiple rows are selected)
        - Math expressions in Amount (e.g. 10+10+10)
        - Multiple damage components per entry (amount + type)
        - Per-entry resist + immune
        - Optional attacker (blank attacker = anonymous)
        - Optional attacker/target prefill for map-mode interactions
        """
        dlg = tk.Toplevel(self)
        dlg.title("Damage")
        dlg.geometry("1120x720")
        dlg.minsize(920, 600)
        dlg.transient(self)

        outer = ttk.Frame(dlg, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # Labels used for Comboboxes (include [#cid] suffix so duplicates are unambiguous).
        labels = self._target_labels()
        attacker_default = ""
        if attacker_cid is not None and attacker_cid in self.combatants:
            attacker_default = self._label_for(self.combatants[attacker_cid])
        elif getattr(self, "current_cid", None) is not None and self.current_cid in self.combatants:
            attacker_default = self._label_for(self.combatants[self.current_cid])
        elif labels:
            attacker_default = labels[0]

        # Determine default targets:
        # - If user has multiple selection, create one entry per selected target (in display order)
        # - Else, use current single selection (if any), otherwise first in list
        selected = self._selected_cids()
        ordered_sel: list[int] = []
        if target_cid is not None and target_cid in self.combatants:
            ordered_sel = [target_cid]
        elif selected:
            want = set(selected)
            for c in self._display_order():
                if c.cid in want:
                    ordered_sel.append(c.cid)
            for cid in selected:
                if cid not in ordered_sel:
                    ordered_sel.append(cid)

        if not ordered_sel:
            # fall back to tree selection (single)
            target_default = labels[0] if labels else ""
            if self.tree.selection():
                try:
                    cid = int(self.tree.selection()[0])
                    if cid in self.combatants:
                        target_default = self._label_for(self.combatants[cid])
                except Exception:
                    pass
            ordered_sel = [self._cid_from_label(target_default)] if target_default else []
            ordered_sel = [cid for cid in ordered_sel if cid is not None and cid in self.combatants]

        # ---- Top options ----
        top = ttk.Frame(outer)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Tip: Amount supports math (10+10+10). Blank Attacker = anonymous log.").pack(
            side=tk.LEFT
        )

        # ---- Scrollable entries area ----
        entries_box = ttk.LabelFrame(outer, text="Entries", padding=8)
        entries_box.pack(fill=tk.BOTH, expand=True, pady=(10, 8))

        # Scroll container
        cont = ttk.Frame(entries_box)
        cont.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(cont, highlightthickness=0)
        vbar = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_config(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_config(evt):
            # Make the inner frame match canvas width for nicer resizing
            try:
                canvas.itemconfigure(inner_id, width=evt.width)
            except Exception:
                pass

        inner.bind("<Configure>", _on_inner_config)
        canvas.bind("<Configure>", _on_canvas_config)

        headers = ["Attacker", "Target", "Damage (Amount + Type)", "Resist", "Immune", "Crit", "", ""]
        for col, h in enumerate(headers):
            ttk.Label(inner, text=h).grid(row=0, column=col, sticky="w", padx=(0, 8))

        damage_types = [
            "",
            "Acid",
            "Bludgeoning",
            "Cold",
            "Fire",
            "Force",
            "Lightning",
            "Necrotic",
            "Piercing",
            "Poison",
            "Psychic",
            "Radiant",
            "Slashing",
            "Thunder",
        ]

        # Combobox values (include a blank "none" option for attacker)
        attacker_values = [""] + (labels or [])

        rows: list[dict] = []

        def _parse_name_from_label(lbl: str) -> Optional[str]:
            lbl = (lbl or "").strip()
            if not lbl:
                return None
            cid = self._cid_from_label(lbl)
            if cid is not None and cid in self.combatants:
                return self.combatants[cid].name
            # For external strings like "Goblin"
            return lbl.split(" [#")[0].strip()

        def _regrid() -> None:
            for i, row in enumerate(rows, start=1):
                r = i
                row["attacker_combo"].grid(row=r, column=0, sticky="we", padx=(0, 8), pady=2)
                row["target_combo"].grid(row=r, column=1, sticky="we", padx=(0, 8), pady=2)
                row["components_frame"].grid(row=r, column=2, sticky="we", padx=(0, 8), pady=2)
                row["res_cb"].grid(row=r, column=3, sticky="w", padx=(0, 8), pady=2)
                row["imm_cb"].grid(row=r, column=4, sticky="w", padx=(0, 8), pady=2)
                row["crit_cb"].grid(row=r, column=5, sticky="w", padx=(0, 8), pady=2)
                row["add_damage_btn"].grid(row=r, column=6, sticky="w", padx=(0, 8), pady=2)
                row["rm_btn"].grid(row=r, column=7, sticky="e", pady=2)

            # Stretch columns
            inner.columnconfigure(0, weight=2)
            inner.columnconfigure(1, weight=2)
            inner.columnconfigure(2, weight=3)
            inner.columnconfigure(3, weight=1)
            inner.columnconfigure(4, weight=1)
            inner.columnconfigure(5, weight=1)

        def add_entry(target_label: str = "", attacker_label: str = "") -> None:
            atk_var = tk.StringVar(value=attacker_label)
            tgt_var = tk.StringVar(value=target_label)
            res_var = tk.BooleanVar(value=False)
            imm_var = tk.BooleanVar(value=False)
            crit_var = tk.BooleanVar(value=False)

            attacker_combo = ttk.Combobox(
                inner, textvariable=atk_var, values=attacker_values, state=("readonly" if attacker_values else "disabled")
            )
            target_combo = ttk.Combobox(
                inner, textvariable=tgt_var, values=(labels or []), state=("readonly" if labels else "disabled")
            )
            components_frame = ttk.Frame(inner)
            components_frame.columnconfigure(0, weight=1)
            components_frame.columnconfigure(1, weight=1)
            res_cb = ttk.Checkbutton(inner, text="", variable=res_var)
            imm_cb = ttk.Checkbutton(inner, text="", variable=imm_var)
            crit_cb = ttk.Checkbutton(inner, text="", variable=crit_var)

            def remove_this():
                if len(rows) <= 1:
                    # keep one row; just clear
                    atk_var.set(attacker_default)
                    tgt_var.set("")
                    for comp in row["components"][1:]:
                        for w in (comp["amt_entry"], comp["dtype_combo"]):
                            try:
                                w.destroy()
                            except Exception:
                                pass
                    row["components"] = row["components"][:1]
                    if row["components"]:
                        row["components"][0]["amt_var"].set("")
                        row["components"][0]["dtype_var"].set("")
                    res_var.set(False)
                    imm_var.set(False)
                    crit_var.set(False)
                    return
                for comp in row["components"]:
                    for w in (comp["amt_entry"], comp["dtype_combo"]):
                        try:
                            w.destroy()
                        except Exception:
                            pass
                for w in (attacker_combo, target_combo, components_frame, res_cb, imm_cb, crit_cb, add_damage_btn, rm_btn):
                    try:
                        w.destroy()
                    except Exception:
                        pass
                try:
                    rows.remove(row)
                except ValueError:
                    pass
                _regrid()

            rm_btn = ttk.Button(inner, text="Keelhaul", command=remove_this)

            def add_component(amount: str = "", dtype: str = "") -> None:
                comp_row = len(row["components"])
                amt_var = tk.StringVar(value=amount)
                dtype_var = tk.StringVar(value=dtype)
                amt_entry = ttk.Entry(components_frame, textvariable=amt_var, width=10)
                dtype_combo = ttk.Combobox(
                    components_frame, textvariable=dtype_var, values=damage_types, state="readonly", width=14
                )
                amt_entry.grid(row=comp_row, column=0, sticky="we", padx=(0, 6), pady=1)
                dtype_combo.grid(row=comp_row, column=1, sticky="we", pady=1)
                row["components"].append(
                    dict(
                        amt_var=amt_var,
                        dtype_var=dtype_var,
                        amt_entry=amt_entry,
                        dtype_combo=dtype_combo,
                    )
                )

            add_damage_btn = ttk.Button(inner, text="Add damage type", command=add_component)

            row = dict(
                attacker_var=atk_var,
                target_var=tgt_var,
                resistant_var=res_var,
                immune_var=imm_var,
                crit_var=crit_var,
                attacker_combo=attacker_combo,
                target_combo=target_combo,
                components_frame=components_frame,
                components=[],
                res_cb=res_cb,
                imm_cb=imm_cb,
                crit_cb=crit_cb,
                add_damage_btn=add_damage_btn,
                rm_btn=rm_btn,
            )
            rows.append(row)
            add_component()
            _regrid()

        # Create default entries
        if ordered_sel:
            for cid in ordered_sel:
                if cid in self.combatants:
                    add_entry(target_label=self._label_for(self.combatants[cid]), attacker_label=attacker_default)
        else:
            add_entry(target_label=(labels[0] if labels else ""), attacker_label=attacker_default)

        # ---- Add entry button (below list) ----
        add_row = ttk.Frame(outer)
        add_row.pack(fill=tk.X)

        def on_add():
            add_entry(target_label="", attacker_label=attacker_default)
            try:
                if rows[-1]["components"]:
                    rows[-1]["components"][0]["amt_entry"].focus_set()
            except Exception:
                pass

        ttk.Button(add_row, text="Add another hit", command=on_add).pack(side=tk.LEFT)

        close_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(add_row, text="Close after apply", variable=close_after).pack(side=tk.RIGHT)

        # ---- Bottom action buttons ----
        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))

        # Make a red-ish button using tk.Button for reliable background color
        def _apply():
            removed_all: list[int] = []
            pre_order = [x.cid for x in self._display_order()]

            if not rows:
                return

            for idx, row in enumerate(rows, start=1):
                # Resolve target
                cid = self._cid_from_label(row["target_var"].get())
                if cid is None or cid not in self.combatants:
                    messagebox.showerror("Damage", f"Row {idx}: pick a valid target.", parent=dlg)
                    return

                components: list[dict] = []
                for comp in row["components"]:
                    amt_text = comp["amt_var"].get().strip()
                    dtype = (comp["dtype_var"].get() or "").strip()
                    if not amt_text and not dtype:
                        continue
                    if not amt_text:
                        messagebox.showerror(
                            "Damage",
                            f"Row {idx}: Amount must be a number or a small math expression (e.g. 10+10+10).",
                            parent=dlg,
                        )
                        return
                    try:
                        amt = self._parse_int_expr(amt_text)
                    except Exception:
                        messagebox.showerror(
                            "Damage",
                            f"Row {idx}: Amount must be a number or a small math expression (e.g. 10+10+10).",
                            parent=dlg,
                        )
                        return
                    if amt < 0:
                        messagebox.showerror("Damage", f"Row {idx}: Amount must be positive.", parent=dlg)
                        return
                    components.append(dict(amount=amt, dtype=dtype))

                if not components:
                    messagebox.showerror("Damage", f"Row {idx}: add at least one damage component.", parent=dlg)
                    return

                c = self.combatants.get(cid)
                if c is None:
                    continue

                target_name = c.name
                attacker_label = row["attacker_var"].get()
                attacker_name = _parse_name_from_label(attacker_label)
                attacker_cid = self._cid_from_label(attacker_label) if attacker_label else None
                resist_note = ""
                imm_note = ""
                base_components = []
                applied_components = []
                total_applied = 0
                for comp in components:
                    dtype_display = comp["dtype"].lower() if comp["dtype"] else "untyped"
                    base_components.append(f"{comp['amount']} {dtype_display}")
                    applied = comp["amount"]
                    if row["resistant_var"].get():
                        applied = applied // 2
                    total_applied += int(applied)
                    applied_components.append(f"{applied} {dtype_display}")
                crit_suffix = " Critical Hit!" if row["crit_var"].get() and total_applied > 0 else ""

                component_summary = " + ".join(base_components)
                applied_summary = " + ".join(applied_components)

                if row["immune_var"].get():
                    imm_note = " (immune)"
                    if attacker_name:
                        if component_summary:
                            self._log(
                                f"{attacker_name} tries to deal {component_summary} damage to {target_name}, but {target_name} is immune.{imm_note}"
                            )
                        else:
                            self._log(f"{attacker_name} tries to deal damage to {target_name}, but {target_name} is immune.{imm_note}")
                    else:
                        if component_summary:
                            self._log(f"Damage to {target_name} was blocked — immune to {component_summary}.{imm_note}")
                        else:
                            self._log(f"Damage to {target_name} was blocked — immune.{imm_note}")
                    continue

                if row["resistant_var"].get():
                    resist_note = " (resistant)"

                old_hp = int(c.hp)
                c.hp = max(0, old_hp - int(total_applied))
                if total_applied > 0 and int(c.hp) < old_hp:
                    self._queue_concentration_save(c, "damage")

                # If they died from above 0 -> 0, log flavor and remove
                if old_hp > 0 and int(c.hp) == 0:
                    dtype_flavor = components[0]["dtype"] if len(components) == 1 else ""
                    flavor = self._death_flavor_line(attacker_name, total_applied, dtype_flavor, target_name) + crit_suffix
                    self._log(flavor)
                    lan = getattr(self, "_lan", None)
                    if lan:
                        lan.play_ko(attacker_cid)
                    self.combatants.pop(cid, None)
                    removed_all.append(cid)
                else:
                    summary = applied_summary if row["resistant_var"].get() else component_summary
                    if attacker_name:
                        self._log(f"{attacker_name} deals {summary} damage to {target_name}{resist_note}{crit_suffix}")
                    else:
                        self._log(f"{target_name} takes {summary} damage{resist_note}{crit_suffix}")

            if removed_all:
                if getattr(self, "start_cid", None) in removed_all:
                    self.start_cid = None
                self._retarget_current_after_removal(removed_all, pre_order=pre_order)

            self._rebuild_table(scroll_to_current=True)

            if close_after.get():
                dlg.destroy()

        act_btn = tk.Button(bottom, text="Deal damage", command=_apply, bg="#8b1e1e", fg="white", padx=14, pady=6)
        act_btn.pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        _apply_dialog_geometry(dlg, 1120, 720, 920, 600)

        # Focus first amount entry
        try:
            if rows[0]["components"]:
                rows[0]["components"][0]["amt_entry"].focus_set()
        except Exception:
            pass

    # -------------------------- Heal tool --------------------------
    def _open_heal_tool(self) -> None:
        """Open the Heal tool."""
        dlg = tk.Toplevel(self)
        dlg.title("Heal")
        dlg.geometry("920x620")
        dlg.minsize(840, 520)
        dlg.transient(self)

        outer = ttk.Frame(dlg, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        labels = self._target_labels()
        attacker_default = ""
        if getattr(self, "current_cid", None) is not None and self.current_cid in self.combatants:
            attacker_default = self._label_for(self.combatants[self.current_cid])
        elif labels:
            attacker_default = labels[0]

        selected = self._selected_cids()
        ordered_sel: list[int] = []
        if selected:
            want = set(selected)
            for c in self._display_order():
                if c.cid in want:
                    ordered_sel.append(c.cid)
            for cid in selected:
                if cid not in ordered_sel:
                    ordered_sel.append(cid)

        if not ordered_sel:
            target_default = labels[0] if labels else ""
            if self.tree.selection():
                try:
                    cid = int(self.tree.selection()[0])
                    if cid in self.combatants:
                        target_default = self._label_for(self.combatants[cid])
                except Exception:
                    pass
            ordered_sel = [self._cid_from_label(target_default)] if target_default else []
            ordered_sel = [cid for cid in ordered_sel if cid is not None and cid in self.combatants]

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Tip: Amount supports math (10+10+10). Blank Attacker = anonymous log.").pack(side=tk.LEFT)

        entries_box = ttk.LabelFrame(outer, text="Entries", padding=8)
        entries_box.pack(fill=tk.BOTH, expand=True, pady=(10, 8))

        cont = ttk.Frame(entries_box)
        cont.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(cont, highlightthickness=0)
        vbar = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_config(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_config(evt):
            try:
                canvas.itemconfigure(inner_id, width=evt.width)
            except Exception:
                pass

        inner.bind("<Configure>", _on_inner_config)
        canvas.bind("<Configure>", _on_canvas_config)

        headers = ["Attacker", "Target", "Heal Amount", ""]
        for col, h in enumerate(headers):
            ttk.Label(inner, text=h).grid(row=0, column=col, sticky="w", padx=(0, 8))

        attacker_values = [""] + (labels or [])

        rows: list[dict] = []

        def _parse_name_from_label(lbl: str) -> Optional[str]:
            lbl = (lbl or "").strip()
            if not lbl:
                return None
            cid = self._cid_from_label(lbl)
            if cid is not None and cid in self.combatants:
                return self.combatants[cid].name
            return lbl.split(" [#")[0].strip()

        def _regrid() -> None:
            for i, row in enumerate(rows, start=1):
                r = i
                row["attacker_combo"].grid(row=r, column=0, sticky="we", padx=(0, 8), pady=2)
                row["target_combo"].grid(row=r, column=1, sticky="we", padx=(0, 8), pady=2)
                row["amount_entry"].grid(row=r, column=2, sticky="we", padx=(0, 8), pady=2)
                row["rm_btn"].grid(row=r, column=3, sticky="e", pady=2)

            inner.columnconfigure(0, weight=2)
            inner.columnconfigure(1, weight=2)
            inner.columnconfigure(2, weight=1)

        def add_entry(target_label: str = "", attacker_label: str = "") -> None:
            atk_var = tk.StringVar(value=attacker_label)
            tgt_var = tk.StringVar(value=target_label)
            amt_var = tk.StringVar()

            attacker_combo = ttk.Combobox(
                inner, textvariable=atk_var, values=attacker_values, state=("readonly" if attacker_values else "disabled")
            )
            target_combo = ttk.Combobox(
                inner, textvariable=tgt_var, values=(labels or []), state=("readonly" if labels else "disabled")
            )
            amount_entry = ttk.Entry(inner, textvariable=amt_var, width=12)

            def remove_this():
                if len(rows) <= 1:
                    atk_var.set(attacker_default)
                    tgt_var.set("")
                    amt_var.set("")
                    return
                for w in (attacker_combo, target_combo, amount_entry, rm_btn):
                    try:
                        w.destroy()
                    except Exception:
                        pass
                try:
                    rows.remove(row)
                except ValueError:
                    pass
                _regrid()

            rm_btn = ttk.Button(inner, text="Keelhaul", command=remove_this)

            row = dict(
                attacker_var=atk_var,
                target_var=tgt_var,
                amount_var=amt_var,
                attacker_combo=attacker_combo,
                target_combo=target_combo,
                amount_entry=amount_entry,
                rm_btn=rm_btn,
            )
            rows.append(row)
            _regrid()

        if ordered_sel:
            for cid in ordered_sel:
                if cid in self.combatants:
                    add_entry(target_label=self._label_for(self.combatants[cid]), attacker_label=attacker_default)
        else:
            add_entry(target_label=(labels[0] if labels else ""), attacker_label=attacker_default)

        add_row = ttk.Frame(outer)
        add_row.pack(fill=tk.X)

        def on_add():
            add_entry(target_label="", attacker_label=attacker_default)
            try:
                rows[-1]["amount_entry"].focus_set()
            except Exception:
                pass

        ttk.Button(add_row, text="Add another heal", command=on_add).pack(side=tk.LEFT)

        temp_hp_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(add_row, text="Temporary HP", variable=temp_hp_mode).pack(side=tk.LEFT, padx=(10, 0))

        close_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(add_row, text="Close after apply", variable=close_after).pack(side=tk.RIGHT)

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))

        def _apply():
            if not rows:
                return

            for idx, row in enumerate(rows, start=1):
                cid = self._cid_from_label(row["target_var"].get())
                if cid is None or cid not in self.combatants:
                    messagebox.showerror("Heal", f"Row {idx}: pick a valid target.", parent=dlg)
                    return

                amt_text = row["amount_var"].get().strip()
                if not amt_text:
                    messagebox.showerror(
                        "Heal",
                        f"Row {idx}: Amount must be a number or a small math expression (e.g. 10+10+10).",
                        parent=dlg,
                    )
                    return
                try:
                    amt = self._parse_int_expr(amt_text)
                except Exception:
                    messagebox.showerror(
                        "Heal",
                        f"Row {idx}: Amount must be a number or a small math expression (e.g. 10+10+10).",
                        parent=dlg,
                    )
                    return
                if amt < 0:
                    messagebox.showerror("Heal", f"Row {idx}: Amount must be positive.", parent=dlg)
                    return

                if not self._apply_heal_to_combatant(cid, amt, is_temp_hp=temp_hp_mode.get()):
                    continue

                c = self.combatants.get(cid)
                if c is None:
                    continue
                target_name = c.name
                attacker_label = row["attacker_var"].get()
                attacker_name = _parse_name_from_label(attacker_label)

                if temp_hp_mode.get():
                    if attacker_name:
                        self._log(f"{attacker_name} grants {target_name} {amt} temp HP")
                    else:
                        self._log(f"{target_name} gains {amt} temp HP")
                else:
                    if attacker_name:
                        self._log(f"{attacker_name} heals {target_name} for {amt} HP")
                    else:
                        self._log(f"{target_name} heals {amt} HP")

            self._rebuild_table(scroll_to_current=True)

            if close_after.get():
                dlg.destroy()

        act_btn = tk.Button(bottom, text="Apply heal", command=_apply, bg="#2d7d46", fg="white", padx=14, pady=6)
        act_btn.pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        _apply_dialog_geometry(dlg, 920, 620, 840, 520)

        try:
            if rows:
                rows[0]["amount_entry"].focus_set()
        except Exception:
            pass

    # -------------------------- Conditions tool --------------------------
    def _open_condition_tool(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Conditions (2024)")
        dlg.geometry("1040x720")
        dlg.minsize(880, 620)
        dlg.transient(self)

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        sel_cids = self._selected_cids()
        if not sel_cids:
            ttk.Label(frm, text="Select 1+ creatures in the table first.").pack(anchor="w")
        else:
            names = ", ".join(self.combatants[cid].name for cid in sel_cids if cid in self.combatants)
            ttk.Label(frm, text=f"Target(s): {names}").pack(anchor="w")

        # --- Set a condition (non-stacking; overwrites duration if already present) ---
        set_box = ttk.LabelFrame(frm, text="Set condition (doesn't stack)", padding=8)
        set_box.pack(fill=tk.X, pady=(10, 0))

        cond_keys = [k for k in CONDITIONS_META.keys() if k not in {"exhaustion", "star_advantage", "dot"}]
        cond_labels = [str(CONDITIONS_META[k]["label"]) for k in cond_keys]

        cond_var = tk.StringVar(value=(cond_labels[0] if cond_labels else ""))
        ttk.Label(set_box, text="Condition").grid(row=0, column=0, sticky="w")
        ttk.Combobox(set_box, textvariable=cond_var, values=cond_labels, state="readonly", width=22).grid(
            row=1, column=0, sticky="w", padx=(0, 10)
        )

        turns_var = tk.StringVar(value="1")
        ttk.Label(set_box, text="Turns (0=indef)").grid(row=0, column=1, sticky="w")
        ttk.Entry(set_box, textvariable=turns_var, width=10).grid(row=1, column=1, sticky="w", padx=(0, 10))

        def resolve_key(label: str) -> Optional[str]:
            for k in cond_keys:
                if str(CONDITIONS_META[k]["label"]) == label:
                    return k
            return None

        def apply_condition():
            if not sel_cids:
                messagebox.showerror("Conditions", "Select 1+ creatures first.", parent=dlg)
                return
            ckey = resolve_key(cond_var.get())
            if not ckey:
                messagebox.showerror("Conditions", "Pick a condition.", parent=dlg)
                return
            ttxt = turns_var.get().strip()
            try:
                t = int(ttxt)
            except ValueError:
                messagebox.showerror("Conditions", "Turns must be an integer (0=indef).", parent=dlg)
                return
            remaining = None if t == 0 else max(1, t)

            for cid in sel_cids:
                if cid not in self.combatants:
                    continue
                c = self.combatants[cid]
                # non-stacking: remove existing of same type
                c.condition_stacks = [st for st in c.condition_stacks if st.ctype != ckey]
                st = ConditionStack(sid=self._next_stack_id, ctype=ckey, remaining_turns=remaining)
                self._next_stack_id += 1
                c.condition_stacks.append(st)
                lab = str(CONDITIONS_META.get(ckey, {}).get("label", ckey))
                if remaining is None:
                    self._log(f"set condition: {lab} (indef)", cid=cid)
                else:
                    self._log(f"set condition: {lab} ({remaining} turn(s))", cid=cid)

            self._rebuild_table(scroll_to_current=True)

        ttk.Button(set_box, text="Apply", command=apply_condition).grid(row=1, column=2, sticky="w")

        # --- Star Advantage ---
        star_box = ttk.LabelFrame(frm, text="Star Advantage", padding=8)
        star_box.pack(fill=tk.X, pady=(10, 0))

        star_turns_var = tk.StringVar(value="1")
        ttk.Label(star_box, text="Turns (0=indef)").grid(row=0, column=0, sticky="w")
        ttk.Entry(star_box, textvariable=star_turns_var, width=10).grid(row=1, column=0, sticky="w", padx=(0, 10))

        def apply_star_advantage():
            if not sel_cids:
                messagebox.showerror("Star Advantage", "Select 1+ creatures first.", parent=dlg)
                return
            try:
                t = int(star_turns_var.get().strip())
            except ValueError:
                messagebox.showerror("Star Advantage", "Turns must be an integer (0=indef).", parent=dlg)
                return
            remaining = None if t == 0 else max(1, t)
            for cid in sel_cids:
                if cid not in self.combatants:
                    continue
                c = self.combatants[cid]
                c.condition_stacks = [st for st in c.condition_stacks if st.ctype != "star_advantage"]
                st = ConditionStack(sid=self._next_stack_id, ctype="star_advantage", remaining_turns=remaining)
                self._next_stack_id += 1
                c.condition_stacks.append(st)
                if remaining is None:
                    self._log("set Star Advantage (indef)", cid=cid)
                else:
                    self._log(f"set Star Advantage ({remaining} turn(s))", cid=cid)
            self._rebuild_table(scroll_to_current=True)

        ttk.Button(star_box, text="Apply", command=apply_star_advantage).grid(row=1, column=1, sticky="w")

        # --- Damage over Time ---
        dot_box = ttk.LabelFrame(frm, text="Damage over Time (DoT)", padding=8)
        dot_box.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(dot_box, text="Type").grid(row=0, column=0, sticky="w")
        dot_type_var = tk.StringVar(value="burn")
        ttk.Combobox(dot_box, textvariable=dot_type_var, values=list(DOT_META.keys()), state="readonly", width=12).grid(
            row=1, column=0, sticky="w", padx=(0, 10)
        )

        ttk.Label(dot_box, text="Turns").grid(row=0, column=1, sticky="w")
        dot_turns_var = tk.StringVar(value="1")
        ttk.Entry(dot_box, textvariable=dot_turns_var, width=6).grid(row=1, column=1, sticky="w", padx=(0, 10))

        dice_frame = ttk.Frame(dot_box)
        dice_frame.grid(row=1, column=2, sticky="w")
        dice_vars: Dict[int, tk.IntVar] = {}
        col = 0
        for die in [4, 6, 8, 10, 12]:
            v = tk.IntVar(value=0)
            dice_vars[die] = v
            ttk.Label(dice_frame, text=f"d{die}").grid(row=0, column=col, sticky="w")
            ttk.Spinbox(dice_frame, from_=0, to=9, width=5, textvariable=v).grid(row=1, column=col, padx=(0, 8))
            col += 1

        def apply_dot():
            if not sel_cids:
                messagebox.showerror("DoT", "Select 1+ creatures first.", parent=dlg)
                return
            try:
                turns = int(dot_turns_var.get().strip())
                if turns <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("DoT", "Turns must be a positive integer.", parent=dlg)
                return
            dice: Dict[int, int] = {die: int(v.get()) for die, v in dice_vars.items() if int(v.get()) > 0}
            if not dice:
                messagebox.showerror("DoT", "Pick at least one die.", parent=dlg)
                return
            dtype = dot_type_var.get().strip()
            for cid in sel_cids:
                if cid not in self.combatants:
                    continue
                c = self.combatants[cid]
                st = ConditionStack(
                    sid=self._next_stack_id,
                    ctype="dot",
                    remaining_turns=turns,
                    dot_type=dtype,
                    dice=dice.copy(),
                )
                self._next_stack_id += 1
                c.condition_stacks.append(st)
                lab = DOT_META.get(dtype, {}).get("label", dtype)
                self._log(f"set DoT {lab} ({turns} turn(s))", cid=cid)
            self._rebuild_table(scroll_to_current=True)

        ttk.Button(dot_box, text="Apply", command=apply_dot).grid(row=1, column=3, sticky="w", padx=(10, 0))

        # --- Exhaustion level (stacks by level) ---
        exh_box = ttk.LabelFrame(frm, text="Exhaustion (level)", padding=8)
        exh_box.pack(fill=tk.X, pady=(10, 0))

        exh_var = tk.StringVar(value="0")
        ttk.Label(exh_box, text="Set level (0-6)").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(exh_box, from_=0, to=6, width=6, textvariable=exh_var).grid(row=1, column=0, sticky="w", padx=(0, 10))

        def set_exhaustion():
            if not sel_cids:
                messagebox.showerror("Conditions", "Select 1+ creatures first.", parent=dlg)
                return
            try:
                lvl = int(exh_var.get().strip())
            except ValueError:
                messagebox.showerror("Conditions", "Exhaustion must be 0-6.", parent=dlg)
                return
            lvl = max(0, min(6, lvl))
            for cid in sel_cids:
                if cid in self.combatants:
                    self.combatants[cid].exhaustion_level = lvl
                    self._log(f"set exhaustion level to {lvl}", cid=cid)
            self._rebuild_table(scroll_to_current=True)

        ttk.Button(exh_box, text="Set", command=set_exhaustion).grid(row=1, column=1, sticky="w")

        # --- If exactly one target, show and allow removing existing effects ---
        if len(sel_cids) == 1 and sel_cids[0] in self.combatants:
            cid = sel_cids[0]
            c = self.combatants[cid]
            lst_box = ttk.LabelFrame(frm, text="Current (double-click to remove)", padding=8)
            lst_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

            lb = tk.Listbox(lst_box, height=10)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb = ttk.Scrollbar(lst_box, orient="vertical", command=lb.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            lb.configure(yscrollcommand=sb.set)

            rows: List[Tuple[str, int]] = []  # (kind, sid)

            def format_dice(dice: Optional[Dict[int, int]]) -> str:
                if not dice:
                    return ""
                parts = []
                for die in sorted(dice.keys()):
                    cnt = int(dice[die])
                    if cnt <= 0:
                        continue
                    parts.append(f"{cnt}d{die}")
                return "+".join(parts)

            def refresh_list():
                nonlocal rows
                rows = []
                lb.delete(0, tk.END)
                for st in sorted(c.condition_stacks, key=lambda x: x.ctype):
                    if st.ctype == "dot":
                        dtype = st.dot_type or "dot"
                        lab = DOT_META.get(dtype, {}).get("label", dtype)
                        dice_str = format_dice(st.dice)
                        turns = "indef" if st.remaining_turns is None else f"{st.remaining_turns}t"
                        txt = f"[C:{st.sid}] DoT {lab} ({dice_str or 'dice?'}; {turns})"
                    else:
                        lab = str(CONDITIONS_META.get(st.ctype, {}).get("label", st.ctype))
                        if st.remaining_turns is None:
                            txt = f"[C:{st.sid}] {lab} (indef)"
                        else:
                            txt = f"[C:{st.sid}] {lab} ({st.remaining_turns})"
                    lb.insert(tk.END, txt)
                    rows.append(("cond", st.sid))
                if c.exhaustion_level > 0:
                    lb.insert(tk.END, f"[E] Exhaustion level {c.exhaustion_level}")

            def remove_selected(_evt=None):
                sel = lb.curselection()
                if not sel:
                    return
                txt = lb.get(sel[0])
                if txt.startswith("[E]"):
                    c.exhaustion_level = 0
                    self._log("cleared exhaustion", cid=cid)
                    refresh_list()
                    self._rebuild_table(scroll_to_current=True)
                    return
                try:
                    sid = int(txt.split(":")[1].split("]")[0])
                except Exception:
                    return
                if txt.startswith("[C:"):
                    # remove condition by sid
                    for st in list(c.condition_stacks):
                        if st.sid == sid:
                            lab = str(CONDITIONS_META.get(st.ctype, {}).get("label", st.ctype))
                            c.condition_stacks.remove(st)
                            self._log(f"removed condition: {lab}", cid=cid)
                            break
                refresh_list()
                self._rebuild_table(scroll_to_current=True)

            lb.bind("<Double-Button-1>", remove_selected)
            refresh_list()

        btns = ttk.Frame(frm)
        btns.pack(anchor="e", pady=(10, 0))
        ttk.Button(btns, text="Close", command=dlg.destroy).pack(side=tk.LEFT)

        _apply_dialog_geometry(dlg, 1040, 720, 880, 620)


    def _selected_cids(self) -> List[int]:
        items = self.tree.selection()
        out: List[int] = []
        for it in items:
            try:
                cid = int(it)
            except ValueError:
                continue
            if cid in self.combatants:
                out.append(cid)
        return out




class BattleMapWindow(tk.Toplevel):
    """A simple grid battle map with draggable unit tokens and AoE overlays."""

    def __init__(self, app: InitiativeTracker) -> None:
        super().__init__(app)
        self.app = app
        self.title("Map Mode")
        self.geometry("980x720")
        self.minsize(720, 520)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Map size prompt
        size = self._prompt_map_size()
        if size is None:
            self.after(0, self.destroy)
            return
        self.cols, self.rows = size  # squares
        self.feet_per_square = 5

        # Map rendering controls
        self._map_margin = 24  # pixels of padding around the grid
        self.zoom_var = tk.DoubleVar(value=32.0)  # pixels per square (5 ft)
        self.obstacle_mode_var = tk.BooleanVar(value=False)
        self.obstacle_erase_var = tk.BooleanVar(value=False)
        self.obstacle_brush_var = tk.IntVar(value=1)
        self.obstacle_single_var = tk.BooleanVar(value=False)
        self.rough_mode_var = tk.BooleanVar(value=False)
        self.rough_erase_var = tk.BooleanVar(value=False)
        self.rough_color_var = tk.StringVar()
        self.rough_color_hex_var = tk.StringVar()
        self.show_all_names_var = tk.BooleanVar(value=False)
        self.dm_move_var = tk.BooleanVar(value=False)
        self.damage_mode_var = tk.BooleanVar(value=False)
        self._last_roster_sig: Optional[Tuple[int, ...]] = None
        self._poll_after_id: Optional[str] = None

        # Grid layout metrics
        self.cell = 32.0
        self.x0 = 0.0
        self.y0 = 0.0

        # Units and overlays
        self.unit_tokens: Dict[int, Dict[str, object]] = {}  # cid -> {col,row,oval,text,marker}
        self._active_cid: Optional[int] = None
        self.obstacles: Set[Tuple[int, int]] = set()  # blocked squares
        self._obstacle_history: List[Set[Tuple[int, int]]] = []
        self._drawing_obstacles: bool = False
        self.rough_terrain: Dict[Tuple[int, int], Dict[str, object]] = {}
        self._drawing_rough: bool = False
        self._suspend_lan_sync: bool = False
        self._map_dirty: bool = False

        # Grouping: multiple units can occupy the same square. We show a single group label and fan the tokens slightly.
        self._cell_to_cids: Dict[Tuple[int, int], List[int]] = {}
        self._group_cells_index: List[Tuple[int, int]] = []
        self._group_members_index: List[int] = []
        self._selected_group_cell: Optional[Tuple[int, int]] = None
        self._group_preferred_cid: Optional[int] = None
        self._suspend_group_ui: bool = False

        # Move-range highlight for the active creature
        self._movehl_items: List[int] = []

        # Auto-placement offsets near the map center (for quick placement)
        self._spawn_offsets: List[Tuple[int, int]] = self._build_spawn_offsets()
        self._spawn_index: int = 0

        # Drag origin (to enforce movement for the active creature)
        self._drag_origin_cell: Optional[Tuple[int, int]] = None

        self._next_aoe_id = 1
        self.aoes: Dict[int, Dict[str, object]] = {}  # aid -> overlay data
        self._selected_aoe: Optional[int] = None
        self._aoe_spell_labels: List[str] = []
        self._aoe_spell_by_label: Dict[str, Dict[str, Any]] = {}
        self._aoe_default_colors = {
            "circle": "#2d4f8a",
            "sphere": "#2d4f8a",
            "cylinder": "#2d4f8a",
            "line": "#2d8a57",
            "wall": "#b57d22",
            "square": "#6b3d8a",
            "cube": "#6b3d8a",
            "cone": "#b56e22",
        }
        self._aoe_fill_colors = {
            "circle": "#a8c5ff",
            "sphere": "#a8c5ff",
            "cylinder": "#a8c5ff",
            "line": "#b7ffe0",
            "wall": "#ffe699",
            "square": "#e2b6ff",
            "cube": "#e2b6ff",
            "cone": "#ffbd6e",
        }
        self._aoe_color_labels: List[str] = []
        self._aoe_color_by_label: Dict[str, str] = {}
        self._aoe_label_by_color: Dict[str, str] = {}
        for name, hex_value in AOE_COLOR_PRESETS:
            label = f"{name} ({hex_value})"
            self._aoe_color_labels.append(label)
            self._aoe_color_by_label[label] = hex_value
            self._aoe_label_by_color[hex_value] = label
        self._rough_color_labels: List[str] = []
        self._rough_preset_by_label: Dict[str, TerrainPreset] = {}
        self._rough_label_by_color: Dict[str, str] = {}
        self._rough_presets: List[TerrainPreset] = list(getattr(self.app, "rough_terrain_presets", []) or [])
        if not self._rough_presets:
            self._rough_presets = _load_rough_terrain_presets()
        for preset in self._rough_presets:
            flags: List[str] = []
            if preset.movement_type == "water":
                flags.append("water")
            if preset.is_rough:
                flags.append("rough")
            flag_label = f" • {', '.join(flags)}" if flags else ""
            label = f"{preset.label} ({preset.color}){flag_label}"
            self._rough_color_labels.append(label)
            self._rough_preset_by_label[label] = preset
            self._rough_label_by_color[preset.color] = label
        self._rough_color_labels.append("Custom")
        default_rough = self._rough_presets[0].color if self._rough_presets else "#8d6e63"
        self.rough_color_var.set(self._rough_label_by_color.get(default_rough, "Custom"))
        self.rough_color_hex_var.set(default_rough)

        # Measurement
        self._measure_start: Optional[Tuple[float, float]] = None
        self._measure_items: List[int] = []
        self._label_bounds: List[Tuple[int, int, int, int]] = []

        # Drag state
        self._drag_kind: Optional[str] = None  # "unit" | "aoe"
        self._drag_id: Optional[int] = None
        self._drag_offset: Tuple[float, float] = (0.0, 0.0)

        # Listbox drag-from-roster state
        self._dragging_from_list: Optional[int] = None
        self._drag_ghost: Optional[tk.Label] = None
        self._hover_tooltip: Optional[tk.Label] = None
        self._hover_tooltip_text: Optional[str] = None

        # Background images
        self._next_bg_id = 1
        self.bg_images: Dict[int, Dict[str, object]] = {}  # bid -> {path,pil,tk,item,x,y,alpha,scale,locked}
        self._selected_bg: Optional[int] = None

        self._build_ui()
        self._apply_lan_map_state()
        try:
            self.refresh_spell_overlays()
        except Exception:
            pass
        self.refresh_units()

        # Keybindings
        self.bind("<Escape>", lambda e: self._clear_measure())
        self.bind("<KeyPress-r>", lambda e: self.refresh_units())
        self.bind("<Control-z>", lambda e: self._undo_obstacle())

        # Auto-refresh units/markers so slain creatures disappear without manual refresh.
        self._start_polling()

    def _apply_lan_map_state(self) -> None:
        redraw_move_highlight = False
        lan_rough = getattr(self.app, "_lan_rough_terrain", None)
        if isinstance(lan_rough, dict):
            loaded_rough: Dict[Tuple[int, int], Dict[str, object]] = {}
            for raw_key, raw_cell in lan_rough.items():
                key: Optional[Tuple[int, int]] = None
                if isinstance(raw_key, str):
                    parts = [part.strip() for part in raw_key.split(",")]
                    if len(parts) == 2:
                        try:
                            key = (int(parts[0]), int(parts[1]))
                        except (TypeError, ValueError):
                            key = None
                elif isinstance(raw_key, (list, tuple)) and len(raw_key) == 2:
                    try:
                        key = (int(raw_key[0]), int(raw_key[1]))
                    except (TypeError, ValueError):
                        key = None
                if key is None:
                    continue
                cell_data = self._rough_cell_data(raw_cell)
                loaded_rough[key] = {
                    "color": cell_data.get("color"),
                    "label": cell_data.get("label"),
                    "movement_type": cell_data.get("movement_type"),
                    "is_swim": bool(cell_data.get("is_swim")),
                    "is_rough": bool(cell_data.get("is_rough")),
                }
            self.rough_terrain = loaded_rough
            self._draw_rough_terrain()
            redraw_move_highlight = True

        lan_obstacles = getattr(self.app, "_lan_obstacles", None)
        if isinstance(lan_obstacles, (set, list, tuple)):
            loaded: Set[Tuple[int, int]] = set()
            for item in lan_obstacles:
                try:
                    col, row = item
                except Exception:
                    continue
                try:
                    loaded.add((int(col), int(row)))
                except Exception:
                    continue
            self.obstacles = loaded
            self._draw_obstacles()
            redraw_move_highlight = True

        if redraw_move_highlight:
            self._update_move_highlight()

    def _on_close(self) -> None:
        try:
            self._stop_polling()
        except Exception:
            pass
        try:
            if getattr(self.app, "_map_window", None) is self:
                self.app._map_window = None
        except Exception:
            pass
        self.destroy()

    def _prompt_map_size(self) -> Optional[Tuple[int, int]]:
        class _MapSizeDialog:
            def __init__(self, parent: tk.Tk | tk.Toplevel) -> None:
                self.result: Optional[Tuple[int, int]] = None
                self._parent = parent
                self._dialog = tk.Toplevel(parent)
                self._dialog.title("Battle Map Size")
                self._dialog.transient(parent)

                self._min = 5
                self._max = 200
                self._cols_var = tk.StringVar(value="20")
                self._rows_var = tk.StringVar(value="20")

                container = ttk.Frame(self._dialog, padding=12)
                container.grid(row=0, column=0, sticky="nsew")
                container.columnconfigure(1, weight=1)

                ttk.Label(container, text="Map width (squares, 5 ft each):").grid(row=0, column=0, sticky="w")
                self._cols_entry = ttk.Entry(container, textvariable=self._cols_var, width=10)
                self._cols_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))

                ttk.Label(container, text="Map height (squares, 5 ft each):").grid(row=1, column=0, sticky="w", pady=(8, 0))
                self._rows_entry = ttk.Entry(container, textvariable=self._rows_var, width=10)
                self._rows_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

                button_row = ttk.Frame(container)
                button_row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
                ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT, padx=(8, 0))
                ttk.Button(button_row, text="OK", command=self._on_ok).pack(side=tk.RIGHT)

                self._dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
                self._dialog.bind("<Return>", lambda _evt: self._on_ok())
                self._dialog.bind("<Escape>", lambda _evt: self._on_cancel())

                self._dialog.update_idletasks()
                self._dialog.wm_attributes("-topmost", True)
                self._dialog.lift()
                self._dialog.focus_force()
                self._dialog.after_idle(lambda: self._dialog.wm_attributes("-topmost", False))

                self._cols_entry.focus_set()
                self._cols_entry.selection_range(0, tk.END)

                self._dialog.wait_window(self._dialog)

            def _parse_value(self, value: str, label: str) -> Optional[int]:
                try:
                    parsed = int(value)
                except ValueError:
                    messagebox.showerror("Battle Map Size", f"{label} must be a whole number.", parent=self._dialog)
                    return None
                if parsed < self._min or parsed > self._max:
                    messagebox.showerror(
                        "Battle Map Size",
                        f"{label} must be between {self._min} and {self._max}.",
                        parent=self._dialog,
                    )
                    return None
                return parsed

            def _on_ok(self) -> None:
                cols = self._parse_value(self._cols_var.get(), "Map width")
                if cols is None:
                    self._cols_entry.focus_set()
                    self._cols_entry.selection_range(0, tk.END)
                    return
                rows = self._parse_value(self._rows_var.get(), "Map height")
                if rows is None:
                    self._rows_entry.focus_set()
                    self._rows_entry.selection_range(0, tk.END)
                    return
                self.result = (cols, rows)
                self._dialog.destroy()

            def _on_cancel(self) -> None:
                self.result = None
                self._dialog.destroy()

        dialog = _MapSizeDialog(self)
        return dialog.result

    @property
    def grid_cols(self) -> int:
        return int(self.cols)

    @property
    def grid_rows(self) -> int:
        return int(self.rows)

    def _build_ui(self) -> None:
        outer = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        outer.pack(fill=tk.BOTH, expand=True)

        left_container = ttk.Frame(outer)
        outer.add(left_container, weight=0)

        left_canvas = tk.Canvas(left_container, highlightthickness=0)
        left_scroll = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left = ttk.Frame(left_canvas, padding=8)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _sync_left_scroll(_evt=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        left.bind("<Configure>", _sync_left_scroll)

        def _sync_left_width(evt):
            left_canvas.itemconfigure(left_window, width=evt.width)

        left_canvas.bind("<Configure>", _sync_left_width)

        right = ttk.Frame(outer, padding=8)
        outer.add(right, weight=1)

        # --- DM controls ---
        dm_ctrl = ttk.LabelFrame(left, text="DM Control", padding=6)
        dm_ctrl.pack(fill=tk.X, pady=(0, 10))
        dm_btn_row = ttk.Frame(dm_ctrl)
        dm_btn_row.pack(fill=tk.X)
        ttk.Button(dm_btn_row, text="Dash", command=self._dm_dash_target).pack(side=tk.LEFT)
        ttk.Button(dm_btn_row, text="Prev Turn", command=self._dm_prev_turn).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(dm_btn_row, text="Next Turn", command=self._dm_next_turn).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(dm_btn_row, text="Stand Up", command=self._dm_stand_up_target).pack(side=tk.LEFT, padx=(8, 0))
        mode_row = ttk.Frame(dm_ctrl)
        mode_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(mode_row, text="Movement:").pack(side=tk.LEFT)
        ttk.Button(mode_row, text="Walk", command=lambda: self._dm_set_mode_target("normal")).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(mode_row, text="Fly", command=lambda: self._dm_set_mode_target("fly")).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(dm_ctrl, text="Library…", command=lambda: self.app._open_dm_reference_library(from_window=self)).pack(
            anchor="w", pady=(6, 0)
        )

        # --- Map view ---
        view = ttk.LabelFrame(left, text="Map View", padding=6)
        view.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(view, text="Zoom (px / square):").grid(row=0, column=0, sticky="w")
        self._zoom_slider = ttk.Scale(view, from_=12, to=80, variable=self.zoom_var, command=self._on_zoom_change)
        self._zoom_slider.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._zoom_val = ttk.Label(view, text="32")
        self._zoom_val.grid(row=0, column=2, sticky="e", padx=(6, 0))
        ttk.Button(view, text="Fit", command=self._fit_to_window).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(view, text="Center", command=self._center_view).grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )
        ttk.Checkbutton(view, text="Draw Obstacles", variable=self.obstacle_mode_var).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(view, text="Erase Obstacles (Shift)", variable=self.obstacle_erase_var).grid(
            row=2, column=1, sticky="w", pady=(6, 0)
        )
        ttk.Button(view, text="Clear Obstacles", command=self._clear_obstacles).grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(view, text="Draw Rough Terrain", variable=self.rough_mode_var).grid(
            row=3, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(view, text="Erase Rough (Shift)", variable=self.rough_erase_var).grid(
            row=3, column=1, sticky="w", pady=(6, 0)
        )
        rough_color_row = ttk.Frame(view)
        rough_color_row.grid(row=3, column=2, sticky="w", pady=(6, 0))
        ttk.Label(rough_color_row, text="Color:").pack(side=tk.LEFT)
        self.rough_color_combo = ttk.Combobox(
            rough_color_row,
            textvariable=self.rough_color_var,
            values=self._rough_color_labels,
            state="readonly",
            width=14,
        )
        self.rough_color_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.rough_color_combo.bind("<<ComboboxSelected>>", lambda e: self._on_rough_color_select())
        ttk.Label(rough_color_row, text="Hex:").pack(side=tk.LEFT, padx=(8, 0))
        self.rough_color_entry = ttk.Entry(rough_color_row, textvariable=self.rough_color_hex_var, width=8)
        self.rough_color_entry.pack(side=tk.LEFT, padx=(4, 0))
        self.rough_color_entry.bind("<FocusOut>", lambda e: self._sync_rough_color_hex())
        ttk.Label(view, text="Brush Size (cells):").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self._obstacle_brush_entry = ttk.Entry(
            view,
            textvariable=self.obstacle_brush_var,
            width=6,
            validate="key",
            validatecommand=(self.register(self._validate_obstacle_brush), "%P"),
        )
        self._obstacle_brush_entry.grid(row=4, column=1, sticky="w", pady=(6, 0))
        self._obstacle_brush_entry.bind("<FocusOut>", lambda e: self._normalize_obstacle_brush())
        ttk.Checkbutton(view, text="Single square", variable=self.obstacle_single_var).grid(
            row=4, column=2, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(view, text="Show All Names", variable=self.show_all_names_var, command=self._redraw_all).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(view, text="DM Move", variable=self.dm_move_var).grid(
            row=6, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(view, text="Damage Mode", variable=self.damage_mode_var).grid(
            row=6, column=1, sticky="w", pady=(6, 0)
        )
        preset_btns = ttk.Frame(view)
        preset_btns.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(preset_btns, text="Save Preset", command=self._save_obstacle_preset).pack(side=tk.LEFT)
        ttk.Button(preset_btns, text="Load Preset", command=self._load_obstacle_preset).pack(side=tk.LEFT, padx=(8, 0))
        view.columnconfigure(1, weight=1)

        # --- Units panel ---
        ttk.Label(left, text="Units (drag onto map)").pack(anchor="w")
        unit_frame = ttk.Frame(left)
        unit_frame.pack(fill=tk.BOTH, expand=False, pady=(4, 10))

        self.units_list = tk.Listbox(unit_frame, height=14, exportselection=False)
        self.units_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(unit_frame, orient=tk.VERTICAL, command=self.units_list.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.units_list.config(yscrollcommand=sb.set)

        self.units_list.bind("<ButtonPress-1>", self._on_units_press)
        self.units_list.bind("<B1-Motion>", self._on_units_motion)
        self.units_list.bind("<ButtonRelease-1>", self._on_units_release)
        self.units_list.bind("<Double-Button-1>", self._on_units_double_click)
        self.units_list.bind("<Return>", lambda e: self._place_selected_units_near_center())
        self.units_list.bind("<<ListboxSelect>>", lambda _e: self._sync_units_movement_mode())

        mode_row = ttk.Frame(left)
        mode_row.pack(fill=tk.X, pady=(4, 8))
        ttk.Label(mode_row, text="Movement:").pack(side=tk.LEFT)
        self.unit_mode_var = tk.StringVar(value=MOVEMENT_MODE_LABELS["normal"])
        self.unit_mode_combo = ttk.Combobox(
            mode_row,
            textvariable=self.unit_mode_var,
            values=[MOVEMENT_MODE_LABELS[mode] for mode in MOVEMENT_MODES],
            state="readonly",
            width=12,
        )
        self.unit_mode_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.unit_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_units_movement_mode())
        self._set_unit_mode_controls_enabled(False)

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(btns, text="Refresh Units (R)", command=self.refresh_units).pack(side=tk.LEFT)
        ttk.Button(btns, text="Place Selected", command=self._place_selected_units_near_center).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Place All", command=self._place_all_units_near_center).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Clear Measure (Esc)", command=self._clear_measure).pack(side=tk.LEFT, padx=(8, 0))

        # --- Groups panel ---
        ttk.Separator(left).pack(fill=tk.X, pady=(6, 10))
        groups_notebook = ttk.Notebook(left)
        groups_notebook.pack(fill=tk.BOTH, expand=False)
        groups_tab = ttk.Frame(groups_notebook)
        groups_notebook.add(groups_tab, text="Groups")

        ttk.Label(groups_tab, text="Grouped Squares").pack(anchor="w")
        group_cells_frame = ttk.Frame(groups_tab)
        group_cells_frame.pack(fill=tk.BOTH, expand=False, pady=(4, 6))
        self.group_cells_list = tk.Listbox(group_cells_frame, height=6, exportselection=False)
        self.group_cells_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        group_cells_sb = ttk.Scrollbar(group_cells_frame, orient=tk.VERTICAL, command=self.group_cells_list.yview)
        group_cells_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.group_cells_list.config(yscrollcommand=group_cells_sb.set)
        self.group_cells_list.bind("<<ListboxSelect>>", lambda e: self._on_group_cell_select())

        ttk.Label(groups_tab, text="Members").pack(anchor="w")
        group_members_frame = ttk.Frame(groups_tab)
        group_members_frame.pack(fill=tk.BOTH, expand=False)
        self.group_members_list = tk.Listbox(group_members_frame, height=6, exportselection=False)
        self.group_members_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        group_members_sb = ttk.Scrollbar(group_members_frame, orient=tk.VERTICAL, command=self.group_members_list.yview)
        group_members_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.group_members_list.config(yscrollcommand=group_members_sb.set)
        self.group_members_list.bind("<<ListboxSelect>>", lambda e: self._on_group_member_select())

        # --- AoE panel ---
        ttk.Separator(left).pack(fill=tk.X, pady=(6, 10))
        ttk.Label(left, text="Spell Overlays (AoE)").pack(anchor="w")

        spell_row = ttk.Frame(left)
        spell_row.pack(fill=tk.X, pady=(4, 6))
        ttk.Label(spell_row, text="Spell:").pack(side=tk.LEFT)
        self.aoe_spell_var = tk.StringVar(value="")
        self.aoe_spell_combo = ttk.Combobox(
            spell_row,
            textvariable=self.aoe_spell_var,
            values=[],
            state="readonly",
            width=24,
        )
        self.aoe_spell_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.aoe_spell_combo.bind("<<ComboboxSelected>>", lambda e: self._add_spell_aoe_from_combo())

        aoe_btns = ttk.Frame(left)
        aoe_btns.pack(fill=tk.X, pady=(4, 6))
        ttk.Button(aoe_btns, text="Add Circle", command=self._add_circle_aoe).pack(side=tk.LEFT)
        ttk.Button(aoe_btns, text="Add Sphere", command=self._add_sphere_aoe).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(aoe_btns, text="Add Square", command=self._add_square_aoe).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(aoe_btns, text="Add Cube", command=self._add_cube_aoe).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(aoe_btns, text="Add Line", command=self._add_line_aoe).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(aoe_btns, text="Add Cone", command=self._add_cone_aoe).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(aoe_btns, text="Add Wall", command=self._add_wall_aoe).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(aoe_btns, text="Remove", command=self._remove_selected_aoe).pack(side=tk.LEFT, padx=(8, 0))

        self.aoe_list = tk.Listbox(left, height=8, exportselection=False)
        self.aoe_list.pack(fill=tk.BOTH, expand=False)
        self.aoe_list.bind("<<ListboxSelect>>", lambda e: self._select_aoe_from_list())
        self.aoe_list.bind("<Double-Button-1>", lambda e: self._rename_selected_aoe())

        self.pin_var = tk.BooleanVar(value=False)
        self.pin_chk = ttk.Checkbutton(left, text="Stationary (pinned)", variable=self.pin_var, command=self._toggle_pin_selected)
        self.pin_chk.pack(anchor="w", pady=(6, 0))

        self.aoe_move_var = tk.BooleanVar(value=False)
        self.aoe_move_chk = ttk.Checkbutton(left, text="Move AoEs", variable=self.aoe_move_var)
        self.aoe_move_chk.pack(anchor="w", pady=(4, 0))

        duration_row = ttk.Frame(left)
        duration_row.pack(anchor="w", pady=(6, 0))
        ttk.Label(duration_row, text="Duration (turns):").pack(side=tk.LEFT)
        self.aoe_duration_var = tk.StringVar(value="")
        self.aoe_duration_ent = ttk.Entry(duration_row, textvariable=self.aoe_duration_var, width=6)
        self.aoe_duration_ent.pack(side=tk.LEFT, padx=(6, 0))
        self.aoe_duration_ent.bind("<Return>", lambda _e: self._apply_aoe_duration())
        self.aoe_duration_ent.bind("<FocusOut>", lambda _e: self._apply_aoe_duration())
        try:
            self.aoe_duration_ent.state(["disabled"])
        except Exception:
            self.aoe_duration_ent.config(state=tk.DISABLED)

        color_row = ttk.Frame(left)
        color_row.pack(anchor="w", pady=(6, 0))
        ttk.Label(color_row, text="Color:").pack(side=tk.LEFT)
        self.aoe_color_var = tk.StringVar(value=self._aoe_color_labels[0] if self._aoe_color_labels else "")
        self.aoe_color_combo = ttk.Combobox(
            color_row,
            textvariable=self.aoe_color_var,
            values=self._aoe_color_labels,
            state="readonly",
            width=18,
        )
        self.aoe_color_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.aoe_color_combo.bind("<<ComboboxSelected>>", lambda e: self._on_aoe_color_change())
        try:
            self.aoe_color_combo.state(["disabled"])
        except Exception:
            self.aoe_color_combo.config(state=tk.DISABLED)

        ttk.Label(left, text="Included in selected AoE:").pack(anchor="w", pady=(10, 0))
        self.included_box = tk.Text(left, height=8, width=28, wrap="word")
        self.included_box.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.included_box.config(state=tk.DISABLED)

        dmg_row = ttk.Frame(left)
        dmg_row.pack(fill=tk.X, pady=(6, 0))
        self.aoe_damage_btn = ttk.Button(dmg_row, text="AoE Damage…", command=self._open_aoe_damage)
        self.aoe_damage_btn.pack(side=tk.LEFT)
        try:
            self.aoe_damage_btn.state(["disabled"])
        except Exception:
            pass

        ttk.Label(left, text="Tip: Right-click two points to measure distance (crow flies).").pack(anchor="w", pady=(10, 0))

        # --- Background images panel ---
        ttk.Separator(left).pack(fill=tk.X, pady=(10, 10))
        ttk.Label(left, text="Background Images").pack(anchor="w")

        bg_btns = ttk.Frame(left)
        bg_btns.pack(fill=tk.X, pady=(4, 6))
        ttk.Button(bg_btns, text="Add Image…", command=self._add_bg_image).pack(side=tk.LEFT)
        ttk.Button(bg_btns, text="Remove", command=self._remove_selected_bg_image).pack(side=tk.LEFT, padx=(8, 0))

        self.bg_list = tk.Listbox(left, height=6, exportselection=False)
        self.bg_list.pack(fill=tk.BOTH, expand=False)
        self.bg_list.bind("<<ListboxSelect>>", lambda e: self._select_bg_from_list())

        self.bg_lock_var = tk.BooleanVar(value=False)
        self.bg_scale_var = tk.DoubleVar(value=100.0)          # percent
        self.bg_transparency_var = tk.DoubleVar(value=0.0)     # percent (0=opaque, 100=invisible)

        ctrl = ttk.Frame(left)
        ctrl.pack(fill=tk.X, pady=(6, 0))
        self.bg_lock_chk = ttk.Checkbutton(ctrl, text="Lock", variable=self.bg_lock_var, command=self._on_bg_lock_toggle)
        self.bg_lock_chk.grid(row=0, column=0, sticky="w")

        ttk.Label(ctrl, text="Scale %").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.bg_scale = ttk.Scale(ctrl, from_=10, to=300, variable=self.bg_scale_var, command=self._on_bg_scale_change)
        self.bg_scale.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        self.bg_scale_val = ttk.Label(ctrl, text="100%")
        self.bg_scale_val.grid(row=1, column=2, sticky="e", padx=(6, 0))

        ttk.Label(ctrl, text="Transparency %").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.bg_alpha = ttk.Scale(ctrl, from_=0, to=100, variable=self.bg_transparency_var, command=self._on_bg_transparency_change)
        self.bg_alpha.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        self.bg_alpha_val = ttk.Label(ctrl, text="0%")
        self.bg_alpha_val.grid(row=2, column=2, sticky="e", padx=(6, 0))

        ctrl.columnconfigure(1, weight=1)
        self._set_bg_controls_enabled(False)

        # --- Map canvas (scrollable) ---
        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, background="#f8f1d4", highlightthickness=1, highlightbackground="#8b6a3d")
        self.vsb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.hsb.set, yscrollcommand=self.vsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self._hover_tooltip = tk.Label(
            self.canvas,
            text="",
            background="#1f1f1f",
            foreground="#eef2f7",
            borderwidth=1,
            relief="solid",
            font=("TkDefaultFont", 9, "bold"),
        )
        self._hover_tooltip.place_forget()

        self.canvas.bind("<Configure>", lambda e: self._redraw_all())
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-2>", self._on_canvas_middle_click)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.canvas.bind("<Motion>", self._on_canvas_hover)
        self.canvas.bind("<Leave>", lambda _e: self._hide_hover_tooltip())

    # ---------------- Units list / drag placement ----------------
    def refresh_units(self) -> None:
        """Refresh the roster list and drop tokens that no longer exist."""
        # Remove tokens for missing combatants
        existing = set(self.app.combatants.keys())
        for cid in list(self.unit_tokens.keys()):
            if cid not in existing:
                self._delete_unit_token(cid)

        self.units_list.delete(0, tk.END)
        self._units_index_to_cid: List[int] = []
        # show in initiative display order first, then others
        ordered = [c.cid for c in self.app._display_order()] if hasattr(self.app, "_display_order") else list(existing)
        seen = set()
        for cid in ordered + [cid for cid in existing if cid not in set(ordered)]:
            if cid in seen or cid not in existing:
                continue
            seen.add(cid)
            c = self.app.combatants[cid]
            label = f"{c.name}  [#{cid}]"
            if cid in self.unit_tokens:
                label += "  (on map)"
            self.units_list.insert(tk.END, label)
            self._units_index_to_cid.append(cid)

        try:
            self.refresh_spell_overlays()
        except Exception:
            pass
        self._sync_units_movement_mode()

    def _set_unit_mode_controls_enabled(self, enabled: bool) -> None:
        if not hasattr(self, "unit_mode_combo"):
            return
        try:
            if enabled:
                self.unit_mode_combo.state(["!disabled"])
            else:
                self.unit_mode_combo.state(["disabled"])
        except Exception:
            self.unit_mode_combo.config(state=(tk.NORMAL if enabled else tk.DISABLED))

    def _selected_unit_cids(self) -> List[int]:
        cids: List[int] = []
        for idx in list(self.units_list.curselection()):
            if 0 <= idx < len(getattr(self, "_units_index_to_cid", [])):
                cids.append(self._units_index_to_cid[idx])
        return cids

    def _sync_units_movement_mode(self) -> None:
        if not hasattr(self, "unit_mode_var"):
            return
        cids = self._selected_unit_cids()
        if not cids:
            self.unit_mode_var.set(MOVEMENT_MODE_LABELS["normal"])
            self._set_unit_mode_controls_enabled(False)
            return
        self._set_unit_mode_controls_enabled(True)
        cid = cids[0]
        creature = self.app.combatants.get(cid)
        mode = self.app._movement_mode_label(getattr(creature, "movement_mode", "normal")) if creature else "Normal"
        self.unit_mode_var.set(mode)

    def _apply_units_movement_mode(self) -> None:
        cids = self._selected_unit_cids()
        if not cids:
            return
        mode_label = str(self.unit_mode_var.get() or MOVEMENT_MODE_LABELS["normal"])
        mode = self.app._normalize_movement_mode(mode_label)
        for cid in cids:
            self.app._set_movement_mode(cid, mode)
        self._update_move_highlight()


    def _start_polling(self) -> None:
        self._stop_polling()
        self._poll_once()

    def _stop_polling(self) -> None:
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None

    def _poll_once(self) -> None:
        if not self.winfo_exists():
            return
        try:
            sig = tuple(sorted(self.app.combatants.keys()))
            if sig != self._last_roster_sig:
                self._last_roster_sig = sig
                self.refresh_units()
            else:
                existing = set(sig)
                for cid in list(self.unit_tokens.keys()):
                    if cid not in existing:
                        self._delete_unit_token(cid)

            # Keep labels/markers in sync with the main tracker
            for cid, tok in list(self.unit_tokens.items()):
                c = self.app.combatants.get(cid)
                if not c:
                    continue
                try:
                    self.canvas.itemconfigure(int(tok["text"]), text=c.name)
                except Exception:
                    pass
                if "marker" in tok:
                    mt = self._marker_text_for(cid)
                    try:
                        self.canvas.itemconfigure(int(tok["marker"]), text=mt, state=("normal" if mt else "hidden"))
                    except Exception:
                        pass

            self.update_unit_token_colors()
            self._apply_active_highlight()
            self._update_move_highlight()
            self._update_included_for_selected()
        except Exception:
            pass

        try:
            self._poll_after_id = self.after(750, self._poll_once)
        except Exception:
            self._poll_after_id = None

    def _on_zoom_change(self, _val: object = None) -> None:
        try:
            self._zoom_val.config(text=str(int(float(self.zoom_var.get()))))
        except Exception:
            pass
        self._redraw_all()
        self._draw_rough_terrain()
        self._draw_obstacles()

    def _fit_to_window(self) -> None:
        try:
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())
            cell = max(
                10.0,
                min(
                    (cw - 2 * self._map_margin) / float(self.cols),
                    (ch - 2 * self._map_margin) / float(self.rows),
                ),
            )
            self.zoom_var.set(cell)
        except Exception:
            return
        self._on_zoom_change()

    def _center_view(self) -> None:
        # Center the view on the middle of the grid (best-effort).
        try:
            sr = tuple(map(float, self.canvas.cget("scrollregion").split()))
            sw = max(1.0, sr[2] - sr[0])
            sh = max(1.0, sr[3] - sr[1])
            cw = max(1.0, float(self.canvas.winfo_width()))
            ch = max(1.0, float(self.canvas.winfo_height()))
            gw = float(self.cols) * float(self.cell)
            gh = float(self.rows) * float(self.cell)
            cx = self._map_margin + gw / 2.0
            cy = self._map_margin + gh / 2.0
            left = max(0.0, min(1.0, (cx - cw / 2.0) / sw))
            top = max(0.0, min(1.0, (cy - ch / 2.0) / sh))
            self.canvas.xview_moveto(left)
            self.canvas.yview_moveto(top)
        except Exception:
            pass

    def _center_on_cid(self, cid: int) -> None:
        try:
            tok = self.unit_tokens.get(int(cid))
            if not tok:
                return
            cx, cy = self._grid_to_pixel(int(tok["col"]), int(tok["row"]))
            sr = tuple(map(float, self.canvas.cget("scrollregion").split()))
            sw = max(1.0, sr[2] - sr[0])
            sh = max(1.0, sr[3] - sr[1])
            cw = max(1.0, float(self.canvas.winfo_width()))
            ch = max(1.0, float(self.canvas.winfo_height()))
            left = max(0.0, min(1.0, (cx - cw / 2.0) / sw))
            top = max(0.0, min(1.0, (cy - ch / 2.0) / sh))
            self.canvas.xview_moveto(left)
            self.canvas.yview_moveto(top)
        except Exception:
            pass



    def _dash_active(self) -> None:
        """Dash the active creature on the map: add one more speed's worth of movement this turn."""
        if self._active_cid is None:
            return
        c = self.app.combatants.get(self._active_cid)
        if not c:
            return
        try:
            base = int(self.app._mode_speed(c))
        except Exception:
            base = int(getattr(c, "speed", 30) or 30)
        total = int(getattr(c, "move_total", 0) or 0)
        if total <= 0:
            total = base
        rem = int(getattr(c, "move_remaining", 0) or 0)

        c.move_total = total + base
        c.move_remaining = rem + base
        try:
            self.app._log(f"{c.name} dashes: move {self.app._move_cell(c)} ft.", cid=c.cid)
        except Exception:
            pass
        try:
            self.app._rebuild_table(scroll_to_current=True)
        except Exception:
            pass
        self._update_move_highlight()

    def _dm_action_target_cid(self) -> Optional[int]:
        cids = self._selected_unit_cids()
        if cids:
            return int(cids[0])
        if self._active_cid is not None and self._active_cid in self.app.combatants:
            return int(self._active_cid)
        return None

    def _dm_next_turn(self) -> None:
        self.app._next_turn()

    def _dm_prev_turn(self) -> None:
        self.app._prev_turn()

    def _dm_dash_target(self) -> None:
        cid = self._dm_action_target_cid()
        if cid is None:
            return
        c = self.app.combatants.get(cid)
        if not c:
            return
        try:
            base = int(self.app._mode_speed(c))
        except Exception:
            base = int(getattr(c, "speed", 30) or 30)
        total = int(getattr(c, "move_total", 0) or 0)
        if total <= 0:
            total = base
        rem = int(getattr(c, "move_remaining", 0) or 0)
        c.move_total = total + base
        c.move_remaining = rem + base
        try:
            self.app._log(f"{c.name} dashed (move {rem}/{total} -> {c.move_remaining}/{c.move_total})", cid=c.cid)
            self.app.start_last_var.set(f"{c.name}: dashed (+{base} ft)")
        except Exception:
            pass
        try:
            self.app._rebuild_table(scroll_to_current=True)
        except Exception:
            pass
        self._update_move_highlight()

    def _dm_stand_up_target(self) -> None:
        cid = self._dm_action_target_cid()
        if cid is None:
            return
        c = self.app.combatants.get(cid)
        if not c or not self.app._has_condition(c, "prone"):
            return
        eff = self.app._effective_speed(c)
        if eff <= 0:
            messagebox.showinfo("Stand Up", "Can't stand up right now (speed is 0).")
            return
        cost = max(0, eff // 2)
        if int(getattr(c, "move_remaining", 0) or 0) < cost:
            messagebox.showinfo("Stand Up", f"Not enough movement to stand (need {cost} ft).")
            return
        c.move_remaining = int(getattr(c, "move_remaining", 0) or 0) - cost
        self.app._remove_condition_type(c, "prone")
        try:
            self.app.start_last_var.set(f"{c.name}: stood up (-{cost} ft)")
            self.app._log(f"stood up (spent {cost} ft, prone removed)", cid=c.cid)
            self.app._rebuild_table(scroll_to_current=True)
        except Exception:
            pass
        self._update_move_highlight()

    def _dm_set_mode_target(self, mode: str) -> None:
        cid = self._dm_action_target_cid()
        if cid is None:
            return
        self.app._set_movement_mode(cid, mode)
        self._sync_units_movement_mode()
        self._update_move_highlight()

    def _clear_obstacles(self) -> None:
        self.obstacles.clear()
        self._redraw_all()
        self._update_move_highlight()

    def _undo_obstacle(self) -> None:
        if not self._obstacle_history:
            return
        self.obstacles = self._obstacle_history.pop()
        self._draw_obstacles()
        self._update_move_highlight()

    def _ensure_preset_dir(self) -> Path:
        preset_dir = _app_data_dir() / "presets"
        preset_dir.mkdir(parents=True, exist_ok=True)
        return preset_dir

    def _save_obstacle_preset(self) -> None:
        preset_dir = self._ensure_preset_dir()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Obstacle Preset",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(preset_dir),
        )
        if not path:
            return
        rough_terrain = []
        for (col, row), cell in sorted(self.rough_terrain.items()):
            cell_data = self._rough_cell_data(cell)
            rough_terrain.append(
                {
                    "col": int(col),
                    "row": int(row),
                    "color": cell_data.get("color"),
                    "label": cell_data.get("label"),
                    "movement_type": cell_data.get("movement_type"),
                    "is_swim": bool(cell_data.get("is_swim")),
                    "is_rough": bool(cell_data.get("is_rough")),
                }
            )
        data = {
            "cols": int(self.cols),
            "rows": int(self.rows),
            "obstacles": sorted([list(pair) for pair in self.obstacles]),
            "rough_terrain": rough_terrain,
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError as exc:
            messagebox.showerror("Save Preset", f"Failed to save preset:\n{exc}", parent=self)

    def _load_obstacle_preset(self) -> None:
        preset_dir = self._ensure_preset_dir()
        path = filedialog.askopenfilename(
            parent=self,
            title="Load Obstacle Preset",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(preset_dir),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Load Preset", f"Failed to load preset:\n{exc}", parent=self)
            return
        if not isinstance(data, dict):
            messagebox.showerror("Load Preset", "Preset data is not a valid object.", parent=self)
            return
        try:
            preset_cols = int(data.get("cols"))
            preset_rows = int(data.get("rows"))
        except (TypeError, ValueError):
            messagebox.showerror("Load Preset", "Preset is missing valid grid dimensions.", parent=self)
            return
        obstacles = data.get("obstacles", [])
        if not isinstance(obstacles, list):
            messagebox.showerror("Load Preset", "Preset obstacle list is invalid.", parent=self)
            return
        rough_terrain = data.get("rough_terrain", [])
        if "rough_terrain" in data and not isinstance(rough_terrain, list):
            messagebox.showerror("Load Preset", "Preset rough terrain list is invalid.", parent=self)
            return
        target_cols = int(self.cols)
        target_rows = int(self.rows)
        if preset_cols != self.cols or preset_rows != self.rows:
            choice = messagebox.askyesnocancel(
                "Preset Size Mismatch",
                (
                    f"Preset is {preset_cols}x{preset_rows}, but the map is {int(self.cols)}x{int(self.rows)}.\n\n"
                    "Yes: resize map to match the preset.\n"
                    "No: keep current size and load only obstacles that fit.\n"
                    "Cancel: abort loading."
                ),
                parent=self,
            )
            if choice is None:
                return
            if choice:
                self.cols = preset_cols
                self.rows = preset_rows
                target_cols = preset_cols
                target_rows = preset_rows
        loaded: Set[Tuple[int, int]] = set()
        for item in obstacles:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            try:
                col = int(item[0])
                row = int(item[1])
            except (TypeError, ValueError):
                continue
            if 0 <= col < target_cols and 0 <= row < target_rows:
                loaded.add((col, row))
        self.obstacles = loaded
        loaded_rough: Dict[Tuple[int, int], Dict[str, object]] = {}
        for entry in rough_terrain:
            if not isinstance(entry, dict):
                continue
            try:
                col = int(entry.get("col"))
                row = int(entry.get("row"))
            except (TypeError, ValueError):
                continue
            if col < 0 or row < 0 or col >= target_cols or row >= target_rows:
                continue
            cell_data = self._rough_cell_data(entry)
            loaded_rough[(col, row)] = {
                "color": cell_data.get("color"),
                "label": cell_data.get("label"),
                "movement_type": cell_data.get("movement_type"),
                "is_swim": bool(cell_data.get("is_swim")),
                "is_rough": bool(cell_data.get("is_rough")),
            }
        self.rough_terrain = loaded_rough
        self._redraw_all()
        self._draw_rough_terrain()
        self._update_move_highlight()

    def _draw_obstacles(self) -> None:
        """Render obstacle squares on top of the grid."""
        try:
            self.canvas.delete("obstacle")
        except Exception:
            pass
        if not self.obstacles:
            return
        for (col, row) in sorted(self.obstacles):
            x1 = self.x0 + col * self.cell
            y1 = self.y0 + row * self.cell
            x2 = x1 + self.cell
            y2 = y1 + self.cell
            try:
                self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill="#000000",
                    outline="",
                    tags=("obstacle",)
                )
            except Exception:
                pass
        try:
            self.canvas.tag_raise("obstacle", "grid")
        except Exception:
            pass

    def _draw_rough_terrain(self) -> None:
        """Render rough terrain squares above the grid but beneath tokens."""
        try:
            self.canvas.delete("rough")
        except Exception:
            pass
        if not self.rough_terrain:
            return
        for (col, row), cell in sorted(self.rough_terrain.items()):
            x1 = self.x0 + col * self.cell
            y1 = self.y0 + row * self.cell
            x2 = x1 + self.cell
            y2 = y1 + self.cell
            cell_data = self._rough_cell_data(cell)
            fill = self._normalize_hex_color(cell_data.get("color")) or "#8d6e63"
            is_rough = bool(cell_data.get("is_rough"))
            is_water = cell_data.get("movement_type") == "water"
            stipple = "gray50" if is_rough else ("gray25" if is_water else "")
            try:
                options = {
                    "fill": fill,
                    "outline": "",
                    "tags": ("rough",),
                }
                if stipple:
                    options["stipple"] = stipple
                self.canvas.create_rectangle(x1, y1, x2, y2, **options)
            except Exception:
                pass
        try:
            self.canvas.tag_raise("rough", "grid")
            self.canvas.tag_lower("rough", "unit")
        except Exception:
            pass

    def _validate_obstacle_brush(self, value: str) -> bool:
        if value == "":
            return True
        if not value.isdigit():
            return False
        return int(value) >= 1

    def _get_obstacle_brush_radius(self) -> int:
        try:
            radius = int(self.obstacle_brush_var.get())
        except (tk.TclError, ValueError, TypeError):
            return 1
        return radius if radius >= 1 else 1

    def _normalize_obstacle_brush(self) -> int:
        radius = self._get_obstacle_brush_radius()
        try:
            current = self.obstacle_brush_var.get()
        except tk.TclError:
            current = None
        if current != radius:
            self.obstacle_brush_var.set(radius)
        return radius

    def _paint_obstacle_from_event(self, event: tk.Event) -> None:
        """Paint or erase an obstacle cell based on the pointer location."""
        cx = float(self.canvas.canvasx(event.x))
        cy = float(self.canvas.canvasy(event.y))
        col, row = self._pixel_to_grid(cx, cy)
        if col is None or row is None:
            return
        if col < 0 or row < 0 or col >= self.cols or row >= self.rows:
            return
        # Shift = erase (or toggle on the UI)
        erase = bool(self.obstacle_erase_var.get()) or bool(event.state & 0x0001)
        radius = self._normalize_obstacle_brush()
        base_col = int(col)
        base_row = int(row)
        if self.obstacle_single_var.get():
            key = (base_col, base_row)
            if erase:
                self.obstacles.discard(key)
            else:
                self.obstacles.add(key)
        else:
            max_delta = int(math.ceil(radius))
            for dc in range(-max_delta, max_delta + 1):
                for dr in range(-max_delta, max_delta + 1):
                    if math.hypot(dc, dr) > radius:
                        continue
                    target_col = base_col + dc
                    target_row = base_row + dr
                    if target_col < 0 or target_row < 0 or target_col >= self.cols or target_row >= self.rows:
                        continue
                    key = (target_col, target_row)
                    if erase:
                        self.obstacles.discard(key)
                    else:
                        self.obstacles.add(key)
        # Redraw obstacles + recompute movement highlight (obstacles affect it)
        self._draw_obstacles()
        self._update_move_highlight()

    def _paint_rough_terrain_from_event(self, event: tk.Event) -> None:
        """Paint or erase a rough terrain cell based on the pointer location."""
        cx = float(self.canvas.canvasx(event.x))
        cy = float(self.canvas.canvasy(event.y))
        col, row = self._pixel_to_grid(cx, cy)
        if col is None or row is None:
            return
        if col < 0 or row < 0 or col >= self.cols or row >= self.rows:
            return
        erase = bool(self.rough_erase_var.get()) or bool(event.state & 0x0001)
        radius = self._normalize_obstacle_brush()
        base_col = int(col)
        base_row = int(row)
        terrain = self._rough_preset_from_ui()
        if self.obstacle_single_var.get():
            key = (base_col, base_row)
            if erase:
                self.rough_terrain.pop(key, None)
            else:
                self.rough_terrain[key] = terrain
        else:
            max_delta = int(math.ceil(radius))
            for dc in range(-max_delta, max_delta + 1):
                for dr in range(-max_delta, max_delta + 1):
                    if math.hypot(dc, dr) > radius:
                        continue
                    target_col = base_col + dc
                    target_row = base_row + dr
                    if target_col < 0 or target_row < 0 or target_col >= self.cols or target_row >= self.rows:
                        continue
                    key = (target_col, target_row)
                    if erase:
                        self.rough_terrain.pop(key, None)
                    else:
                        self.rough_terrain[key] = dict(terrain)
        self._draw_rough_terrain()
        self._update_move_highlight()


    def _on_units_press(self, event: tk.Event) -> None:
        idx = self.units_list.nearest(event.y)
        if idx < 0 or idx >= len(getattr(self, "_units_index_to_cid", [])):
            return
        self.units_list.selection_clear(0, tk.END)
        self.units_list.selection_set(idx)
        self._sync_units_movement_mode()
        cid = self._units_index_to_cid[idx]
        self._dragging_from_list = cid
        name = self.app.combatants[cid].name if cid in self.app.combatants else str(cid)
        self._make_ghost(f"➜ {name}")

    def _make_ghost(self, text: str) -> None:
        if self._drag_ghost is None or not self._drag_ghost.winfo_exists():
            self._drag_ghost = tk.Label(self, text=text, relief="solid", borderwidth=1, background="#fff7c2")
        self._drag_ghost.lift()

    def _on_units_motion(self, event: tk.Event) -> None:
        if self._dragging_from_list is None:
            return
        if self._drag_ghost is None:
            return
        # position ghost near cursor (window coords)
        x = event.x_root - self.winfo_rootx() + 12
        y = event.y_root - self.winfo_rooty() + 12
        self._drag_ghost.place(x=x, y=y)

    def _on_units_release(self, event: tk.Event) -> None:
        cid = self._dragging_from_list
        self._dragging_from_list = None
        if self._drag_ghost is not None and self._drag_ghost.winfo_exists():
            self._drag_ghost.place_forget()

        if cid is None or cid not in self.app.combatants:
            return

        w = self.winfo_containing(event.x_root, event.y_root)
        if w is None:
            return

        # Drop only if over the canvas (or a child of it)
        if w is self.canvas or str(w).startswith(str(self.canvas)):
            xw = event.x_root - self.canvas.winfo_rootx()
            yw = event.y_root - self.canvas.winfo_rooty()
            x = self.canvas.canvasx(xw)
            y = self.canvas.canvasy(yw)
            self._place_unit_at_pixel(cid, x, y)

    
    def _build_spawn_offsets(self) -> List[Tuple[int, int]]:
        """Build a spiral of offsets around (0,0) used for quick placement near map center."""
        offsets: List[Tuple[int, int]] = []
        x = 0
        y = 0
        dx = 0
        dy = -1
        steps = max(64, self.cols * self.rows * 2)
        for _ in range(steps):
            offsets.append((x, y))
            # turn at the corners of a square spiral
            if (x == y) or (x < 0 and x == -y) or (x > 0 and x == 1 - y):
                dx, dy = -dy, dx
            x += dx
            y += dy
            if len(offsets) >= self.cols * self.rows:
                break
        if not offsets:
            offsets = [(0, 0)]
        return offsets

    def _next_spawn_cell(self) -> Tuple[int, int]:
        cx = self.cols // 2
        cy = self.rows // 2
        n = max(1, len(self._spawn_offsets))
        tried = 0
        while tried < n:
            ox, oy = self._spawn_offsets[self._spawn_index % n]
            self._spawn_index += 1
            tried += 1
            col = cx + ox
            row = cy + oy
            if 0 <= col < self.cols and 0 <= row < self.rows:
                return col, row
        return max(0, min(self.cols - 1, cx)), max(0, min(self.rows - 1, cy))

    def _on_units_double_click(self, event: tk.Event) -> None:
        idx = self.units_list.nearest(event.y)
        try:
            idx_int = int(idx)
        except Exception:
            return
        if 0 <= idx_int < len(getattr(self, "_units_index_to_cid", [])):
            cid = self._units_index_to_cid[idx_int]
            self._place_units_near_center([cid])

    def _place_selected_units_near_center(self) -> None:
        cids: List[int] = []
        for idx in list(self.units_list.curselection()):
            if 0 <= idx < len(getattr(self, "_units_index_to_cid", [])):
                cids.append(self._units_index_to_cid[idx])
        if not cids:
            return
        self._place_units_near_center(cids)

    def _place_all_units_near_center(self) -> None:
        cids = [cid for cid in sorted(self.app.combatants.keys()) if cid not in self.unit_tokens]
        if not cids:
            return
        self._place_units_near_center(cids)

    def _place_units_near_center(self, cids: List[int]) -> None:
        placed_any = False
        for cid in cids:
            if cid not in self.app.combatants:
                continue
            if cid in self.unit_tokens:
                continue
            col, row = self._next_spawn_cell()
            self._create_unit_token(cid, col, row)
            placed_any = True

        if placed_any:
            self.refresh_units()
            self._update_groups()
            self._update_move_highlight()
            self._update_included_for_selected()

    def _place_unit_at_pixel(self, cid: int, x: float, y: float) -> None:
        col, row = self._pixel_to_grid(x, y)
        if col is None or row is None:
            return
        if cid in self.unit_tokens:
            # move existing token
            self.unit_tokens[cid]["col"] = col
            self.unit_tokens[cid]["row"] = row
        else:
            self._create_unit_token(cid, col, row)

        self._sync_mount_pair_position(cid, col, row)
        self.refresh_units()
        self._update_groups()
        self._update_move_highlight()
        self._update_included_for_selected()

    def _sync_mount_pair_position(self, cid: int, col: int, row: int) -> None:
        c = self.app.combatants.get(cid)
        if not c:
            return
        partner_cid = getattr(c, "rider_cid", None)
        if partner_cid is None:
            partner_cid = getattr(c, "mounted_by_cid", None)
        if partner_cid is None:
            return
        if isinstance(partner_cid, str):
            cleaned = partner_cid.strip()
            stripped = cleaned.lstrip("-")
            if not stripped or not stripped.isdigit():
                return
            partner_id = int(cleaned)
        else:
            try:
                partner_id = int(partner_cid)
            except (TypeError, ValueError):
                return
        tok = self.unit_tokens.get(partner_id)
        if not tok:
            return
        tok["col"] = col
        tok["row"] = row
        self._layout_unit(partner_id)

    def _normalize_token_color(self, color: object) -> Optional[str]:
        if not isinstance(color, str):
            return None
        value = color.strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            return None
        return value

    def _normalize_hex_color(self, color: object) -> Optional[str]:
        if not isinstance(color, str):
            return None
        value = color.strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            return None
        return value

    def _normalize_movement_type(self, value: object, is_swim: bool = False) -> str:
        return _normalize_movement_type(value, is_swim=is_swim)

    def _rough_cell_data(self, cell: object) -> Dict[str, object]:
        if isinstance(cell, dict):
            color = self._normalize_hex_color(cell.get("color"))
            label = str(cell.get("label") or "")
            is_swim = bool(cell.get("is_swim", False))
            movement_type = self._normalize_movement_type(cell.get("movement_type"), is_swim=is_swim)
            is_swim = movement_type == "water"
            is_rough = bool(cell.get("is_rough", False))
            return {
                "color": color or "#8d6e63",
                "label": label,
                "movement_type": movement_type,
                "is_swim": is_swim,
                "is_rough": is_rough,
            }
        if isinstance(cell, str):
            color = self._normalize_hex_color(cell) or "#8d6e63"
            return {"color": color, "label": "", "movement_type": "ground", "is_swim": False, "is_rough": True}
        return {"color": "#8d6e63", "label": "", "movement_type": "ground", "is_swim": False, "is_rough": False}

    def _rough_preset_from_ui(self) -> Dict[str, object]:
        label = str(self.rough_color_var.get() or "")
        preset = self._rough_preset_by_label.get(label)
        color = self._normalize_hex_color(self.rough_color_hex_var.get())
        if preset:
            return {
                "label": preset.label,
                "color": color or preset.color,
                "movement_type": preset.movement_type,
                "is_swim": preset.movement_type == "water",
                "is_rough": preset.is_rough,
            }
        if not color:
            color = self._rough_presets[0].color if self._rough_presets else "#8d6e63"
        return {"label": "Custom", "color": color, "movement_type": "ground", "is_swim": False, "is_rough": True}

    def _water_movement_multiplier(self, c: Optional[Combatant], mode: str) -> float:
        if c is None:
            return 1.0
        if self._normalize_movement_mode(mode) != "normal":
            return 1.0
        land_speed = max(0, int(getattr(c, "speed", 0) or 0))
        if land_speed <= 0:
            return 1.0
        swim_speed = max(0, int(getattr(c, "swim_speed", 0) or 0))
        if swim_speed <= 0:
            swim_speed = max(1, int(land_speed / 2))
        if swim_speed <= 0:
            return 1.0
        return float(land_speed) / float(swim_speed)

    def _on_rough_color_select(self) -> None:
        label = str(self.rough_color_var.get() or "")
        preset = self._rough_preset_by_label.get(label)
        if preset:
            self.rough_color_hex_var.set(preset.color)
        else:
            self.rough_color_var.set("Custom")

    def _sync_rough_color_hex(self) -> None:
        preset = self._rough_preset_from_ui()
        color = str(preset.get("color") or "#8d6e63")
        self.rough_color_hex_var.set(color)
        label = self._rough_label_by_color.get(color)
        if label:
            self.rough_color_var.set(label)
        else:
            self.rough_color_var.set("Custom")

    def _darken_color(self, color: str, factor: float = 0.55) -> str:
        r = max(0, min(255, int(int(color[1:3], 16) * factor)))
        g = max(0, min(255, int(int(color[3:5], 16) * factor)))
        b = max(0, min(255, int(int(color[5:7], 16) * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _role_token_colors(self, c: Combatant) -> Tuple[str, str]:
        if c.is_pc:
            return "#cfead1", "#1d6b26"
        if c.ally:
            return "#d6f5d6", "#2b8a3e"
        return "#f6d6d6", "#8a2b2b"

    def _token_colors_for(self, c: Combatant) -> Tuple[str, str]:
        token_color = self._normalize_token_color(getattr(c, "token_color", None))
        if token_color:
            return token_color, self._darken_color(token_color)
        return self._role_token_colors(c)

    def update_unit_token_colors(self) -> None:
        for cid, tok in self.unit_tokens.items():
            c = self.app.combatants.get(cid)
            if not c:
                continue
            fill, outline = self._token_colors_for(c)
            try:
                self.canvas.itemconfigure(int(tok["oval"]), fill=fill, outline=outline)
            except Exception:
                pass

    def _create_unit_token(self, cid: int, col: int, row: int) -> None:
        c = self.app.combatants[cid]
        x, y = self._grid_to_pixel(col, row)
        r = self.cell * 0.42

        fill, outline = self._token_colors_for(c)

        oval = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill=fill, outline=outline, width=2,
            tags=(f"unit:{cid}", "unit")
        )

        # Name lives ABOVE the token, so the token interior can show condition markers
        name_y = y - r - 2
        name_text = self.canvas.create_text(
            x, name_y,
            text=c.name,
            anchor="s",
            font=("TkDefaultFont", 9, "bold"),
            tags=(f"unit:{cid}", "unitname")
        )

        # Condition / effect markers (DoT, conditions, star advantage, etc.)
        mt = self._marker_text_for(cid)
        marker_text = self.canvas.create_text(
            x, y,
            text=mt,
            font=("TkDefaultFont", 9),
            tags=(f"unit:{cid}", "unitmarker")
        )
        if not mt:
            try:
                self.canvas.itemconfigure(marker_text, state="hidden")
            except Exception:
                pass

        self.unit_tokens[cid] = {"col": col, "row": row, "oval": oval, "text": name_text, "marker": marker_text}

        # Re-evaluate grouping + labels now that a token exists
        self._update_groups()
        self._apply_active_highlight()
        self._update_move_highlight()


    def _delete_unit_token(self, cid: int) -> None:
        tok = self.unit_tokens.get(cid)
        if not tok:
            return
        try:
            self.canvas.delete(int(tok["oval"]))
            self.canvas.delete(int(tok["text"]))
            if "marker" in tok:
                self.canvas.delete(int(tok["marker"]))
        except Exception:
            pass
        self.unit_tokens.pop(cid, None)

        # Group labels and move highlight may change when a token leaves the map
        self._update_groups()
        self._update_move_highlight()
        self._update_included_for_selected()

    # ---------------- Canvas grid & geometry ----------------
    def _compute_metrics(self) -> None:
        # Scrollable + zoomable grid: cell size comes from the zoom slider.
        try:
            self.cell = float(self.zoom_var.get())
        except Exception:
            self.cell = 32.0
        self.x0 = float(self._map_margin)
        self.y0 = float(self._map_margin)

        # Ensure the scroll region always contains the full grid plus margins.
        gw = float(self.cols) * float(self.cell)
        gh = float(self.rows) * float(self.cell)
        try:
            self.canvas.config(scrollregion=(0, 0, gw + 2 * self._map_margin, gh + 2 * self._map_margin))
        except Exception:
            pass


    def _grid_to_pixel(self, col: int, row: int) -> Tuple[float, float]:
        x = self.x0 + (col + 0.5) * self.cell
        y = self.y0 + (row + 0.5) * self.cell
        return x, y

    def _pixel_to_grid(self, x: float, y: float) -> Tuple[Optional[int], Optional[int]]:
        # x,y are canvas-local
        if x < self.x0 or y < self.y0:
            return None, None
        col = int((x - self.x0) // self.cell)
        row = int((y - self.y0) // self.cell)
        if col < 0 or row < 0 or col >= self.cols or row >= self.rows:
            return None, None
        return col, row

    def _redraw_all(self) -> None:
        self._compute_metrics()
        self.canvas.delete("grid")
        self.canvas.delete("measure")
        self.canvas.delete("movehl")
        self.canvas.delete("group")
        self.canvas.delete("rough")
        self.canvas.delete("obstacle")
        # Recreate measure items later if needed
        self._measure_items = []
        self._measure_start = None

        # Draw grid
        # border
        self.canvas.create_rectangle(
            self.x0, self.y0, self.x0 + self.cols * self.cell, self.y0 + self.rows * self.cell,
            outline="#7a5a30", width=2, tags=("grid",)
        )
        for i in range(1, self.cols):
            x = self.x0 + i * self.cell
            self.canvas.create_line(x, self.y0, x, self.y0 + self.rows * self.cell, fill="#d0c3a0", tags=("grid",))
        for j in range(1, self.rows):
            y = self.y0 + j * self.cell
            self.canvas.create_line(self.x0, y, self.x0 + self.cols * self.cell, y, fill="#d0c3a0", tags=("grid",))

        # Keep background images beneath the grid and tokens.
        try:
            self.canvas.tag_lower("bgimg", "grid")
        except Exception:
            try:
                self.canvas.tag_lower("bgimg")
            except Exception:
                pass

        # Rough terrain (slow movement)
        self._draw_rough_terrain()

        # Obstacles (block movement)
        self._draw_obstacles()

        # Move-range overlay goes above the grid but below tokens
        self._update_move_highlight()

        # Layout tokens (incl. grouping + condition markers)
        self._update_groups()

        # Layout AoEs (kept above tokens)
        for aid in list(self.aoes.keys()):
            self._layout_aoe(aid)

        self._apply_active_highlight()
        self._update_included_for_selected()


    def _layout_unit(self, cid: int) -> None:
        tok = self.unit_tokens.get(cid)
        if not tok:
            return

        col = int(tok["col"])
        row = int(tok["row"])
        x, y = self._grid_to_pixel(col, row)
        r = self.cell * 0.42

        # If multiple units share the same square, fan them slightly so they can still be selected.
        mates = self._cell_to_cids.get((col, row), [cid])
        if len(mates) > 1:
            mates2 = list(mates)
            try:
                mates2.sort()
            except Exception:
                pass
            try:
                idx = mates2.index(cid)
            except ValueError:
                idx = 0
            n = max(1, len(mates2))
            ang = (2.0 * math.pi * idx) / float(n)
            rad = self.cell * 0.18
            x = x + math.cos(ang) * rad
            y = y + math.sin(ang) * rad

        self.canvas.coords(int(tok["oval"]), x - r, y - r, x + r, y + r)

        # Name above token
        name_y = y - r - 2
        text_id = int(tok["text"])
        try:
            state = self.canvas.itemcget(text_id, "state")
        except Exception:
            state = "normal"
        prefer_show = self._active_cid == cid
        if state != "hidden" or prefer_show:
            try:
                self.canvas.itemconfigure(text_id, state="normal")
            except Exception:
                pass
            self._resolve_label_position(text_id, x, name_y, prefer_show)

        # Condition markers in the token
        if "marker" in tok:
            self.canvas.coords(int(tok["marker"]), x, y)
            try:
                mt = self._marker_text_for(cid)
                self.canvas.itemconfigure(int(tok["marker"]), text=mt, state=("normal" if mt else "hidden"))
            except Exception:
                pass
        self._sync_aoe_anchor_for_cid(cid)

    
    def _marker_text_for(self, cid: int) -> str:
        c = self.app.combatants.get(cid)
        if not c:
            return ""
        try:
            s = self.app._format_effects(c)
        except Exception:
            s = ""
        return (s or "").strip()

    def _update_groups(self) -> None:
        """Recompute shared-square groups, update group labels, and relayout all tokens."""
        cell_to: Dict[Tuple[int, int], List[int]] = {}
        for cid, tok in self.unit_tokens.items():
            try:
                col = int(tok["col"])
                row = int(tok["row"])
            except Exception:
                continue
            cell_to.setdefault((col, row), []).append(cid)

        self._cell_to_cids = cell_to

        # Clear old group labels and rebuild
        try:
            self.canvas.delete("group")
        except Exception:
            pass

        # Show/hide individual name labels
        for (col, row), cids in cell_to.items():
            if len(cids) > 1:
                for cid in cids:
                    tok = self.unit_tokens.get(cid)
                    if not tok:
                        continue
                    try:
                        if cid == self._active_cid:
                            self.canvas.itemconfigure(int(tok["text"]), state="normal")
                        else:
                            self.canvas.itemconfigure(int(tok["text"]), state="hidden")
                    except Exception:
                        pass
            else:
                cid = cids[0]
                tok = self.unit_tokens.get(cid)
                if not tok:
                    continue
                c = self.app.combatants.get(cid)
                try:
                    self.canvas.itemconfigure(int(tok["text"]), state="normal")
                    if c is not None:
                        self.canvas.itemconfigure(int(tok["text"]), text=c.name)
                except Exception:
                    pass

        self._label_bounds = []
        for cid in self.unit_tokens.keys():
            self._layout_unit(cid)

        # Create group labels
        for (col, row), cids in cell_to.items():
            if len(cids) <= 1:
                continue
            names: List[str] = []
            for cid in sorted(cids):
                c = self.app.combatants.get(cid)
                if c:
                    names.append(c.name)
            label = f"Group ({len(names)}): " + ", ".join(names)

            x, y = self._grid_to_pixel(col, row)
            r = self.cell * 0.42
            gy = y - r - 2
            try:
                gid = self.canvas.create_text(
                    x, gy,
                    text=label,
                    anchor="s",
                    width=max(120, int(self.cell * 3.8)),
                    font=("TkDefaultFont", 9, "bold"),
                    tags=("group",)
                )
                prefer_show = self._active_cid in cids
                self._resolve_label_position(gid, x, gy, prefer_show)
                self.canvas.tag_raise(gid)
            except Exception:
                pass

        self._raise_aoe_overlays()
        self._refresh_groups_panel()

    def _labels_overlap(self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    def _resolve_label_position(self, item_id: int, x: float, y: float, prefer_show: bool) -> None:
        step = max(6.0, float(self.cell) * 0.35)
        offsets = (0.0, -step, step, -2 * step, 2 * step)
        allow_hide = not bool(self.show_all_names_var.get())
        for dy in offsets:
            try:
                self.canvas.coords(item_id, x, y + dy)
            except Exception:
                continue
            bbox = self.canvas.bbox(item_id)
            if not bbox:
                continue
            if not any(self._labels_overlap(bbox, existing) for existing in self._label_bounds):
                self._label_bounds.append(bbox)
                return
        if allow_hide and not prefer_show:
            try:
                self.canvas.itemconfigure(item_id, state="hidden")
            except Exception:
                pass
            return
        try:
            self.canvas.coords(item_id, x, y)
        except Exception:
            return
        bbox = self.canvas.bbox(item_id)
        if bbox:
            self._label_bounds.append(bbox)

    def _refresh_groups_panel(self) -> None:
        if not hasattr(self, "group_cells_list"):
            return
        self._suspend_group_ui = True
        try:
            grouped_cells = [
                (cell, cids)
                for cell, cids in sorted(self._cell_to_cids.items(), key=lambda item: (item[0][1], item[0][0]))
                if len(cids) > 1
            ]
            self.group_cells_list.delete(0, tk.END)
            self._group_cells_index = []
            for (col, row), cids in grouped_cells:
                self.group_cells_list.insert(tk.END, f"({col},{row}) — {len(cids)} members")
                self._group_cells_index.append((col, row))

            if self._selected_group_cell in self._group_cells_index:
                idx = self._group_cells_index.index(self._selected_group_cell)
                self.group_cells_list.selection_set(idx)
                self.group_cells_list.activate(idx)
            else:
                self._selected_group_cell = None
                self.group_cells_list.selection_clear(0, tk.END)

            self._refresh_group_members_list()
        finally:
            self._suspend_group_ui = False

    def _refresh_group_members_list(self) -> None:
        if not hasattr(self, "group_members_list"):
            return
        self.group_members_list.delete(0, tk.END)
        self._group_members_index = []
        if self._selected_group_cell is None:
            self._group_preferred_cid = None
            return
        cids = list(self._cell_to_cids.get(self._selected_group_cell, []))
        if len(cids) <= 1:
            self._selected_group_cell = None
            self._group_preferred_cid = None
            return
        order = [c.cid for c in self.app._display_order()] if hasattr(self.app, "_display_order") else []
        order_index = {cid: i for i, cid in enumerate(order)}
        cids.sort(key=lambda cid: order_index.get(cid, 10**9))
        for cid in cids:
            c = self.app.combatants.get(cid)
            name = c.name if c else f"#{cid}"
            self.group_members_list.insert(tk.END, f"{name} [#{cid}]")
            self._group_members_index.append(cid)
        if self._group_preferred_cid in self._group_members_index:
            idx = self._group_members_index.index(self._group_preferred_cid)
            self.group_members_list.selection_set(idx)
            self.group_members_list.activate(idx)
        else:
            self._group_preferred_cid = None
            self.group_members_list.selection_clear(0, tk.END)

    def _on_group_cell_select(self) -> None:
        if self._suspend_group_ui:
            return
        selection = self.group_cells_list.curselection()
        if not selection:
            self._selected_group_cell = None
            self._group_preferred_cid = None
            self._refresh_group_members_list()
            return
        idx = int(selection[0])
        if idx < 0 or idx >= len(self._group_cells_index):
            return
        self._selected_group_cell = self._group_cells_index[idx]
        self._refresh_group_members_list()

    def _on_group_member_select(self) -> None:
        if self._suspend_group_ui:
            return
        selection = self.group_members_list.curselection()
        if not selection:
            self._group_preferred_cid = None
            return
        idx = int(selection[0])
        if idx < 0 or idx >= len(self._group_members_index):
            return
        cid = self._group_members_index[idx]
        self._group_preferred_cid = cid
        self.set_active(cid)


    def _movement_cost_map(
        self,
        start_col: int,
        start_row: int,
        max_ft: int,
        creature: Optional[Combatant] = None,
    ) -> Dict[Tuple[int, int], int]:
        """
        Compute minimal movement cost (in feet) from a start square to all squares, up to max_ft.

        Uses the common 5e diagonal rule: diagonals alternate 5/10 ft (scaled by feet_per_square).
        Blocks movement through obstacles, applies swim/rough terrain multipliers, and prevents
        corner-cutting around obstacle squares.
        """
        import heapq

        step = int(self.feet_per_square)
        diag5 = step
        diag10 = step * 2

        # State includes diagonal parity: 0 -> next diagonal costs 5, 1 -> next diagonal costs 10
        start = (start_col, start_row, 0)
        pq: List[Tuple[int, int, int, int]] = [(0, start_col, start_row, 0)]
        best: Dict[Tuple[int, int, int], int] = {start: 0}
        best_sq: Dict[Tuple[int, int], int] = {(start_col, start_row): 0}

        obstacles = getattr(self, "obstacles", set()) or set()
        rough_terrain = getattr(self, "rough_terrain", {}) or {}
        mode = self.app._normalize_movement_mode(getattr(creature, "movement_mode", "normal"))
        water_multiplier = self.app._water_movement_multiplier(creature, mode)

        while pq:
            cost, col, row, parity = heapq.heappop(pq)
            if cost != best.get((col, row, parity), None):
                continue
            if cost > max_ft:
                continue

            prev = best_sq.get((col, row))
            if prev is None or cost < prev:
                best_sq[(col, row)] = cost

            for dc, dr, is_diag in (
                (-1, 0, False), (1, 0, False), (0, -1, False), (0, 1, False),
                (-1, -1, True), (1, -1, True), (-1, 1, True), (1, 1, True),
            ):
                nc, nr = col + dc, row + dr
                if nc < 0 or nr < 0 or nc >= self.cols or nr >= self.rows:
                    continue
                if (nc, nr) in obstacles:
                    continue

                # no corner-cutting
                if is_diag:
                    if (col + dc, row) in obstacles or (col, row + dr) in obstacles:
                        continue
                    step_cost = diag5 if parity == 0 else diag10
                    npar = 1 - parity
                else:
                    step_cost = step
                    npar = parity

                current_cell = self._rough_cell_data(rough_terrain.get((col, row)))
                target_cell = self._rough_cell_data(rough_terrain.get((nc, nr)))
                current_type = current_cell.get("movement_type")
                target_type = target_cell.get("movement_type")
                if mode == "swim" and target_type != "water":
                    continue
                if mode == "burrow" and target_type == "water":
                    continue
                if mode != "fly":
                    if current_type == "water" or target_type == "water":
                        step_cost = int(math.ceil(step_cost * water_multiplier))
                    if bool(target_cell.get("is_rough")):
                        step_cost *= 2

                ncost = cost + step_cost
                if ncost > max_ft:
                    continue
                key = (nc, nr, npar)
                if ncost < best.get(key, 10**9):
                    best[key] = ncost
                    heapq.heappush(pq, (ncost, nc, nr, npar))

        return best_sq

    def _update_move_highlight(self) -> None:
        """Highlight reachable squares for the active creature, based on its remaining movement."""
        try:
            self.canvas.delete("movehl")
        except Exception:
            pass
        self._movehl_items = []

        if self._active_cid is None:
            return
        if self._active_cid not in self.unit_tokens:
            return

        c = self.app.combatants.get(self._active_cid)
        if not c:
            return

        move_ft = int(getattr(c, "move_remaining", 0) or 0)
        if move_ft <= 0:
            return

        tok = self.unit_tokens[self._active_cid]
        col0 = int(tok["col"])
        row0 = int(tok["row"])

        cost_map = self._movement_cost_map(col0, row0, move_ft, c)

        for (col, row), cost in cost_map.items():
            if cost <= 0:
                continue
            x1 = self.x0 + col * self.cell
            y1 = self.y0 + row * self.cell
            x2 = x1 + self.cell
            y2 = y1 + self.cell
            try:
                rid = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill="#74c0fc",
                    outline="",
                    stipple="gray25",
                    tags=("movehl",)
                )
                self._movehl_items.append(rid)
            except Exception:
                pass

        # Keep the overlay above the grid/obstacles but below tokens
        try:
            self.canvas.tag_raise("movehl", "grid")
            self.canvas.tag_lower("movehl", "unit")
            self.canvas.tag_lower("movehl", "rough")
        except Exception:
            try:
                self.canvas.tag_raise("movehl")
            except Exception:
                pass

    def _movement_cost_between(
        self,
        origin: Tuple[int, int],
        dest: Tuple[int, int],
        max_ft: int,
        creature: Optional[Combatant] = None,
    ) -> Optional[int]:
        if origin == dest:
            return 0
        cost_map = self._movement_cost_map(origin[0], origin[1], max_ft, creature)
        return cost_map.get(dest)

    def _aoe_default_color(self, kind: str) -> str:
        return str(self._aoe_default_colors.get(kind, "#2d4f8a"))

    def _aoe_fill_color(self, kind: str) -> str:
        return str(self._aoe_fill_colors.get(kind, "#e2b6ff"))

    def _normalize_aoe_color(self, color: object, kind: str) -> str:
        if isinstance(color, str):
            cleaned = color.strip()
            if cleaned:
                return cleaned
        return self._aoe_default_color(kind)

    def _sync_aoe_color_ui(self, aid: Optional[int]) -> None:
        combo = getattr(self, "aoe_color_combo", None)
        var = getattr(self, "aoe_color_var", None)
        if combo is None or var is None:
            return
        if aid is None or aid not in self.aoes:
            var.set("")
            try:
                combo.state(["disabled"])
            except Exception:
                combo.config(state=tk.DISABLED)
            return
        d = self.aoes[aid]
        kind = str(d.get("kind") or "")
        color = self._normalize_aoe_color(d.get("color"), kind)
        d["color"] = color
        label = self._aoe_label_by_color.get(color)
        if label is None:
            label = self._aoe_color_labels[0] if self._aoe_color_labels else color
        var.set(label)
        try:
            combo.state(["!disabled"])
        except Exception:
            combo.config(state=tk.NORMAL)

    def _sync_aoe_duration_ui(self, aid: Optional[int]) -> None:
        entry = getattr(self, "aoe_duration_ent", None)
        var = getattr(self, "aoe_duration_var", None)
        if entry is None or var is None:
            return
        if aid is None or aid not in self.aoes:
            var.set("")
            try:
                entry.state(["disabled"])
            except Exception:
                entry.config(state=tk.DISABLED)
            return
        duration = self.aoes[aid].get("duration_turns")
        if duration is None:
            var.set("")
        else:
            var.set(str(duration))
        try:
            entry.state(["!disabled"])
        except Exception:
            entry.config(state=tk.NORMAL)

    def _apply_aoe_duration(self) -> None:
        aid = self._selected_aoe
        if aid is None or aid not in self.aoes:
            return
        raw = str(self.aoe_duration_var.get() or "").strip()
        if raw == "":
            duration = None
        else:
            try:
                duration = int(raw)
            except Exception:
                messagebox.showerror("AoE Duration", "Duration must be an integer (0=indefinite).", parent=self)
                self._sync_aoe_duration_ui(aid)
                return
            if duration < 0:
                messagebox.showerror("AoE Duration", "Duration must be 0 or greater.", parent=self)
                self._sync_aoe_duration_ui(aid)
                return
        self.aoes[aid]["duration_turns"] = duration
        self._refresh_aoe_list(select=aid)

    def _apply_aoe_color(self, aid: int) -> None:
        d = self.aoes.get(aid)
        if not d:
            return
        kind = str(d.get("kind") or "")
        color = self._normalize_aoe_color(d.get("color"), kind)
        d["color"] = color
        try:
            self.canvas.itemconfigure(int(d["shape"]), outline=color)
        except Exception:
            pass
        try:
            self.canvas.itemconfigure(int(d["label"]), fill=color)
        except Exception:
            pass

    def _on_aoe_color_change(self) -> None:
        aid = self._selected_aoe
        if aid is None or aid not in self.aoes:
            return
        label = str(self.aoe_color_var.get() or "")
        color = self._aoe_color_by_label.get(label)
        if not color:
            return
        self.aoes[aid]["color"] = color
        self._apply_aoe_color(aid)

    def _prompt_circle_aoe_params(self, title: str = "Circle AoE") -> Optional[Tuple[int, str]]:
        """Prompt for circle size and whether it's radius or diameter (required, mutually exclusive)."""
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("420x220")
        dlg.minsize(380, 200)
        dlg.transient(self)

        out: dict[str, object] = {"value": None, "mode": "radius"}

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Enter size (ft):").grid(row=0, column=0, sticky="w")
        val_var = tk.StringVar(value="20")
        ent = ttk.Entry(frm, textvariable=val_var, width=10)
        ent.grid(row=0, column=1, sticky="w", padx=(6, 0))

        mode_var = tk.StringVar(value="radius")
        mode_box = ttk.Frame(frm)
        mode_box.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(mode_box, text="Interpret as:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_box, text="Radius", variable=mode_var, value="radius").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(mode_box, text="Diameter", variable=mode_var, value="diameter").pack(side=tk.LEFT, padx=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

        def on_ok() -> None:
            raw = (val_var.get() or "").strip()
            try:
                v = int(raw)
            except Exception:
                messagebox.showerror("Circle AoE", "Size must be an integer (ft).", parent=dlg)
                return
            if v <= 0:
                messagebox.showerror("Circle AoE", "Size must be greater than 0.", parent=dlg)
                return
            out["value"] = v
            out["mode"] = mode_var.get()
            dlg.destroy()

        def on_cancel() -> None:
            out["value"] = None
            dlg.destroy()

        ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=(8, 0))

        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: on_cancel())
        try:
            ent.focus_set()
            ent.select_range(0, tk.END)
        except Exception:
            pass

        self.wait_window(dlg)
        if out["value"] is None:
            return None
        return int(out["value"]), str(out["mode"])

    # ---------------- AoE overlays ----------------
    def _add_circle_aoe(self) -> None:
        res = self._prompt_circle_aoe_params()
        if res is None:
            return
        ft, mode = res
        radius_ft = float(ft) / 2.0 if mode == "diameter" else float(ft)
        radius_sq = max(0.5, radius_ft / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        # place at center
        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        self.aoes[aid] = {"kind": "circle", "radius_sq": radius_sq, "cx": cx, "cy": cy, "pinned": False,
                          "color": self._aoe_default_color("circle"),
                          "name": f"AoE {aid}", "shape": None, "label": None,
                          "duration_turns": None, "remaining_turns": None}
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)

    def _add_sphere_aoe(self) -> None:
        res = self._prompt_circle_aoe_params("Sphere AoE")
        if res is None:
            return
        ft, mode = res
        radius_ft = float(ft) / 2.0 if mode == "diameter" else float(ft)
        radius_sq = max(0.5, radius_ft / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        self.aoes[aid] = {"kind": "sphere", "radius_sq": radius_sq, "cx": cx, "cy": cy, "pinned": False,
                          "color": self._aoe_default_color("sphere"),
                          "name": f"AoE {aid}", "shape": None, "label": None,
                          "duration_turns": None, "remaining_turns": None}
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)

    def _add_cube_aoe(self) -> None:
        ft = simpledialog.askinteger("Cube AoE", "Enter side length (ft):", initialvalue=15, minvalue=5, maxvalue=1000, parent=self)
        if ft is None:
            return
        side_sq = max(1.0, float(ft) / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        self.aoes[aid] = {"kind": "cube", "side_sq": side_sq, "cx": cx, "cy": cy, "pinned": False,
                          "color": self._aoe_default_color("cube"),
                          "name": f"AoE {aid}", "shape": None, "label": None,
                          "duration_turns": None, "remaining_turns": None}
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)

    def _add_square_aoe(self) -> None:
        ft = simpledialog.askinteger("Square AoE", "Enter side length (ft):", initialvalue=15, minvalue=5, maxvalue=1000, parent=self)
        if ft is None:
            return
        side_sq = max(1.0, float(ft) / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        self.aoes[aid] = {"kind": "square", "side_sq": side_sq, "cx": cx, "cy": cy, "pinned": False,
                          "color": self._aoe_default_color("square"),
                          "name": f"AoE {aid}", "shape": None, "label": None,
                          "duration_turns": None, "remaining_turns": None}
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)


    def _prompt_cone_aoe_params(self) -> Optional[Tuple[int, int, str]]:
        """Prompt for cone length and angle (degrees), plus orientation."""
        dlg = tk.Toplevel(self)
        dlg.title("Cone AoE")
        dlg.geometry("460x260")
        dlg.minsize(420, 230)
        dlg.transient(self)

        out: Dict[str, Optional[Union[int, str]]] = {"length": None, "angle": None, "orient": "vertical"}

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Length (ft):").grid(row=0, column=0, sticky="w")
        length_var = tk.StringVar(value="30")
        length_ent = ttk.Entry(frm, textvariable=length_var, width=10)
        length_ent.grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(frm, text="Angle (deg):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        angle_var = tk.StringVar(value="90")
        angle_ent = ttk.Entry(frm, textvariable=angle_var, width=10)
        angle_ent.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        orient_var = tk.StringVar(value="vertical")
        orient_box = ttk.Frame(frm)
        orient_box.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(orient_box, text="Orientation:").pack(side=tk.LEFT)
        ttk.Radiobutton(orient_box, text="Horizontal", variable=orient_var, value="horizontal").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(orient_box, text="Vertical", variable=orient_var, value="vertical").pack(side=tk.LEFT, padx=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def on_ok() -> None:
            try:
                L = int((length_var.get() or "").strip())
                A = int((angle_var.get() or "").strip())
            except Exception:
                messagebox.showerror("Cone AoE", "Length/Angle must be integers.", parent=dlg)
                return
            if L <= 0 or A <= 0:
                messagebox.showerror("Cone AoE", "Length/Angle must be positive.", parent=dlg)
                return
            out["length"] = L
            out["angle"] = A
            out["orient"] = str(orient_var.get() or "vertical")
            dlg.destroy()

        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=(0, 8))

        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.after(150, lambda: (length_ent.focus_set(), length_ent.select_range(0, tk.END)))
        self.wait_window(dlg)

        if out["length"] is None or out["angle"] is None:
            return None
        return int(out["length"]), int(out["angle"]), str(out["orient"])

    def _prompt_line_aoe_params(self) -> Optional[Tuple[int, int, str]]:
        """Prompt for line AoE length and width in feet, and orientation (horizontal/vertical)."""
        dlg = tk.Toplevel(self)
        dlg.title("Line AoE")
        dlg.geometry("460x260")
        dlg.minsize(420, 230)
        dlg.transient(self)

        out: Dict[str, Optional[Union[int, str]]] = {"length": None, "width": None, "orient": "vertical"}

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Length (ft):").grid(row=0, column=0, sticky="w")
        length_var = tk.StringVar(value="100")
        length_ent = ttk.Entry(frm, textvariable=length_var, width=10)
        length_ent.grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(frm, text="Width (ft):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        width_var = tk.StringVar(value="5")
        width_ent = ttk.Entry(frm, textvariable=width_var, width=10)
        width_ent.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        orient_var = tk.StringVar(value="vertical")
        orient_box = ttk.Frame(frm)
        orient_box.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(orient_box, text="Orientation:").pack(side=tk.LEFT)
        ttk.Radiobutton(orient_box, text="Horizontal", variable=orient_var, value="horizontal").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(orient_box, text="Vertical", variable=orient_var, value="vertical").pack(side=tk.LEFT, padx=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def on_ok() -> None:
            try:
                L = int((length_var.get() or "").strip())
                W = int((width_var.get() or "").strip())
            except Exception:
                messagebox.showerror("Line AoE", "Length/Width must be integers (ft).", parent=dlg)
                return
            if L <= 0 or W <= 0:
                messagebox.showerror("Line AoE", "Length/Width must be positive.", parent=dlg)
                return
            out["length"] = L
            out["width"] = W
            out["orient"] = str(orient_var.get() or "vertical")
            dlg.destroy()

        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=(0, 8))

        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.after(150, lambda: (length_ent.focus_set(), length_ent.select_range(0, tk.END)))
        self.wait_window(dlg)

        if out["length"] is None or out["width"] is None:
            return None
        return int(out["length"]), int(out["width"]), str(out["orient"])

    def _prompt_wall_aoe_params(self) -> Optional[Tuple[int, int, Optional[int], str]]:
        """Prompt for wall AoE length, width, optional height, and orientation."""
        dlg = tk.Toplevel(self)
        dlg.title("Wall AoE")
        dlg.geometry("460x280")
        dlg.minsize(420, 240)
        dlg.transient(self)

        out: Dict[str, Optional[Union[int, str]]] = {"length": None, "width": None, "height": None, "orient": "vertical"}

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Length (ft):").grid(row=0, column=0, sticky="w")
        length_var = tk.StringVar(value="30")
        length_ent = ttk.Entry(frm, textvariable=length_var, width=10)
        length_ent.grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(frm, text="Width (ft):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        width_var = tk.StringVar(value="5")
        width_ent = ttk.Entry(frm, textvariable=width_var, width=10)
        width_ent.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        ttk.Label(frm, text="Height (ft, optional):").grid(row=2, column=0, sticky="w", pady=(8, 0))
        height_var = tk.StringVar(value="")
        height_ent = ttk.Entry(frm, textvariable=height_var, width=10)
        height_ent.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        orient_var = tk.StringVar(value="vertical")
        orient_box = ttk.Frame(frm)
        orient_box.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(orient_box, text="Orientation:").pack(side=tk.LEFT)
        ttk.Radiobutton(orient_box, text="Horizontal", variable=orient_var, value="horizontal").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(orient_box, text="Vertical", variable=orient_var, value="vertical").pack(side=tk.LEFT, padx=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def on_ok() -> None:
            try:
                L = int((length_var.get() or "").strip())
                W = int((width_var.get() or "").strip())
            except Exception:
                messagebox.showerror("Wall AoE", "Length/Width must be integers (ft).", parent=dlg)
                return
            if L <= 0 or W <= 0:
                messagebox.showerror("Wall AoE", "Length/Width must be positive.", parent=dlg)
                return
            H = None
            height_raw = (height_var.get() or "").strip()
            if height_raw:
                try:
                    H = int(height_raw)
                except Exception:
                    messagebox.showerror("Wall AoE", "Height must be an integer (ft).", parent=dlg)
                    return
                if H <= 0:
                    messagebox.showerror("Wall AoE", "Height must be positive.", parent=dlg)
                    return
            out["length"] = L
            out["width"] = W
            out["height"] = H
            out["orient"] = str(orient_var.get() or "vertical")
            dlg.destroy()

        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=(0, 8))

        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.after(150, lambda: (length_ent.focus_set(), length_ent.select_range(0, tk.END)))
        self.wait_window(dlg)

        if out["length"] is None or out["width"] is None:
            return None
        return int(out["length"]), int(out["width"]), out.get("height"), str(out["orient"])

    def _add_line_aoe(self) -> None:
        res = self._prompt_line_aoe_params()
        if res is None:
            return
        length_ft, width_ft, orient = res
        length_sq = max(1.0, float(length_ft) / self.feet_per_square)
        width_sq = max(1.0, float(width_ft) / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        angle_deg = 0.0 if orient == "horizontal" else 90.0
        angle_rad = math.radians(angle_deg)
        half_len = length_sq / 2.0
        ax = cx - math.cos(angle_rad) * half_len
        ay = cy - math.sin(angle_rad) * half_len
        self.aoes[aid] = {
            "kind": "line",
            "length_sq": length_sq,
            "width_sq": width_sq,
            "orient": orient,
            "angle_deg": angle_deg,
            "ax": ax,
            "ay": ay,
            "cx": cx,
            "cy": cy,
            "pinned": False,
            "color": self._aoe_default_color("line"),
            "name": f"AoE {aid}",
            "shape": None,
            "label": None,
            "duration_turns": None,
            "remaining_turns": None,
        }
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)

    def _add_wall_aoe(self) -> None:
        res = self._prompt_wall_aoe_params()
        if res is None:
            return
        length_ft, width_ft, height_ft, orient = res
        length_sq = max(1.0, float(length_ft) / self.feet_per_square)
        width_sq = max(1.0, float(width_ft) / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        self.aoes[aid] = {
            "kind": "wall",
            "length_sq": length_sq,
            "width_sq": width_sq,
            "orient": orient,
            "angle_deg": 0.0 if orient == "horizontal" else 90.0,
            "ax": cx,
            "ay": cy,
            "cx": cx,
            "cy": cy,
            "pinned": False,
            "color": self._aoe_default_color("wall"),
            "name": f"AoE {aid}",
            "shape": None,
            "label": None,
            "duration_turns": None,
            "remaining_turns": None,
        }
        if height_ft is not None:
            self.aoes[aid]["height_ft"] = float(height_ft)
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)

    def _add_cone_aoe(self) -> None:
        res = self._prompt_cone_aoe_params()
        if res is None:
            return
        length_ft, angle_deg, orient = res
        length_sq = max(1.0, float(length_ft) / self.feet_per_square)

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        self.aoes[aid] = {
            "kind": "cone",
            "length_sq": length_sq,
            "angle_deg": float(angle_deg),
            "orient": orient,
            "ax": cx,
            "ay": cy,
            "cx": cx,
            "cy": cy,
            "pinned": False,
            "color": self._aoe_default_color("cone"),
            "name": f"AoE {aid}",
            "shape": None,
            "label": None,
            "duration_turns": None,
            "remaining_turns": None,
        }
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)


    def _create_aoe_items(self, aid: int) -> None:
        d = self.aoes[aid]
        kind = str(d["kind"])
        color = self._normalize_aoe_color(d.get("color"), kind)
        d["color"] = color
        shape_id: int
        label_id: int

        # initial placeholder coords, then layout
        if kind in ("circle", "sphere", "cylinder"):
            shape_id = self.canvas.create_oval(0, 0, 1, 1, outline=color, width=3, dash=(6, 4),
                                               fill=self._aoe_fill_color(kind), stipple="gray25",
                                               tags=(f"aoe:{aid}", "aoe"))
        elif kind == "line" or kind == "wall":
            shape_id = self.canvas.create_polygon(0, 0, 1, 1, 2, 2, 3, 3, outline=color, width=3, dash=(6, 4),
                                                  fill=self._aoe_fill_color(kind), stipple="gray25",
                                                  tags=(f"aoe:{aid}", "aoe"))
        elif kind == "cone":
            shape_id = self.canvas.create_arc(
                0,
                0,
                1,
                1,
                start=0,
                extent=90,
                style=tk.PIESLICE,
                outline=color,
                width=3,
                dash=(6, 4),
                fill=self._aoe_fill_color(kind),
                stipple="gray25",
                tags=(f"aoe:{aid}", "aoe"),
            )
        elif kind in ("square", "cube"):
            shape_id = self.canvas.create_polygon(0, 0, 1, 1, 2, 2, 3, 3, outline=color, width=3, dash=(6, 4),
                                                  fill=self._aoe_fill_color(kind), stipple="gray25",
                                                  tags=(f"aoe:{aid}", "aoe"))
        else:
            shape_id = self.canvas.create_rectangle(0, 0, 1, 1, outline=color, width=3, dash=(6, 4),
                                                    fill=self._aoe_fill_color(kind), stipple="gray25",
                                                    tags=(f"aoe:{aid}", "aoe"))
        label_id = self.canvas.create_text(0, 0, text=str(d.get("name") or f"AoE {aid}"), font=("TkDefaultFont", 9, "bold"),
                                           fill=color, tags=(f"aoe:{aid}", "aoelabel"))

        d["shape"] = shape_id
        d["label"] = label_id
        self._layout_aoe(aid)

    def _resolve_aoe_anchor(self, d: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        anchor_cid = d.get("anchor_cid")
        if anchor_cid is None:
            return None
        try:
            cid = int(anchor_cid)
        except Exception:
            return None
        tok = self.unit_tokens.get(cid)
        if not tok:
            return None
        try:
            ax = float(tok.get("col"))
            ay = float(tok.get("row"))
        except Exception:
            return None
        d["ax"] = ax
        d["ay"] = ay
        return ax, ay

    def _sync_aoe_anchor_for_cid(self, cid: int) -> None:
        tok = self.unit_tokens.get(cid)
        if not tok:
            return
        try:
            ax = float(tok.get("col"))
            ay = float(tok.get("row"))
        except Exception:
            return
        updated = False
        for aid, d in list(self.aoes.items()):
            if d.get("anchor_cid") is None:
                continue
            try:
                if int(d.get("anchor_cid")) != int(cid):
                    continue
            except Exception:
                continue
            kind = str(d.get("kind") or "")
            d["ax"] = ax
            d["ay"] = ay
            if kind == "line":
                length_sq = float(d.get("length_sq") or 0.0)
                angle = d.get("angle_deg")
                orient = str(d.get("orient") or "vertical")
                if angle is None:
                    angle = 0.0 if orient == "horizontal" else 90.0
                angle_rad = math.radians(float(angle))
                half_len = length_sq / 2.0
                cx = ax + math.cos(angle_rad) * half_len
                cy = ay + math.sin(angle_rad) * half_len
                d["cx"] = cx
                d["cy"] = cy
            elif kind == "cone":
                d["cx"] = ax
                d["cy"] = ay
            updated = True
            self._layout_aoe(aid)
        if updated:
            self._update_included_for_selected()

    def _layout_aoe(self, aid: int) -> None:
        d = self.aoes.get(aid)
        if not d:
            return
        kind = str(d["kind"])
        anchor = None
        if kind in ("line", "cone"):
            anchor = self._resolve_aoe_anchor(d)
            if anchor is not None:
                ax, ay = anchor
                if kind == "line":
                    length_sq = float(d.get("length_sq") or 0.0)
                    angle = d.get("angle_deg")
                    orient = str(d.get("orient") or "vertical")
                    if angle is None:
                        angle = 0.0 if orient == "horizontal" else 90.0
                    angle_rad = math.radians(float(angle))
                    half_len = length_sq / 2.0
                    cx = ax + math.cos(angle_rad) * half_len
                    cy = ay + math.sin(angle_rad) * half_len
                    d["cx"] = cx
                    d["cy"] = cy
                else:
                    d["cx"] = ax
                    d["cy"] = ay
        if kind == "cone" and anchor is None:
            d["ax"] = float(d.get("cx", 0.0))
            d["ay"] = float(d.get("cy", 0.0))
        cx = float(d["cx"])
        cy = float(d["cy"])
        x = self.x0 + (cx + 0.5) * self.cell
        y = self.y0 + (cy + 0.5) * self.cell

        if kind in ("circle", "sphere", "cylinder"):
            r = float(d["radius_sq"]) * self.cell
            self.canvas.coords(int(d["shape"]), x - r, y - r, x + r, y + r)
        elif kind == "line" or kind == "wall":
            length_px = float(d["length_sq"]) * self.cell
            width_px = float(d["width_sq"]) * self.cell
            orient = str(d.get("orient") or "vertical")
            angle = d.get("angle_deg")
            if angle is None:
                angle = 0.0 if orient == "horizontal" else 90.0
            angle_rad = math.radians(float(angle))
            dx = math.cos(angle_rad)
            dy = math.sin(angle_rad)
            half_len = length_px / 2.0
            half_w = width_px / 2.0
            px = -dy
            py = dx
            p1 = (x + dx * half_len + px * half_w, y + dy * half_len + py * half_w)
            p2 = (x + dx * half_len - px * half_w, y + dy * half_len - py * half_w)
            p3 = (x - dx * half_len - px * half_w, y - dy * half_len - py * half_w)
            p4 = (x - dx * half_len + px * half_w, y - dy * half_len + py * half_w)
            self.canvas.coords(int(d["shape"]), p1[0], p1[1], p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])
        elif kind == "cone":
            length_px = float(d["length_sq"]) * self.cell
            spread_deg = d.get("spread_deg")
            has_spread = spread_deg is not None
            if spread_deg is None:
                spread_deg = d.get("angle_deg")
            if spread_deg is None:
                spread_deg = 90.0
            else:
                spread_deg = float(spread_deg)
            orient = str(d.get("orient") or "vertical")
            heading_deg = 0.0 if orient == "horizontal" else -90.0
            if has_spread:
                angle = d.get("angle_deg")
                if angle is not None:
                    heading_deg = float(angle)
            # Match LAN client convention: 0° = east/right, +90° = south/down.
            # Tk uses CCW-positive degrees, so invert heading and sweep clockwise.
            start = -heading_deg + (spread_deg / 2.0)
            self.canvas.coords(int(d["shape"]), x - length_px, y - length_px, x + length_px, y + length_px)
            try:
                self.canvas.itemconfigure(int(d["shape"]), start=start, extent=-spread_deg)
            except Exception:
                pass
        else:
            half = float(d["side_sq"]) * self.cell / 2.0
            angle = d.get("angle_deg") if kind in ("square", "cube") else None
            angle_rad = math.radians(float(angle)) if angle is not None else 0.0
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
            points: List[float] = []
            for px, py in corners:
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                points.extend([x + rx, y + ry])
            self.canvas.coords(int(d["shape"]), *points)

        self.canvas.coords(int(d["label"]), x, y)
        self._raise_aoe_overlays()

    def _raise_aoe_overlays(self) -> None:
        ref_tag = None
        try:
            if self.canvas.find_withtag("unitmarker"):
                ref_tag = "unitmarker"
            elif self.canvas.find_withtag("unitname"):
                ref_tag = "unitname"
            elif self.canvas.find_withtag("unit"):
                ref_tag = "unit"
        except Exception:
            ref_tag = None
        if ref_tag is None:
            return
        for aid in list(self.aoes.keys()):
            try:
                self.canvas.tag_lower(f"aoe:{aid}", ref_tag)
            except Exception:
                pass

    def _aoe_move_mode_active(self) -> bool:
        return bool(getattr(self, "aoe_move_var", None) and self.aoe_move_var.get())

    def _spell_aoe_presets(self) -> List[Dict[str, Any]]:
        app = getattr(self, "app", None)
        if app is None or not hasattr(app, "_spell_presets_payload"):
            return []
        try:
            presets = app._spell_presets_payload()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for entry in presets:
            if not isinstance(entry, dict):
                continue
            # AoE placement only needs shape + dimensions; ignore automation/range flags.
            shape = str(entry.get("shape") or "").strip().lower()
            if not shape:
                continue
            if shape not in ("circle", "square", "line", "sphere", "cube", "cone", "cylinder", "wall"):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            out.append(entry)
        out.sort(key=lambda p: str(p.get("name") or "").lower())
        return out

    def refresh_spell_overlays(self) -> None:
        combo = getattr(self, "aoe_spell_combo", None)
        var = getattr(self, "aoe_spell_var", None)
        if combo is None or var is None:
            return
        presets = self._spell_aoe_presets()
        labels = [str(entry.get("name") or "") for entry in presets if str(entry.get("name") or "").strip()]
        self._aoe_spell_labels = labels
        self._aoe_spell_by_label = {label: preset for label, preset in zip(labels, presets)}
        combo.configure(values=labels)
        if not labels:
            var.set("")
            try:
                combo.state(["disabled"])
            except Exception:
                combo.config(state=tk.DISABLED)
            return
        if var.get() not in labels:
            var.set("")
        try:
            combo.state(["!disabled"])
        except Exception:
            combo.config(state=tk.NORMAL)

    def _add_spell_aoe_from_combo(self) -> None:
        var = getattr(self, "aoe_spell_var", None)
        if var is None:
            return
        label = str(var.get() or "").strip()
        preset = self._aoe_spell_by_label.get(label)
        if not preset:
            return
        self._add_spell_aoe(preset)

    def _add_spell_aoe(self, preset: Dict[str, Any]) -> None:
        name = str(preset.get("name") or "").strip()
        shape = str(preset.get("shape") or "").strip().lower()
        if not name or not shape:
            return
        feet = float(self.feet_per_square) if self.feet_per_square else 5.0
        if feet <= 0:
            feet = 5.0
        radius_ft = preset.get("radius_ft")
        side_ft = preset.get("side_ft")
        length_ft = preset.get("length_ft")
        width_ft = preset.get("width_ft")
        height_ft = preset.get("height_ft")
        angle_deg = preset.get("angle_deg")
        color = str(preset.get("color") or "").strip()
        if not color:
            color = self._aoe_default_color(shape)

        def _to_float(value: Any) -> Optional[float]:
            try:
                num = float(value)
            except Exception:
                return None
            if not (num == num and abs(num) != float("inf")):
                return None
            return num

        radius_val = _to_float(radius_ft)
        side_val = _to_float(side_ft)
        length_val = _to_float(length_ft)
        width_val = _to_float(width_ft)
        height_val = _to_float(height_ft)
        angle_val = _to_float(angle_deg)

        cx = (self.cols - 1) / 2.0
        cy = (self.rows - 1) / 2.0

        aid = self._next_aoe_id
        self._next_aoe_id += 1

        app = getattr(self, "app", None)
        owner_cid = None
        if app is not None:
            current_cid = getattr(app, "current_cid", None)
            if current_cid in getattr(app, "combatants", {}):
                owner_cid = current_cid
        aoe: Dict[str, Any] = {
            "kind": shape,
            "cx": cx,
            "cy": cy,
            "pinned": False,
            "color": color,
            "name": name,
            "shape": None,
            "label": None,
            "duration_turns": None,
            "remaining_turns": None,
            "from_spell": True,
            "owner_cid": owner_cid,
        }

        if shape in ("circle", "sphere", "cylinder"):
            if radius_val is None or radius_val <= 0:
                messagebox.showinfo("Spell AoE", "Selected spell is missing a radius.", parent=self)
                return
            aoe["radius_sq"] = max(0.5, radius_val / feet)
            aoe["radius_ft"] = radius_val
            if shape == "cylinder" and height_val is not None:
                aoe["height_ft"] = height_val
        elif shape in ("square", "cube"):
            if side_val is None or side_val <= 0:
                messagebox.showinfo("Spell AoE", "Selected spell is missing a side length.", parent=self)
                return
            aoe["side_sq"] = max(1.0, side_val / feet)
            aoe["side_ft"] = side_val
        elif shape == "cone":
            if length_val is None or length_val <= 0:
                messagebox.showinfo("Spell AoE", "Selected spell is missing a cone length.", parent=self)
                return
            aoe["length_sq"] = max(1.0, length_val / feet)
            aoe["length_ft"] = length_val
            aoe["angle_deg"] = angle_val if angle_val is not None else 90.0
            aoe["orient"] = "vertical"
            aoe["ax"] = cx
            aoe["ay"] = cy
        elif shape in ("line", "wall"):
            if length_val is None or length_val <= 0:
                messagebox.showinfo("Spell AoE", "Selected spell is missing a length.", parent=self)
                return
            if width_val is None or width_val <= 0:
                messagebox.showinfo("Spell AoE", "Selected spell is missing a width.", parent=self)
                return
            aoe["length_sq"] = max(1.0, length_val / feet)
            aoe["width_sq"] = max(1.0, width_val / feet)
            aoe["length_ft"] = length_val
            aoe["width_ft"] = width_val
            aoe["orient"] = "vertical"
            aoe["ax"] = cx
            aoe["ay"] = cy
            if angle_val is not None:
                aoe["angle_deg"] = angle_val
            if shape == "wall" and height_val is not None:
                aoe["height_ft"] = height_val
        else:
            return

        aoe["save_type"] = preset.get("save_type")
        aoe["damage_type"] = preset.get("damage_type")
        if preset.get("damage_types"):
            aoe["damage_types"] = list(preset.get("damage_types"))
        if preset.get("half_on_pass") is not None:
            aoe["half_on_pass"] = bool(preset.get("half_on_pass"))
        if preset.get("condition_on_fail") is not None:
            aoe["condition_on_fail"] = bool(preset.get("condition_on_fail"))
        if preset.get("condition_key"):
            aoe["condition_key"] = str(preset.get("condition_key"))
        if preset.get("condition_turns") not in (None, ""):
            aoe["condition_turns"] = preset.get("condition_turns")
        if preset.get("dice") not in (None, ""):
            aoe["dice"] = str(preset.get("dice"))
            aoe["default_damage"] = aoe.get("default_damage") or aoe["dice"]
        if preset.get("default_damage") not in (None, ""):
            aoe["default_damage"] = str(preset.get("default_damage"))

        if preset.get("concentration") is True:
            aoe["concentration_bound"] = True
        self.aoes[aid] = aoe
        self._create_aoe_items(aid)
        self._refresh_aoe_list(select=aid)
        if preset.get("concentration") is True:
            if app and owner_cid in getattr(app, "combatants", {}):
                caster = app.combatants[owner_cid]
                caster.concentrating = True
                try:
                    spell_level = int(preset.get("level"))
                except Exception:
                    spell_level = None
                if spell_level is not None and spell_level < 0:
                    spell_level = None
                caster.concentration_spell_level = spell_level
                caster.concentration_started_turn = (int(app.round_num), int(app.turn_num))
                aoe_ids = list(getattr(caster, "concentration_aoe_ids", []) or [])
                if aid not in aoe_ids:
                    aoe_ids.append(aid)
                caster.concentration_aoe_ids = aoe_ids

    def _refresh_aoe_list(self, select: Optional[int] = None) -> None:
        self.aoe_list.delete(0, tk.END)
        self._aoe_index_to_id: List[int] = []
        kind_icons = {
            "circle": "◯",
            "sphere": "◯",
            "cylinder": "◯",
            "square": "□",
            "cube": "□",
            "line": "▭",
            "wall": "▮",
            "cone": "▲",
        }
        for aid in sorted(self.aoes.keys()):
            d = self.aoes[aid]
            kind_name = str(d.get("kind") or "")
            kind = kind_icons.get(kind_name, "□")
            pin = ""
            if d.get("pinned"):
                remaining = d.get("remaining_turns")
                if isinstance(remaining, int):
                    pin = f" (pinned, {remaining}t)"
                else:
                    pin = " (pinned)"
            name = str(d.get("name") or f"AoE {aid}")
            height_ft = d.get("height_ft")
            if kind_name in ("sphere", "cylinder") and isinstance(height_ft, (int, float)) and height_ft > 0:
                name = f"{name} (h {height_ft:g}ft)"
            self.aoe_list.insert(tk.END, f"{kind} {name} [{aid}]{pin}")
            self._aoe_index_to_id.append(aid)

        if select is not None and select in self.aoes:
            try:
                idx = self._aoe_index_to_id.index(select)
                self.aoe_list.selection_clear(0, tk.END)
                self.aoe_list.selection_set(idx)
                self.aoe_list.see(idx)
                self._selected_aoe = select
                self.pin_var.set(bool(self.aoes[select].get("pinned")))
            except Exception:
                pass
        self._update_included_for_selected()
        self._sync_aoe_color_ui(self._selected_aoe)
        self._sync_aoe_duration_ui(self._selected_aoe)

    def _select_aoe_from_list(self) -> None:
        sel = self.aoe_list.curselection()
        if not sel:
            self._selected_aoe = None
            self.pin_var.set(False)
            self._update_included_for_selected()
            self._update_aoe_damage_button([])
            self._sync_aoe_color_ui(None)
            self._sync_aoe_duration_ui(None)
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(getattr(self, "_aoe_index_to_id", [])):
            return
        aid = self._aoe_index_to_id[idx]
        self._selected_aoe = aid
        self.pin_var.set(bool(self.aoes[aid].get("pinned")))
        self._raise_aoe_overlays()
        self._update_included_for_selected()
        self._sync_aoe_color_ui(aid)
        self._sync_aoe_duration_ui(aid)

    def _toggle_pin_selected(self) -> None:
        aid = self._selected_aoe
        if aid is None or aid not in self.aoes:
            return
        pinned = bool(self.pin_var.get())
        self.aoes[aid]["pinned"] = pinned
        if pinned:
            duration = self.aoes[aid].get("duration_turns")
            if isinstance(duration, int) and duration > 0:
                self.aoes[aid]["remaining_turns"] = duration
            else:
                self.aoes[aid]["remaining_turns"] = None
        else:
            self.aoes[aid]["remaining_turns"] = None
        self._refresh_aoe_list(select=aid)



    def _rename_selected_aoe(self) -> None:
        """Rename the selected AoE overlay (double-click in the AoE list)."""
        aid = self._selected_aoe
        if aid is None:
            sel = self.aoe_list.curselection()
            if sel and 0 <= int(sel[0]) < len(getattr(self, "_aoe_index_to_id", [])):
                aid = self._aoe_index_to_id[int(sel[0])]
        if aid is None or aid not in self.aoes:
            return
        cur = str(self.aoes[aid].get("name") or f"AoE {aid}")
        name = simpledialog.askstring("Rename AoE", "Enter AoE name:", initialvalue=cur, parent=self)
        if name is None:
            return
        name = name.strip()
        if not name:
            name = f"AoE {aid}"
        self.aoes[aid]["name"] = name
        self._refresh_aoe_list(select=aid)
        # Update label text immediately (count will be appended by _update_included_for_selected)
        self._update_included_for_selected()

    # ---------------- Background images ----------------
    def _set_bg_controls_enabled(self, enabled: bool) -> None:
        widgets = [getattr(self, "bg_lock_chk", None), getattr(self, "bg_scale", None), getattr(self, "bg_alpha", None)]
        for w in widgets:
            if w is None:
                continue
            try:
                w.state(["!disabled"] if enabled else ["disabled"])
            except Exception:
                try:
                    w.config(state=tk.NORMAL if enabled else tk.DISABLED)
                except Exception:
                    pass

    def _refresh_bg_list(self, select: Optional[int] = None) -> None:
        lb = getattr(self, "bg_list", None)
        if lb is None:
            return
        lb.delete(0, tk.END)
        self._bg_index_to_id = []
        for bid in sorted(self.bg_images.keys()):
            d = self.bg_images[bid]
            path = str(d.get("path") or "")
            name = Path(path).name if path else f"Image {bid}"
            lock = " 🔒" if bool(d.get("locked")) else ""
            lb.insert(tk.END, f"{name} [{bid}]{lock}")
            self._bg_index_to_id.append(bid)

        if select is not None and select in self.bg_images:
            try:
                idx = self._bg_index_to_id.index(select)
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.see(idx)
                self._selected_bg = select
            except Exception:
                pass

    def _select_bg_from_list(self) -> None:
        sel = self.bg_list.curselection()
        if not sel:
            self._selected_bg = None
            self._set_bg_controls_enabled(False)
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(getattr(self, "_bg_index_to_id", [])):
            return
        bid = self._bg_index_to_id[idx]
        self._selected_bg = bid
        d = self.bg_images.get(bid, {})
        try:
            self.bg_lock_var.set(bool(d.get("locked")))
            self.bg_scale_var.set(float(d.get("scale_pct", 100.0)))
            self.bg_transparency_var.set(float(d.get("trans_pct", 0.0)))
            self.bg_scale_val.config(text=f"{int(float(self.bg_scale_var.get()))}%")
            self.bg_alpha_val.config(text=f"{int(float(self.bg_transparency_var.get()))}%")
        except Exception:
            pass
        self._set_bg_controls_enabled(True)

        # Bring selection to front slightly (still under grid)
        try:
            self.canvas.tag_raise(f"bg:{bid}")
            self.canvas.tag_lower(f"bg:{bid}", "grid")
        except Exception:
            pass

    def _add_bg_image(self) -> None:
        if Image is None:
            msg = "Pillow (PIL) is required to load images."
            if PIL_IMAGE_IMPORT_ERROR:
                msg += f"\n\nImport error: {PIL_IMAGE_IMPORT_ERROR}"
            msg += "\n\nUbuntu/Debian: sudo apt install python3-pil"
            msg += "\nOr (pip): python3 -m pip install --user pillow"
            messagebox.showerror("Background Images", msg, parent=self)
            return
        if ImageTk is None:
            msg = "Pillow ImageTk support is required to display images in Tk."
            if PIL_IMAGETK_IMPORT_ERROR:
                msg += f"\n\nImport error: {PIL_IMAGETK_IMPORT_ERROR}"
            msg += "\n\nUbuntu/Debian: sudo apt install python3-pil.imagetk"
            msg += "\nOr (pip): python3 -m pip install --user pillow"
            messagebox.showerror("Background Images", msg, parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Select background image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            pil = Image.open(path).convert("RGBA")
        except Exception as e:
            messagebox.showerror("Background Images", f"Failed to open image:\n{e}", parent=self)
            return

        # Default placement: center of map bounds
        self._compute_metrics()
        cx = self.x0 + (self.cols * self.cell) / 2.0
        cy = self.y0 + (self.rows * self.cell) / 2.0

        bid = self._next_bg_id
        self._next_bg_id += 1

        d: Dict[str, object] = {
            "path": path,
            "pil": pil,          # original RGBA
            "tk": None,          # ImageTk.PhotoImage
            "item": None,        # canvas item id
            "x": cx,
            "y": cy,
            "scale_pct": 100.0,
            "trans_pct": 0.0,    # transparency percent
            "locked": False,
        }
        self.bg_images[bid] = d
        self._update_bg_canvas_item(bid, recreate=True)
        self._refresh_bg_list(select=bid)
        self._select_bg_from_list()

    def _remove_selected_bg_image(self) -> None:
        bid = self._selected_bg
        if bid is None or bid not in self.bg_images:
            return
        d = self.bg_images.pop(bid)
        try:
            item = int(d.get("item") or 0)
            if item:
                self.canvas.delete(item)
        except Exception:
            pass
        self._selected_bg = None
        self._refresh_bg_list()
        self._set_bg_controls_enabled(False)

    def _on_bg_lock_toggle(self) -> None:
        bid = self._selected_bg
        if bid is None or bid not in self.bg_images:
            return
        self.bg_images[bid]["locked"] = bool(self.bg_lock_var.get())
        self._refresh_bg_list(select=bid)

    def _on_bg_scale_change(self, value: object) -> None:
        try:
            v = float(value)
        except Exception:
            try:
                v = float(self.bg_scale_var.get())
            except Exception:
                return
        self.bg_scale_val.config(text=f"{int(v)}%")
        bid = self._selected_bg
        if bid is None or bid not in self.bg_images:
            return
        self.bg_images[bid]["scale_pct"] = float(v)
        self._update_bg_canvas_item(bid)

    def _on_bg_transparency_change(self, value: object) -> None:
        try:
            v = float(value)
        except Exception:
            try:
                v = float(self.bg_transparency_var.get())
            except Exception:
                return
        self.bg_alpha_val.config(text=f"{int(v)}%")
        bid = self._selected_bg
        if bid is None or bid not in self.bg_images:
            return
        self.bg_images[bid]["trans_pct"] = float(v)
        self._update_bg_canvas_item(bid)

    def _make_tk_image(self, pil: object, scale_pct: float, trans_pct: float) -> object:
        """Return an ImageTk.PhotoImage with scaling and transparency applied."""
        if Image is None or ImageTk is None:
            return None
        im = pil.copy()
        try:
            im = im.convert("RGBA")
        except Exception:
            pass

        # transparency percent: 0=opaque, 100=fully transparent
        alpha = max(0.0, min(1.0, 1.0 - (float(trans_pct) / 100.0)))
        if alpha < 1.0:
            r, g, b, a = im.split()
            a = a.point(lambda p: int(p * alpha))
            im = Image.merge("RGBA", (r, g, b, a))

        scale = max(0.05, float(scale_pct) / 100.0)
        if abs(scale - 1.0) > 1e-6:
            w, h = im.size
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            im = im.resize((nw, nh), Image.LANCZOS)

        return ImageTk.PhotoImage(im)

    def _update_bg_canvas_item(self, bid: int, recreate: bool = False) -> None:
        d = self.bg_images.get(bid)
        if not d:
            return
        pil = d.get("pil")
        if pil is None:
            return
        tkimg = self._make_tk_image(pil, float(d.get("scale_pct", 100.0)), float(d.get("trans_pct", 0.0)))
        if tkimg is None:
            return
        d["tk"] = tkimg  # keep reference

        item = d.get("item")
        if recreate or not item:
            x = float(d.get("x", 0.0))
            y = float(d.get("y", 0.0))
            item_id = self.canvas.create_image(x, y, image=tkimg, anchor="center", tags=("bgimg", f"bg:{bid}"))
            d["item"] = item_id
            # keep behind everything interactable, but allow click-through via hit test
            try:
                self.canvas.tag_lower(item_id, "grid")
            except Exception:
                try:
                    self.canvas.tag_lower(item_id)
                except Exception:
                    pass
        else:
            try:
                self.canvas.itemconfigure(int(item), image=tkimg)
            except Exception:
                pass
    def _remove_selected_aoe(self) -> None:
        aid = self._selected_aoe
        if aid is None:
            return
        self._remove_aoe_by_id(aid)

    def _remove_aoe_by_id(self, aid: int) -> None:
        if aid not in self.aoes:
            return
        d = self.aoes.pop(aid)
        app = getattr(self, "app", None)
        if app is not None:
            lan_store = getattr(app, "_lan_aoes", None)
            if isinstance(lan_store, dict):
                lan_store.pop(aid, None)
            owner_cid = d.get("owner_cid")
            if owner_cid in getattr(app, "combatants", {}):
                caster = app.combatants[owner_cid]
                aoe_ids = list(getattr(caster, "concentration_aoe_ids", []) or [])
                if aid in aoe_ids:
                    caster.concentration_aoe_ids = [entry for entry in aoe_ids if entry != aid]
        try:
            self.canvas.delete(int(d["shape"]))
            self.canvas.delete(int(d["label"]))
        except Exception:
            pass
        if self._selected_aoe == aid:
            self._selected_aoe = None
            self.pin_var.set(False)
        self._refresh_aoe_list()
        self._update_included_for_selected()

    # ---------------- Canvas interactions ----------------
    def _on_canvas_press(self, event: tk.Event) -> None:
        # Use canvas coordinates (scroll-safe)
        mx = float(self.canvas.canvasx(event.x))
        my = float(self.canvas.canvasy(event.y))
        shift_held = bool(event.state & 0x0001)

        # Obstacle paint mode (disables other interactions while enabled)
        try:
            if bool(self.rough_mode_var.get()):
                self._suspend_lan_sync = True
                self._map_dirty = False
                self._drawing_rough = True
                self._paint_rough_terrain_from_event(event)
                return
            if bool(self.obstacle_mode_var.get()):
                if not self._drawing_obstacles:
                    self._obstacle_history.append(set(self.obstacles))
                self._suspend_lan_sync = True
                self._map_dirty = False
                self._drawing_obstacles = True
                self._paint_obstacle_from_event(event)
                return
        except Exception:
            pass

        # Determine clicked object (click-through grid/measure)
        item = None
        overl = self.canvas.find_overlapping(mx, my, mx, my)
        if overl:
            for cand in reversed(overl):
                tg = self.canvas.gettags(cand)
                if "unit" in tg or "unitname" in tg or "unitmarker" in tg or any(t.startswith("unit:") for t in tg):
                    item = cand
                    break
            if item is None:
                for cand in reversed(overl):
                    tg = self.canvas.gettags(cand)
                    if "grid" in tg or "measure" in tg or "movehl" in tg:
                        continue
                    if any(t.startswith("aoe:") for t in tg):
                        if self._aoe_move_mode_active() or shift_held:
                            item = cand
                            break
                        continue
                    item = cand
                    break

        preferred_cid = self._group_preferred_cid
        if preferred_cid is not None:
            col, row = self._pixel_to_grid(mx, my)
            if col is not None and row is not None:
                cell_cids = self._cell_to_cids.get((col, row), [])
                if preferred_cid in cell_cids and len(cell_cids) > 1:
                    if item is None:
                        self._begin_unit_drag(preferred_cid, mx, my)
                        return
                    tags = self.canvas.gettags(item)
                    if "grid" in tags or "measure" in tags or "movehl" in tags or "group" in tags:
                        self._begin_unit_drag(preferred_cid, mx, my)
                        return

        if item is None:
            self._drag_kind = None
            self._drag_id = None
            self._drag_origin_cell = None
            return

        tags = self.canvas.gettags(item)
        for t in tags:
            if t.startswith("bg:"):
                bid = int(t.split(":", 1)[1])
                self._selected_bg = bid
                try:
                    self._refresh_bg_list(select=bid)
                    self._select_bg_from_list()
                except Exception:
                    pass
                if bool(self.bg_images.get(bid, {}).get("locked")):
                    self._drag_kind = None
                    self._drag_id = None
                    return
                self._drag_kind = "bg"
                self._drag_id = bid
                try:
                    x, y = self.canvas.coords(int(self.bg_images[bid]["item"]))
                    self._drag_offset = (x - mx, y - my)
                except Exception:
                    self._drag_offset = (0.0, 0.0)
                return

            if t.startswith("unit:"):
                cid = int(t.split(":", 1)[1])
                if self._damage_mode_active():
                    self._open_damage_for_target(cid)
                    return
                self._begin_unit_drag(cid, mx, my)
                return

            if t.startswith("aoe:"):
                aid = int(t.split(":", 1)[1])
                self._begin_aoe_drag(aid, mx, my)
                return

        self._drag_kind = None
        self._drag_id = None
        self._drag_origin_cell = None

    def _begin_aoe_drag(self, aid: int, mx: float, my: float) -> None:
        if bool(self.aoes.get(aid, {}).get("pinned")):
            self._selected_aoe = aid
            self._refresh_aoe_list(select=aid)
            return
        d = self.aoes.get(aid)
        if not d:
            return
        owner_cid = d.get("owner_cid")
        active_cid = getattr(self, "_active_cid", None)
        owner_is_dm = isinstance(owner_cid, str) and owner_cid.lower() == "dm"
        is_dm = bool(
            getattr(self, "_dm_override", False)
            or getattr(self, "dm_override", False)
            or (hasattr(self, "app") and bool(getattr(self.app, "dm_override", False)))
            or (hasattr(self, "app") and bool(getattr(self.app, "is_dm", False)))
            or (hasattr(self, "app") and bool(getattr(self.app, "is_admin", False)))
        )
        if not (is_dm or owner_is_dm):
            if owner_cid is not None and active_cid is not None and int(owner_cid) != int(active_cid):
                if hasattr(self, "app"):
                    try:
                        owner_combatant = self.app.combatants.get(int(owner_cid))
                        name = owner_combatant.name if owner_combatant else None
                    except Exception:
                        name = None
                    if name:
                        try:
                            self.app._log(f"{name} owns that spell. Wait for their turn.")
                        except Exception:
                            pass
                return
            if owner_cid is not None and active_cid is None:
                return
        self._drag_kind = "aoe"
        self._drag_id = aid
        cx = self.x0 + (float(d["cx"]) + 0.5) * self.cell
        cy = self.y0 + (float(d["cy"]) + 0.5) * self.cell
        self._drag_offset = (cx - mx, cy - my)
        self._selected_aoe = aid
        self._refresh_aoe_list(select=aid)

    def _begin_unit_drag(self, cid: int, mx: float, my: float) -> None:
        self._drag_kind = "unit"
        self._drag_id = cid
        # record origin cell for movement enforcement
        try:
            self._drag_origin_cell = (int(self.unit_tokens[cid]["col"]), int(self.unit_tokens[cid]["row"]))
        except Exception:
            self._drag_origin_cell = None
        try:
            cx, cy = self._grid_to_pixel(int(self.unit_tokens[cid]["col"]), int(self.unit_tokens[cid]["row"]))
            self._drag_offset = (cx - mx, cy - my)
        except Exception:
            self._drag_offset = (0.0, 0.0)

    def _dm_move_active(self) -> bool:
        try:
            return bool(self.dm_move_var.get())
        except tk.TclError:
            return False

    def _damage_mode_active(self) -> bool:
        try:
            return bool(self.damage_mode_var.get())
        except tk.TclError:
            return False

    def _is_enemy_cid(self, cid: int) -> bool:
        combatant = self.app.combatants.get(int(cid)) if hasattr(self, "app") else None
        if combatant is None:
            return False
        return not bool(getattr(combatant, "ally", False) or getattr(combatant, "is_pc", False))

    def _open_damage_for_target(
        self,
        target_cid: int,
        attacker_cid: Optional[int] = None,
        consume_mode: bool = True,
    ) -> None:
        active_cid = attacker_cid
        if active_cid is None:
            active_cid = getattr(self, "_active_cid", None)
        if active_cid is None:
            active_cid = getattr(self.app, "current_cid", None)
        try:
            self.app._open_damage_tool(attacker_cid=active_cid, target_cid=target_cid)
        except Exception:
            return
        if consume_mode:
            try:
                self.damage_mode_var.set(False)
            except tk.TclError:
                pass

    def _on_canvas_middle_click(self, event: tk.Event) -> None:
        if not hasattr(self, "canvas"):
            return
        mx = float(self.canvas.canvasx(event.x))
        my = float(self.canvas.canvasy(event.y))
        overl = self.canvas.find_overlapping(mx, my, mx, my)
        if not overl:
            return
        for cand in reversed(overl):
            tags = self.canvas.gettags(cand)
            unit_tag = next((tag for tag in tags if tag.startswith("unit:")), None)
            if not unit_tag:
                continue
            try:
                target_cid = int(unit_tag.split(":", 1)[1])
            except Exception:
                return
            if not self._is_enemy_cid(target_cid):
                return
            self._open_damage_for_target(
                target_cid=target_cid,
                attacker_cid=getattr(self.app, "current_cid", None),
                consume_mode=False,
            )
            return

    def _group_label_for_cids(self, cids: List[int]) -> str:
        names: List[str] = []
        for cid in cids:
            c = self.app.combatants.get(cid)
            if c:
                names.append(c.name)
        if not names:
            return f"Group ({len(cids)})"
        first = names[0]
        if all(name == first for name in names):
            return f"{len(names)}x {first}"
        if bool(self.show_all_names_var.get()):
            return f"Group ({len(names)}): " + ", ".join(names)
        return f"Group ({len(names)})"

    def _hover_label_for_cell(self, col: int, row: int) -> Optional[str]:
        cids = list(self._cell_to_cids.get((col, row), []))
        if not cids:
            return None
        if len(cids) == 1:
            c = self.app.combatants.get(cids[0])
            return c.name if c else f"#{cids[0]}"
        return self._group_label_for_cids(cids)

    def _show_hover_tooltip(self, text: str, event: tk.Event) -> None:
        if self._hover_tooltip is None:
            return
        if self._hover_tooltip_text != text:
            try:
                self._hover_tooltip.config(text=text)
            except Exception:
                pass
            self._hover_tooltip_text = text
        try:
            self._hover_tooltip.place(x=int(event.x + 12), y=int(event.y + 12))
        except Exception:
            pass

    def _hide_hover_tooltip(self) -> None:
        if self._hover_tooltip is None:
            return
        if self._hover_tooltip_text is None:
            return
        try:
            self._hover_tooltip.place_forget()
        except Exception:
            pass
        self._hover_tooltip_text = None

    def _on_canvas_hover(self, event: tk.Event) -> None:
        if getattr(self, "_drawing_obstacles", False) or getattr(self, "_drawing_rough", False):
            self._hide_hover_tooltip()
            return
        if self._drag_kind is not None or self._drag_id is not None:
            self._hide_hover_tooltip()
            return
        if self._dragging_from_list is not None:
            self._hide_hover_tooltip()
            return

        item = self.canvas.find_withtag("current")
        if not item:
            self._hide_hover_tooltip()
            return
        tags = self.canvas.gettags(item)
        cid: Optional[int] = None
        for t in tags:
            if t.startswith("unit:"):
                try:
                    cid = int(t.split(":", 1)[1])
                except Exception:
                    cid = None
                break

        label: Optional[str] = None
        if cid is not None and cid in self.unit_tokens:
            try:
                col = int(self.unit_tokens[cid]["col"])
                row = int(self.unit_tokens[cid]["row"])
            except Exception:
                col = row = None
            if col is not None and row is not None:
                cids = list(self._cell_to_cids.get((col, row), []))
                if len(cids) > 1:
                    label = self._group_label_for_cids(cids)
                else:
                    label = self._hover_label_for_cell(col, row)
        elif "group" in tags:
            mx = float(self.canvas.canvasx(event.x))
            my = float(self.canvas.canvasy(event.y))
            col, row = self._pixel_to_grid(mx, my)
            if col is not None and row is not None:
                label = self._hover_label_for_cell(int(col), int(row))

        if label:
            self._show_hover_tooltip(label, event)
        else:
            self._hide_hover_tooltip()



    def _on_canvas_motion(self, event: tk.Event) -> None:
        # Obstacle paint mode
        if getattr(self, "_drawing_obstacles", False):
            self._paint_obstacle_from_event(event)
            return
        if getattr(self, "_drawing_rough", False):
            self._paint_rough_terrain_from_event(event)
            return
        self._hide_hover_tooltip()

        if self._drag_kind is None or self._drag_id is None:
            return

        mx = float(self.canvas.canvasx(event.x))
        my = float(self.canvas.canvasy(event.y))
        x = mx + float(self._drag_offset[0])
        y = my + float(self._drag_offset[1])

        if self._drag_kind == "bg":
            bid = int(self._drag_id)
            d = self.bg_images.get(bid)
            if not d:
                return
            item = int(d.get("item") or 0)
            if not item:
                return
            self.canvas.coords(item, x, y)
            d["x"] = x
            d["y"] = y

        elif self._drag_kind == "unit":
            col, row = self._pixel_to_grid(x, y)
            if col is None or row is None:
                return
            self.unit_tokens[self._drag_id]["col"] = col
            self.unit_tokens[self._drag_id]["row"] = row
            self._layout_unit(self._drag_id)
            self._sync_mount_pair_position(int(self._drag_id), col, row)

        elif self._drag_kind == "aoe":
            # allow half-square precision for overlays
            if x < self.x0 or y < self.y0:
                return
            d = self.aoes.get(self._drag_id)
            if not d:
                return
            kind = str(d.get("kind") or "")
            shift_held = bool(event.state & 0x0001)
            if kind in ("line", "cone", "cube", "wall", "square") and shift_held:
                anchor = self._resolve_aoe_anchor(d)
                if anchor is not None:
                    ax, ay = anchor
                else:
                    ax = float(d.get("ax", d.get("cx", 0.0)))
                    ay = float(d.get("ay", d.get("cy", 0.0)))
                ax_px = self.x0 + (ax + 0.5) * self.cell
                ay_px = self.y0 + (ay + 0.5) * self.cell
                dx = x - ax_px
                dy = y - ay_px
                if abs(dx) + abs(dy) < 0.01:
                    return
                if kind == "cone" and d.get("spread_deg") is None:
                    spread = d.get("angle_deg")
                    if spread is not None:
                        d["spread_deg"] = float(spread)
                angle = math.degrees(math.atan2(dy, dx))
                d["angle_deg"] = angle
                if kind == "line":
                    length_sq = float(d.get("length_sq") or 0.0)
                    half_len = length_sq / 2.0
                    rad = math.radians(angle)
                    cx = ax + math.cos(rad) * half_len
                    cy = ay + math.sin(rad) * half_len
                    d["ax"] = ax
                    d["ay"] = ay
                    d["cx"] = cx
                    d["cy"] = cy
            else:
                cx = (x - self.x0) / self.cell - 0.5
                cy = (y - self.y0) / self.cell - 0.5
                old_cx = float(d.get("cx", cx))
                old_cy = float(d.get("cy", cy))
                d["cx"] = cx
                d["cy"] = cy
                if kind in ("line", "wall"):
                    anchor = self._resolve_aoe_anchor(d)
                    if anchor is None:
                        angle = d.get("angle_deg")
                        orient = str(d.get("orient") or "vertical")
                        if angle is None:
                            angle = 0.0 if orient == "horizontal" else 90.0
                        angle_rad = math.radians(float(angle))
                        half_len = float(d.get("length_sq") or 0.0) / 2.0
                        d["ax"] = cx - math.cos(angle_rad) * half_len
                        d["ay"] = cy - math.sin(angle_rad) * half_len
                elif kind == "cone":
                    anchor = self._resolve_aoe_anchor(d)
                    if anchor is None:
                        d["ax"] = cx
                        d["ay"] = cy
            self._layout_aoe(self._drag_id)

        self._update_included_for_selected()



    def _on_canvas_release(self, event: tk.Event) -> None:
        # Finish obstacle painting
        if getattr(self, "_drawing_obstacles", False):
            self._drawing_obstacles = False
            self._suspend_lan_sync = False
            self._map_dirty = True
            return
        if getattr(self, "_drawing_rough", False):
            self._drawing_rough = False
            self._suspend_lan_sync = False
            self._map_dirty = True
            return

        # Finalize drags, enforce movement for the active creature, then refresh grouping/highlights.
        if self._drag_kind == "unit" and self._drag_id is not None:
            cid = int(self._drag_id)
            origin = self._drag_origin_cell
            if origin and cid in self.unit_tokens:
                new_col = int(self.unit_tokens[cid]["col"])
                new_row = int(self.unit_tokens[cid]["row"])

                if self._active_cid == cid and not self._dm_move_active():
                    c = self.app.combatants.get(cid)
                    if c is not None:
                        # Compute movement cost using diagonal 5/10 rule + obstacles.
                        req = None
                        try:
                            max_query = int(self.feet_per_square) * (self.cols + self.rows) * 4
                            req = self._movement_cost_between(origin, (new_col, new_row), max_query, c)
                        except Exception:
                            req = None

                        if req is None:
                            # Unreachable (blocked by obstacles / no valid path); snap back and ignore.
                            self.unit_tokens[cid]["col"] = origin[0]
                            self.unit_tokens[cid]["row"] = origin[1]
                            self._layout_unit(cid)
                            try:
                                self.app._log(f"{c.name} can't reach that square (blocked).", cid=cid)
                            except Exception:
                                pass
                            cost = 0
                        else:
                            cost = int(req)
                        if cost > 0:
                            if cost > int(getattr(c, "move_remaining", 0) or 0):
                                # Snap back
                                self.unit_tokens[cid]["col"] = origin[0]
                                self.unit_tokens[cid]["row"] = origin[1]
                                self._layout_unit(cid)
                                try:
                                    self.app._log(f"{c.name} tries to move {cost} ft on the map, but only {c.move_remaining} ft be left.", cid=cid)
                                except Exception:
                                    pass
                            else:
                                try:
                                    c.move_remaining = int(c.move_remaining) - cost
                                except Exception:
                                    c.move_remaining = max(0, int(getattr(c, "move_remaining", 0) or 0) - cost)
                                try:
                                    self.app._log(f"{c.name} moves {cost} ft on the map.", cid=cid)
                                    self.app._rebuild_table(scroll_to_current=True)
                                except Exception:
                                    pass
            tok = self.unit_tokens.get(cid)
            if tok:
                try:
                    col = int(tok.get("col"))
                    row = int(tok.get("row"))
                except (TypeError, ValueError):
                    pass
                else:
                    self._sync_mount_pair_position(cid, col, row)

        if self._drag_kind in ("unit", "aoe"):
            self._update_groups()
            self._update_move_highlight()
            self._update_included_for_selected()

        # overlays keep float center
        self._drag_kind = None
        self._drag_id = None
        self._drag_origin_cell = None

    def _on_canvas_double_click(self, event: tk.Event) -> None:
        if getattr(self, "_drawing_obstacles", False) or getattr(self, "_drawing_rough", False):
            return
        if not (self._aoe_move_mode_active() or bool(event.state & 0x0001)):
            return
        mx = float(self.canvas.canvasx(event.x))
        my = float(self.canvas.canvasy(event.y))
        items = self.canvas.find_overlapping(mx, my, mx, my)
        if not items:
            return
        chosen = None
        for cand in reversed(items):
            tags = self.canvas.gettags(cand)
            if "grid" in tags or "measure" in tags or "movehl" in tags:
                continue
            if any(t.startswith("aoe:") for t in tags):
                chosen = cand
                break
        if chosen is None:
            return
        tags = self.canvas.gettags(chosen)
        for t in tags:
            if not t.startswith("aoe:"):
                continue
            aid = int(t.split(":", 1)[1])
            self._begin_aoe_drag(aid, mx, my)
            return

    # ---------------- Measurement ----------------
    def _on_canvas_right_click(self, event: tk.Event) -> None:
        # Two-click measurement in feet (crow flies)
        mx = float(self.canvas.canvasx(event.x))
        my = float(self.canvas.canvasy(event.y))
        col, row = self._pixel_to_grid(mx, my)
        if col is None or row is None:
            return
        px, py = self._grid_to_pixel(col, row)

        if self._measure_start is None:
            self._clear_measure()
            self._measure_start = (px, py)
            dot = self.canvas.create_oval(px - 4, py - 4, px + 4, py + 4, fill="#333", outline="", tags=("measure",))
            self._measure_items.append(dot)
            return

        sx, sy = self._measure_start
        dx = (px - sx) / self.cell
        dy = (py - sy) / self.cell
        dist_sq = (dx * dx + dy * dy) ** 0.5
        dist_ft = dist_sq * self.feet_per_square

        line = self.canvas.create_line(sx, sy, px, py, fill="#333", width=2, arrow=tk.LAST, tags=("measure",))
        label = self.canvas.create_text((sx + px) / 2.0, (sy + py) / 2.0 - 10,
                                        text=f"{dist_ft:.1f} ft", font=("TkDefaultFont", 10, "bold"),
                                        tags=("measure",))
        self._measure_items.extend([line, label])
        self._measure_start = None

    def _clear_measure(self) -> None:
        try:
            self.canvas.delete("measure")
        except Exception:
            pass
        self._measure_start = None
        self._measure_items = []

    # ---------------- AoE inclusion ----------------
    def _update_included_for_selected(self) -> None:
        aid = self._selected_aoe
        if aid is None or aid not in self.aoes:
            self._set_included_text("")
            self._update_aoe_damage_button([])
            return
        included = self._compute_included_units(aid)
        lines = []
        for cid in included:
            c = self.app.combatants.get(cid)
            if not c:
                continue
            lines.append(f"- {c.name}  [#{cid}]")
        self._set_included_text("\n".join(lines) if lines else "(none)")
        self._update_aoe_damage_button(included)

        # Update overlay label with count
        try:
            d = self.aoes[aid]
            nm = str(d.get("name") or f"AoE {aid}")
            self.canvas.itemconfigure(int(d["label"]), text=f"{nm} ({len(included)})")
        except Exception:
            pass

    
    def _update_aoe_damage_button(self, included: Optional[List[int]] = None) -> None:
        """Enable/disable AoE Damage button based on current selection."""
        btn = getattr(self, "aoe_damage_btn", None)
        if btn is None:
            return
        aid = self._selected_aoe
        if aid is None or aid not in self.aoes:
            try:
                btn.state(["disabled"])
            except Exception:
                btn.config(state=tk.DISABLED)
            return
        if included is None:
            try:
                included = self._compute_included_units(aid)
            except Exception:
                included = []
        if included:
            try:
                btn.state(["!disabled"])
            except Exception:
                btn.config(state=tk.NORMAL)
        else:
            try:
                btn.state(["disabled"])
            except Exception:
                btn.config(state=tk.DISABLED)

    def _open_aoe_damage(self, aid: Optional[int] = None, included_override: Optional[List[int]] = None) -> None:
        """AoE save roller + manual damage apply to all units inside the selected AoE."""
        if aid is None:
            aid = self._selected_aoe
        if aid is None or aid not in self.aoes:
            messagebox.showinfo("AoE Damage", "Select an AoE first.", parent=self)
            return
        if included_override is None:
            included = self._compute_included_units(aid)
        else:
            included = [cid for cid in included_override if cid in self.app.combatants]
        if not included:
            messagebox.showinfo("AoE Damage", "No units are inside the selected AoE.", parent=self)
            return

        dlg = tk.Toplevel(self)
        dname = str(self.aoes[aid].get("name") or f"AoE {aid}")
        dlg.title(f"AoE Damage ({dname})")
        dlg.geometry("1120x720")
        dlg.minsize(900, 600)
        dlg.transient(self)

        outer = ttk.Frame(dlg, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # --- Controls ---
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, expand=False)

        # Attacker list
        attacker_names = [""]
        order = [c.cid for c in self.app._display_order()] if hasattr(self.app, "_display_order") else []
        seen: set[int] = set()
        for cid in order + [cid for cid in self.app.combatants.keys() if cid not in set(order)]:
            if cid in seen:
                continue
            seen.add(cid)
            c = self.app.combatants.get(cid)
            if c:
                attacker_names.append(c.name)

        attacker_var = tk.StringVar(value="")
        if getattr(self.app, "current_cid", None) in self.app.combatants:
            attacker_var.set(self.app.combatants[self.app.current_cid].name)

        use_attacker_var = tk.BooleanVar(value=True)

        ttk.Label(controls, text="Spellcaster:").grid(row=0, column=0, sticky="w")
        attacker_cb = ttk.Combobox(controls, textvariable=attacker_var, values=attacker_names, state="readonly", width=22)
        attacker_cb.grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Checkbutton(controls, text="Use attacker in log", variable=use_attacker_var).grid(row=0, column=2, sticky="w")

        aoe_meta = self.aoes.get(aid, {})
        spell_owner = str(aoe_meta.get("owner") or "").strip()
        from_spell = bool(
            aoe_meta.get("from_spell")
            or aoe_meta.get("owner_cid") is not None
            or spell_owner
        )
        owner_cid = aoe_meta.get("owner_cid")
        owner_combatant = None
        if isinstance(owner_cid, int) and owner_cid in self.app.combatants:
            owner_combatant = self.app.combatants[owner_cid]
        elif spell_owner:
            for c in self.app.combatants.values():
                if c.name == spell_owner:
                    owner_combatant = c
                    break

        # Save DC + save type
        dc_var = tk.StringVar(value="15")
        ttk.Label(controls, text="Save DC:").grid(row=0, column=3, sticky="w")
        dc_ent = ttk.Entry(controls, textvariable=dc_var, width=6)
        dc_ent.grid(row=0, column=4, sticky="w", padx=(6, 12))

        max_nat1_var = tk.StringVar(value="")
        ttk.Label(controls, text="Max on nat 1:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        max_nat1_ent = ttk.Entry(controls, textvariable=max_nat1_var, width=10)
        max_nat1_ent.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=(8, 0))

        save_types = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
        save_var = tk.StringVar(value="DEX")
        ttk.Label(controls, text="Save:").grid(row=1, column=3, sticky="w", pady=(8, 0))
        save_cb = ttk.Combobox(controls, textvariable=save_var, values=save_types, state="readonly", width=5)
        save_cb.grid(row=1, column=4, sticky="w", padx=(6, 12), pady=(8, 0))

        half_on_pass = tk.BooleanVar(value=from_spell)
        half_cb = ttk.Checkbutton(controls, text="Half on pass (per component)", variable=half_on_pass)
        half_cb.grid(row=1, column=2, sticky="w", pady=(8, 0))

        apply_condition_var = tk.BooleanVar(value=False)
        cond_keys = [k for k in CONDITIONS_META.keys() if k != "exhaustion"]
        cond_labels = [str(CONDITIONS_META[k]["label"]) for k in cond_keys]
        condition_var = tk.StringVar(value=(cond_labels[0] if cond_labels else ""))
        condition_turns_var = tk.StringVar(value="0")

        ttk.Checkbutton(
            controls,
            text="Apply condition on failed save",
            variable=apply_condition_var,
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(controls, text="Condition:").grid(row=2, column=1, sticky="w", pady=(8, 0))
        condition_cb = ttk.Combobox(
            controls,
            textvariable=condition_var,
            values=cond_labels,
            state="readonly",
            width=18,
        )
        condition_cb.grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Label(controls, text="Turns (0=indef):").grid(row=2, column=3, sticky="w", pady=(8, 0))
        condition_turns_ent = ttk.Entry(controls, textvariable=condition_turns_var, width=8)
        condition_turns_ent.grid(row=2, column=4, sticky="w", pady=(8, 0))

        def _toggle_condition_controls(*_args: object) -> None:
            state = ["!disabled"] if apply_condition_var.get() else ["disabled"]
            try:
                condition_cb.state(state)
            except Exception:
                condition_cb.config(state=(tk.NORMAL if apply_condition_var.get() else tk.DISABLED))
            try:
                condition_turns_ent.state(state)
            except Exception:
                condition_turns_ent.config(state=(tk.NORMAL if apply_condition_var.get() else tk.DISABLED))

        apply_condition_var.trace_add("write", _toggle_condition_controls)

        def _match_damage_type(value: str) -> str:
            val = (value or "").strip()
            if not val:
                return ""
            val_lower = val.lower()
            for dtype in DAMAGE_TYPES:
                if dtype.lower() == val_lower:
                    return dtype
            return val

        if aoe_meta.get("dc") not in (None, ""):
            try:
                dc_var.set(str(int(aoe_meta.get("dc"))))
            except Exception:
                dc_var.set(str(aoe_meta.get("dc")))
        if aoe_meta.get("save_type"):
            save_choice = str(aoe_meta.get("save_type") or "").strip().upper()
            if save_choice in save_types:
                save_var.set(save_choice)
        if aoe_meta.get("half_on_pass") is not None:
            half_on_pass.set(bool(aoe_meta.get("half_on_pass")))
        if aoe_meta.get("condition_on_fail") is not None:
            apply_condition_var.set(bool(aoe_meta.get("condition_on_fail")))
        if aoe_meta.get("condition_key") in cond_keys:
            label = str(CONDITIONS_META.get(aoe_meta.get("condition_key"), {}).get("label", ""))
            if label:
                condition_var.set(label)
        if aoe_meta.get("condition_turns") not in (None, ""):
            condition_turns_var.set(str(aoe_meta.get("condition_turns")))

        if from_spell:
            note = "From spell"
            if spell_owner:
                note = f"{note} ({spell_owner})"
            ttk.Label(controls, text=note, foreground="#666").grid(row=3, column=3, columnspan=2, sticky="w", pady=(8, 0))
            if aoe_meta.get("dc") not in (None, ""):
                try:
                    dc_ent.state(["disabled"])
                except Exception:
                    dc_ent.config(state=tk.DISABLED)
            if aoe_meta.get("save_type"):
                try:
                    save_cb.state(["disabled"])
                except Exception:
                    save_cb.config(state=tk.DISABLED)
            if aoe_meta.get("half_on_pass") is not None:
                try:
                    half_cb.state(["disabled"])
                except Exception:
                    half_cb.config(state=tk.DISABLED)

        components_frame = ttk.LabelFrame(outer, text="Damage components")
        components_frame.pack(fill=tk.X, pady=(12, 0))

        comp_header = ttk.Frame(components_frame)
        comp_header.pack(fill=tk.X)
        ttk.Label(comp_header, text="Amount (math ok)").pack(side=tk.LEFT)
        ttk.Label(comp_header, text="Type").pack(side=tk.LEFT, padx=(86, 0))

        comp_rows = ttk.Frame(components_frame)
        comp_rows.pack(fill=tk.X, pady=(4, 0))
        damage_components: List[Dict[str, object]] = []

        def _update_component_buttons() -> None:
            for comp in damage_components:
                btn = comp.get("remove_btn")
                if not isinstance(btn, ttk.Button):
                    continue
                if len(damage_components) <= 1:
                    btn.state(["disabled"])
                else:
                    btn.state(["!disabled"])

        def _remove_component(row: ttk.Frame) -> None:
            for idx, comp in enumerate(damage_components):
                if comp.get("row") is row:
                    damage_components.pop(idx)
                    row.destroy()
                    break
            _update_component_buttons()

        def _add_component(amount: str = "", dtype: str = "", locked: bool = False) -> None:
            row = ttk.Frame(comp_rows)
            amount_var = tk.StringVar(value=amount)
            dtype_var = tk.StringVar(value=dtype)
            amount_ent = ttk.Entry(row, textvariable=amount_var, width=10)
            dtype_cb = ttk.Combobox(row, textvariable=dtype_var, values=DAMAGE_TYPES, state="readonly", width=14)
            amount_ent.pack(side=tk.LEFT, padx=(0, 10))
            dtype_cb.pack(side=tk.LEFT, padx=(0, 10))
            remove_btn = ttk.Button(row, text="Remove", command=lambda: _remove_component(row))
            remove_btn.pack(side=tk.LEFT)
            row.pack(fill=tk.X, pady=2)
            if locked:
                try:
                    amount_ent.state(["disabled"])
                except Exception:
                    amount_ent.config(state=tk.DISABLED)
                try:
                    dtype_cb.state(["disabled"])
                except Exception:
                    dtype_cb.config(state=tk.DISABLED)
            damage_components.append(
                {
                    "amount_var": amount_var,
                    "dtype_var": dtype_var,
                    "row": row,
                    "remove_btn": remove_btn,
                    "amount_ent": amount_ent,
                    "dtype_cb": dtype_cb,
                }
            )
            _update_component_buttons()

        default_amount = ""
        default_type = ""
        if aoe_meta.get("default_damage") not in (None, ""):
            default_amount = str(aoe_meta.get("default_damage"))
        elif aoe_meta.get("dice") not in (None, ""):
            default_amount = str(aoe_meta.get("dice"))
        if aoe_meta.get("damage_type"):
            default_type = _match_damage_type(str(aoe_meta.get("damage_type") or ""))

        damage_type_list: List[str] = []
        raw_damage_types = aoe_meta.get("damage_types")
        if isinstance(raw_damage_types, (list, tuple)):
            for entry in raw_damage_types:
                matched = _match_damage_type(str(entry or ""))
                if matched:
                    damage_type_list.append(matched)

        if damage_type_list:
            for dtype in damage_type_list:
                _add_component(default_amount, dtype, locked=False)
        else:
            _add_component(default_amount, default_type, locked=False)

        add_comp_btn = ttk.Button(components_frame, text="Add damage type", command=_add_component)
        add_comp_btn.pack(anchor="w", pady=(6, 0))

        # --- Table ---
        mid = ttk.Frame(outer)
        mid.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        cols = ("name", "roll", "mod", "total", "result", "immune")
        tv = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended", height=12)
        tv.heading("name", text="Creature")
        tv.heading("roll", text="d20")
        tv.heading("mod", text="Mod")
        tv.heading("total", text="Total")
        tv.heading("result", text="Pass?")
        tv.heading("immune", text="Immune?")
        tv.column("name", width=240, anchor="w")
        tv.column("roll", width=60, anchor="center")
        tv.column("mod", width=60, anchor="center")
        tv.column("total", width=70, anchor="center")
        tv.column("result", width=70, anchor="center")
        tv.column("immune", width=80, anchor="center")
        tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=tv.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tv.config(yscrollcommand=sb.set)

        cid_by_iid: Dict[str, int] = {}
        rolls: Dict[int, int] = {}
        mods: Dict[int, int] = {}
        immune: Dict[int, bool] = {}

        def _save_key() -> str:
            return (save_var.get() or "").strip().lower()

        def _lookup_save_mod(c: Combatant, save_key: str) -> int:
            if not save_key:
                return 0
            saves = getattr(c, "saving_throws", None)
            if isinstance(saves, dict):
                if save_key in saves:
                    val = saves.get(save_key)
                    if isinstance(val, int):
                        return int(val)
                    if isinstance(val, str):
                        raw = val.strip()
                        if raw.startswith("+"):
                            raw = raw[1:]
                        if raw.lstrip("-").isdigit():
                            return int(raw)
            mods = getattr(c, "ability_mods", None)
            if isinstance(mods, dict):
                val = mods.get(save_key)
                if isinstance(val, int):
                    return int(val)
            return 0

        def _reset_mods_from_saves() -> None:
            save_key = _save_key()
            for cid in list(mods.keys()):
                c = self.app.combatants.get(cid)
                mods[cid] = _lookup_save_mod(c, save_key) if c else 0

        # Populate rows
        for cid in included:
            c = self.app.combatants.get(cid)
            if not c:
                continue
            mod = _lookup_save_mod(c, _save_key())
            iid = tv.insert("", tk.END, values=(c.name, "", str(mod), "", "", "No"))
            cid_by_iid[iid] = cid
            mods[cid] = mod
            immune[cid] = False

        def _immune_col_index() -> str:
            return f"#{cols.index('immune') + 1}"

        def _update_immune_cell(iid: str, cid: int) -> None:
            tv.set(iid, "immune", "Yes" if immune.get(cid, False) else "No")

        def _toggle_immune(event: tk.Event) -> Optional[str]:
            if tv.identify("region", event.x, event.y) != "cell":
                return None
            if tv.identify_column(event.x) != _immune_col_index():
                return None
            iid = tv.identify_row(event.y)
            if not iid:
                return None
            cid = cid_by_iid.get(iid)
            if cid is None:
                return None
            immune[cid] = not immune.get(cid, False)
            _update_immune_cell(iid, cid)
            return "break"

        tv.bind("<Button-1>", _toggle_immune, add=True)

        def _parse_dc() -> int:
            try:
                return int((dc_var.get() or "").strip())
            except Exception:
                raise ValueError

        def refresh() -> None:
            try:
                dc = _parse_dc()
            except Exception:
                dc = 0
            for iid, cid in cid_by_iid.items():
                r = int(rolls.get(cid, 0))
                m = int(mods.get(cid, 0))
                tot = r + m
                passed = (r > 0 and r != 1 and tot >= dc)
                tv.set(iid, "roll", str(r) if r > 0 else "")
                tv.set(iid, "mod", str(m))
                tv.set(iid, "total", str(tot) if r > 0 else "")
                tv.set(iid, "result", "PASS" if passed else ("FAIL" if r > 0 else ""))

        def _on_save_change(*_args: object) -> None:
            _reset_mods_from_saves()
            refresh()

        save_var.trace_add("write", _on_save_change)

        def roll_all() -> None:
            try:
                _parse_dc()
            except Exception:
                messagebox.showerror("AoE Damage", "Save DC must be an integer.", parent=dlg)
                return
            for cid in list(mods.keys()):
                rolls[cid] = random.randint(1, 20)
            refresh()

        # Bulk modifier control
        bulk = ttk.Frame(outer)
        bulk.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(bulk, text="Set mod (selected rows):").pack(side=tk.LEFT)
        bulk_mod_var = tk.StringVar(value="0")
        bulk_ent = ttk.Entry(bulk, textvariable=bulk_mod_var, width=8)
        bulk_ent.pack(side=tk.LEFT, padx=(6, 0))

        def apply_mod() -> None:
            try:
                v = int((bulk_mod_var.get() or "").strip())
            except Exception:
                messagebox.showerror("AoE Damage", "Modifier must be an integer.", parent=dlg)
                return
            sel = tv.selection()
            targets = sel if sel else list(cid_by_iid.keys())
            for iid in targets:
                cid = cid_by_iid.get(iid)
                if cid is None:
                    continue
                mods[cid] = v
            refresh()

        ttk.Button(bulk, text="Apply", command=apply_mod).pack(side=tk.LEFT, padx=(8, 0))

        # Buttons
        btns = ttk.Frame(outer)
        btns.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btns, text="Roll", command=roll_all).pack(side=tk.LEFT)

        def apply_damage() -> None:
            if not rolls:
                messagebox.showinfo("AoE Damage", "Roll saves first.", parent=dlg)
                return
            try:
                dc = _parse_dc()
            except Exception:
                messagebox.showerror("AoE Damage", "Save DC must be an integer.", parent=dlg)
                return
            apply_condition = bool(apply_condition_var.get())
            condition_key: Optional[str] = None
            condition_turns: Optional[int] = None
            if apply_condition:
                label = condition_var.get()
                for key in cond_keys:
                    if str(CONDITIONS_META[key]["label"]) == label:
                        condition_key = key
                        break
                if not condition_key:
                    messagebox.showerror("AoE Damage", "Pick a condition to apply.", parent=dlg)
                    return
                try:
                    raw_turns = int((condition_turns_var.get() or "").strip())
                except ValueError:
                    messagebox.showerror("AoE Damage", "Condition turns must be an integer (0=indef).", parent=dlg)
                    return
                condition_turns = None if raw_turns == 0 else max(1, raw_turns)

            aoe_meta["condition_on_fail"] = apply_condition
            if condition_key:
                aoe_meta["condition_key"] = condition_key
            aoe_meta["condition_turns"] = condition_turns_var.get().strip()
            components: List[Tuple[int, str]] = []

            def _parse_damage_amount(amount_raw: str) -> int:
                raw = amount_raw.strip().lower()
                match = re.fullmatch(r"(\\d+)d(4|6|8|10|12)", raw)
                if match:
                    count = int(match.group(1))
                    die = int(match.group(2))
                    if count <= 0:
                        raise ValueError("Dice count must be positive.")
                    return int(self.app._roll_dice_dict({die: count}))
                return int(self.app._parse_int_expr(amount_raw))

            for comp in damage_components:
                amount_raw = (comp["amount_var"].get() or "").strip()
                dtype = (comp["dtype_var"].get() or "").strip()
                if amount_raw == "":
                    if dtype:
                        messagebox.showerror("AoE Damage", "Enter a damage amount for each component.", parent=dlg)
                        return
                    continue
                try:
                    amount_val = _parse_damage_amount(amount_raw)
                except Exception:
                    messagebox.showerror(
                        "AoE Damage",
                        "Damage amounts must be numbers, dice (e.g. 8d6), or simple math expressions.",
                        parent=dlg,
                    )
                    return
                components.append((max(0, amount_val), dtype))

            if not components:
                messagebox.showerror("AoE Damage", "Enter at least one damage component.", parent=dlg)
                return

            max_nat1_total: Optional[int] = None
            max_nat1_raw = (max_nat1_var.get() or "").strip()
            if max_nat1_raw:
                try:
                    max_nat1_total = int(self.app._parse_int_expr(max_nat1_raw))
                except Exception:
                    messagebox.showerror(
                        "AoE Damage",
                        "Max damage on nat 1 must be a number or simple math expression.",
                        parent=dlg,
                    )
                    return
                if max_nat1_total < 0:
                    messagebox.showerror("AoE Damage", "Max damage on nat 1 must be a positive number.", parent=dlg)
                    return

            attacker = (attacker_var.get() or "").strip()
            if not attacker and getattr(self.app, "current_cid", None) in self.app.combatants:
                attacker = self.app.combatants[self.app.current_cid].name
            use_att = bool(use_attacker_var.get()) and attacker != ""
            save_name = save_var.get()
            attacker_cid: Optional[int] = None
            if isinstance(owner_cid, int):
                attacker_cid = owner_cid
            elif attacker and getattr(self.app, "current_cid", None) in self.app.combatants:
                cur = self.app.combatants.get(self.app.current_cid)
                if cur and cur.name == attacker:
                    attacker_cid = cur.cid
            elif attacker:
                for combatant in self.app.combatants.values():
                    if combatant.name == attacker:
                        attacker_cid = combatant.cid
                        break

            if from_spell and owner_combatant:
                spell_name = str(aoe_meta.get("name") or "").strip().lower() or "a spell"
                spell_level = aoe_meta.get("level")
                try:
                    level_num = int(spell_level)
                except Exception:
                    level_num = None
                if level_num is not None and level_num >= 0:
                    cast_log = f"{owner_combatant.name} cast {spell_name} at level {level_num}"
                else:
                    cast_log = f"{owner_combatant.name} cast {spell_name}"
                if not self.app._use_action(owner_combatant, log_message=cast_log):
                    self.app._log(f"{owner_combatant.name} has no actions left to spend", cid=owner_combatant.cid)

            removed: List[int] = []
            death_info: Dict[int, Tuple[Optional[str], int, str]] = {}
            death_logged: set[int] = set()
            damage_dealt = False

            def _format_component_desc(items: List[Tuple[int, str]]) -> str:
                return " + ".join(
                    [
                        f"{amt} {dtype}".strip()
                        for amt, dtype in items
                        if amt > 0
                    ]
                )

            for cid in included:
                c = self.app.combatants.get(cid)
                if not c:
                    continue
                r = int(rolls.get(cid, 0))
                m = int(mods.get(cid, 0))
                tot = r + m
                passed = (r > 0 and r != 1 and tot >= dc)
                is_immune = immune.get(cid, False)
                lan_logger = getattr(getattr(self.app, "_lan", None), "_append_lan_log", None)
                if callable(lan_logger):
                    try:
                        lan_logger(f"AoE save debug: target={c.name} save={save_name} total={tot} dc={dc} passed={passed}", level="info")
                    except Exception:
                        pass
                nat1_max_applied = bool(max_nat1_total is not None and r == 1)
                applied_components: List[Tuple[int, str]] = []
                total_damage = 0
                component_desc = ""
                if nat1_max_applied:
                    total_damage = int(max_nat1_total or 0)
                    component_desc = f"{total_damage} (max on nat 1)"
                else:
                    for amount_val, dtype in components:
                        if passed:
                            applied = amount_val // 2 if half_on_pass.get() else 0
                        else:
                            applied = amount_val
                        applied_components.append((applied, dtype))
                        total_damage += applied
                    component_desc = _format_component_desc(applied_components)

                immune_desc = component_desc
                if not immune_desc:
                    immune_desc = _format_component_desc(components)

                before = int(getattr(c, "hp", 0))
                if is_immune:
                    if immune_desc:
                        self.app._log(f"Damage to {c.name} was blocked — immune to {immune_desc}.")
                    else:
                        self.app._log(f"Damage to {c.name} was blocked — immune.")
                elif total_damage > 0:
                    damage_dealt = True
                    c.hp = max(0, before - int(total_damage))
                after = int(getattr(c, "hp", 0))
                if not is_immune and total_damage > 0 and after < before:
                    self.app._queue_concentration_save(c, "aoe")

                died = (before > 0 and after == 0)
                if died and not is_immune:
                    dtype_note = " + ".join([d for _, d in applied_components if d]).strip()
                    death_info[cid] = (attacker or None, int(total_damage), dtype_note)
                    lan = getattr(self.app, "_lan", None)
                    if lan:
                        lan.play_ko(attacker_cid)

                # Log
                if not is_immune:
                    nat1_note = " (max on nat 1)" if nat1_max_applied else ""
                    if total_damage == 0:
                        if use_att:
                            self.app._log(
                                f"{dname}: {attacker} hits {c.name} (save {save_name} {tot}) — no damage{nat1_note}"
                            )
                        else:
                            self.app._log(f"{dname}: {c.name} avoids AoE damage (save {save_name} {tot}){nat1_note}")
                    else:
                        half_note = " (half on pass per component)" if (passed and half_on_pass.get()) else ""
                        dead_note = " (Dead)" if (died and use_att) else ""
                        if use_att:
                            self.app._log(
                                f"{dname}: {attacker} hits {c.name} for {component_desc} damage (save {save_name} {tot} {'pass' if passed else 'fail'}{half_note}){dead_note}"
                            )
                        else:
                            self.app._log(
                                f"{dname}: {c.name} takes {component_desc} damage (save {save_name} {tot} {'pass' if passed else 'fail'}{half_note})"
                            )

                if died and use_att and not is_immune:
                    death_logged.add(cid)

                if apply_condition and (r > 0 and not passed) and condition_key and not is_immune:
                    c.condition_stacks = [st for st in c.condition_stacks if st.ctype != condition_key]
                    st = ConditionStack(
                        sid=self.app._next_stack_id,
                        ctype=condition_key,
                        remaining_turns=condition_turns,
                    )
                    self.app._next_stack_id += 1
                    c.condition_stacks.append(st)
                    lab = str(CONDITIONS_META.get(condition_key, {}).get("label", condition_key))
                    if condition_turns is None:
                        self.app._log(f"set condition: {lab} (indef)", cid=cid)
                    else:
                        self.app._log(f"set condition: {lab} ({condition_turns} turn(s))", cid=cid)
                elif apply_condition and (r > 0 and not passed) and condition_key and is_immune:
                    self.app._log(f"Condition blocked for {c.name} — immune.", cid=cid)

                if died:
                    removed.append(cid)

            if removed:
                for cid in removed:
                    nm = self.app.combatants[cid].name if cid in self.app.combatants else "(unknown)"
                    if cid in death_logged:
                        self.app.combatants.pop(cid, None)
                        continue
                    attacker, dmg, dtype = death_info.get(cid, (None, 0, ""))
                    self.app._log(self.app._death_flavor_line(attacker, dmg, dtype, nm))
                    self.app.combatants.pop(cid, None)
                if getattr(self.app, "current_cid", None) in removed:
                    self.app.current_cid = None
                self.app._rebuild_table()
                self.refresh_units()

            self.app._rebuild_table()
            self._update_included_for_selected()
            refresh()
            if damage_dealt and self.aoes.get(aid, {}).get("pinned") is False and not self.aoes.get(aid, {}).get("persistent"):
                self._remove_aoe_by_id(aid)
            if close_after_var.get():
                dlg.destroy()

        ttk.Button(btns, text="Apply damage", command=apply_damage).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)
        close_after_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btns, text="Close after apply", variable=close_after_var).pack(side=tk.RIGHT, padx=(0, 8))

        dlg.bind("<Escape>", lambda e: dlg.destroy())
        try:
            if damage_components:
                first_ent = damage_components[0].get("amount_ent")
                if isinstance(first_ent, ttk.Entry):
                    first_ent.focus_set()
        except Exception:
            pass

        _toggle_condition_controls()

        refresh()

        _apply_dialog_geometry(dlg, 1120, 720, 900, 600)

    def _set_included_text(self, text: str) -> None:
        self.included_box.config(state=tk.NORMAL)
        self.included_box.delete("1.0", tk.END)
        self.included_box.insert("1.0", text)
        self.included_box.config(state=tk.DISABLED)

    def _compute_included_units(self, aid: int) -> List[int]:
        d = self.aoes[aid]
        kind = str(d["kind"])
        cx_px = self.x0 + (float(d["cx"]) + 0.5) * self.cell
        cy_px = self.y0 + (float(d["cy"]) + 0.5) * self.cell

        included: List[int] = []
        if kind in ("circle", "sphere", "cylinder"):
            r_px = float(d["radius_sq"]) * self.cell
            r2 = r_px * r_px
            for cid, tok in self.unit_tokens.items():
                x, y = self._grid_to_pixel(int(tok["col"]), int(tok["row"]))
                if (x - cx_px) ** 2 + (y - cy_px) ** 2 <= r2:
                    included.append(cid)
        elif kind in ("line", "wall"):
            length_px = float(d["length_sq"]) * self.cell
            width_px = float(d["width_sq"]) * self.cell
            angle_deg = d.get("angle_deg")
            if angle_deg is None:
                orient = str(d.get("orient") or "vertical")
                angle_deg = 0.0 if orient == "horizontal" else 90.0
            angle_rad = math.radians(float(angle_deg))
            cos_a = math.cos(-angle_rad)
            sin_a = math.sin(-angle_rad)
            for cid, tok in self.unit_tokens.items():
                x, y = self._grid_to_pixel(int(tok["col"]), int(tok["row"]))
                dx = x - cx_px
                dy = y - cy_px
                rx = dx * cos_a - dy * sin_a
                ry = dx * sin_a + dy * cos_a
                token_half = self.cell / 2.0
                if abs(rx) <= length_px / 2.0 + token_half and abs(ry) <= width_px / 2.0 + token_half:
                    included.append(cid)
        elif kind == "cone":
            length_px = float(d.get("length_sq") or 0.0) * self.cell
            spread_deg = d.get("spread_deg")
            has_spread = spread_deg is not None
            if spread_deg is None:
                spread_deg = d.get("angle_deg")
            if spread_deg is None:
                spread_deg = 90.0
            else:
                spread_deg = float(spread_deg)
            orient = str(d.get("orient") or "vertical")
            heading_deg = 0.0 if orient == "horizontal" else -90.0
            if has_spread:
                angle = d.get("angle_deg")
                if angle is not None:
                    heading_deg = float(angle)
            heading_rad = math.radians(heading_deg)
            half_spread = math.radians(spread_deg / 2.0)
            for cid, tok in self.unit_tokens.items():
                x, y = self._grid_to_pixel(int(tok["col"]), int(tok["row"]))
                dx = x - cx_px
                dy = y - cy_px
                dist = math.hypot(dx, dy)
                if dist > length_px + (self.cell / 2.0):
                    continue
                angle = math.atan2(dy, dx) - heading_rad
                while angle <= -math.pi:
                    angle += math.pi * 2
                while angle > math.pi:
                    angle -= math.pi * 2
                if abs(angle) <= half_spread:
                    included.append(cid)
        else:
            half = float(d["side_sq"]) * self.cell / 2.0
            angle = d.get("angle_deg") if kind in ("square", "cube") else None
            if angle is None:
                x1, y1 = cx_px - half, cy_px - half
                x2, y2 = cx_px + half, cy_px + half
                for cid, tok in self.unit_tokens.items():
                    x, y = self._grid_to_pixel(int(tok["col"]), int(tok["row"]))
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        included.append(cid)
            else:
                angle_rad = math.radians(float(angle))
                cos_a = math.cos(-angle_rad)
                sin_a = math.sin(-angle_rad)
                for cid, tok in self.unit_tokens.items():
                    x, y = self._grid_to_pixel(int(tok["col"]), int(tok["row"]))
                    dx = x - cx_px
                    dy = y - cy_px
                    rx = dx * cos_a - dy * sin_a
                    ry = dx * sin_a + dy * cos_a
                    if abs(rx) <= half and abs(ry) <= half:
                        included.append(cid)

        # stable order: by initiative order if possible
        order = [c.cid for c in self.app._display_order()] if hasattr(self.app, "_display_order") else []
        order_index = {cid: i for i, cid in enumerate(order)}
        included.sort(key=lambda cid: order_index.get(cid, 10**9))
        return included

    # ---------------- Active token highlight ----------------
    def set_active(self, cid: Optional[int], auto_center: bool = False) -> None:
        self._active_cid = cid
        self._apply_active_highlight()
        self._update_move_highlight()
        # Conditions / markers often change on turn transitions; refresh token markers + group labels.
        self._update_groups()
        if auto_center and cid is not None:
            self._center_on_cid(cid)

    def _apply_active_highlight(self) -> None:
        # reset all outlines to width=2
        for cid, tok in self.unit_tokens.items():
            try:
                self.canvas.itemconfigure(int(tok["oval"]), width=2)
            except Exception:
                pass
        if self._active_cid is None or self._active_cid not in self.unit_tokens:
            return
        tok = self.unit_tokens[self._active_cid]
        try:
            self.canvas.itemconfigure(int(tok["oval"]), width=4)
            self.canvas.tag_raise(int(tok["oval"]))
            if "marker" in tok:
                self.canvas.tag_raise(int(tok["marker"]))
            self.canvas.tag_raise(int(tok["text"]))
        except Exception:
            pass



if __name__ == "__main__":
    app = InitiativeTracker()
    app.mainloop()
