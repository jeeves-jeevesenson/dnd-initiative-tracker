#!/usr/bin/env python3
"""
Character YAML Builder (Tkinter GUI wizard)

Autodetects:
  ./Spells   (spell YAMLs)
  ./players  (character YAMLs)

Key features added per request:
- No args needed: run it in your project root and it discovers ./Spells and ./players
- Setup page lists existing character YAMLs in ./players (open/edit) + New
- Prepared spells picker ONLY lists spells from Known spells
- Vitals page includes HP (max/current/temp), hit dice, speed, formulas
- Pages persist state on Back/Next; list editors auto-apply on selection changes
- Robust Features editor:
    * categories: race/class/subclass/background/feat/item/special/custom
    * per-rest/per-day uses via pools created by the feature (or global pools)
    * spell grants: cantrips / known / always-prepared
    * limited “free casts” tied to a pool (consume pool, bypass slots)
    * actions granted by features (action/bonus/reaction + uses pool)
    * modifiers (generic, app-interpreted)
    * damage riders (conditional extra damage, optionally limited by a pool)

Schema notes (why the model is shaped this way):
- Many abilities are “uses per rest” (short/long) and are well-represented as pools. See UA Class Feature Variants
  examples like Tireless uses per ability modifier per long rest, Wild Companion expending another feature’s uses,
  and Blessed Strikes adding extra damage with timing limits. :contentReference[oaicite:0]{index=0}
- Many “racial/feat spell” traits are “cast X once per long rest” and explicitly don’t require spell slots; modeling
  as a limited cast tied to a pool matches that pattern. :contentReference[oaicite:1]{index=1}

Requires:
  pip install pyyaml

Run:
  python3 character_builder.py
"""

from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Dict, List, Optional, Callable

import yaml


# -----------------------------
# Helpers
# -----------------------------
def slugify(s: str, sep: str = "_") -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s-]+", sep, s).strip(sep)
    return s or "id"


def safe_int(s: str, default: int = 0) -> int:
    s = (s or "").strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return default


def scan_yaml_files(dirpath: str) -> List[str]:
    if not dirpath or not os.path.isdir(dirpath):
        return []
    out = []
    for fn in os.listdir(dirpath):
        if fn.lower().endswith(".yaml"):
            out.append(os.path.join(dirpath, fn))
    out.sort(key=lambda p: os.path.basename(p).lower())
    return out


def scan_spell_ids(spells_dir: str) -> List[str]:
    if not spells_dir or not os.path.isdir(spells_dir):
        return []
    ids: List[str] = []
    for fn in os.listdir(spells_dir):
        if fn.lower().endswith(".yaml"):
            ids.append(os.path.splitext(fn)[0])
    ids.sort()
    return ids


def read_spell_yaml_text(spells_dir: str, spell_id: str, max_chars: int = 200_000) -> str:
    path = os.path.join(spells_dir, f"{spell_id}.yaml")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(max_chars)
    except Exception as e:
        return f"# Error reading {path}: {e}"


def merge_defaults(user_obj: Any, defaults: Any) -> Any:
    """
    Merge defaults into a user-loaded object without clobbering user data.
    - If user is missing keys present in defaults, add them.
    - Recurse on dicts.
    """
    if isinstance(defaults, dict):
        if not isinstance(user_obj, dict):
            user_obj = {}
        for k, dv in defaults.items():
            if k not in user_obj:
                user_obj[k] = dv
            else:
                user_obj[k] = merge_defaults(user_obj[k], dv)
        return user_obj
    return user_obj


# -----------------------------
# Schema
# -----------------------------
def base_feature_template() -> Dict[str, Any]:
    return {
        "id": "new_feature",
        "name": "New Feature",
        "category": "custom",  # race/class/subclass/background/feat/item/special/custom
        "source": "",
        "level_acquired": 1,
        "tags": [],
        "description": "",
        "grants": {
            "pools": [],  # pool defs created by this feature
            "spells": {
                "cantrips": [],
                "known": [],
                "always_prepared": [],
                "casts": [],  # limited casts tied to pools
            },
            "actions": [],  # action/bonus/reaction abilities granted
            "modifiers": [],  # generic modifiers (your app interprets)
            "damage_riders": [],  # conditional extra damage
        },
        "notes": "",
    }


def base_template() -> Dict[str, Any]:
    return {
        "format_version": 2,
        "name": "",
        "player": "",
        "campaign": "",
        "ip": "",
        "identity": {
            "pronouns": "",
            "ancestry": "",
            "background": "",
            "alignment": "",
            "description": "",
        },
        "leveling": {
            "level": 1,
            "classes": [
                {"name": "", "subclass": "", "level": 1}
            ],
        },
        "abilities": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        "proficiency": {
            "bonus": 2,
            "saves": [],
            "skills": {"expertise": [], "proficient": []},
            "tools": [],
            "languages": [],
        },
        "vitals": {
            "max_hp": 1,
            "current_hp": 1,
            "temp_hp": 0,
            "hit_dice": {"die": "d8", "total": 1, "spent": 0},
            "speed": {"walk": 30, "climb": 0, "fly": 0, "swim": 0},
            "initiative": {"formula": "dex_mod"},
            "passive_perception": {"formula": "10 + wis_mod"},
        },
        "defenses": {
            "ac": {
                "sources": [
                    {"id": "unarmored", "label": "Unarmored", "when": "always", "base_formula": "10 + dex_mod"}
                ],
                "bonuses": [],
            },
            "resistances": [],
            "immunities": [],
            "vulnerabilities": [],
        },
        "resources": {"pools": []},
        "features": [],  # robust feature objects; see base_feature_template
        "actions": [],
        "reactions": [],
        "bonus_actions": [],
        "spellcasting": {
            "enabled": False,
            "spell_yaml_paths": ["./Spells"],
            "casting_ability": "",
            "save_dc_formula": "8 + prof + casting_mod",
            "spell_attack_formula": "prof + casting_mod",
            "cantrips": {"max": 0, "known": []},
            "known_spells": {"max": 0, "known": []},
            "prepared_spells": {"max_formula": "0", "prepared": []},
        },
        "inventory": {
            "currency": {"gp": 0, "sp": 0, "cp": 0},
            "items": [],
        },
        "notes": {},
    }


# -----------------------------
# Base page class
# -----------------------------
class WizardPage(ttk.Frame):
    title: str = "Page"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master)
        self.app = app

    def on_show(self) -> None:
        pass

    def save_to_state(self) -> bool:
        return True


# -----------------------------
# Shared editors
# -----------------------------
class SpellPicker(ttk.Frame):
    """
    Searchable spell list + selected list + YAML preview.

    You control which IDs appear via set_all_ids(ids).
    Selected list is user-managed (add/remove), exposed via get_selected().
    """

    def __init__(
        self,
        master: tk.Widget,
        app: "WizardApp",
        label: str,
        on_change: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master)
        self.app = app
        self.label = label
        self.on_change = on_change

        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=2)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(4, weight=1)

        ttk.Label(self, text=label).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="Selected").grid(row=0, column=2, sticky="w")

        self.search_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.search_var).grid(row=1, column=0, sticky="ew", pady=(4, 4))
        self.search_var.trace_add("write", lambda *_: self.refresh_all_list())

        self.all_list = tk.Listbox(self, height=10)
        self.all_list.grid(row=2, column=0, sticky="nsew")
        self.all_list.bind("<<ListboxSelect>>", self.on_select_spell_in_all)

        mid = ttk.Frame(self)
        mid.grid(row=2, column=1, sticky="ns", padx=8)
        ttk.Button(mid, text="Add →", command=self.add_selected).grid(row=0, column=0, pady=(0, 6))
        ttk.Button(mid, text="← Remove", command=self.remove_selected).grid(row=1, column=0)

        self.sel_list = tk.Listbox(self, height=10)
        self.sel_list.grid(row=2, column=2, sticky="nsew")

        ttk.Label(self, text="Spell YAML preview").grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.preview = tk.Text(self, height=10, wrap="none")
        self.preview.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(4, 0))

        self._all_ids: List[str] = []
        self._selected: List[str] = []

    def set_all_ids(self, ids: List[str]) -> None:
        self._all_ids = ids[:]
        self.refresh_all_list()

    def set_selected(self, selected: List[str]) -> None:
        self._selected = selected[:]
        self.refresh_selected_list()

    def get_selected(self) -> List[str]:
        return self._selected[:]

    def refresh_all_list(self) -> None:
        q = self.search_var.get().strip().lower()
        self.all_list.delete(0, "end")
        for sid in self._all_ids:
            if not q or q in sid.lower():
                self.all_list.insert("end", sid)

    def refresh_selected_list(self) -> None:
        self.sel_list.delete(0, "end")
        for sid in self._selected:
            self.sel_list.insert("end", sid)

    def on_select_spell_in_all(self, _evt: Any) -> None:
        sel = self.all_list.curselection()
        if not sel:
            return
        sid = self.all_list.get(sel[0])
        text = read_spell_yaml_text(self.app.spells_dir, sid)
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text if text else f"# {sid}.yaml not found")

    def add_selected(self) -> None:
        sel = self.all_list.curselection()
        if not sel:
            return
        sid = self.all_list.get(sel[0])
        if sid not in self._selected:
            self._selected.append(sid)
            self.refresh_selected_list()
            if self.on_change:
                self.on_change()

    def remove_selected(self) -> None:
        sel = self.sel_list.curselection()
        if not sel:
            return
        sid = self.sel_list.get(sel[0])
        self._selected = [x for x in self._selected if x != sid]
        self.refresh_selected_list()
        if self.on_change:
            self.on_change()


# -----------------------------
# Setup / Library page
# -----------------------------
class SetupPage(WizardPage):
    title = "Library"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(10, 6))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Detected directories:").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"Spells: {app.spells_dir}", foreground="#555").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(top, text=f"Players: {app.players_dir}", foreground="#555").grid(row=2, column=0, sticky="w", pady=(2, 0))

        self.spell_count = ttk.Label(top, text="", foreground="#555")
        self.spell_count.grid(row=1, column=1, sticky="w", padx=12)

        self.char_count = ttk.Label(top, text="", foreground="#555")
        self.char_count.grid(row=2, column=1, sticky="w", padx=12)

        btns = ttk.Frame(self)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        ttk.Button(btns, text="New Character", command=self.app.new_character).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="Open YAML…", command=self.open_any_yaml).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(btns, text="Refresh Library", command=self.refresh_lists).grid(row=0, column=2)

        ttk.Label(self, text="Characters in ./players").grid(row=2, column=0, sticky="nw", padx=8, pady=(6, 0))
        self.listbox = tk.Listbox(self, height=14)
        self.listbox.grid(row=2, column=0, sticky="nsew", padx=8, pady=6)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.open_selected())

        right = ttk.Frame(self)
        right.grid(row=2, column=1, sticky="nsew", padx=8, pady=6)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(right, text="Selected file preview").grid(row=0, column=0, sticky="w")
        self.preview = tk.Text(right, wrap="none")
        self.preview.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        ttk.Button(right, text="Open Selected", command=self.open_selected).grid(row=2, column=0, sticky="w", pady=(8, 0))

    def on_show(self) -> None:
        self.refresh_lists()

    def refresh_lists(self) -> None:
        self.app.refresh_spell_cache()
        self.app.refresh_player_cache()
        self.spell_count.config(text=f"{len(self.app.spell_ids)} spell YAMLs found")
        self.char_count.config(text=f"{len(self.app.player_files)} character YAMLs found")

        self.listbox.delete(0, "end")
        for p in self.app.player_files:
            self.listbox.insert("end", os.path.basename(p))

        self.preview.delete("1.0", "end")

    def open_any_yaml(self) -> None:
        path = filedialog.askopenfilename(
            title="Open character YAML…",
            initialdir=self.app.players_dir,
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
        )
        if path:
            self.app.load_character(path)
            self.app.go_to_page_title("Basics")

    def open_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.app.player_files):
            return
        path = self.app.player_files[idx]
        self.app.load_character(path)
        self.app.go_to_page_title("Basics")

    def save_to_state(self) -> bool:
        # nothing
        return True


# -----------------------------
# Basics page
# -----------------------------
class BasicsPage(WizardPage):
    title = "Basics"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)

        self.columnconfigure(1, weight=1)
        self.rowconfigure(9, weight=1)

        ttk.Label(self, text="Character name:").grid(row=0, column=0, sticky="w", padx=8, pady=(10, 4))
        self.name_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=8, pady=(10, 4))
        ttk.Label(self, text="(required)", foreground="#555").grid(row=0, column=2, sticky="w", padx=8, pady=(10, 4))

        ttk.Label(self, text="Player:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.player_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.player_var).grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Campaign:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.campaign_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.campaign_var).grid(row=2, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="IP:").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.ip_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.ip_var).grid(row=3, column=1, sticky="ew", padx=8, pady=4)

        ttk.Separator(self).grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 10))

        ttk.Label(self, text="Pronouns:").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        self.pronouns_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.pronouns_var).grid(row=5, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Ancestry/species:").grid(row=6, column=0, sticky="w", padx=8, pady=4)
        self.ancestry_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.ancestry_var).grid(row=6, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Background:").grid(row=7, column=0, sticky="w", padx=8, pady=4)
        self.background_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.background_var).grid(row=7, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Alignment:").grid(row=8, column=0, sticky="w", padx=8, pady=4)
        self.alignment_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.alignment_var).grid(row=8, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Description:").grid(row=9, column=0, sticky="nw", padx=8, pady=4)
        self.desc_text = tk.Text(self, height=8, wrap="word")
        self.desc_text.grid(row=9, column=1, sticky="nsew", padx=8, pady=4)

    def on_show(self) -> None:
        c = self.app.char
        self.name_var.set(c.get("name", ""))
        self.player_var.set(c.get("player", ""))
        self.campaign_var.set(c.get("campaign", ""))
        self.ip_var.set(c.get("ip", ""))

        ident = c.get("identity", {})
        self.pronouns_var.set(ident.get("pronouns", ""))
        self.ancestry_var.set(ident.get("ancestry", ""))
        self.background_var.set(ident.get("background", ""))
        self.alignment_var.set(ident.get("alignment", ""))

        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", ident.get("description", "") or "")

    def save_to_state(self) -> bool:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Missing name", "Character name is required.")
            return False

        c = self.app.char
        c["name"] = name
        c["player"] = self.player_var.get().strip()
        c["campaign"] = self.campaign_var.get().strip()
        c["ip"] = self.ip_var.get().strip()

        c["identity"]["pronouns"] = self.pronouns_var.get().strip()
        c["identity"]["ancestry"] = self.ancestry_var.get().strip()
        c["identity"]["background"] = self.background_var.get().strip()
        c["identity"]["alignment"] = self.alignment_var.get().strip()
        c["identity"]["description"] = self.desc_text.get("1.0", "end").strip()
        return True


# -----------------------------
# Level & abilities page
# -----------------------------
class LevelAbilitiesPage(WizardPage):
    title = "Level & Abilities"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Total level:").grid(row=0, column=0, sticky="w", padx=8, pady=(10, 4))
        self.level_var = tk.StringVar(value="1")
        ttk.Entry(self, textvariable=self.level_var, width=8).grid(row=0, column=1, sticky="w", padx=8, pady=(10, 4))
        ttk.Label(self, text="Example: 5", foreground="#555").grid(row=0, column=2, sticky="w", padx=8, pady=(10, 4))

        ttk.Label(self, text="Class:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.class_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.class_var).grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Subclass:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.subclass_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.subclass_var).grid(row=2, column=1, sticky="ew", padx=8, pady=4)

        ttk.Separator(self).grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 10))

        ttk.Label(self, text="Abilities:").grid(row=4, column=0, sticky="nw", padx=8, pady=4)
        grid = ttk.Frame(self)
        grid.grid(row=4, column=1, sticky="w", padx=8, pady=4)

        self.ability_vars: Dict[str, tk.StringVar] = {}
        for i, key in enumerate(["str", "dex", "con", "int", "wis", "cha"]):
            ttk.Label(grid, text=key.upper()).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)
            v = tk.StringVar(value="10")
            self.ability_vars[key] = v
            ttk.Entry(grid, textvariable=v, width=6).grid(row=i, column=1, sticky="w", pady=2)

    def on_show(self) -> None:
        c = self.app.char
        self.level_var.set(str(c["leveling"].get("level", 1)))
        cls0 = c["leveling"]["classes"][0] if c["leveling"]["classes"] else {"name": "", "subclass": "", "level": c["leveling"]["level"]}
        self.class_var.set(cls0.get("name", ""))
        self.subclass_var.set(cls0.get("subclass", ""))

        ab = c.get("abilities", {})
        for k, v in self.ability_vars.items():
            v.set(str(ab.get(k, 10)))

    def save_to_state(self) -> bool:
        c = self.app.char
        lvl = safe_int(self.level_var.get(), 1)
        if lvl <= 0:
            messagebox.showerror("Invalid level", "Level must be >= 1.")
            return False

        cname = self.class_var.get().strip()
        if not cname:
            messagebox.showerror("Missing class", "Class is required (multiclass can be added later).")
            return False

        c["leveling"]["level"] = lvl
        c["leveling"]["classes"] = [{
            "name": cname,
            "subclass": self.subclass_var.get().strip(),
            "level": lvl,
        }]

        for k, var in self.ability_vars.items():
            c["abilities"][k] = safe_int(var.get(), 10)
        return True


# -----------------------------
# Vitals page (HP etc)
# -----------------------------
class VitalsPage(WizardPage):
    title = "Vitals"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="HP").grid(row=0, column=0, sticky="w", padx=8, pady=(10, 4))
        hp = ttk.Frame(self)
        hp.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=4)

        self.max_hp = tk.StringVar()
        self.cur_hp = tk.StringVar()
        self.tmp_hp = tk.StringVar()

        ttk.Label(hp, text="Max:").grid(row=0, column=0, sticky="w")
        ttk.Entry(hp, textvariable=self.max_hp, width=8).grid(row=0, column=1, padx=(6, 16))
        ttk.Label(hp, text="Current:").grid(row=0, column=2, sticky="w")
        ttk.Entry(hp, textvariable=self.cur_hp, width=8).grid(row=0, column=3, padx=(6, 16))
        ttk.Label(hp, text="Temp:").grid(row=0, column=4, sticky="w")
        ttk.Entry(hp, textvariable=self.tmp_hp, width=8).grid(row=0, column=5, padx=(6, 0))

        ttk.Separator(self).grid(row=2, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 10))

        ttk.Label(self, text="Hit Dice").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        hd = ttk.Frame(self)
        hd.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=4)

        self.hd_die = tk.StringVar()
        self.hd_total = tk.StringVar()
        self.hd_spent = tk.StringVar()

        ttk.Label(hd, text="Die:").grid(row=0, column=0, sticky="w")
        ttk.Entry(hd, textvariable=self.hd_die, width=8).grid(row=0, column=1, padx=(6, 16))
        ttk.Label(hd, text="Total:").grid(row=0, column=2, sticky="w")
        ttk.Entry(hd, textvariable=self.hd_total, width=8).grid(row=0, column=3, padx=(6, 16))
        ttk.Label(hd, text="Spent:").grid(row=0, column=4, sticky="w")
        ttk.Entry(hd, textvariable=self.hd_spent, width=8).grid(row=0, column=5, padx=(6, 0))

        ttk.Separator(self).grid(row=5, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 10))

        ttk.Label(self, text="Speed").grid(row=6, column=0, sticky="w", padx=8, pady=4)
        sp = ttk.Frame(self)
        sp.grid(row=7, column=0, columnspan=3, sticky="ew", padx=8, pady=4)

        self.walk = tk.StringVar()
        self.climb = tk.StringVar()
        self.fly = tk.StringVar()
        self.swim = tk.StringVar()

        ttk.Label(sp, text="Walk:").grid(row=0, column=0, sticky="w")
        ttk.Entry(sp, textvariable=self.walk, width=8).grid(row=0, column=1, padx=(6, 16))
        ttk.Label(sp, text="Climb:").grid(row=0, column=2, sticky="w")
        ttk.Entry(sp, textvariable=self.climb, width=8).grid(row=0, column=3, padx=(6, 16))
        ttk.Label(sp, text="Fly:").grid(row=0, column=4, sticky="w")
        ttk.Entry(sp, textvariable=self.fly, width=8).grid(row=0, column=5, padx=(6, 16))
        ttk.Label(sp, text="Swim:").grid(row=0, column=6, sticky="w")
        ttk.Entry(sp, textvariable=self.swim, width=8).grid(row=0, column=7, padx=(6, 0))

        ttk.Separator(self).grid(row=8, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 10))

        ttk.Label(self, text="Formulas").grid(row=9, column=0, sticky="w", padx=8, pady=4)
        fm = ttk.Frame(self)
        fm.grid(row=10, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
        fm.columnconfigure(1, weight=1)

        self.init_formula = tk.StringVar()
        self.pp_formula = tk.StringVar()

        ttk.Label(fm, text="Initiative formula:").grid(row=0, column=0, sticky="w")
        ttk.Entry(fm, textvariable=self.init_formula).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(fm, text="Passive Perception formula:").grid(row=1, column=0, sticky="w")
        ttk.Entry(fm, textvariable=self.pp_formula).grid(row=1, column=1, sticky="ew", padx=(8, 0))

    def on_show(self) -> None:
        v = self.app.char.get("vitals", {})
        self.max_hp.set(str(v.get("max_hp", 1)))
        self.cur_hp.set(str(v.get("current_hp", 1)))
        self.tmp_hp.set(str(v.get("temp_hp", 0)))

        hd = v.get("hit_dice", {})
        self.hd_die.set(str(hd.get("die", "d8")))
        self.hd_total.set(str(hd.get("total", self.app.char.get("leveling", {}).get("level", 1))))
        self.hd_spent.set(str(hd.get("spent", 0)))

        sp = v.get("speed", {})
        self.walk.set(str(sp.get("walk", 30)))
        self.climb.set(str(sp.get("climb", 0)))
        self.fly.set(str(sp.get("fly", 0)))
        self.swim.set(str(sp.get("swim", 0)))

        self.init_formula.set(str(v.get("initiative", {}).get("formula", "dex_mod")))
        self.pp_formula.set(str(v.get("passive_perception", {}).get("formula", "10 + wis_mod")))

    def save_to_state(self) -> bool:
        c = self.app.char
        v = c["vitals"]

        max_hp = safe_int(self.max_hp.get(), 1)
        cur_hp = safe_int(self.cur_hp.get(), max_hp)
        tmp_hp = safe_int(self.tmp_hp.get(), 0)

        if max_hp <= 0:
            messagebox.showerror("Invalid HP", "Max HP must be >= 1.")
            return False

        v["max_hp"] = max_hp
        v["current_hp"] = max(0, cur_hp)
        v["temp_hp"] = max(0, tmp_hp)

        v["hit_dice"]["die"] = (self.hd_die.get().strip() or "d8")
        v["hit_dice"]["total"] = max(0, safe_int(self.hd_total.get(), c["leveling"]["level"]))
        v["hit_dice"]["spent"] = max(0, safe_int(self.hd_spent.get(), 0))

        v["speed"]["walk"] = max(0, safe_int(self.walk.get(), 30))
        v["speed"]["climb"] = max(0, safe_int(self.climb.get(), 0))
        v["speed"]["fly"] = max(0, safe_int(self.fly.get(), 0))
        v["speed"]["swim"] = max(0, safe_int(self.swim.get(), 0))

        v["initiative"]["formula"] = self.init_formula.get().strip() or "dex_mod"
        v["passive_perception"]["formula"] = self.pp_formula.get().strip() or "10 + wis_mod"
        return True


# -----------------------------
# Resources page (global pools)
# -----------------------------
class ResourcesPage(WizardPage):
    title = "Resources"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        outer = ttk.Frame(self)
        outer.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(0, weight=1)

        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Resource pools").grid(row=0, column=0, sticky="w")
        self.pool_list = tk.Listbox(left, height=12)
        self.pool_list.grid(row=1, column=0, sticky="nsew", pady=(4, 4))
        self.pool_list.bind("<<ListboxSelect>>", self.on_select_pool)

        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Add", command=self.add_pool).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Remove", command=self.remove_pool).grid(row=0, column=1)

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        self.e_id = tk.StringVar()
        self.e_label = tk.StringVar()
        self.e_current = tk.StringVar()
        self.e_max = tk.StringVar()
        self.e_reset = tk.StringVar(value="long_rest")
        self.e_notes = tk.StringVar()

        row = 0
        ttk.Label(right, text="id:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.e_id).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1
        ttk.Label(right, text="label:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.e_label).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1
        ttk.Label(right, text="current:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.e_current).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1
        ttk.Label(right, text="max_formula:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.e_max).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1
        ttk.Label(right, text="reset:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.e_reset, values=["long_rest", "short_rest", "dawn", "never", "custom"], state="readonly").grid(
            row=row, column=1, sticky="w", pady=2
        )
        row += 1
        ttk.Label(right, text="notes:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.e_notes).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Button(right, text="Apply changes", command=self.apply_changes).grid(row=row, column=1, sticky="w", pady=(10, 0))

        self._selected_index: Optional[int] = None

    def on_show(self) -> None:
        self.refresh_list()
        self._selected_index = None

    def refresh_list(self) -> None:
        self.pool_list.delete(0, "end")
        pools = self.app.char["resources"]["pools"]
        for p in pools:
            self.pool_list.insert("end", f"{p.get('id','')}  —  {p.get('label','')}")

    def on_select_pool(self, _evt: Any) -> None:
        self.apply_changes(silent=True)
        sel = self.pool_list.curselection()
        if not sel:
            return
        idx = sel[0]
        pools = self.app.char["resources"]["pools"]
        if idx < 0 or idx >= len(pools):
            return
        p = pools[idx]
        self._selected_index = idx
        self.e_id.set(str(p.get("id", "")))
        self.e_label.set(str(p.get("label", "")))
        self.e_current.set(str(p.get("current", 0)))
        self.e_max.set(str(p.get("max_formula", 1)))
        self.e_reset.set(str(p.get("reset", "long_rest")))
        self.e_notes.set(str(p.get("notes", "")))

    def add_pool(self) -> None:
        pools = self.app.char["resources"]["pools"]
        label = "New Pool"
        pid = slugify(label)
        existing = {p.get("id") for p in pools}
        base = pid
        n = 2
        while pid in existing:
            pid = f"{base}_{n}"
            n += 1
        pools.append({"id": pid, "label": label, "current": 0, "max_formula": 1, "reset": "long_rest", "notes": ""})
        self.refresh_list()
        self.pool_list.selection_set(len(pools) - 1)
        self.on_select_pool(None)

    def remove_pool(self) -> None:
        sel = self.pool_list.curselection()
        if not sel:
            return
        idx = sel[0]
        pools = self.app.char["resources"]["pools"]
        if idx < 0 or idx >= len(pools):
            return
        if not messagebox.askyesno("Remove pool", f"Remove pool '{pools[idx].get('label','')}'?"):
            return
        pools.pop(idx)
        self.refresh_list()
        self._selected_index = None

    def apply_changes(self, silent: bool = False) -> None:
        if self._selected_index is None:
            return
        pools = self.app.char["resources"]["pools"]
        idx = self._selected_index
        if idx < 0 or idx >= len(pools):
            return

        pid = self.e_id.get().strip()
        if not pid:
            if not silent:
                messagebox.showerror("Invalid pool", "Pool id cannot be empty.")
            return

        other_ids = {p.get("id") for i, p in enumerate(pools) if i != idx}
        if pid in other_ids:
            if not silent:
                messagebox.showerror("Duplicate id", f"Pool id '{pid}' already exists.")
            return

        pools[idx]["id"] = pid
        pools[idx]["label"] = self.e_label.get().strip()
        pools[idx]["current"] = max(0, safe_int(self.e_current.get(), 0))

        max_raw = self.e_max.get().strip()
        pools[idx]["max_formula"] = safe_int(max_raw, 0) if re.fullmatch(r"-?\d+", max_raw) else (max_raw or 0)

        pools[idx]["reset"] = self.e_reset.get().strip() or "long_rest"
        pools[idx]["notes"] = self.e_notes.get().strip()

        self.refresh_list()
        self.pool_list.selection_set(idx)
        self._selected_index = idx

    def save_to_state(self) -> bool:
        self.apply_changes(silent=True)
        return True


# -----------------------------
# Spellcasting page
# -----------------------------
class SpellcastingPage(WizardPage):
    title = "Spellcasting"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 4))
        top.columnconfigure(3, weight=1)

        self.enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Enable spellcasting", variable=self.enabled_var).grid(row=0, column=0, sticky="w")

        ttk.Label(top, text="Casting ability:").grid(row=0, column=1, sticky="e")
        self.ability_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.ability_var, width=8).grid(row=0, column=2, sticky="w", padx=(8, 0))

        formulas = ttk.Frame(self)
        formulas.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 6))
        formulas.columnconfigure(1, weight=1)

        ttk.Label(formulas, text="Save DC formula:").grid(row=0, column=0, sticky="w")
        self.dc_var = tk.StringVar()
        ttk.Entry(formulas, textvariable=self.dc_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(formulas, text="Spell attack formula:").grid(row=1, column=0, sticky="w")
        self.atk_var = tk.StringVar()
        ttk.Entry(formulas, textvariable=self.atk_var).grid(row=1, column=1, sticky="ew", padx=(8, 0))

        counts = ttk.Frame(self)
        counts.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 6))

        ttk.Label(counts, text="Cantrips max:").grid(row=0, column=0, sticky="w")
        self.cantrips_max_var = tk.StringVar(value="0")
        ttk.Entry(counts, textvariable=self.cantrips_max_var, width=8).grid(row=0, column=1, sticky="w", padx=(8, 20))

        ttk.Label(counts, text="Known spells max:").grid(row=0, column=2, sticky="w")
        self.known_max_var = tk.StringVar(value="0")
        ttk.Entry(counts, textvariable=self.known_max_var, width=8).grid(row=0, column=3, sticky="w", padx=(8, 20))

        ttk.Label(counts, text="Prepared max_formula:").grid(row=0, column=4, sticky="w")
        self.prep_max_var = tk.StringVar(value="0")
        ttk.Entry(counts, textvariable=self.prep_max_var, width=18).grid(row=0, column=5, sticky="w", padx=(8, 0))

        pickers = ttk.Frame(self)
        pickers.grid(row=4, column=0, sticky="nsew", padx=8, pady=(6, 8))
        pickers.columnconfigure(0, weight=1)
        pickers.rowconfigure(0, weight=1)

        nb = ttk.Notebook(pickers)
        nb.grid(row=0, column=0, sticky="nsew")
        self.nb = nb

        self.cantrip_picker = SpellPicker(nb, app, "Cantrips (spell IDs)")
        self.known_picker = SpellPicker(nb, app, "Known spells (spell IDs)", on_change=self.on_known_changed)
        self.prep_picker = SpellPicker(nb, app, "Prepared spells (only from Known)")

        nb.add(self.cantrip_picker, text="Cantrips")
        nb.add(self.known_picker, text="Known")
        nb.add(self.prep_picker, text="Prepared")

        self.hint = ttk.Label(self, text="Prepared list is constrained to the Known list on this page.", foreground="#555")
        self.hint.grid(row=5, column=0, sticky="w", padx=8, pady=(0, 10))

    def on_show(self) -> None:
        c = self.app.char
        sc = c.get("spellcasting", {})
        self.enabled_var.set(bool(sc.get("enabled", False)))
        self.ability_var.set(sc.get("casting_ability", "") or "")
        self.dc_var.set(sc.get("save_dc_formula", "8 + prof + casting_mod"))
        self.atk_var.set(sc.get("spell_attack_formula", "prof + casting_mod"))
        self.cantrips_max_var.set(str(sc.get("cantrips", {}).get("max", 0)))
        self.known_max_var.set(str(sc.get("known_spells", {}).get("max", 0)))
        self.prep_max_var.set(str(sc.get("prepared_spells", {}).get("max_formula", "0")))

        all_ids = self.app.spell_ids[:]
        self.cantrip_picker.set_all_ids(all_ids)
        self.known_picker.set_all_ids(all_ids)

        self.cantrip_picker.set_selected(sc.get("cantrips", {}).get("known", []) or [])
        self.known_picker.set_selected(sc.get("known_spells", {}).get("known", []) or [])

        self.on_known_changed(load_existing_prepared=sc.get("prepared_spells", {}).get("prepared", []) or [])

    def on_known_changed(self, load_existing_prepared: Optional[List[str]] = None) -> None:
        known = self.known_picker.get_selected()
        known_set = set(known)

        # Prepared options restricted to known
        self.prep_picker.set_all_ids(known)

        if load_existing_prepared is not None:
            prepared = [s for s in load_existing_prepared if s in known_set]
        else:
            prepared = [s for s in self.prep_picker.get_selected() if s in known_set]
        self.prep_picker.set_selected(prepared)

    def save_to_state(self) -> bool:
        c = self.app.char
        sc = c["spellcasting"]

        sc["enabled"] = bool(self.enabled_var.get())
        sc["spell_yaml_paths"] = [self.app.spells_dir]

        if sc["enabled"] and not (self.ability_var.get().strip()):
            messagebox.showerror("Missing casting ability", "Spellcasting is enabled; casting_ability is required.")
            return False

        sc["casting_ability"] = self.ability_var.get().strip()
        sc["save_dc_formula"] = self.dc_var.get().strip() or "8 + prof + casting_mod"
        sc["spell_attack_formula"] = self.atk_var.get().strip() or "prof + casting_mod"

        sc["cantrips"]["max"] = max(0, safe_int(self.cantrips_max_var.get(), 0))
        sc["known_spells"]["max"] = max(0, safe_int(self.known_max_var.get(), 0))
        sc["prepared_spells"]["max_formula"] = self.prep_max_var.get().strip() or "0"

        sc["cantrips"]["known"] = self.cantrip_picker.get_selected()
        sc["known_spells"]["known"] = self.known_picker.get_selected()

        known_set = set(sc["known_spells"]["known"])
        sc["prepared_spells"]["prepared"] = [s for s in self.prep_picker.get_selected() if s in known_set]
        return True


# -----------------------------
# Features page (robust)
# -----------------------------
class FeaturesPage(WizardPage):
    title = "Features"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(0, weight=1)

        # Left: feature list
        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Features").grid(row=0, column=0, sticky="w")

        self.feature_list = tk.Listbox(left, height=18)
        self.feature_list.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.feature_list.bind("<<ListboxSelect>>", self.on_select_feature)

        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Add", command=self.add_feature).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Duplicate", command=self.dup_feature).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(btns, text="Remove", command=self.remove_feature).grid(row=0, column=2)

        # Right: editor
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        self._selected_idx: Optional[int] = None

        # Header fields
        self.f_id = tk.StringVar()
        self.f_name = tk.StringVar()
        self.f_cat = tk.StringVar(value="custom")
        self.f_source = tk.StringVar()
        self.f_level = tk.StringVar(value="1")
        self.f_tags = tk.StringVar()

        row = 0
        ttk.Label(right, text="id:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.f_id).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="name:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.f_name).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        meta = ttk.Frame(right)
        meta.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
        meta.columnconfigure(5, weight=1)

        ttk.Label(meta, text="category:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            meta,
            textvariable=self.f_cat,
            values=["race", "class", "subclass", "background", "feat", "item", "special", "custom"],
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=(6, 16))

        ttk.Label(meta, text="level_acquired:").grid(row=0, column=2, sticky="w")
        ttk.Entry(meta, textvariable=self.f_level, width=6).grid(row=0, column=3, sticky="w", padx=(6, 16))

        ttk.Label(meta, text="source:").grid(row=0, column=4, sticky="w")
        ttk.Entry(meta, textvariable=self.f_source).grid(row=0, column=5, sticky="ew", padx=(6, 0))
        row += 1

        ttk.Label(right, text="tags (comma-separated):").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.f_tags).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="description:").grid(row=row, column=0, sticky="nw", pady=2)
        self.f_desc = tk.Text(right, height=5, wrap="word")
        self.f_desc.grid(row=row, column=1, sticky="nsew", pady=2)
        row += 1

        # Notebook for grants
        nb = ttk.Notebook(right)
        nb.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        right.rowconfigure(row, weight=1)

        self.nb = nb

        self.tab_pools = ttk.Frame(nb)
        self.tab_spells = ttk.Frame(nb)
        self.tab_actions = ttk.Frame(nb)
        self.tab_mods = ttk.Frame(nb)
        self.tab_damage = ttk.Frame(nb)

        nb.add(self.tab_pools, text="Pools")
        nb.add(self.tab_spells, text="Spells")
        nb.add(self.tab_actions, text="Actions")
        nb.add(self.tab_mods, text="Modifiers")
        nb.add(self.tab_damage, text="Damage Riders")

        # Build tabs
        self._build_pools_tab()
        self._build_spells_tab()
        self._build_actions_tab()
        self._build_mods_tab()
        self._build_damage_tab()

        ttk.Label(
            right,
            text="Tip: Use Pools + Spells(casts) to model “once/long rest free casting” or feature-limited abilities.",
            foreground="#555",
        ).grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    # ----- Tab builders -----
    def _build_pools_tab(self) -> None:
        f = self.tab_pools
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=2)
        f.rowconfigure(0, weight=1)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Feature pools").grid(row=0, column=0, sticky="w")

        self.fp_list = tk.Listbox(left, height=10)
        self.fp_list.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.fp_list.bind("<<ListboxSelect>>", self._on_select_fp)

        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Add", command=self._fp_add).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Remove", command=self._fp_remove).grid(row=0, column=1)

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        right.columnconfigure(1, weight=1)

        self.fp_id = tk.StringVar()
        self.fp_label = tk.StringVar()
        self.fp_current = tk.StringVar()
        self.fp_max = tk.StringVar()
        self.fp_reset = tk.StringVar(value="long_rest")
        self.fp_notes = tk.StringVar()
        self._fp_sel: Optional[int] = None

        r = 0
        ttk.Label(right, text="id:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fp_id).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="label:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fp_label).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="current:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fp_current).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="max_formula:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fp_max).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="reset:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.fp_reset, values=["long_rest", "short_rest", "dawn", "never", "custom"], state="readonly").grid(
            row=r, column=1, sticky="w", pady=2
        ); r += 1
        ttk.Label(right, text="notes:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fp_notes).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Button(right, text="Apply", command=self._fp_apply).grid(row=r, column=1, sticky="w", pady=(8, 0))

    def _build_spells_tab(self) -> None:
        f = self.tab_spells
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        nb = ttk.Notebook(f)
        nb.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.fspell_nb = nb

        self.sp_can = SpellPicker(nb, self.app, "Granted cantrips (feature)")
        self.sp_known = SpellPicker(nb, self.app, "Granted known spells (feature)")
        self.sp_always = SpellPicker(nb, self.app, "Always-prepared spells (feature)")
        nb.add(self.sp_can, text="Cantrips")
        nb.add(self.sp_known, text="Known")
        nb.add(self.sp_always, text="Always Prepared")

        # Limited casts editor
        cast_tab = ttk.Frame(nb)
        nb.add(cast_tab, text="Casts (limited/free)")

        cast_tab.columnconfigure(0, weight=2)
        cast_tab.columnconfigure(1, weight=1)
        cast_tab.columnconfigure(2, weight=2)
        cast_tab.rowconfigure(1, weight=1)

        ttk.Label(
            cast_tab,
            text="Each entry: a spell consumes a pool (feature pool or global pool). Set bypass_slots=true for free casts.",
            foreground="#555",
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        self.fc_tree = ttk.Treeview(cast_tab, columns=("spell", "pool", "cost", "atype", "bypass"), show="headings", height=7)
        for col, title in [("spell", "Spell"), ("pool", "Pool"), ("cost", "Cost"), ("atype", "Action"), ("bypass", "Bypass slots")]:
            self.fc_tree.heading(col, text=title)
            self.fc_tree.column(col, width=130 if col in ("spell", "pool") else 90, stretch=True)
        self.fc_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.fc_tree.bind("<<TreeviewSelect>>", self._fc_select)

        ed = ttk.Frame(cast_tab)
        ed.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=(10, 0), pady=(6, 0))
        ed.columnconfigure(1, weight=1)

        self.fc_spell = tk.StringVar()
        self.fc_pool = tk.StringVar()
        self.fc_cost = tk.StringVar(value="1")
        self.fc_action = tk.StringVar(value="action")
        self.fc_bypass = tk.BooleanVar(value=True)
        self.fc_notes = tk.StringVar()
        self._fc_sel: Optional[int] = None

        ttk.Label(ed, text="Spell:").grid(row=0, column=0, sticky="w", pady=2)
        self.fc_spell_box = ttk.Combobox(ed, textvariable=self.fc_spell, values=[], state="readonly")
        self.fc_spell_box.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(ed, text="Pool:").grid(row=1, column=0, sticky="w", pady=2)
        self.fc_pool_box = ttk.Combobox(ed, textvariable=self.fc_pool, values=[], state="readonly")
        self.fc_pool_box.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(ed, text="Cost:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(ed, textvariable=self.fc_cost, width=8).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(ed, text="Action type:").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Combobox(ed, textvariable=self.fc_action, values=["action", "bonus_action", "reaction"], state="readonly").grid(
            row=3, column=1, sticky="w", pady=2
        )

        ttk.Checkbutton(ed, text="Bypass spell slots (free cast)", variable=self.fc_bypass).grid(row=4, column=1, sticky="w", pady=(6, 2))

        ttk.Label(ed, text="Notes:").grid(row=5, column=0, sticky="w", pady=2)
        ttk.Entry(ed, textvariable=self.fc_notes).grid(row=5, column=1, sticky="ew", pady=2)

        b = ttk.Frame(ed)
        b.grid(row=6, column=1, sticky="w", pady=(8, 0))
        ttk.Button(b, text="Add / Update", command=self._fc_add_or_update).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(b, text="Remove", command=self._fc_remove).grid(row=0, column=1)

    def _build_actions_tab(self) -> None:
        f = self.tab_actions
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=2)
        f.rowconfigure(0, weight=1)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Granted actions").grid(row=0, column=0, sticky="w")
        self.fa_list = tk.Listbox(left, height=10)
        self.fa_list.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.fa_list.bind("<<ListboxSelect>>", self._fa_select)

        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Add", command=self._fa_add).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Remove", command=self._fa_remove).grid(row=0, column=1)

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        self.fa_name = tk.StringVar()
        self.fa_type = tk.StringVar(value="action")
        self.fa_pool = tk.StringVar()
        self.fa_cost = tk.StringVar(value="1")
        self.fa_notes = tk.StringVar()
        self.fa_desc = tk.Text(right, height=5, wrap="word")
        self._fa_sel: Optional[int] = None

        r = 0
        ttk.Label(right, text="name:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fa_name).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(right, text="type:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.fa_type, values=["action", "bonus_action", "reaction", "passive"], state="readonly").grid(
            row=r, column=1, sticky="w", pady=2
        ); r += 1

        ttk.Label(right, text="uses pool (optional):").grid(row=r, column=0, sticky="w", pady=2)
        self.fa_pool_box = ttk.Combobox(right, textvariable=self.fa_pool, values=[], state="readonly")
        self.fa_pool_box.grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(right, text="pool cost:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fa_cost, width=8).grid(row=r, column=1, sticky="w", pady=2); r += 1

        ttk.Label(right, text="description:").grid(row=r, column=0, sticky="nw", pady=2)
        self.fa_desc.grid(row=r, column=1, sticky="nsew", pady=2); r += 1

        ttk.Label(right, text="notes:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fa_notes).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Button(right, text="Apply", command=self._fa_apply).grid(row=r, column=1, sticky="w", pady=(8, 0))

    def _build_mods_tab(self) -> None:
        f = self.tab_mods
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=2)
        f.rowconfigure(0, weight=1)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Modifiers").grid(row=0, column=0, sticky="w")

        self.fm_list = tk.Listbox(left, height=10)
        self.fm_list.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.fm_list.bind("<<ListboxSelect>>", self._fm_select)

        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Add", command=self._fm_add).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Remove", command=self._fm_remove).grid(row=0, column=1)

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        right.columnconfigure(1, weight=1)

        self.fm_target = tk.StringVar()
        self.fm_mode = tk.StringVar(value="add")
        self.fm_value = tk.StringVar()
        self.fm_when = tk.StringVar()
        self.fm_notes = tk.StringVar()
        self._fm_sel: Optional[int] = None

        r = 0
        ttk.Label(right, text="target:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fm_target).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(right, text="mode:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.fm_mode, values=["add", "set", "mul", "advantage", "disadvantage"], state="readonly").grid(
            row=r, column=1, sticky="w", pady=2
        ); r += 1

        ttk.Label(right, text="value:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fm_value).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(right, text="when (condition expr):").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fm_when).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(right, text="notes:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fm_notes).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(
            right,
            text="Examples: target=ac mode=add value=1 when=wearing_armor:light",
            foreground="#555",
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 0)); r += 1

        ttk.Button(right, text="Apply", command=self._fm_apply).grid(row=r, column=1, sticky="w", pady=(8, 0))

    def _build_damage_tab(self) -> None:
        f = self.tab_damage
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=2)
        f.rowconfigure(0, weight=1)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Damage riders").grid(row=0, column=0, sticky="w")

        self.fd_list = tk.Listbox(left, height=10)
        self.fd_list.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.fd_list.bind("<<ListboxSelect>>", self._fd_select)

        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Add", command=self._fd_add).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Remove", command=self._fd_remove).grid(row=0, column=1)

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        right.columnconfigure(1, weight=1)

        self.fd_name = tk.StringVar()
        self.fd_when = tk.StringVar()
        self.fd_dice = tk.StringVar()
        self.fd_dtype = tk.StringVar(value="radiant")
        self.fd_applies = tk.StringVar(value="weapon_attack")
        self.fd_pool = tk.StringVar()
        self.fd_cost = tk.StringVar(value="1")
        self.fd_notes = tk.StringVar()
        self._fd_sel: Optional[int] = None

        r = 0
        ttk.Label(right, text="name:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fd_name).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="when (condition expr):").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fd_when).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="damage dice:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fd_dice).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="damage type:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fd_dtype).grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="applies_to:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.fd_applies, values=["weapon_attack", "spell_attack", "any_damage", "melee_attack", "ranged_attack"], state="readonly").grid(
            row=r, column=1, sticky="w", pady=2
        ); r += 1
        ttk.Label(right, text="limit pool (optional):").grid(row=r, column=0, sticky="w", pady=2)
        self.fd_pool_box = ttk.Combobox(right, textvariable=self.fd_pool, values=[], state="readonly")
        self.fd_pool_box.grid(row=r, column=1, sticky="ew", pady=2); r += 1
        ttk.Label(right, text="pool cost:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fd_cost, width=8).grid(row=r, column=1, sticky="w", pady=2); r += 1
        ttk.Label(right, text="notes:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.fd_notes).grid(row=r, column=1, sticky="ew", pady=2); r += 1

        ttk.Label(
            right,
            text="Example: 1d8 radiant once/turn -> when=once_per_turn, dice=1d8, type=radiant",
            foreground="#555",
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 0)); r += 1

        ttk.Button(right, text="Apply", command=self._fd_apply).grid(row=r, column=1, sticky="w", pady=(8, 0))

    # ----- Utilities -----
    def _current_feature(self) -> Optional[Dict[str, Any]]:
        if self._selected_idx is None:
            return None
        feats = self.app.char.get("features", [])
        if self._selected_idx < 0 or self._selected_idx >= len(feats):
            return None
        return feats[self._selected_idx]

    def _refresh_feature_list(self) -> None:
        self.feature_list.delete(0, "end")
        for ft in self.app.char.get("features", []):
            self.feature_list.insert("end", f"{ft.get('category','custom')}: {ft.get('name','')}")

    def _update_feature_dependent_choices(self) -> None:
        # pools comboboxes in spells/actions/damage should include global pools + feature pools
        global_pools = [p.get("id") for p in self.app.char.get("resources", {}).get("pools", []) if p.get("id")]
        ft = self._current_feature()
        feat_pools = [p.get("id") for p in (ft or {}).get("grants", {}).get("pools", []) if p.get("id")]
        pool_choices = sorted(set(global_pools + feat_pools))

        # spells combobox
        self.fc_spell_box.configure(values=self.app.spell_ids)
        self.fc_pool_box.configure(values=pool_choices)

        # actions pool combobox
        self.fa_pool_box.configure(values=[""] + pool_choices)
        # damage pool combobox
        self.fd_pool_box.configure(values=[""] + pool_choices)

    # ----- Feature list ops -----
    def add_feature(self) -> None:
        self.save_to_state()
        feats = self.app.char["features"]
        ft = base_feature_template()
        base_id = slugify(ft["name"])
        existing = {f.get("id") for f in feats}
        fid = base_id
        n = 2
        while fid in existing:
            fid = f"{base_id}_{n}"; n += 1
        ft["id"] = fid
        feats.append(ft)
        self._refresh_feature_list()
        self.feature_list.selection_set(len(feats) - 1)
        self.on_select_feature(None)

    def dup_feature(self) -> None:
        self.save_to_state()
        ft = self._current_feature()
        if not ft:
            return
        feats = self.app.char["features"]
        copy = yaml.safe_load(yaml.safe_dump(ft))  # deep copy
        copy["name"] = f"{copy.get('name','Feature')} (copy)"
        base_id = slugify(copy["name"])
        existing = {f.get("id") for f in feats}
        fid = base_id
        n = 2
        while fid in existing:
            fid = f"{base_id}_{n}"; n += 1
        copy["id"] = fid
        feats.append(copy)
        self._refresh_feature_list()
        self.feature_list.selection_set(len(feats) - 1)
        self.on_select_feature(None)

    def remove_feature(self) -> None:
        ft = self._current_feature()
        if not ft:
            return
        if not messagebox.askyesno("Remove feature", f"Remove feature '{ft.get('name','')}'?"):
            return
        feats = self.app.char["features"]
        feats.pop(self._selected_idx)  # type: ignore[arg-type]
        self._selected_idx = None
        self._refresh_feature_list()

    # ----- Selection handling -----
    def on_show(self) -> None:
        self._refresh_feature_list()
        self._selected_idx = None
        self._update_feature_dependent_choices()

    def on_select_feature(self, _evt: Any) -> None:
        sel = self.feature_list.curselection()
        if not sel:
            self._selected_idx = None
            return
        idx = sel[0]
        
        # If already on this feature, no need to do anything
        if idx == self._selected_idx:
            return
        
        # Try to save the current feature before switching
        if not self.save_to_state():
            # Save failed, revert the listbox selection
            if self._selected_idx is not None:
                self.feature_list.selection_clear(0, "end")
                self.feature_list.selection_set(self._selected_idx)
            return
        
        # Update to the new selection
        self._selected_idx = idx
        ft = self._current_feature()
        if not ft:
            return

        self.f_id.set(ft.get("id", ""))
        self.f_name.set(ft.get("name", ""))
        self.f_cat.set(ft.get("category", "custom"))
        self.f_source.set(ft.get("source", ""))
        self.f_level.set(str(ft.get("level_acquired", 1)))
        self.f_tags.set(", ".join(ft.get("tags", []) or []))
        self.f_desc.delete("1.0", "end")
        self.f_desc.insert("1.0", ft.get("description", "") or "")

        # pools
        self._fp_sel = None
        self._refresh_fp_list()

        # spells
        all_ids = self.app.spell_ids[:]
        self.sp_can.set_all_ids(all_ids)
        self.sp_known.set_all_ids(all_ids)
        self.sp_always.set_all_ids(all_ids)
        gsp = (ft.get("grants", {}).get("spells", {}) or {})
        self.sp_can.set_selected(gsp.get("cantrips", []) or [])
        self.sp_known.set_selected(gsp.get("known", []) or [])
        self.sp_always.set_selected(gsp.get("always_prepared", []) or [])
        self._refresh_fc_tree()

        # actions/mods/damage
        self._fa_sel = None
        self._refresh_fa_list()
        self._fm_sel = None
        self._refresh_fm_list()
        self._fd_sel = None
        self._refresh_fd_list()

        self._update_feature_dependent_choices()

    # ----- Save -----
    def save_to_state(self) -> bool:
        ft = self._current_feature()
        if ft is None:
            return True

        fid = self.f_id.get().strip()
        if not fid:
            messagebox.showerror("Invalid feature", "Feature id cannot be empty.")
            return False
        # keep ids unique across features
        feats = self.app.char.get("features", [])
        other_ids = {f.get("id") for f in feats if f is not ft}
        if fid in other_ids:
            # Auto-rename with a number suffix
            base_id = fid
            n = 2
            while fid in other_ids:
                fid = f"{base_id}_{n}"
                n += 1
            response = messagebox.askyesno(
                "Duplicate Feature ID", 
                f"Feature id '{base_id}' already exists.\n\nAuto-rename to '{fid}'?"
            )
            if response:
                self.f_id.set(fid)
            else:
                return False

        ft["id"] = fid
        ft["name"] = self.f_name.get().strip()
        ft["category"] = self.f_cat.get().strip() or "custom"
        ft["source"] = self.f_source.get().strip()
        ft["level_acquired"] = max(1, safe_int(self.f_level.get(), 1))
        ft["tags"] = [t.strip() for t in (self.f_tags.get() or "").split(",") if t.strip()]
        ft["description"] = self.f_desc.get("1.0", "end").strip()

        # persist tab data
        ft.setdefault("grants", {})
        ft["grants"].setdefault("pools", [])
        ft["grants"].setdefault("spells", {})
        ft["grants"]["spells"]["cantrips"] = self.sp_can.get_selected()
        ft["grants"]["spells"]["known"] = self.sp_known.get_selected()
        ft["grants"]["spells"]["always_prepared"] = self.sp_always.get_selected()

        # ensure current pool/action/mod/damage editors apply
        self._fp_apply(silent=True)
        self._fa_apply(silent=True)
        self._fm_apply(silent=True)
        self._fd_apply(silent=True)

        # refresh display label
        self._refresh_feature_list()
        if self._selected_idx is not None:
            self.feature_list.selection_clear(0, "end")
            self.feature_list.selection_set(self._selected_idx)

        return True

    # ----- Pools tab behavior -----
    def _feature_pools(self) -> List[Dict[str, Any]]:
        ft = self._current_feature()
        if not ft:
            return []
        ft.setdefault("grants", {}).setdefault("pools", [])
        return ft["grants"]["pools"]

    def _refresh_fp_list(self) -> None:
        self.fp_list.delete(0, "end")
        for p in self._feature_pools():
            self.fp_list.insert("end", f"{p.get('id','')} — {p.get('label','')}")

    def _on_select_fp(self, _evt: Any) -> None:
        self._fp_apply(silent=True)
        sel = self.fp_list.curselection()
        if not sel:
            return
        idx = sel[0]
        pools = self._feature_pools()
        if idx < 0 or idx >= len(pools):
            return
        p = pools[idx]
        self._fp_sel = idx
        self.fp_id.set(p.get("id", ""))
        self.fp_label.set(p.get("label", ""))
        self.fp_current.set(str(p.get("current", 0)))
        self.fp_max.set(str(p.get("max_formula", 1)))
        self.fp_reset.set(p.get("reset", "long_rest"))
        self.fp_notes.set(p.get("notes", ""))

    def _fp_add(self) -> None:
        pools = self._feature_pools()
        label = "New Feature Pool"
        pid = slugify(label)
        existing = {p.get("id") for p in pools} | {p.get("id") for p in self.app.char.get("resources", {}).get("pools", [])}
        base = pid
        n = 2
        while pid in existing:
            pid = f"{base}_{n}"; n += 1
        pools.append({"id": pid, "label": label, "current": 0, "max_formula": 1, "reset": "long_rest", "notes": ""})
        self._refresh_fp_list()
        self.fp_list.selection_set(len(pools) - 1)
        self._on_select_fp(None)
        self._update_feature_dependent_choices()

    def _fp_remove(self) -> None:
        sel = self.fp_list.curselection()
        if not sel:
            return
        idx = sel[0]
        pools = self._feature_pools()
        if idx < 0 or idx >= len(pools):
            return
        pools.pop(idx)
        self._fp_sel = None
        self._refresh_fp_list()
        self._update_feature_dependent_choices()

    def _fp_apply(self, silent: bool = False) -> None:
        pools = self._feature_pools()
        if self._fp_sel is None:
            return
        idx = self._fp_sel
        if idx < 0 or idx >= len(pools):
            return

        pid = self.fp_id.get().strip()
        if not pid:
            if not silent:
                messagebox.showerror("Invalid pool", "Pool id cannot be empty.")
            return

        # pool id uniqueness across feature pools + global pools
        global_ids = {p.get("id") for p in self.app.char.get("resources", {}).get("pools", [])}
        other_feat_ids = {p.get("id") for i, p in enumerate(pools) if i != idx}
        if pid in global_ids or pid in other_feat_ids:
            if not silent:
                messagebox.showerror("Duplicate pool id", f"Pool id '{pid}' already exists (global or feature).")
            return

        pools[idx]["id"] = pid
        pools[idx]["label"] = self.fp_label.get().strip()
        pools[idx]["current"] = max(0, safe_int(self.fp_current.get(), 0))
        max_raw = self.fp_max.get().strip()
        pools[idx]["max_formula"] = safe_int(max_raw, 0) if re.fullmatch(r"-?\d+", max_raw) else (max_raw or 0)
        pools[idx]["reset"] = self.fp_reset.get().strip() or "long_rest"
        pools[idx]["notes"] = self.fp_notes.get().strip()
        self._refresh_fp_list()
        self.fp_list.selection_set(idx)
        self._fp_sel = idx
        self._update_feature_dependent_choices()

    # ----- Spells(casts) behavior -----
    def _feature_casts(self) -> List[Dict[str, Any]]:
        ft = self._current_feature()
        if not ft:
            return []
        ft.setdefault("grants", {}).setdefault("spells", {}).setdefault("casts", [])
        return ft["grants"]["spells"]["casts"]

    def _refresh_fc_tree(self) -> None:
        for iid in self.fc_tree.get_children():
            self.fc_tree.delete(iid)
        casts = self._feature_casts()
        for i, r in enumerate(casts):
            spell = r.get("spell", "")
            cons = r.get("consumes", {}) or {}
            pool = cons.get("pool", "")
            cost = cons.get("cost", 1)
            at = r.get("action_type", "action")
            bypass = "yes" if r.get("bypass_slots", True) else "no"
            self.fc_tree.insert("", "end", iid=str(i), values=(spell, pool, cost, at, bypass))

        # update dropdowns
        self._update_feature_dependent_choices()

    def _fc_select(self, _evt: Any) -> None:
        sel = self.fc_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        casts = self._feature_casts()
        if i < 0 or i >= len(casts):
            return
        r = casts[i]
        self._fc_sel = i
        self.fc_spell.set(r.get("spell", ""))
        cons = r.get("consumes", {}) or {}
        self.fc_pool.set(cons.get("pool", ""))
        self.fc_cost.set(str(cons.get("cost", 1)))
        self.fc_action.set(r.get("action_type", "action") or "action")
        self.fc_bypass.set(bool(r.get("bypass_slots", True)))
        self.fc_notes.set(r.get("notes", "") or "")

    def _fc_add_or_update(self) -> None:
        casts = self._feature_casts()
        spell = self.fc_spell.get().strip()
        pool = self.fc_pool.get().strip()
        cost = max(1, safe_int(self.fc_cost.get(), 1))
        at = self.fc_action.get().strip() or "action"
        bypass = bool(self.fc_bypass.get())
        notes = self.fc_notes.get().strip()

        if not spell:
            messagebox.showerror("Missing spell", "Select a spell.")
            return
        if not pool:
            messagebox.showerror("Missing pool", "Select a pool (feature pool or global pool).")
            return

        entry = {"spell": spell, "action_type": at, "consumes": {"pool": pool, "cost": cost}, "bypass_slots": bypass, "notes": notes}

        # unique by (spell,pool) is overkill; simplest unique by spell
        existing_i = next((i for i, r in enumerate(casts) if r.get("spell") == spell), None)
        if existing_i is not None:
            casts[existing_i] = entry
        else:
            casts.append(entry)

        self._refresh_fc_tree()

    def _fc_remove(self) -> None:
        casts = self._feature_casts()
        sel = self.fc_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        if i < 0 or i >= len(casts):
            return
        casts.pop(i)
        self._refresh_fc_tree()

    # ----- Actions tab behavior -----
    def _feature_actions(self) -> List[Dict[str, Any]]:
        ft = self._current_feature()
        if not ft:
            return []
        ft.setdefault("grants", {}).setdefault("actions", [])
        return ft["grants"]["actions"]

    def _refresh_fa_list(self) -> None:
        self.fa_list.delete(0, "end")
        for a in self._feature_actions():
            self.fa_list.insert("end", f"{a.get('type','action')}: {a.get('name','')}")

        self._update_feature_dependent_choices()

    def _fa_select(self, _evt: Any) -> None:
        self._fa_apply(silent=True)
        sel = self.fa_list.curselection()
        if not sel:
            return
        idx = sel[0]
        acts = self._feature_actions()
        if idx < 0 or idx >= len(acts):
            return
        a = acts[idx]
        self._fa_sel = idx
        self.fa_name.set(a.get("name", ""))
        self.fa_type.set(a.get("type", "action") or "action")
        uses = a.get("uses", {}) or {}
        self.fa_pool.set(uses.get("pool", "") or "")
        self.fa_cost.set(str(uses.get("cost", 1)))
        self.fa_desc.delete("1.0", "end")
        self.fa_desc.insert("1.0", a.get("description", "") or "")
        self.fa_notes.set(a.get("notes", "") or "")

    def _fa_add(self) -> None:
        acts = self._feature_actions()
        acts.append({"name": "New Ability", "type": "action", "description": "", "uses": {}, "notes": ""})
        self._refresh_fa_list()
        self.fa_list.selection_set(len(acts) - 1)
        self._fa_select(None)

    def _fa_remove(self) -> None:
        sel = self.fa_list.curselection()
        if not sel:
            return
        idx = sel[0]
        acts = self._feature_actions()
        if idx < 0 or idx >= len(acts):
            return
        acts.pop(idx)
        self._fa_sel = None
        self._refresh_fa_list()

    def _fa_apply(self, silent: bool = False) -> None:
        acts = self._feature_actions()
        if self._fa_sel is None:
            return
        idx = self._fa_sel
        if idx < 0 or idx >= len(acts):
            return

        name = self.fa_name.get().strip()
        if not name:
            if not silent:
                messagebox.showerror("Invalid action", "Action name cannot be empty.")
            return

        a = acts[idx]
        a["name"] = name
        a["type"] = self.fa_type.get().strip() or "action"
        a["description"] = self.fa_desc.get("1.0", "end").strip()
        a["notes"] = self.fa_notes.get().strip()

        pool = self.fa_pool.get().strip()
        if pool:
            a["uses"] = {"pool": pool, "cost": max(1, safe_int(self.fa_cost.get(), 1))}
        else:
            a["uses"] = {}

        self._refresh_fa_list()
        self.fa_list.selection_set(idx)
        self._fa_sel = idx

    # ----- Modifiers tab behavior -----
    def _feature_mods(self) -> List[Dict[str, Any]]:
        ft = self._current_feature()
        if not ft:
            return []
        ft.setdefault("grants", {}).setdefault("modifiers", [])
        return ft["grants"]["modifiers"]

    def _refresh_fm_list(self) -> None:
        self.fm_list.delete(0, "end")
        for m in self._feature_mods():
            self.fm_list.insert("end", f"{m.get('target','?')} {m.get('mode','add')} {m.get('value','')}")
        self._update_feature_dependent_choices()

    def _fm_select(self, _evt: Any) -> None:
        self._fm_apply(silent=True)
        sel = self.fm_list.curselection()
        if not sel:
            return
        idx = sel[0]
        mods = self._feature_mods()
        if idx < 0 or idx >= len(mods):
            return
        m = mods[idx]
        self._fm_sel = idx
        self.fm_target.set(m.get("target", ""))
        self.fm_mode.set(m.get("mode", "add") or "add")
        self.fm_value.set(str(m.get("value", "")))
        self.fm_when.set(m.get("when", ""))
        self.fm_notes.set(m.get("notes", ""))

    def _fm_add(self) -> None:
        mods = self._feature_mods()
        mods.append({"target": "", "mode": "add", "value": "", "when": "", "notes": ""})
        self._refresh_fm_list()
        self.fm_list.selection_set(len(mods) - 1)
        self._fm_select(None)

    def _fm_remove(self) -> None:
        sel = self.fm_list.curselection()
        if not sel:
            return
        idx = sel[0]
        mods = self._feature_mods()
        if idx < 0 or idx >= len(mods):
            return
        mods.pop(idx)
        self._fm_sel = None
        self._refresh_fm_list()

    def _fm_apply(self, silent: bool = False) -> None:
        mods = self._feature_mods()
        if self._fm_sel is None:
            return
        idx = self._fm_sel
        if idx < 0 or idx >= len(mods):
            return

        mods[idx]["target"] = self.fm_target.get().strip()
        mods[idx]["mode"] = self.fm_mode.get().strip() or "add"
        mods[idx]["value"] = self.fm_value.get().strip()
        mods[idx]["when"] = self.fm_when.get().strip()
        mods[idx]["notes"] = self.fm_notes.get().strip()

        self._refresh_fm_list()
        self.fm_list.selection_set(idx)
        self._fm_sel = idx

    # ----- Damage tab behavior -----
    def _feature_damage(self) -> List[Dict[str, Any]]:
        ft = self._current_feature()
        if not ft:
            return []
        ft.setdefault("grants", {}).setdefault("damage_riders", [])
        return ft["grants"]["damage_riders"]

    def _refresh_fd_list(self) -> None:
        self.fd_list.delete(0, "end")
        for d in self._feature_damage():
            self.fd_list.insert("end", f"{d.get('name','')} ({d.get('dice','') } {d.get('type','')})")
        self._update_feature_dependent_choices()

    def _fd_select(self, _evt: Any) -> None:
        self._fd_apply(silent=True)
        sel = self.fd_list.curselection()
        if not sel:
            return
        idx = sel[0]
        ds = self._feature_damage()
        if idx < 0 or idx >= len(ds):
            return
        d = ds[idx]
        self._fd_sel = idx
        self.fd_name.set(d.get("name", ""))
        self.fd_when.set(d.get("when", ""))
        self.fd_dice.set(d.get("dice", ""))
        self.fd_dtype.set(d.get("type", ""))
        self.fd_applies.set(d.get("applies_to", "weapon_attack") or "weapon_attack")
        lim = d.get("limit", {}) or {}
        self.fd_pool.set(lim.get("pool", "") or "")
        self.fd_cost.set(str(lim.get("cost", 1)))
        self.fd_notes.set(d.get("notes", "") or "")

    def _fd_add(self) -> None:
        ds = self._feature_damage()
        ds.append({"name": "New Rider", "when": "", "dice": "1d6", "type": "fire", "applies_to": "weapon_attack", "limit": {}, "notes": ""})
        self._refresh_fd_list()
        self.fd_list.selection_set(len(ds) - 1)
        self._fd_select(None)

    def _fd_remove(self) -> None:
        sel = self.fd_list.curselection()
        if not sel:
            return
        idx = sel[0]
        ds = self._feature_damage()
        if idx < 0 or idx >= len(ds):
            return
        ds.pop(idx)
        self._fd_sel = None
        self._refresh_fd_list()

    def _fd_apply(self, silent: bool = False) -> None:
        ds = self._feature_damage()
        if self._fd_sel is None:
            return
        idx = self._fd_sel
        if idx < 0 or idx >= len(ds):
            return

        name = self.fd_name.get().strip()
        if not name and not silent:
            messagebox.showerror("Invalid rider", "Damage rider name cannot be empty.")
            return

        d = ds[idx]
        d["name"] = name
        d["when"] = self.fd_when.get().strip()
        d["dice"] = self.fd_dice.get().strip()
        d["type"] = self.fd_dtype.get().strip()
        d["applies_to"] = self.fd_applies.get().strip() or "weapon_attack"
        pool = self.fd_pool.get().strip()
        if pool:
            d["limit"] = {"pool": pool, "cost": max(1, safe_int(self.fd_cost.get(), 1))}
        else:
            d["limit"] = {}
        d["notes"] = self.fd_notes.get().strip()

        self._refresh_fd_list()
        self.fd_list.selection_set(idx)
        self._fd_sel = idx


# -----------------------------
# Review/save page
# -----------------------------
class ReviewSavePage(WizardPage):
    title = "Review & Save"

    def __init__(self, master: tk.Widget, app: "WizardApp"):
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Final YAML preview:").grid(row=0, column=0, sticky="w", padx=8, pady=(10, 4))
        self.preview = tk.Text(self, wrap="none")
        self.preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 10))
        ttk.Button(btns, text="Save", command=self.app.save_current).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="Save As…", command=self.app.save_as).grid(row=0, column=1)

        self.path_label = ttk.Label(self, text="", foreground="#555")
        self.path_label.grid(row=3, column=0, sticky="w", padx=8, pady=(0, 10))

    def on_show(self) -> None:
        text = yaml.safe_dump(self.app.char, sort_keys=False, allow_unicode=True)
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.path_label.config(text=f"File: {self.app.current_path or '(unsaved)'}")


# -----------------------------
# Wizard app
# -----------------------------
class WizardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Character YAML Builder")
        self.geometry("1200x900")

        # autodetect dirs - check if we're in scripts/ subdirectory
        cwd = os.getcwd()
        # If script is in scripts/ directory, use parent directory
        if os.path.basename(cwd) == "scripts":
            root_dir = os.path.dirname(cwd)
        else:
            root_dir = cwd
        self.spells_dir = os.path.join(root_dir, "Spells")
        self.players_dir = os.path.join(root_dir, "players")
        os.makedirs(self.players_dir, exist_ok=True)

        self.spell_ids: List[str] = []
        self.player_files: List[str] = []

        self.current_path: Optional[str] = None
        self.char: Dict[str, Any] = base_template()

        self.refresh_spell_cache()
        self.refresh_player_cache()

        # Menu
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New", command=self.new_character)
        filem.add_command(label="Open…", command=self.open_dialog)
        filem.add_separator()
        filem.add_command(label="Save", command=self.save_current)
        filem.add_command(label="Save As…", command=self.save_as)
        filem.add_separator()
        filem.add_command(label="Quit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)
        self.config(menu=menubar)

        # Layout
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.columnconfigure(0, weight=1)

        main = ttk.Frame(self)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        nav = ttk.Frame(self)
        nav.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        nav.columnconfigure(1, weight=1)

        self.pages: List[WizardPage] = [
            SetupPage(main, self),
            BasicsPage(main, self),
            LevelAbilitiesPage(main, self),
            VitalsPage(main, self),
            ResourcesPage(main, self),
            SpellcastingPage(main, self),
            FeaturesPage(main, self),
            ReviewSavePage(main, self),
        ]
        self.page_index = 0

        self.page_container = ttk.Frame(main)
        self.page_container.grid(row=0, column=0, sticky="nsew")
        self.page_container.columnconfigure(0, weight=1)
        self.page_container.rowconfigure(0, weight=1)

        for p in self.pages:
            p.grid(in_=self.page_container, row=0, column=0, sticky="nsew")

        ttk.Label(sidebar, text="Pages").grid(row=0, column=0, sticky="w", padx=8, pady=(10, 4))
        self.page_list = tk.Listbox(sidebar, height=16)
        self.page_list.grid(row=1, column=0, sticky="nsw", padx=8, pady=4)
        for p in self.pages:
            self.page_list.insert("end", p.title)
        self.page_list.bind("<<ListboxSelect>>", self.on_sidebar_select)

        ttk.Label(sidebar, text="Project", foreground="#555").grid(row=2, column=0, sticky="w", padx=8, pady=(12, 2))
        self.side_dirs = ttk.Label(sidebar, text=f"Spells: {self.spells_dir}\nPlayers: {self.players_dir}", wraplength=300)
        self.side_dirs.grid(row=3, column=0, sticky="w", padx=8)

        self.side_file = ttk.Label(sidebar, text="", foreground="#555", wraplength=300)
        self.side_file.grid(row=4, column=0, sticky="w", padx=8, pady=(12, 0))

        self.back_btn = ttk.Button(nav, text="← Back", command=self.go_back)
        self.back_btn.grid(row=0, column=0, sticky="w")

        # Save Current Feature button (only visible on Features page)
        self.save_feature_btn = ttk.Button(nav, text="Save Current Feature", command=self.save_current_feature)
        self.save_feature_btn.grid(row=0, column=2, sticky="e", padx=(0, 10))
        self.save_feature_btn.grid_remove()  # Hide by default

        self.next_btn = ttk.Button(nav, text="Next →", command=self.go_next)
        self.next_btn.grid(row=0, column=3, sticky="e")

        self.progress = ttk.Label(nav, text="")
        self.progress.grid(row=0, column=1, sticky="ew")

        self.show_page(0)

        # warn if spells dir missing
        if not os.path.isdir(self.spells_dir):
            messagebox.showwarning(
                "Spells directory missing",
                "Could not find ./Spells in the working directory.\n\nSpell pickers will be empty until you create it or run from the correct folder.",
            )

    def refresh_spell_cache(self) -> None:
        self.spell_ids = scan_spell_ids(self.spells_dir)

    def refresh_player_cache(self) -> None:
        self.player_files = scan_yaml_files(self.players_dir)

    # ----- navigation -----
    def on_sidebar_select(self, _evt: Any) -> None:
        sel = self.page_list.curselection()
        if not sel:
            return
        target = sel[0]
        if not self.pages[self.page_index].save_to_state():
            return
        self.show_page(target)

    def show_page(self, idx: int) -> None:
        idx = max(0, min(idx, len(self.pages) - 1))
        self.page_index = idx
        page = self.pages[idx]
        page.tkraise()
        page.on_show()

        self.page_list.selection_clear(0, "end")
        self.page_list.selection_set(idx)

        self.back_btn.configure(state=("disabled" if idx == 0 else "normal"))
        self.next_btn.configure(text=("Finish" if idx == len(self.pages) - 1 else "Next →"))
        self.progress.configure(text=f"{idx + 1} / {len(self.pages)} — {page.title}")

        # Show "Save Current Feature" button only on Features page
        if page.title == "Features":
            self.save_feature_btn.grid()
        else:
            self.save_feature_btn.grid_remove()

        self.side_file.configure(text=f"File: {self.current_path or '(unsaved)'}")

    def go_back(self) -> None:
        if self.page_index <= 0:
            return
        if not self.pages[self.page_index].save_to_state():
            return
        self.show_page(self.page_index - 1)

    def go_next(self) -> None:
        if not self.pages[self.page_index].save_to_state():
            return
        if self.page_index >= len(self.pages) - 1:
            return
        self.show_page(self.page_index + 1)

    def go_to_page_title(self, title: str) -> None:
        for i, p in enumerate(self.pages):
            if p.title == title:
                if self.pages[self.page_index].save_to_state():
                    self.show_page(i)
                return

    def save_current_feature(self) -> None:
        """Save the currently edited feature on the Features page."""
        page = self.pages[self.page_index]
        if page.title == "Features":
            if page.save_to_state():
                messagebox.showinfo("Feature Saved", "Current feature saved successfully.")

    # ----- file ops -----
    def new_character(self) -> None:
        if not self.pages[self.page_index].save_to_state():
            return
        self.char = base_template()
        self.current_path = None
        self.show_page(1)  # Basics

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open character YAML…",
            initialdir=self.players_dir,
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
        )
        if path:
            self.load_character(path)
            self.show_page(1)

    def load_character(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError("Top-level YAML must be a mapping/dict.")
        except Exception as e:
            messagebox.showerror("Open failed", str(e))
            return

        merged = merge_defaults(data, base_template())
        # ensure features list has grants subkeys
        feats = merged.get("features", [])
        if isinstance(feats, list):
            for ft in feats:
                if isinstance(ft, dict):
                    ft.setdefault("grants", {}).setdefault("pools", [])
                    ft.setdefault("grants", {}).setdefault("spells", {}).setdefault("casts", [])
                    ft.setdefault("grants", {}).setdefault("actions", [])
                    ft.setdefault("grants", {}).setdefault("modifiers", [])
                    ft.setdefault("grants", {}).setdefault("damage_riders", [])

        self.char = merged
        self.current_path = path

        # update spells_dir if the YAML points somewhere sensible
        try:
            sc = self.char.get("spellcasting", {})
            paths = sc.get("spell_yaml_paths") or []
            if paths and isinstance(paths, list) and isinstance(paths[0], str):
                candidate = paths[0]
                if not os.path.isabs(candidate):
                    candidate = os.path.join(os.path.dirname(path), candidate)
                if os.path.isdir(candidate):
                    self.spells_dir = os.path.abspath(candidate)
        except Exception:
            pass

        self.refresh_spell_cache()
        self.refresh_player_cache()

    def save_current(self) -> None:
        # ensure current page saved into state first
        if not self.pages[self.page_index].save_to_state():
            return

        if not self.current_path:
            # default to ./players/<slugname>.yaml
            name = (self.char.get("name") or "").strip()
            if not name:
                messagebox.showerror("Missing name", "Set the character name before saving.")
                return
            self.current_path = os.path.join(self.players_dir, f"{slugify(name)}.yaml")

        try:
            # maintain relative spell path as ./Spells by default
            self.char.setdefault("spellcasting", {}).setdefault("spell_yaml_paths", ["./Spells"])
            self.char["spellcasting"]["spell_yaml_paths"] = ["./Spells"]
            with open(self.current_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.char, f, sort_keys=False, allow_unicode=True)
            self.refresh_player_cache()
            self.side_file.configure(text=f"File: {self.current_path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def save_as(self) -> None:
        if not self.pages[self.page_index].save_to_state():
            return
        path = filedialog.asksaveasfilename(
            title="Save character YAML as…",
            initialdir=self.players_dir,
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
        )
        if not path:
            return
        self.current_path = path
        self.save_current()


def main() -> int:
    app = WizardApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
