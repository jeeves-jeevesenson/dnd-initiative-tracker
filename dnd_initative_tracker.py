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
import math
from functools import lru_cache
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
import shutil
import re
import os
import hashlib
import hmac
import secrets
import traceback
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import copy

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

# Monster YAML loader (PyYAML)
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

# Import the full tracker as the base.
# Keep this file in the same folder as helper_script.py
try:
    import helper_script as base
    import update_checker
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "Arrr! I can’t find/load helper_script.py in this folder.\n"
        "Make sure helper_script and dnd_initative_tracker be in the same directory.\n\n"
        f"Import error: {e}"
    )


def _load_character_schema_helpers() -> Tuple[Callable[[], Dict[str, Any]], Callable[[Any, Any], Any], Callable[[str, str], str]]:
    base_template = None
    merge_defaults = None
    slugify = None
    try:
        scripts_dir = Path(__file__).resolve().parent / "scripts"
        module_path = scripts_dir / "skeleton_gui.py"
        if module_path.exists():
            spec = importlib.util.spec_from_file_location("inittracker_skeleton_gui", module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                base_template = getattr(module, "base_template", None)
                merge_defaults = getattr(module, "merge_defaults", None)
                slugify = getattr(module, "slugify", None)
    except Exception:
        base_template = None
        merge_defaults = None
        slugify = None

    def fallback_base_template() -> Dict[str, Any]:
        return {
            "format_version": 2,
            "name": "",
            "player": "",
            "campaign": "",
            "ip": "",
            "identity": {},
            "leveling": {},
            "abilities": {},
            "proficiency": {},
            "vitals": {},
            "defenses": {},
            "resources": {},
            "features": [],
            "actions": [
                {
                    "name": "Attack",
                    "description": "Make a weapon or unarmed attack against a target within range.",
                    "type": "action",
                },
                {
                    "name": "Dash",
                    "description": "Gain extra movement for the current turn equal to your speed.",
                    "type": "action",
                },
                {
                    "name": "Disengage",
                    "description": "Your movement does not provoke opportunity attacks for the rest of the turn.",
                    "type": "action",
                },
                {
                    "name": "Dodge",
                    "description": "Until the start of your next turn, attack rolls against you have disadvantage if you can see the attacker, and you make Dexterity saves with advantage.",
                    "type": "action",
                },
                {
                    "name": "Help",
                    "description": "Aid a creature in the next ability check or attack roll against a target within 5 feet of you.",
                    "type": "action",
                },
                {
                    "name": "Hide",
                    "description": "Attempt to hide by making a Dexterity (Stealth) check.",
                    "type": "action",
                },
                {
                    "name": "Influence",
                    "description": "Attempt to influence a creature through conversation, bargaining, or intimidation.",
                    "type": "action",
                },
                {
                    "name": "Magic",
                    "description": "Cast a spell or use a magical feature that takes an action.",
                    "type": "action",
                },
                {
                    "name": "Ready",
                    "description": "Prepare an action and a trigger; use your reaction to perform it when the trigger occurs.",
                    "type": "action",
                },
                {
                    "name": "Search",
                    "description": "Devote attention to finding something by making a Wisdom (Perception) or Intelligence (Investigation) check.",
                    "type": "action",
                },
                {
                    "name": "Study",
                    "description": "Focus on detailed observation or research to gain information about a creature, object, or situation.",
                    "type": "action",
                },
                {
                    "name": "Utilize",
                    "description": "Use an object or interact with the environment in a significant way.",
                    "type": "action",
                },
            ],
            "reactions": [
                {
                    "name": "Opportunity Attack",
                    "description": "When a hostile creature you can see moves out of your reach, you can use your reaction to make one melee attack against it.",
                    "type": "reaction",
                },
                {
                    "name": "Reaction",
                    "description": "You can take a reaction when a trigger occurs. A reaction is only available once per round.",
                    "type": "reaction",
                },
            ],
            "bonus_actions": [
                {
                    "name": "Bonus Action",
                    "description": "You can take a bonus action only when a feature, spell, or ability says you can.",
                    "type": "bonus_action",
                }
            ],
            "spellcasting": {},
            "inventory": {},
            "notes": {},
        }

    def fallback_merge_defaults(user_obj: Any, defaults: Any) -> Any:
        if isinstance(defaults, dict):
            if not isinstance(user_obj, dict):
                user_obj = {}
            for key, value in defaults.items():
                if key not in user_obj:
                    user_obj[key] = copy.deepcopy(value)
                else:
                    user_obj[key] = fallback_merge_defaults(user_obj[key], value)
            return user_obj
        return user_obj

    def fallback_slugify(value: str, sep: str = "_") -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s-]+", sep, text).strip(sep)
        return text or "id"

    base_template = base_template or fallback_base_template
    merge_defaults = merge_defaults or fallback_merge_defaults
    slugify = slugify or fallback_slugify
    return base_template, merge_defaults, slugify


_CHARACTER_BASE_TEMPLATE, _CHARACTER_MERGE_DEFAULTS, _CHARACTER_SLUGIFY = _load_character_schema_helpers()


def _character_schema_path() -> Path:
    try:
        return Path(__file__).resolve().parent / "assets" / "web" / "new_character" / "schema.json"
    except Exception:
        return Path("assets") / "web" / "new_character" / "schema.json"


def _schema_type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    return type(value).__name__


def _scan_spell_ids(spells_dir: Optional[Path]) -> List[str]:
    if not spells_dir or not spells_dir.is_dir():
        return []
    ids = [path.stem for path in spells_dir.iterdir() if path.is_file() and path.suffix.lower() == ".yaml"]
    ids.sort()
    return ids


def _read_spell_yaml_text(spells_dir: Optional[Path], spell_id: str, max_chars: int = 200_000) -> str:
    if not spells_dir:
        return ""
    path = spells_dir / f"{spell_id}.yaml"
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return handle.read(max_chars)
    except Exception as exc:
        return f"# Error reading {path}: {exc}"


def _schema_node_from_field(field: Dict[str, Any]) -> Dict[str, Any]:
    node: Dict[str, Any] = {
        "type": field.get("type", "string"),
        "required": bool(field.get("required", False)),
    }
    if "default" in field:
        node["default"] = field["default"]
    if node["type"] == "object":
        node["fields"] = {child["key"]: _schema_node_from_field(child) for child in field.get("fields", [])}
    if node["type"] == "array":
        items = field.get("items")
        node["items"] = _schema_node_from_field(items) if isinstance(items, dict) else {"type": "string"}
    if node["type"] == "map":
        node["value_type"] = field.get("value_type", "string")
    return node


def _insert_schema_node(root: Dict[str, Any], path: List[str], node: Dict[str, Any]) -> None:
    cursor = root
    for key in path[:-1]:
        fields = cursor.setdefault("fields", {})
        if key not in fields:
            fields[key] = {"type": "object", "fields": {}}
        cursor = fields[key]
    if not path:
        root.setdefault("fields", {}).update(node.get("fields", {}))
    else:
        cursor.setdefault("fields", {})[path[-1]] = node


def _build_character_schema_tree(config: Dict[str, Any]) -> Dict[str, Any]:
    root: Dict[str, Any] = {"type": "object", "fields": {}}
    for section in config.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_type = section.get("type", "object")
        node: Dict[str, Any] = {"type": section_type}
        if "default" in section:
            node["default"] = section["default"]
        if section_type == "object":
            node["fields"] = {child["key"]: _schema_node_from_field(child) for child in section.get("fields", [])}
        elif section_type == "array":
            items = section.get("items")
            node["items"] = _schema_node_from_field(items) if isinstance(items, dict) else {"type": "string"}
        elif section_type == "map":
            node["value_type"] = section.get("value_type", "string")
        path = section.get("path") or []
        _insert_schema_node(root, list(path), node)
    return root


def _schema_default_for_node(node: Dict[str, Any]) -> Any:
    if "default" in node:
        return copy.deepcopy(node["default"])
    node_type = node.get("type")
    if isinstance(node_type, list):
        return ""
    if node_type == "object":
        return {key: _schema_default_for_node(child) for key, child in node.get("fields", {}).items()}
    if node_type == "array":
        return []
    if node_type == "map":
        return {}
    if node_type == "boolean":
        return False
    if node_type in ("integer", "number"):
        return 0
    return ""


def _schema_defaults_from_tree(tree: Dict[str, Any]) -> Dict[str, Any]:
    if tree.get("type") != "object":
        return {}
    return _schema_default_for_node(tree)


def _schema_type_matches(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_schema_type_matches(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "map":
        return isinstance(value, dict)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    return True


def _character_schema_errors_from_tree(payload: Any, schema: Dict[str, Any], path: str = "") -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []

    def add_error(message: str) -> None:
        errors.append({"path": path or ".", "message": message})

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(payload, dict):
            add_error(f"Expected object, got {_schema_type_name(payload)}.")
            return errors
        fields = schema.get("fields", {})
        for key, child_schema in fields.items():
            if child_schema.get("required") and key not in payload:
                errors.append({"path": f"{path}.{key}" if path else key, "message": "Missing required field."})
                continue
            if key in payload:
                next_path = f"{path}.{key}" if path else key
                errors.extend(_character_schema_errors_from_tree(payload[key], child_schema, next_path))
        return errors
    if expected_type == "array":
        if not isinstance(payload, list):
            add_error(f"Expected array, got {_schema_type_name(payload)}.")
            return errors
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(payload):
                next_path = f"{path}[{index}]" if path else f"[{index}]"
                errors.extend(_character_schema_errors_from_tree(item, item_schema, next_path))
        return errors
    if expected_type == "map":
        if not isinstance(payload, dict):
            add_error(f"Expected object map, got {_schema_type_name(payload)}.")
            return errors
        value_type = schema.get("value_type")
        if value_type:
            for key, value in payload.items():
                if not _schema_type_matches(value, value_type):
                    errors.append(
                        {
                            "path": f"{path}.{key}" if path else key,
                            "message": f"Expected {value_type}, got {_schema_type_name(value)}.",
                        }
                    )
        return errors
    if expected_type is not None:
        if not _schema_type_matches(payload, expected_type):
            add_error(f"Expected {expected_type}, got {_schema_type_name(payload)}.")
    return errors


def _readme_section_headings(readme_path: Path) -> List[str]:
    try:
        text = readme_path.read_text(encoding="utf-8")
    except Exception:
        return []
    headings: List[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            in_section = heading == "Complete YAML Structure Reference"
            continue
        if in_section and line.startswith("### "):
            headings.append(line[4:].strip())
    return headings


def _character_schema_readme_map(config: Dict[str, Any]) -> Dict[str, Any]:
    readme_path = Path(__file__).resolve().parent / config.get("readme_path", "players/README.md")
    headings = _readme_section_headings(readme_path)
    schema_headings = [
        section.get("readme_heading")
        for section in config.get("sections", [])
        if isinstance(section, dict) and section.get("readme_heading")
    ]
    missing_in_readme = [heading for heading in schema_headings if heading not in headings]
    missing_in_schema = [heading for heading in headings if heading not in schema_headings]
    return {
        "readme_headings": headings,
        "schema_headings": schema_headings,
        "missing_in_readme": missing_in_readme,
        "missing_in_schema": missing_in_schema,
        "readme_path": str(readme_path),
    }


def _load_character_schema_config() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    path = _character_schema_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}, {}, {}
    if not isinstance(raw, dict):
        return {}, {}, {}, {}
    tree = _build_character_schema_tree(raw)
    defaults = _schema_defaults_from_tree(tree)
    readme_map = _character_schema_readme_map(raw)
    return raw, tree, defaults, readme_map


_CHARACTER_SCHEMA_CONFIG, _CHARACTER_SCHEMA_TREE, _CHARACTER_SCHEMA_DEFAULTS, _CHARACTER_SCHEMA_README_MAP = (
    _load_character_schema_config()
)


@dataclass
class CharacterApiError(Exception):
    status_code: int
    detail: Any


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


def _archive_startup_logs() -> None:
    """Move existing .log files in logs/ into logs/old logs/<timestamp>/."""
    try:
        logs = _ensure_logs_dir()
    except OSError:
        return
    try:
        candidates = (entry for entry in logs.iterdir() if entry.is_file() and entry.name.endswith(".log"))
        first_entry = next(candidates, None)
    except OSError:
        return
    if first_entry is None:
        return
    entries = [first_entry, *candidates]
    try:
        archive_root = logs / "old logs"
        archive_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        archive_dir = archive_root / stamp
        archive_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for entry in entries:
        try:
            dest = archive_dir / entry.name
            if dest.exists():
                base = entry.stem
                suffix = entry.suffix
                n = 1
                while dest.exists():
                    dest = archive_dir / f"{base}_{n}{suffix}"
                    n += 1
            shutil.move(str(entry), str(dest))
        except OSError:
            pass


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


def _make_client_error_logger() -> logging.Logger:
    """Return a logger that writes to ./logs/client_errors.log."""
    lg = logging.getLogger("inittracker.client_errors")
    if getattr(lg, "_inittracker_configured", False):
        return lg

    lg.setLevel(logging.INFO)
    logs = _ensure_logs_dir()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")

    try:
        fh = logging.FileHandler(logs / "client_errors.log", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        lg.addHandler(fh)
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


def _parse_fractional_cr(value: str) -> Optional[float]:
    match = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", value)
    if not match:
        return None
    denom = int(match.group(2))
    if denom == 0:
        return None
    return int(match.group(1)) / denom


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _directory_signature(directory: Path, files: List[Path]) -> Tuple[int, int, Tuple[str, ...]]:
    try:
        stat = directory.stat()
        mtime_ns = int(stat.st_mtime_ns)
    except Exception:
        mtime_ns = 0
    names = tuple(sorted(path.name for path in files))
    return (mtime_ns, len(names), names)


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

_LAN_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "web" / "lan"
_CAST_TIME_BONUS_RE = re.compile(r"\bbonus[\s-]*action\b")
_CAST_TIME_REACTION_RE = re.compile(r"\breaction\b")
_CAST_TIME_ACTION_RE = re.compile(r"\baction\b")


@lru_cache(maxsize=None)
def _load_lan_asset(name: str) -> str:
    try:
        asset_path = _LAN_ASSET_DIR / name
    except Exception:
        asset_path = Path("assets") / "web" / "lan" / name
    return asset_path.read_text(encoding="utf-8")


HTML_INDEX = _load_lan_asset("index.html").replace("__DAMAGE_TYPE_OPTIONS__", DAMAGE_TYPE_OPTIONS)
SERVICE_WORKER_JS = _load_lan_asset("sw.js")


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
    fly_speed: Optional[int]
    burrow_speed: Optional[int]
    climb_speed: Optional[int]
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
    proficiency: Dict[str, Any] = field(default_factory=dict)
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
            "proficiency": dict(self.proficiency),
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
        self._view_only_clients: set[int] = set()
        self._claims: Dict[int, int] = {}   # id(websocket) -> cid
        self._cid_to_ws: Dict[int, set[int]] = {}  # cid -> {id(websocket), ...}
        self._cid_to_host: Dict[int, set[str]] = {}  # cid -> {host, ...}
        self._host_assignments: Dict[str, int] = self._load_host_assignments()  # host -> cid (persistent)
        self._yaml_host_assignments: Dict[str, Dict[str, Any]] = {}
        self._host_presets: Dict[str, Dict[str, Any]] = {}
        self._cid_push_subscriptions: Dict[int, List[Dict[str, Any]]] = {}
        self._client_error_logger = _make_client_error_logger()
        self._client_log_lock = threading.Lock()
        self._client_log_state: Dict[str, Tuple[float, int]] = {}
        self._client_log_window_s: float = 60.0
        self._client_log_max: int = 30

        self._actions: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._last_snapshot: Optional[Dict[str, Any]] = None
        self._last_static_json: Optional[str] = None
        self._polling: bool = False
        self._grid_version: int = 0
        self._grid_pending: Dict[int, Tuple[int, float]] = {}
        self._grid_resend_seconds: float = 1.5
        self._grid_last_sent: Optional[Tuple[Optional[int], Optional[int]]] = None
        self._terrain_version: int = 0
        self._terrain_pending: Dict[int, Tuple[int, float]] = {}
        self._terrain_resend_seconds: float = 1.5
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

    @staticmethod
    def _json_dumps(payload: Any) -> str:
        def sanitize(value: Any) -> Any:
            if isinstance(value, float):
                return value if math.isfinite(value) else 0.0
            if isinstance(value, dict):
                return {key: sanitize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if isinstance(value, tuple):
                return [sanitize(item) for item in value]
            if isinstance(value, set):
                return [sanitize(item) for item in value]
            return value

        def default(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, (set, tuple)):
                return list(value)
            return str(value)

        return json.dumps(sanitize(payload), allow_nan=False, default=default)

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

    def _allow_client_log(self, host: str) -> bool:
        host = str(host or "").strip() or "unknown"
        now = time.time()
        with self._client_log_lock:
            window_start, count = self._client_log_state.get(host, (now, 0))
            if now - window_start >= self._client_log_window_s:
                window_start, count = now, 0
            if count >= self._client_log_max:
                self._client_log_state[host] = (window_start, count)
                return False
            count += 1
            self._client_log_state[host] = (window_start, count)
            return True

    def _log_client_error(self, entry: Dict[str, Any]) -> None:
        try:
            payload = self._json_dumps(entry)
            self._client_error_logger.info(payload)
        except Exception:
            self.app._oplog("Failed to record client error log entry.", level="warning")

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

    def _assigned_character_name_for_host(self, host: str) -> Optional[str]:
        host = str(host or "").strip()
        if not host:
            return None
        with self._clients_lock:
            yaml_entry = self._yaml_host_assignments.get(host)
        if isinstance(yaml_entry, dict):
            name = str(yaml_entry.get("name") or "").strip()
            if name:
                return name
        cid = self._assigned_cid_for_host(host)
        if cid is None:
            return None
        name = self._pc_name_for(int(cid))
        if name.startswith("cid:"):
            return None
        return name

    def _sync_yaml_host_assignments(self, profiles: Dict[str, Dict[str, Any]]) -> None:
        if not isinstance(profiles, dict):
            profiles = {}
        def normalize_name(value: Any) -> Optional[str]:
            text = str(value or "").strip()
            return text.lower() if text else None

        def coerce_cid(value: Any) -> Optional[int]:
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            try:
                parsed = int(str(value).strip())
            except Exception:
                return None
            return parsed

        name_to_cid: Dict[str, int] = {}
        pcs = list(self._cached_pcs)
        if not pcs:
            try:
                pcs = list(
                    self.app._lan_pcs() if hasattr(self.app, "_lan_pcs") else self.app._lan_claimable()
                )
            except Exception:
                pcs = []
        pc_names: List[str] = []
        for pc in pcs:
            if not isinstance(pc, dict):
                continue
            name = str(pc.get("name") or "").strip()
            cid = coerce_cid(pc.get("cid"))
            if name and isinstance(cid, int):
                normalized = normalize_name(name)
                if normalized:
                    name_to_cid[normalized] = int(cid)
                    pc_names.append(name)

        host_map: Dict[str, Dict[str, Any]] = {}
        conflicts: List[Tuple[str, str, str]] = []
        yaml_names: List[str] = []
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
            profile_name = str(name)
            identity_name = identity.get("name")
            if profile_name:
                yaml_names.append(profile_name)
            if identity_name:
                yaml_names.append(str(identity_name))
            cid = coerce_cid(identity.get("cid"))
            if cid is None:
                cid = coerce_cid(profile.get("cid"))
            if cid is None:
                candidate_names = {
                    normalize_name(profile_name),
                    normalize_name(identity_name),
                }
                candidate_names.discard(None)
                for candidate in candidate_names:
                    cid = name_to_cid.get(candidate)
                    if cid is not None:
                        break
            host_map[host] = {"name": profile_name, "cid": cid}

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
                if pcs:
                    self.app._oplog(
                        f"LAN YAML assignment skipped: {info.get('name')} has host {host} but no matching cid.",
                        level="warning",
                    )
                    self.app._oplog(
                        "LAN YAML assignment debug: "
                        f"available_pcs={sorted(set(pc_names))} yaml_names={sorted(set(yaml_names))}",
                        level="debug",
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

        self._fastapi_app = FastAPI()
        assets_dir = Path(__file__).parent / "assets"
        self._fastapi_app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        web_entrypoint = assets_dir / "web" / "new_character" / "index.html"
        edit_entrypoint = assets_dir / "web" / "edit_character" / "index.html"
        for asset_name in ("alert.wav", "ko.wav"):
            if not (assets_dir / asset_name).exists():
                self.app._oplog(
                    f"LAN assets missing {asset_name} at {assets_dir / asset_name} (check assets_dir path).",
                    level="warning",
                )

        @self._fastapi_app.get("/")
        async def index():
            push_key = self.cfg.vapid_public_key
            push_key_value = json.dumps(push_key) if push_key else "undefined"
            return HTMLResponse(HTML_INDEX.replace("__PUSH_PUBLIC_KEY__", push_key_value))

        @self._fastapi_app.get("/map_view")
        async def map_view():
            push_key = self.cfg.vapid_public_key
            push_key_value = json.dumps(push_key) if push_key else "undefined"
            return HTMLResponse(HTML_INDEX.replace("__PUSH_PUBLIC_KEY__", push_key_value))

        @self._fastapi_app.get("/new_character")
        async def new_character():
            if not web_entrypoint.exists():
                raise HTTPException(status_code=404, detail="New character page missing.")
            return HTMLResponse(web_entrypoint.read_text(encoding="utf-8"))

        @self._fastapi_app.get("/config")
        async def edit_character():
            if not edit_entrypoint.exists():
                raise HTTPException(status_code=404, detail="Edit character page missing.")
            return HTMLResponse(edit_entrypoint.read_text(encoding="utf-8"))

        @self._fastapi_app.get("/sw.js")
        async def service_worker():
            return Response(SERVICE_WORKER_JS, media_type="application/javascript")

        @self._fastapi_app.post("/api/push/subscribe")
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

        @self._fastapi_app.post("/api/admin/login")
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

        @self._fastapi_app.get("/api/admin/sessions")
        async def admin_sessions(request: Request):
            self._require_admin(request)
            return self._admin_sessions_payload()

        @self._fastapi_app.post("/api/admin/assign_ip")
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

        @self._fastapi_app.post("/api/client-log")
        async def client_log(request: Request, payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            host = getattr(getattr(request, "client", None), "host", "")
            if not self._is_host_allowed(host):
                raise HTTPException(status_code=403, detail="Unauthorized host.")
            if not self._allow_client_log(host):
                return {"ok": True, "logged": False, "rate_limited": True}
            missing = [
                field
                for field in ("message", "stack", "url", "userAgent", "timestamp")
                if field not in payload
            ]
            if missing:
                raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}.")

            def normalize_field(
                name: str,
                value: Any,
                *,
                required: bool = True,
                max_len: int = 2048,
            ) -> str:
                if value is None:
                    if required:
                        raise HTTPException(status_code=400, detail=f"Missing {name}.")
                    return ""
                if isinstance(value, (dict, list)):
                    raise HTTPException(status_code=400, detail=f"Invalid {name}.")
                text = str(value).strip()
                if required and not text:
                    raise HTTPException(status_code=400, detail=f"Missing {name}.")
                if len(text) > max_len:
                    text = text[:max_len]
                return text

            message = normalize_field("message", payload.get("message"), max_len=4000)
            stack = normalize_field("stack", payload.get("stack"), required=False, max_len=20000)
            url = normalize_field("url", payload.get("url"), max_len=2000)
            user_agent = normalize_field("userAgent", payload.get("userAgent"), max_len=512)
            timestamp = normalize_field("timestamp", payload.get("timestamp"), max_len=128)
            entry = {
                "message": message,
                "stack": stack,
                "url": url,
                "userAgent": user_agent,
                "timestamp": timestamp,
                "host": host,
                "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._log_client_error(entry)
            return {"ok": True, "logged": True}

        @self._fastapi_app.get("/api/spells")
        async def list_spells(details: bool = False, raw: bool = False):
            spells_dir = self.app._resolve_spells_dir()
            ids = _scan_spell_ids(spells_dir)
            payload: Dict[str, Any] = {"ids": ids}
            if not details:
                return payload
            spells: List[Dict[str, Any]] = []
            if not spells_dir:
                payload["spells"] = spells
                return payload
            for spell_id in ids:
                text = _read_spell_yaml_text(spells_dir, spell_id)
                if not text:
                    spells.append({"id": spell_id, "raw": None, "parsed": None, "error": "Spell not found."})
                    continue
                entry: Dict[str, Any] = {"id": spell_id, "raw": text}
                if not raw and yaml is not None:
                    try:
                        entry["parsed"] = yaml.safe_load(text)
                    except Exception as exc:
                        entry["parsed"] = None
                        entry["error"] = f"Failed to parse YAML: {exc}"
                spells.append(entry)
            payload["spells"] = spells
            return payload

        @self._fastapi_app.get("/api/spells/{spell_id}")
        async def get_spell(spell_id: str, raw: bool = False):
            spell_id = str(spell_id or "").strip()
            if not spell_id:
                raise HTTPException(status_code=400, detail="Missing spell id.")
            spells_dir = self.app._resolve_spells_dir()
            if not spells_dir:
                raise HTTPException(status_code=404, detail="Spells directory not found.")
            text = _read_spell_yaml_text(spells_dir, spell_id)
            if not text:
                raise HTTPException(status_code=404, detail="Spell not found.")
            payload: Dict[str, Any] = {"id": spell_id, "raw": text}
            if not raw and yaml is not None:
                try:
                    payload["parsed"] = yaml.safe_load(text)
                except Exception as exc:
                    payload["parsed"] = None
                    payload["error"] = f"Failed to parse YAML: {exc}"
            return payload

        @self._fastapi_app.post("/api/spells/{spell_id}/color")
        async def update_spell_color(spell_id: str, payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            spell_id = str(spell_id or "").strip()
            if not spell_id:
                raise HTTPException(status_code=400, detail="Missing spell id.")
            try:
                result = self.app._save_spell_color(spell_id, payload.get("color"))
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Spell not found.")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except RuntimeError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            except Exception:
                raise HTTPException(status_code=500, detail="Failed to save spell color.")
            return {"ok": True, "spell": result}

        @self._fastapi_app.get("/api/characters")
        async def list_characters():
            return {"files": self.app._list_character_filenames()}

        @self._fastapi_app.get("/api/characters/schema")
        async def get_character_schema():
            return {
                "schema": self.app._character_schema_config(),
                "readme_map": self.app._character_schema_readme_map(),
            }

        @self._fastapi_app.post("/api/characters/export")
        async def export_character(payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            if yaml is None:
                raise HTTPException(status_code=500, detail="YAML support is not available.")
            data = payload.get("data")
            if data is None:
                raise HTTPException(status_code=400, detail="Missing character data.")
            try:
                text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Unable to export YAML: {exc}")
            return Response(text, media_type="application/x-yaml")

        @self._fastapi_app.get("/api/characters/by_ip")
        async def get_character_by_ip(request: Request):
            host = getattr(getattr(request, "client", None), "host", "")
            name = self._assigned_character_name_for_host(host)
            if not name:
                raise HTTPException(status_code=404, detail="No assigned character.")
            try:
                return self.app._get_character_payload(name)
            except CharacterApiError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        @self._fastapi_app.get("/api/characters/{name}")
        async def get_character(name: str):
            try:
                return self.app._get_character_payload(name)
            except CharacterApiError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        @self._fastapi_app.post("/api/characters")
        async def create_character(payload: Dict[str, Any] = Body(...)):
            try:
                return self.app._create_character_payload(payload)
            except CharacterApiError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        @self._fastapi_app.put("/api/characters/{name}")
        async def update_character(name: str, payload: Dict[str, Any] = Body(...)):
            try:
                return self.app._update_character_payload(name, payload)
            except CharacterApiError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        @self._fastapi_app.post("/api/characters/{name}/overwrite")
        async def overwrite_character(name: str, payload: Dict[str, Any] = Body(...)):
            try:
                return self.app._overwrite_character_payload(name, payload)
            except CharacterApiError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail)

        @self._fastapi_app.post("/api/players/{name}/spells")
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

        @self._fastapi_app.post("/api/players/{name}/spellbook")
        async def update_player_spellbook(name: str, payload: Dict[str, Any] = Body(...)):
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid payload.")
            player_name = str(name or "").strip()
            if not player_name:
                raise HTTPException(status_code=400, detail="Missing player name.")
            try:
                profile = self.app._save_player_spellbook(player_name, payload)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except RuntimeError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            except Exception:
                raise HTTPException(status_code=500, detail="Failed to save player spellbook.")
            return {"ok": True, "player": profile}

        @self._fastapi_app.websocket("/ws_view")
        async def ws_view_endpoint(ws: WebSocket):
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
                    "view_only": True,
                }
                self._view_only_clients.add(ws_id)
            self.app._oplog(f"LAN map view connected ws_id={ws_id} host={host}:{port} ua={ua}")
            try:
                await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                await self._send_terrain_update_async(ws_id, self._terrain_payload())
                # Send static data first (spell presets, etc.) - only sent once
                await ws.send_text(
                    self._json_dumps({"type": "static_data", "data": self._static_data_payload()})
                )
                # Then send initial state without static data
                await ws.send_text(
                    self._json_dumps({"type": "state", "state": self._dynamic_snapshot_payload(), "pcs": self._pcs_payload()})
                )
            except (TypeError, ValueError) as exc:
                self.app._oplog(
                    f"LAN map view serialization failed during initial send ws_id={ws_id}: {exc}", level="warning"
                )
                await ws.close(code=1011, reason="Server error while preparing state.")
                return
            except Exception as exc:
                self.app._oplog(f"LAN map view error during initial send ws_id={ws_id}: {exc}", level="warning")
                return
            try:
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
                    if typ == "grid_request":
                        await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                    elif typ == "terrain_request":
                        await self._send_terrain_update_async(ws_id, self._terrain_payload())
                    elif typ == "state_request":
                        await self._send_full_state_async(ws_id)
                    elif typ == "grid_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._grid_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._grid_pending.pop(ws_id, None)
                    elif typ == "terrain_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._terrain_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._terrain_pending.pop(ws_id, None)
                    elif typ == "log_request":
                        try:
                            lines = self.app._lan_battle_log_lines()
                        except Exception:
                            lines = []
                        await ws.send_text(self._json_dumps({"type": "battle_log", "lines": lines}))
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                self.app._oplog(f"LAN map view error during loop ws_id={ws_id}: {exc}", level="warning")
            finally:
                with self._clients_lock:
                    self._clients.pop(ws_id, None)
                    self._clients_meta.pop(ws_id, None)
                    self._client_hosts.pop(ws_id, None)
                    self._view_only_clients.discard(ws_id)
                    self._grid_pending.pop(ws_id, None)
                    self._terrain_pending.pop(ws_id, None)
                self.app._oplog(f"LAN map view disconnected ws_id={ws_id}")

        @self._fastapi_app.websocket("/ws")
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
                await self._send_terrain_update_async(ws_id, self._terrain_payload())
                # Send static data first (spell presets, etc.) - only sent once
                await ws.send_text(
                    self._json_dumps({"type": "static_data", "data": self._static_data_payload()})
                )
                # Then send initial state without static data
                await ws.send_text(
                    self._json_dumps({"type": "state", "state": self._dynamic_snapshot_payload(), "pcs": self._pcs_payload()})
                )
                await self._auto_assign_host(ws_id, host)
            except (TypeError, ValueError) as exc:
                self.app._oplog(
                    f"LAN session serialization failed during initial send ws_id={ws_id}: {exc}", level="warning"
                )
                await ws.close(code=1011, reason="Server error while preparing state.")
                return
            except Exception as exc:
                self.app._oplog(f"LAN session error during initial send ws_id={ws_id}: {exc}", level="warning")
                return
            try:
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
                            await ws.send_text(self._json_dumps({"type": "preset_error", "error": "Invalid preset payload."}))
                            continue
                        host_key = self._client_hosts.get(ws_id) or f"ws:{ws_id}"
                        if preset is None:
                            self._host_presets.pop(host_key, None)
                        else:
                            self._host_presets[host_key] = preset
                        await ws.send_text(self._json_dumps({"type": "preset_saved"}))
                    elif typ == "load_preset":
                        host_key = self._client_hosts.get(ws_id) or f"ws:{ws_id}"
                        preset = self._host_presets.get(host_key)
                        await ws.send_text(self._json_dumps({"type": "preset", "preset": preset}))
                    elif typ == "grid_request":
                        await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
                    elif typ == "terrain_request":
                        await self._send_terrain_update_async(ws_id, self._terrain_payload())
                    elif typ == "state_request":
                        await self._send_full_state_async(ws_id)
                    elif typ == "grid_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._grid_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._grid_pending.pop(ws_id, None)
                    elif typ == "terrain_ack":
                        ver = msg.get("version")
                        with self._clients_lock:
                            pending = self._terrain_pending.get(ws_id)
                            if pending and pending[0] == ver:
                                self._terrain_pending.pop(ws_id, None)
                    elif typ == "log_request":
                        try:
                            lines = self.app._lan_battle_log_lines()
                        except Exception:
                            lines = []
                        await ws.send_text(self._json_dumps({"type": "battle_log", "lines": lines}))
                    elif typ in (
                        "move",
                        "dash",
                        "perform_action",
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
            except Exception as exc:
                self.app._oplog(f"LAN session error during loop ws_id={ws_id}: {exc}", level="warning")
            finally:
                with self._clients_lock:
                    self._clients.pop(ws_id, None)
                    self._clients_meta.pop(ws_id, None)
                    self._client_hosts.pop(ws_id, None)
                    self._view_only_clients.discard(ws_id)
                    old = self._drop_claim(ws_id)
                    self._grid_pending.pop(ws_id, None)
                    self._terrain_pending.pop(ws_id, None)
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

            config = uvicorn.Config(self._fastapi_app, host=self.cfg.host, port=self.cfg.port, log_level="warning", access_log=False)
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
            try:
                self.app._lan_apply_action(msg)
            except Exception as exc:
                ws_id = msg.get("_ws_id")
                error_details = traceback.format_exc()
                self.app._oplog(f"LAN action failed: {exc}\n{error_details}", level="warning")
                try:
                    self.toast(ws_id, "Something went wrong handling that action.")
                except Exception:
                    pass

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
        prev_snap = self._last_snapshot or {}
        if self._last_snapshot is None:
            self._last_snapshot = copy.deepcopy(snap)
        else:
            turn_update = self._build_turn_update(prev_snap, snap)
            if turn_update:
                self._broadcast_payload({"type": "turn_update", **turn_update})

            units_snapshot, unit_updates = self._build_unit_updates(prev_snap, snap)
            if units_snapshot is not None:
                self._broadcast_payload({"type": "units_snapshot", "units": units_snapshot})
            elif unit_updates:
                self._broadcast_payload({"type": "unit_update", "updates": unit_updates})

            terrain_patch = self._build_terrain_patch(prev_snap, snap)
            if terrain_patch:
                self._broadcast_payload({"type": "terrain_patch", **terrain_patch})

            aoe_patch = self._build_aoe_patch(prev_snap, snap)
            if aoe_patch:
                self._broadcast_payload({"type": "aoe_patch", **aoe_patch})

            self._last_snapshot = copy.deepcopy(snap)

        try:
            static_payload = self._static_data_payload()
            static_json = json.dumps(static_payload, sort_keys=True, separators=(",", ":"))
        except Exception:
            static_payload = None
            static_json = None
        if static_payload is not None and static_json is not None:
            if self._last_static_json is None:
                self._last_static_json = static_json
            elif static_json != self._last_static_json:
                self._last_static_json = static_json
                self._broadcast_payload({"type": "static_data", "data": static_payload})

        # 3) continue polling
        if self._polling:
            self.app.after(120, self._tick)

    @staticmethod
    def _unit_lookup(units: Any) -> Dict[int, Dict[str, Any]]:
        lookup: Dict[int, Dict[str, Any]] = {}
        if not isinstance(units, list):
            return lookup
        for unit in units:
            if not isinstance(unit, dict):
                continue
            try:
                cid = int(unit.get("cid"))
            except Exception:
                continue
            lookup[cid] = unit
        return lookup

    @staticmethod
    def _rough_lookup(rough: Any) -> Dict[Tuple[int, int], Dict[str, Any]]:
        lookup: Dict[Tuple[int, int], Dict[str, Any]] = {}
        if not isinstance(rough, list):
            return lookup
        for cell in rough:
            if not isinstance(cell, dict):
                continue
            try:
                key = (int(cell.get("col")), int(cell.get("row")))
            except Exception:
                continue
            lookup[key] = cell
        return lookup

    @staticmethod
    def _obstacle_lookup(obstacles: Any) -> set[Tuple[int, int]]:
        out: set[Tuple[int, int]] = set()
        if not isinstance(obstacles, list):
            return out
        for entry in obstacles:
            if not isinstance(entry, dict):
                continue
            try:
                out.add((int(entry.get("col")), int(entry.get("row"))))
            except Exception:
                continue
        return out

    def _build_turn_update(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        update: Dict[str, Any] = {}
        if prev.get("active_cid") != curr.get("active_cid"):
            update["active_cid"] = curr.get("active_cid")
        if prev.get("round_num") != curr.get("round_num"):
            update["round_num"] = curr.get("round_num")
        if prev.get("turn_order") != curr.get("turn_order"):
            update["turn_order"] = curr.get("turn_order")
        return update

    def _build_unit_updates(
        self, prev: Dict[str, Any], curr: Dict[str, Any]
    ) -> Tuple[Optional[List[Dict[str, Any]]], List[Dict[str, Any]]]:
        prev_units = self._unit_lookup(prev.get("units"))
        curr_units = self._unit_lookup(curr.get("units"))
        if set(prev_units.keys()) != set(curr_units.keys()):
            return list(curr.get("units", [])) if isinstance(curr.get("units"), list) else [], []

        updates: List[Dict[str, Any]] = []
        fields = [
            "name",
            "role",
            "token_color",
            "hp",
            "move_remaining",
            "move_total",
            "action_remaining",
            "bonus_action_remaining",
            "reaction_remaining",
            "spell_cast_remaining",
            "marks",
            "is_prone",
            "is_spellcaster",
            "actions",
            "bonus_actions",
        ]
        for cid, curr_unit in curr_units.items():
            prev_unit = prev_units.get(cid, {})
            patch: Dict[str, Any] = {"cid": cid}
            prev_pos = prev_unit.get("pos") if isinstance(prev_unit.get("pos"), dict) else {}
            curr_pos = curr_unit.get("pos") if isinstance(curr_unit.get("pos"), dict) else {}
            if prev_pos != curr_pos and curr_pos:
                patch["pos"] = curr_pos
            for field in fields:
                if prev_unit.get(field) != curr_unit.get(field):
                    patch[field] = curr_unit.get(field)
            if len(patch) > 1:
                updates.append(patch)
        return None, updates

    def _build_terrain_patch(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        prev_rough = self._rough_lookup(prev.get("rough_terrain"))
        curr_rough = self._rough_lookup(curr.get("rough_terrain"))
        rough_updates: List[Dict[str, Any]] = []
        rough_removals: List[Dict[str, int]] = []
        for key, cell in curr_rough.items():
            if prev_rough.get(key) != cell:
                rough_updates.append(cell)
        for key in prev_rough.keys() - curr_rough.keys():
            rough_removals.append({"col": key[0], "row": key[1]})

        prev_obs = self._obstacle_lookup(prev.get("obstacles"))
        curr_obs = self._obstacle_lookup(curr.get("obstacles"))
        obstacle_updates = [{"col": key[0], "row": key[1]} for key in sorted(curr_obs - prev_obs)]
        obstacle_removals = [{"col": key[0], "row": key[1]} for key in sorted(prev_obs - curr_obs)]

        patch: Dict[str, Any] = {}
        if rough_updates:
            patch["rough_updates"] = rough_updates
        if rough_removals:
            patch["rough_removals"] = rough_removals
        if obstacle_updates:
            patch["obstacle_updates"] = obstacle_updates
        if obstacle_removals:
            patch["obstacle_removals"] = obstacle_removals
        return patch

    def _build_aoe_patch(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        prev_aoes = {int(a.get("aid")): a for a in prev.get("aoes", []) if isinstance(a, dict) and "aid" in a}
        curr_aoes = {int(a.get("aid")): a for a in curr.get("aoes", []) if isinstance(a, dict) and "aid" in a}
        updates: List[Dict[str, Any]] = []
        removals: List[int] = []
        for aid, aoe in curr_aoes.items():
            if prev_aoes.get(aid) != aoe:
                updates.append(aoe)
        for aid in prev_aoes.keys() - curr_aoes.keys():
            removals.append(int(aid))
        patch: Dict[str, Any] = {}
        if updates:
            patch["updates"] = updates
        if removals:
            patch["removals"] = removals
        return patch

    def _pcs_payload(self) -> List[Dict[str, Any]]:
        pcs = list(self._cached_pcs)
        with self._clients_lock:
            cid_to_host = {cid: set(hosts) for cid, hosts in self._cid_to_host.items()}
        profiles = self.app._player_profiles_payload() if hasattr(self.app, "_player_profiles_payload") else {}
        out: List[Dict[str, Any]] = []
        for p in pcs:
            pp = dict(p)
            cid = int(pp.get("cid", -1))
            hosts = cid_to_host.get(cid) or set()
            pp["claimed_by"] = ", ".join(sorted(hosts)) if hosts else None
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
        return True

    # ---------- Server-thread safe broadcast ----------

    def _broadcast_state(self, snap: Dict[str, Any]) -> None:
        if not self._loop:
            return
        coro = self._broadcast_state_async(snap)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    def _broadcast_payload(self, payload: Dict[str, Any]) -> None:
        if not self._loop:
            return
        coro = self._broadcast_payload_async(payload)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _broadcast_state_async(self, snap: Dict[str, Any]) -> None:
        try:
            payload = self._json_dumps({"type": "state", "state": self._dynamic_snapshot_payload(), "pcs": self._pcs_payload()})
        except Exception as exc:
            self.app._oplog(f"LAN state broadcast serialization failed: {exc}", level="warning")
            return
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
                    self._drop_claim(ws_id)
                    self._clients.pop(ws_id, None)
                    self._clients_meta.pop(ws_id, None)
                    self._client_hosts.pop(ws_id, None)

    async def _broadcast_payload_async(self, payload: Dict[str, Any]) -> None:
        try:
            text = self._json_dumps(payload)
        except Exception as exc:
            self.app._oplog(f"LAN payload broadcast serialization failed: {exc}", level="warning")
            return
        to_drop: List[int] = []
        with self._clients_lock:
            items = list(self._clients.items())
        for ws_id, ws in items:
            try:
                await ws.send_text(text)
            except Exception:
                to_drop.append(ws_id)
        if to_drop:
            with self._clients_lock:
                for ws_id in to_drop:
                    self._drop_claim(ws_id)
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

    def _broadcast_terrain_update(self, terrain: Dict[str, Any]) -> None:
        if not self._loop:
            return
        coro = self._broadcast_terrain_update_async(terrain)
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    async def _broadcast_grid_update_async(self, grid: Dict[str, Any]) -> None:
        try:
            payload = self._json_dumps({"type": "grid_update", "grid": grid, "version": self._grid_version})
        except Exception as exc:
            self.app._oplog(f"LAN grid broadcast serialization failed: {exc}", level="warning")
            return
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

    async def _broadcast_terrain_update_async(self, terrain: Dict[str, Any]) -> None:
        try:
            payload = self._json_dumps(
                {"type": "terrain_update", "terrain": terrain, "version": self._terrain_version}
            )
        except Exception as exc:
            self.app._oplog(f"LAN terrain broadcast serialization failed: {exc}", level="warning")
            return
        now = time.time()
        with self._clients_lock:
            items = list(self._clients.items())
        for ws_id, ws in items:
            try:
                await ws.send_text(payload)
                with self._clients_lock:
                    self._terrain_pending[ws_id] = (self._terrain_version, now)
            except Exception:
                with self._clients_lock:
                    self._terrain_pending.pop(ws_id, None)

    async def _send_grid_update_async(self, ws_id: int, grid: Dict[str, Any]) -> None:
        payload = self._json_dumps({"type": "grid_update", "grid": grid, "version": self._grid_version})
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        if isinstance(grid, dict):
            self._grid_last_sent = (grid.get("cols"), grid.get("rows"))
        try:
            await ws.send_text(payload)
            with self._clients_lock:
                self._grid_pending[ws_id] = (self._grid_version, time.time())
        except Exception:
            with self._clients_lock:
                self._grid_pending.pop(ws_id, None)

    async def _send_terrain_update_async(self, ws_id: int, terrain: Dict[str, Any]) -> None:
        payload = self._json_dumps({"type": "terrain_update", "terrain": terrain, "version": self._terrain_version})
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        try:
            await ws.send_text(payload)
            with self._clients_lock:
                self._terrain_pending[ws_id] = (self._terrain_version, time.time())
        except Exception:
            with self._clients_lock:
                self._terrain_pending.pop(ws_id, None)

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
                asyncio.run_coroutine_threadsafe(ws.send_text(self._json_dumps(payload)), self._loop)
                with self._clients_lock:
                    self._grid_pending[ws_id] = (self._grid_version, now)
            except Exception:
                with self._clients_lock:
                    self._grid_pending.pop(ws_id, None)

    def _resend_terrain_updates(self) -> None:
        if not self._loop or not self._terrain_pending:
            return
        now = time.time()
        with self._clients_lock:
            pending = list(self._terrain_pending.items())
            clients = dict(self._clients)
        for ws_id, (ver, last_sent) in pending:
            if ver != self._terrain_version:
                with self._clients_lock:
                    self._terrain_pending.pop(ws_id, None)
                continue
            if now - last_sent < self._terrain_resend_seconds:
                continue
            ws = clients.get(ws_id)
            if not ws:
                with self._clients_lock:
                    self._terrain_pending.pop(ws_id, None)
                continue
            payload = {"type": "terrain_update", "terrain": self._terrain_payload(), "version": self._terrain_version}
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(self._json_dumps(payload)), self._loop)
                with self._clients_lock:
                    self._terrain_pending[ws_id] = (self._terrain_version, now)
            except Exception:
                with self._clients_lock:
                    self._terrain_pending.pop(ws_id, None)

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
            ws_ids = list(self._cid_to_ws.get(attacker_cid, set()))
        if not ws_ids:
            return
        self._ko_played = True
        for ws_id in ws_ids:
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
            await ws.send_text(self._json_dumps({"type": "toast", "text": text}))
        except Exception:
            pass

    async def _send_async(self, ws_id: int, payload: Dict[str, Any]) -> None:
        with self._clients_lock:
            ws = self._clients.get(ws_id)
        if not ws:
            return
        try:
            await ws.send_text(self._json_dumps(payload))
        except Exception:
            pass

    async def _send_full_state_async(self, ws_id: int) -> None:
        await self._send_grid_update_async(ws_id, self._cached_snapshot.get("grid", {}))
        await self._send_terrain_update_async(ws_id, self._terrain_payload())
        await self._send_async(ws_id, {"type": "static_data", "data": self._static_data_payload()})
        await self._send_async(
            ws_id,
            {"type": "state", "state": self._dynamic_snapshot_payload(), "pcs": self._pcs_payload()},
        )

    def _drop_claim(self, ws_id: int) -> Optional[int]:
        with self._clients_lock:
            old = self._claims.pop(ws_id, None)
            if old is None:
                return None
            host = self._client_hosts.get(ws_id, "")
            ws_set = self._cid_to_ws.get(int(old))
            if ws_set is not None:
                ws_set.discard(ws_id)
                if not ws_set:
                    self._cid_to_ws.pop(int(old), None)
            host_set = self._cid_to_host.get(int(old))
            if host_set is not None and host:
                remaining_ws = self._cid_to_ws.get(int(old), set())
                still_has_host = any(self._client_hosts.get(w) == host for w in remaining_ws)
                if not still_has_host:
                    host_set.discard(host)
                    if not host_set:
                        self._cid_to_host.pop(int(old), None)
        return old

    async def _unclaim_ws_async(
        self, ws_id: int, reason: str = "Unclaimed", clear_ownership: bool = False
    ) -> None:
        # Drop claim mapping
        old = self._drop_claim(ws_id)
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

        self._drop_claim(ws_id)
        with self._clients_lock:
            host = self._client_hosts.get(ws_id, "")
            self._claims[ws_id] = int(cid)
            self._cid_to_ws.setdefault(int(cid), set()).add(ws_id)
            if host:
                self._cid_to_host.setdefault(int(cid), set()).add(host)

        await self._send_async(ws_id, {"type": "force_claim", "cid": int(cid), "text": note})
        name = self._pc_name_for(int(cid))
        self.app._oplog(f"LAN session ws_id={ws_id} claimed {name} ({note})")

    # ---------- helpers ----------

    def _resolve_local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                ip = sock.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass
        try:
            ip = socket.gethostbyname(socket.gethostname())
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        return "127.0.0.1"

    def _display_host(self) -> str:
        host = str(self.cfg.host or "").strip()
        if host in ("", "0.0.0.0", "::", "127.0.0.1", "localhost"):
            return self._resolve_local_ip()
        return host

    def is_running(self) -> bool:
        return bool(self._server_thread and self._server_thread.is_alive())

    def _best_lan_url(self) -> str:
        return f"http://{self._display_host()}:{self.cfg.port}/"

    def _cached_snapshot_payload(self) -> Dict[str, Any]:
        snap = dict(self._cached_snapshot)
        units = snap.get("units")
        if isinstance(units, list):
            with self._clients_lock:
                cid_to_host = {cid: set(hosts) for cid, hosts in self._cid_to_host.items()}
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
                hosts = cid_to_host.get(cid) or set()
                copy_unit["claimed_by"] = ", ".join(sorted(hosts)) if hosts else None
                enriched.append(copy_unit)
            snap["units"] = enriched
        return snap

    def _terrain_payload(self, snap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        src = snap if isinstance(snap, dict) else self._cached_snapshot
        rough = src.get("rough_terrain")
        if not isinstance(rough, list):
            rough = []
        obstacles = src.get("obstacles")
        if not isinstance(obstacles, list):
            obstacles = []
        return {"rough_terrain": rough, "obstacles": obstacles}

    def _static_data_payload(self) -> Dict[str, Any]:
        """Return static data that only needs to be sent once on connection."""
        return {
            "spell_presets": self._cached_snapshot.get("spell_presets", []),
            "player_spells": self._cached_snapshot.get("player_spells", {}),
            "player_profiles": self._cached_snapshot.get("player_profiles", {}),
        }

    def _dynamic_snapshot_payload(self) -> Dict[str, Any]:
        """Return dynamic state without static data (for regular broadcasts)."""
        snap = self._cached_snapshot_payload()
        # Remove static fields to reduce payload size
        snap.pop("spell_presets", None)
        snap.pop("player_spells", None)
        snap.pop("player_profiles", None)
        snap.pop("rough_terrain", None)
        snap.pop("obstacles", None)
        snap.pop("grid", None)
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
        _archive_startup_logs()
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
        self._spell_dir_signature: Optional[Tuple[int, int, Tuple[str, ...]]] = None
        self._player_yaml_cache_by_path: Dict[Path, Optional[Dict[str, Any]]] = {}
        self._player_yaml_meta_by_path: Dict[Path, Dict[str, object]] = {}
        self._player_yaml_data_by_name: Dict[str, Dict[str, Any]] = {}
        self._player_yaml_name_map: Dict[str, Path] = {}
        self._player_yaml_dir_signature: Optional[Tuple[int, int, Tuple[str, ...]]] = None
        self._player_yaml_last_refresh = 0.0
        self._player_yaml_refresh_interval_s = 1.0
        self._player_yaml_lock = threading.Lock()
        self._spell_yaml_lock = threading.Lock()
        self._player_yaml_refresh_scheduled = False

        # LAN state for when map window isn't open
        self._lan_grid_cols = 20
        self._lan_grid_rows = 20
        self._lan_positions: Dict[int, Tuple[int, int]] = {}  # cid -> (col,row)
        self._lan_obstacles: set[Tuple[int, int]] = set()
        self._lan_rough_terrain: Dict[Tuple[int, int], object] = {}
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
        self._spell_dir_signature = None

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
        if not hasattr(self, "_spell_presets_cache"):
            self._spell_presets_cache = None
            self._spell_index_entries = {}
            self._spell_index_loaded = False
            self._spell_dir_notice = None
            self._spell_dir_signature = None
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
            "reaction_remaining": int(getattr(c, "reaction_remaining", 0) or 0),
            "spell_cast_remaining": int(getattr(c, "spell_cast_remaining", 0) or 0),
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
        c.reaction_remaining = int(snap.get("reaction_remaining", c.reaction_remaining))
        c.spell_cast_remaining = int(snap.get("spell_cast_remaining", c.spell_cast_remaining))

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
            
            # Add Help menu
            help_menu = tk.Menu(menubar, tearoff=0)
            help_menu.add_command(label="Check for Updates", command=self._check_for_updates)
            help_menu.add_command(label="Update Log", command=self._show_update_log)
            help_menu.add_command(label="About", command=self._show_about)
            menubar.add_cascade(label="Help", menu=help_menu)
            
            self.config(menu=menubar)
        except Exception:
            pass

    def _show_lan_url(self) -> None:
        if not self._lan.is_running():
            self._lan.start()
            if not self._lan.is_running():
                return
        url = self._lan._best_lan_url()
        messagebox.showinfo("LAN URL", f"Open this on yer LAN devices:\n\n{url}")

    def _show_lan_qr(self) -> None:
        if not self._lan.is_running():
            self._lan.start()
            if not self._lan.is_running():
                return
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
    
    def _check_for_updates(self) -> None:
        """Check for available updates from GitHub."""
        try:
            import subprocess
            import sys
            
            # Run update check in a separate thread to avoid blocking UI
            def check_updates_thread():
                try:
                    has_update, message, update_info = update_checker.check_for_updates()
                    
                    # Schedule UI update on main thread
                    def show_result():
                        if has_update and update_info:
                            # Show update available dialog
                            update_type = update_info.get("type", "")
                            
                            # Ask user if they want to update
                            result = messagebox.askyesno(
                                "Update Available",
                                f"{message}\n\nWould you like to update now?\n\n"
                                "Note: The application will need to be restarted after updating.",
                                icon="info"
                            )
                            
                            if result:
                                # Get the update command
                                update_cmd = update_checker.get_update_command()
                                
                                if update_cmd:
                                    # Show info about running update
                                    messagebox.showinfo(
                                        "Running Update",
                                        "The update script will now run in a separate window.\n\n"
                                        "Please follow the instructions in the update window.\n"
                                        "After the update completes, restart the application."
                                    )
                                    
                                    # Launch update script in a new terminal/console
                                    if sys.platform.startswith("win"):
                                        # Windows: use start command to open in new window
                                        subprocess.Popen(
                                            update_cmd,
                                            shell=True,
                                            creationflags=subprocess.CREATE_NEW_CONSOLE
                                        )
                                    else:
                                        # Linux/macOS: try to open in a terminal
                                        script_path = update_cmd.split('"')[1] if '"' in update_cmd else None
                                        if script_path:
                                            # Try various terminal emulators
                                            terminals = [
                                                ["gnome-terminal", "--", "bash", script_path],
                                                ["konsole", "-e", "bash", script_path],
                                                ["xterm", "-e", "bash", script_path],
                                                ["x-terminal-emulator", "-e", "bash", script_path],
                                            ]
                                            
                                            launched = False
                                            for term_cmd in terminals:
                                                try:
                                                    subprocess.Popen(term_cmd)
                                                    launched = True
                                                    break
                                                except FileNotFoundError:
                                                    continue
                                            
                                            if not launched:
                                                # Fallback: run in background and show message
                                                subprocess.Popen(["bash", script_path])
                                                messagebox.showinfo(
                                                    "Update Running",
                                                    "The update is running in the background.\n"
                                                    "Check your terminal for progress."
                                                )
                                else:
                                    # No update command available, show manual instructions
                                    messagebox.showinfo(
                                        "Update Available",
                                        f"{message}\n\nTo update manually:\n\n"
                                        "1. Close the application\n"
                                        "2. Navigate to the installation directory\n"
                                        "3. Run: git pull origin main\n"
                                        "4. Run: pip install -r requirements.txt\n"
                                        "5. Restart the application"
                                    )
                        else:
                            # No updates available
                            messagebox.showinfo("No Updates", message)
                    
                    # Schedule on main thread
                    self.after(0, show_result)
                    
                except Exception as e:
                    # Schedule error message on main thread
                    def show_error():
                        messagebox.showerror(
                            "Update Check Failed",
                            f"Could not check for updates.\n\n"
                            f"Error: {str(e)}\n\n"
                            "Please check your internet connection and try again."
                        )
                    self.after(0, show_error)
            
            # Start the check in a background thread
            thread = threading.Thread(target=check_updates_thread, daemon=True)
            thread.start()
            
            # Show a message that we're checking
            messagebox.showinfo(
                "Checking for Updates",
                "Checking for updates from GitHub...\n\n"
                "This may take a few moments.",
                icon="info"
            )
            
        except Exception as e:
            messagebox.showerror(
                "Update Check Error",
                f"Could not check for updates.\n\nError: {str(e)}"
            )
    
    def _show_about(self) -> None:
        """Show about dialog with version information."""
        try:
            current_version = update_checker.get_current_version()
            local_commit = update_checker.get_local_git_commit()
            
            version_info = f"Version: v{current_version}"
            if local_commit:
                version_info += f"\nCommit: {local_commit}"
            
            messagebox.showinfo(
                "About D&D Initiative Tracker",
                f"D&D Initiative Tracker\n\n"
                f"{version_info}\n\n"
                f"A combat management system for D&D 5e\n"
                f"with LAN/mobile web client support.\n\n"
                f"Repository: github.com/jeeves-jeevesenson/dnd-initiative-tracker"
            )
        except Exception as e:
            messagebox.showinfo(
                "About D&D Initiative Tracker",
                f"D&D Initiative Tracker\n\n"
                f"Version: v{APP_VERSION}\n\n"
                f"A combat management system for D&D 5e\n"
                f"with LAN/mobile web client support."
            )

    def _show_update_log(self) -> None:
        """Show the update log from the most recent update attempts."""
        log_path = Path(__file__).resolve().parent / "logs" / "update.log"
        if not log_path.exists():
            messagebox.showinfo(
                "Update Log",
                "No update log found yet.\n\n"
                "Run Help → Check for Updates to generate one."
            )
            return

        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            messagebox.showerror(
                "Update Log",
                f"Could not read the update log.\n\nError: {exc}"
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Update Log")
        dialog.geometry("760x520")
        dialog.transient(self)

        text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", log_text)
        text.configure(state=tk.DISABLED)
    
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
                    cfg_paths = {}
                    for path in players_dir.glob("*.yaml"):
                        if not path.is_file():
                            continue
                        profile_name = self._player_name_from_filename(path)
                        # Prefer normalized player name, fall back to filename stem.
                        for key in (profile_name, path.stem):
                            if not key:
                                continue
                            if key in cfg_paths and cfg_paths[key] != path:
                                self._oplog(
                                    f"Player YAML {path.name}: name '{key}' already mapped; skipping.",
                                    level="warning",
                                )
                                continue
                            cfg_paths[key] = path
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
            fly_speed = 0
            burrow_speed = 0
            climb_speed = 0
            water = False
            actions: List[Dict[str, Any]] = []
            bonus_actions: List[Dict[str, Any]] = []

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
                profile = self._normalize_player_profile(data, nm)
                resources = profile.get("resources", {}) if isinstance(profile, dict) else {}
                defenses = profile.get("defenses", {}) if isinstance(profile, dict) else {}
                # accept a few key names
                speed_source = resources.get("base_movement", resources.get("speed"))
                if speed_source is not None:
                    parsed = base._parse_speed_data(speed_source)
                    if parsed[0] is not None:
                        speed = int(parsed[0])
                    if parsed[1] is not None:
                        swim = int(parsed[1])
                    if parsed[2] is not None:
                        fly_speed = int(parsed[2])
                    if parsed[3] is not None:
                        burrow_speed = int(parsed[3])
                    if parsed[4] is not None:
                        climb_speed = int(parsed[4])
                if "speed" in resources and speed_source is None:
                    speed = int(resources.get("speed", speed) or speed)
                swim = int(resources.get("swim_speed", swim) or swim)
                fly_speed = int(resources.get("fly_speed", fly_speed) or fly_speed)
                burrow_speed = int(resources.get("burrow_speed", burrow_speed) or burrow_speed)
                climb_speed = int(resources.get("climb_speed", climb_speed) or climb_speed)
                hp = int(defenses.get("hp", hp) or hp)
                actions = self._normalize_action_entries(resources.get("actions"), "action")
                bonus_actions = self._normalize_action_entries(resources.get("bonus_actions"), "bonus_action")

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
                    fly_speed=int(fly_speed),
                    burrow_speed=int(burrow_speed),
                    climb_speed=int(climb_speed),
                    movement_mode="Swim" if water else "Normal",
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

    @staticmethod
    def _player_name_from_filename(path: Path) -> Optional[str]:
        """Normalize a player filename into a roster-friendly name."""
        # Example: "player-name_example" -> "player name example".
        stem = path.stem.strip()
        if not stem:
            return None
        name = stem.replace("-", " ").replace("_", " ")
        name = " ".join(name.split())  # collapse extra whitespace
        return name or None

    def _normalize_spell_color(self, color: Any) -> Optional[str]:
        return self._normalize_token_color(color)

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
        rough_terrain: Dict[Tuple[int, int], object] = dict(getattr(self, "_lan_rough_terrain", {}) or {})
        map_batching = False

        if mw is not None:
            try:
                cols = int(getattr(mw, "cols", cols))
                rows = int(getattr(mw, "rows", rows))
            except Exception:
                pass
            try:
                map_batching = bool(
                    getattr(mw, "_suspend_lan_sync", False)
                    or getattr(mw, "_drawing_obstacles", False)
                    or getattr(mw, "_drawing_rough", False)
                )
            except Exception:
                map_batching = False
            try:
                self._lan_sync_aoes_to_map(mw)
                aoe_source = dict(getattr(mw, "aoes", {}) or {})
            except Exception:
                pass
            if not map_batching:
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
            if not map_batching:
                try:
                    self._lan_obstacles = set(obstacles)
                    self._lan_rough_terrain = dict(rough_terrain)
                except Exception:
                    pass

        def _log_invalid_aoe_value(aid_value: int, name_value: str, kind_value: str, key: str, raw_value: Any) -> None:
            self._oplog(
                f"LAN AoE invalid value aid={aid_value} name={name_value} kind={kind_value} key={key} value={raw_value!r}",
                level="warning",
            )

        def _finite_float(
            raw_value: Any,
            aid_value: int,
            name_value: str,
            kind_value: str,
            key: str,
            *,
            default: float = 0.0,
            skip_invalid: bool = False,
        ) -> Optional[float]:
            try:
                candidate = float(raw_value)
            except Exception:
                _log_invalid_aoe_value(aid_value, name_value, kind_value, key, raw_value)
                return None if skip_invalid else default
            if not math.isfinite(candidate):
                _log_invalid_aoe_value(aid_value, name_value, kind_value, key, raw_value)
                return None if skip_invalid else default
            return candidate

        try:
            for aid, d in sorted((aoe_source or {}).items()):
                kind = str(d.get("kind") or d.get("shape") or "").lower()
                if kind not in ("circle", "square", "line", "sphere", "cube", "cone", "cylinder", "wall"):
                    continue
                aid_int = int(aid)
                name = str(d.get("name") or f"AoE {aid}")
                payload: Dict[str, Any] = {
                    "aid": aid_int,
                    "kind": kind,
                    "name": name,
                    "color": str(d.get("color") or ""),
                    "cx": _finite_float(d.get("cx") or 0.0, aid_int, name, kind, "cx") or 0.0,
                    "cy": _finite_float(d.get("cy") or 0.0, aid_int, name, kind, "cy") or 0.0,
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
                    payload["radius_sq"] = _finite_float(
                        d.get("radius_sq") or 0.0, aid_int, name, kind, "radius_sq"
                    ) or 0.0
                    if d.get("radius_ft") is not None:
                        radius_ft = _finite_float(
                            d.get("radius_ft"), aid_int, name, kind, "radius_ft", skip_invalid=True
                        )
                        if radius_ft is not None:
                            payload["radius_ft"] = radius_ft
                    if d.get("height_ft") is not None:
                        height_ft = _finite_float(
                            d.get("height_ft"), aid_int, name, kind, "height_ft", skip_invalid=True
                        )
                        if height_ft is not None:
                            payload["height_ft"] = height_ft
                elif kind in ("line", "wall"):
                    payload["length_sq"] = _finite_float(
                        d.get("length_sq") or 0.0, aid_int, name, kind, "length_sq"
                    ) or 0.0
                    payload["width_sq"] = _finite_float(
                        d.get("width_sq") or 0.0, aid_int, name, kind, "width_sq"
                    ) or 0.0
                    payload["orient"] = str(d.get("orient") or "vertical")
                    if d.get("angle_deg") is not None:
                        angle_deg = _finite_float(
                            d.get("angle_deg"), aid_int, name, kind, "angle_deg", skip_invalid=True
                        )
                        if angle_deg is not None:
                            payload["angle_deg"] = angle_deg
                    if d.get("length_ft") is not None:
                        length_ft = _finite_float(
                            d.get("length_ft"), aid_int, name, kind, "length_ft", skip_invalid=True
                        )
                        if length_ft is not None:
                            payload["length_ft"] = length_ft
                    if d.get("width_ft") is not None:
                        width_ft = _finite_float(
                            d.get("width_ft"), aid_int, name, kind, "width_ft", skip_invalid=True
                        )
                        if width_ft is not None:
                            payload["width_ft"] = width_ft
                    if d.get("thickness_ft") is not None:
                        thickness_ft = _finite_float(
                            d.get("thickness_ft"), aid_int, name, kind, "thickness_ft", skip_invalid=True
                        )
                        if thickness_ft is not None:
                            payload["thickness_ft"] = thickness_ft
                    if d.get("height_ft") is not None:
                        height_ft = _finite_float(
                            d.get("height_ft"), aid_int, name, kind, "height_ft", skip_invalid=True
                        )
                        if height_ft is not None:
                            payload["height_ft"] = height_ft
                elif kind == "cone":
                    payload["length_sq"] = _finite_float(
                        d.get("length_sq") or 0.0, aid_int, name, kind, "length_sq"
                    ) or 0.0
                    payload["orient"] = str(d.get("orient") or "vertical")
                    if d.get("angle_deg") is not None:
                        angle_deg = _finite_float(
                            d.get("angle_deg"), aid_int, name, kind, "angle_deg", skip_invalid=True
                        )
                        if angle_deg is not None:
                            payload["angle_deg"] = angle_deg
                    if d.get("length_ft") is not None:
                        length_ft = _finite_float(
                            d.get("length_ft"), aid_int, name, kind, "length_ft", skip_invalid=True
                        )
                        if length_ft is not None:
                            payload["length_ft"] = length_ft
                else:
                    payload["side_sq"] = _finite_float(
                        d.get("side_sq") or 0.0, aid_int, name, kind, "side_sq"
                    ) or 0.0
                    if d.get("side_ft") is not None:
                        side_ft = _finite_float(
                            d.get("side_ft"), aid_int, name, kind, "side_ft", skip_invalid=True
                        )
                        if side_ft is not None:
                            payload["side_ft"] = side_ft
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
            actions = self._normalize_action_entries(getattr(c, "actions", []), "action")
            bonus_actions = self._normalize_action_entries(getattr(c, "bonus_actions", []), "bonus_action")
            units.append(
                {
                    "cid": c.cid,
                    "name": str(c.name),
                    "role": role if role in ("pc", "ally", "enemy") else "enemy",
                    "token_color": self._token_color_payload(c),
                    "hp": int(getattr(c, "hp", 0) or 0),
                    "speed": int(getattr(c, "speed", 0) or 0),
                    "swim_speed": int(getattr(c, "swim_speed", 0) or 0),
                    "fly_speed": int(getattr(c, "fly_speed", 0) or 0),
                    "burrow_speed": int(getattr(c, "burrow_speed", 0) or 0),
                    "move_remaining": int(getattr(c, "move_remaining", 0) or 0),
                    "move_total": int(getattr(c, "move_total", 0) or 0),
                    "movement_mode": self._movement_mode_label(getattr(c, "movement_mode", "normal")),
                    "action_remaining": int(getattr(c, "action_remaining", 0) or 0),
                    "bonus_action_remaining": int(getattr(c, "bonus_action_remaining", 0) or 0),
                    "reaction_remaining": int(getattr(c, "reaction_remaining", 0) or 0),
                    "spell_cast_remaining": int(getattr(c, "spell_cast_remaining", 0) or 0),
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
                is_rough = bool(cell.get("is_rough", False))
                movement_type = self._normalize_movement_type(cell.get("movement_type"), is_swim=bool(cell.get("is_swim", False)))
            else:
                color = str(cell)
                is_rough = True
                movement_type = "ground"
            rough_payload.append(
                {
                    "col": int(c),
                    "row": int(r),
                    "color": color,
                    "movement_type": movement_type,
                    "is_swim": movement_type == "water",
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
        dir_signature = _directory_signature(spells_dir, files)

        ops = _make_ops_logger()
        if not files:
            self._spell_presets_cache = []
            self._spell_index_entries = {}
            self._spell_index_loaded = True
            self._spell_dir_signature = dir_signature
            _write_index_file(self._spell_index_path(), {"version": 1, "entries": {}})
            return []

        if self._spell_presets_cache is not None and dir_signature == self._spell_dir_signature:
            return list(self._spell_presets_cache)

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

        def normalize_color(value: Any) -> Optional[str]:
            if not isinstance(value, str):
                return None
            raw = value.strip().lower()
            if re.fullmatch(r"#[0-9a-f]{6}", raw):
                return raw
            return None

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
            color = normalize_color(parsed.get("color"))
            import_data = parsed.get("import") if isinstance(parsed.get("import"), dict) else {}
            url = import_data.get("url")
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
                "slug": fp.stem,
                "schema": schema,
                "id": spell_id,
                "name": name,
                "level": level,
                "school": school,
                "tags": tags,
                "casting_time": self._normalize_casting_time(casting_time),
                "range": str(spell_range).strip() if spell_range not in (None, "") else None,
                "ritual": ritual if isinstance(ritual, bool) else None,
                "concentration": concentration if isinstance(concentration, bool) else None,
                "lists": lists,
                "mechanics": mechanics,
                "automation": automation,
            }
            if color:
                preset["color"] = color
            if isinstance(url, str) and url.strip():
                preset["url"] = url.strip()

            targeting = mechanics.get("targeting") if isinstance(mechanics.get("targeting"), dict) else {}
            range_data = targeting.get("range") if isinstance(targeting.get("range"), dict) else {}
            area = targeting.get("area") if isinstance(targeting.get("area"), dict) else {}
            shape_raw = str(area.get("shape") or "").strip().lower()
            shape_map = {
                "circle": "sphere",
                "square": "cube",
            }
            shape = shape_map.get(shape_raw, shape_raw)
            has_area = bool(shape)
            has_aoe_tag = any(str(tag).strip().lower() == "aoe" for tag in tags)
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
                preset["is_aoe"] = True
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
            elif has_aoe_tag:
                preset["is_aoe"] = True

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

            if not preset.get("shape") and has_aoe_tag and not has_area:
                warnings.append("tagged aoe but missing targeting area")
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
                    if "slug" not in preset:
                        preset = dict(preset)
                        preset["slug"] = fp.stem
                        entry["preset"] = preset
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
        self._spell_dir_signature = dir_signature
        if not used_cached_only or not cache_names_match:
            _write_index_file(self._spell_index_path(), {"version": 1, "entries": new_entries})

        return presets

    def _players_dir(self) -> Path:
        try:
            return Path(__file__).resolve().parent / "players"
        except Exception:
            return Path.cwd() / "players"

    def _write_player_yaml_atomic(self, path: Path, payload: Dict[str, Any]) -> None:
        if yaml is None:
            raise RuntimeError("PyYAML is required for spell persistence.")
        yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with self._player_yaml_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(yaml_text, encoding="utf-8")
            tmp_path.replace(path)

    def _write_spell_yaml_atomic(self, path: Path, payload: Dict[str, Any]) -> None:
        if yaml is None:
            raise RuntimeError("PyYAML is required for spell persistence.")
        yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with self._spell_yaml_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(yaml_text, encoding="utf-8")
            tmp_path.replace(path)

    def _schedule_player_yaml_refresh(self) -> None:
        if self._player_yaml_refresh_scheduled:
            return
        self._player_yaml_refresh_scheduled = True

        def refresh() -> None:
            self._player_yaml_refresh_scheduled = False
            try:
                self._load_player_yaml_cache(force_refresh=True)
            except Exception:
                return
            try:
                self._lan._cached_snapshot = self._lan_snapshot()
            except Exception:
                pass

        try:
            self.after(200, refresh)
        except Exception:
            refresh()

    @staticmethod
    def _sanitize_player_filename(name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "").strip())
        slug = slug.strip("-._")
        return slug or "player"

    def _character_schema_template(self) -> Dict[str, Any]:
        if _CHARACTER_SCHEMA_DEFAULTS:
            return copy.deepcopy(_CHARACTER_SCHEMA_DEFAULTS)
        return _CHARACTER_BASE_TEMPLATE()

    def _character_schema_config(self) -> Dict[str, Any]:
        return _CHARACTER_SCHEMA_CONFIG or {}

    def _character_schema_readme_map(self) -> Dict[str, Any]:
        return _CHARACTER_SCHEMA_README_MAP or {}

    def _character_slugify(self, name: str) -> str:
        return _CHARACTER_SLUGIFY(str(name or "").strip(), "_")

    def _character_merge_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(payload)
        return _CHARACTER_MERGE_DEFAULTS(merged, self._character_schema_template())

    def _character_type_name(self, value: Any) -> str:
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if value is None:
            return "null"
        return type(value).__name__

    def _character_schema_errors(self, payload: Any, schema: Any, path: str = "") -> List[Dict[str, str]]:
        errors: List[Dict[str, str]] = []

        def add_error(message: str) -> None:
            errors.append({"path": path or ".", "message": message})

        if isinstance(schema, dict):
            if not isinstance(payload, dict):
                add_error(f"Expected object, got {self._character_type_name(payload)}.")
                return errors
            for key, schema_value in schema.items():
                if key not in payload:
                    continue
                next_path = f"{path}.{key}" if path else key
                errors.extend(self._character_schema_errors(payload[key], schema_value, next_path))
            return errors
        if isinstance(schema, list):
            if not isinstance(payload, list):
                add_error(f"Expected array, got {self._character_type_name(payload)}.")
                return errors
            if schema:
                item_schema = schema[0]
                for index, item in enumerate(payload):
                    next_path = f"{path}[{index}]" if path else f"[{index}]"
                    errors.extend(self._character_schema_errors(item, item_schema, next_path))
            return errors
        if isinstance(schema, bool):
            if not isinstance(payload, bool):
                add_error(f"Expected boolean, got {self._character_type_name(payload)}.")
            return errors
        if isinstance(schema, int) and not isinstance(schema, bool):
            if not isinstance(payload, int) or isinstance(payload, bool):
                add_error(f"Expected integer, got {self._character_type_name(payload)}.")
            return errors
        if isinstance(schema, float):
            if not isinstance(payload, (int, float)) or isinstance(payload, bool):
                add_error(f"Expected number, got {self._character_type_name(payload)}.")
            return errors
        if isinstance(schema, str):
            if not isinstance(payload, str):
                add_error(f"Expected string, got {self._character_type_name(payload)}.")
            return errors
        return errors

    def _validate_character_payload(self, payload: Any) -> List[Dict[str, str]]:
        if not isinstance(payload, dict):
            return [{"path": ".", "message": "Expected object payload."}]
        if _CHARACTER_SCHEMA_TREE:
            return _character_schema_errors_from_tree(payload, _CHARACTER_SCHEMA_TREE)
        schema = self._character_schema_template()
        return self._character_schema_errors(payload, schema)

    def _extract_character_name(self, payload: Dict[str, Any]) -> Optional[str]:
        name = payload.get("name")
        if not name and isinstance(payload.get("identity"), dict):
            name = payload["identity"].get("name")
        text = str(name or "").strip()
        return text or None

    def _apply_character_name(self, payload: Dict[str, Any], name: str) -> Dict[str, Any]:
        payload = dict(payload)
        payload["name"] = name
        identity = payload.get("identity")
        if not isinstance(identity, dict):
            identity = {}
        if not identity.get("name"):
            identity["name"] = name
        payload["identity"] = identity
        return payload

    def _deep_merge_dict(self, base_obj: Any, updates: Any) -> Any:
        if isinstance(base_obj, dict) and isinstance(updates, dict):
            merged: Dict[str, Any] = {}
            for key in base_obj:
                merged[key] = copy.deepcopy(base_obj[key])
            for key, value in updates.items():
                merged[key] = self._deep_merge_dict(base_obj.get(key), value)
            return merged
        return copy.deepcopy(updates)

    def _resolve_character_path(self, name: str) -> Optional[Path]:
        if not name:
            return None
        self._load_player_yaml_cache()
        key = name.lower()
        path = self._player_yaml_name_map.get(key)
        if path and path.exists():
            return path
        players_dir = self._players_dir()
        slug = self._character_slugify(name)
        if slug:
            candidate = players_dir / f"{slug}.yaml"
            if candidate.exists():
                return candidate
        candidate = players_dir / name
        if candidate.suffix.lower() not in (".yaml", ".yml"):
            candidate = candidate.with_suffix(".yaml")
        if candidate.exists():
            return candidate
        return None

    def _load_character_raw(self, path: Path) -> Dict[str, Any]:
        if yaml is None:
            raise CharacterApiError(status_code=500, detail={"error": "yaml_unavailable"})
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CharacterApiError(status_code=500, detail={"error": "read_failed", "message": str(exc)})
        return raw if isinstance(raw, dict) else {}

    def _store_character_yaml(self, path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._write_player_yaml_atomic(path, payload)
        meta = _file_stat_metadata(path)
        self._player_yaml_cache_by_path[path] = payload
        self._player_yaml_meta_by_path[path] = meta
        profile = self._normalize_player_profile(payload, path.stem)
        profile_name = profile.get("name", path.stem)
        self._player_yaml_data_by_name[profile_name] = profile
        self._player_yaml_name_map[profile_name.lower()] = path
        self._player_yaml_name_map[path.stem.lower()] = path
        self._schedule_player_yaml_refresh()
        return profile

    def _normalize_character_filename(self, raw_filename: Optional[str], fallback_name: str) -> str:
        filename = str(raw_filename or "").strip()
        if filename:
            base = Path(filename).name
        else:
            base = self._character_slugify(fallback_name)
        stem = Path(base).stem or base or "character"
        stem = self._sanitize_player_filename(stem)
        return f"{stem}.yaml"

    def _archive_character_file(self, path: Path) -> Path:
        players_dir = self._players_dir()
        old_dir = players_dir / "old"
        old_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"{path.stem}.yaml.old"
        candidate = old_dir / base_name
        if not candidate.exists():
            path.replace(candidate)
            return candidate
        index = 1
        while True:
            candidate = old_dir / f"{base_name}.{index}"
            if not candidate.exists():
                path.replace(candidate)
                return candidate
            index += 1

    def _list_character_filenames(self) -> List[str]:
        players_dir = self._players_dir()
        if not players_dir.exists():
            return []
        files = list(players_dir.glob("*.yaml")) + list(players_dir.glob("*.yml"))
        files.sort(key=lambda path: path.name.lower())
        return [path.name for path in files]

    def _get_character_payload(self, name: str) -> Dict[str, Any]:
        path = self._resolve_character_path(name)
        if path is None:
            raise CharacterApiError(status_code=404, detail={"error": "not_found", "message": "Character not found."})
        raw = self._load_character_raw(path)
        merged = self._character_merge_defaults(raw)
        return {"filename": path.name, "character": merged}

    def _create_character_payload(self, payload: Any) -> Dict[str, Any]:
        errors = self._validate_character_payload(payload)
        if errors:
            raise CharacterApiError(
                status_code=400,
                detail={"error": "validation_error", "errors": errors},
            )
        name = self._extract_character_name(payload)
        if not name:
            raise CharacterApiError(
                status_code=400,
                detail={"error": "validation_error", "errors": [{"path": "name", "message": "Name is required."}]},
            )
        slug = self._character_slugify(name)
        players_dir = self._players_dir()
        players_dir.mkdir(parents=True, exist_ok=True)
        path = players_dir / f"{slug}.yaml"
        if path.exists():
            raise CharacterApiError(
                status_code=409,
                detail={"error": "already_exists", "message": "Character file already exists."},
            )
        normalized = self._apply_character_name(payload, name)
        normalized = self._character_merge_defaults(normalized)
        profile = self._store_character_yaml(path, normalized)
        return {"filename": path.name, "character": profile}

    def _update_character_payload(self, name: str, payload: Any) -> Dict[str, Any]:
        errors = self._validate_character_payload(payload)
        if errors:
            raise CharacterApiError(
                status_code=400,
                detail={"error": "validation_error", "errors": errors},
            )
        path = self._resolve_character_path(name)
        if path is None:
            raise CharacterApiError(status_code=404, detail={"error": "not_found", "message": "Character not found."})
        updated_name = self._extract_character_name(payload) or name
        slug = self._character_slugify(updated_name)
        if slug and path.stem.lower() != slug.lower():
            raise CharacterApiError(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "errors": [{"path": "name", "message": "Name does not match the URL resource."}],
                },
            )
        raw = self._load_character_raw(path)
        merged = self._deep_merge_dict(raw, payload if isinstance(payload, dict) else {})
        merged = self._apply_character_name(merged, updated_name)
        merged = self._character_merge_defaults(merged)
        profile = self._store_character_yaml(path, merged)
        return {"filename": path.name, "character": profile}

    def _overwrite_character_payload(self, name: str, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise CharacterApiError(status_code=400, detail={"error": "validation_error", "message": "Invalid payload."})
        data = payload.get("data") if "data" in payload else payload
        if not isinstance(data, dict):
            raise CharacterApiError(
                status_code=400,
                detail={"error": "validation_error", "message": "Character data is required."},
            )
        errors = self._validate_character_payload(data)
        if errors:
            raise CharacterApiError(
                status_code=400,
                detail={"error": "validation_error", "errors": errors},
            )
        path = self._resolve_character_path(name)
        if path is None:
            raise CharacterApiError(status_code=404, detail={"error": "not_found", "message": "Character not found."})

        updated_name = self._extract_character_name(data) or name
        filename = self._normalize_character_filename(payload.get("filename"), updated_name)
        players_dir = self._players_dir()
        players_dir.mkdir(parents=True, exist_ok=True)
        new_path = players_dir / filename
        if new_path.exists() and new_path.resolve() != path.resolve():
            raise CharacterApiError(
                status_code=409,
                detail={"error": "already_exists", "message": "Target filename already exists."},
            )

        archived = self._archive_character_file(path)
        normalized = self._apply_character_name(data, updated_name)
        normalized = self._character_merge_defaults(normalized)
        profile = self._store_character_yaml(new_path, normalized)
        return {"filename": new_path.name, "character": profile, "archived": archived.name}

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

    def _spell_preset_name_lookup(self) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        try:
            presets = self._spell_presets_payload()
        except Exception:
            presets = []
        for preset in presets if isinstance(presets, list) else []:
            if not isinstance(preset, dict):
                continue
            name = str(preset.get("name") or "").strip()
            if not name:
                continue
            lookup[name.lower()] = name
            preset_id = str(preset.get("id") or "").strip()
            if preset_id:
                lookup[preset_id.lower()] = name

        entries = self._load_spell_index_entries()
        for filename, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            preset = entry.get("preset")
            if not isinstance(preset, dict):
                continue
            name = str(preset.get("name") or "").strip()
            if not name:
                continue
            file_key = str(filename or "").strip()
            if file_key:
                lookup[file_key.lower()] = name
                stem = Path(file_key).stem
                if stem:
                    lookup[stem.lower()] = name
            preset_id = str(preset.get("id") or "").strip()
            if preset_id:
                lookup[preset_id.lower()] = name
        return lookup

    def _normalize_spell_reference_list(self, value: Any) -> List[str]:
        def normalize_name(raw: Any) -> Optional[str]:
            text = str(raw or "").strip()
            return text or None

        lookup = self._spell_preset_name_lookup()
        raw_list: List[str] = []
        if isinstance(value, list):
            raw_list = [name for item in value if (name := normalize_name(item))]
        elif isinstance(value, str):
            name = normalize_name(value)
            raw_list = [name] if name else []

        seen = set()
        mapped: List[str] = []
        for item in raw_list:
            key = item.lower()
            resolved = lookup.get(key, item)
            if resolved in seen:
                continue
            seen.add(resolved)
            mapped.append(resolved)
        return mapped

    @staticmethod
    def _normalize_spell_slug_list(value: Any) -> List[str]:
        def normalize_name(raw: Any) -> Optional[str]:
            text = str(raw or "").strip()
            return text or None

        if isinstance(value, list):
            raw_list = [name for item in value if (name := normalize_name(item))]
        elif isinstance(value, str):
            name = normalize_name(value)
            raw_list = [name] if name else []
        else:
            raw_list = []

        seen = set()
        slugs: List[str] = []
        for item in raw_list:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            slugs.append(item)
        return slugs

    @staticmethod
    def _normalize_casting_time(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        raw = str(value).strip()
        if not raw:
            return None
        lower = raw.lower()
        if _CAST_TIME_BONUS_RE.search(lower):
            return "Bonus Action"
        if _CAST_TIME_REACTION_RE.search(lower):
            return "Reaction"
        if _CAST_TIME_ACTION_RE.search(lower):
            return "Action"
        return raw

    @staticmethod
    def _coerce_level_value(leveling: Dict[str, Any]) -> int:
        raw = leveling.get("level") or leveling.get("total_level") or leveling.get("lvl")
        try:
            value = int(raw)
        except Exception:
            return 0
        return max(0, value)

    @staticmethod
    def _proficiency_bonus_for_level(level: int) -> int:
        if level >= 17:
            return 6
        if level >= 13:
            return 5
        if level >= 9:
            return 4
        if level >= 5:
            return 3
        if level >= 1:
            return 2
        return 0

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
        proficiency = self._normalize_player_section(data.get("proficiency"))
        defenses = self._normalize_player_section(data.get("defenses"))
        resources = self._normalize_player_section(data.get("resources"))
        spellcasting = self._normalize_player_section(data.get("spellcasting"))
        inventory = self._normalize_player_section(data.get("inventory"))

        if "level" not in leveling:
            classes = leveling.get("classes")
            if isinstance(classes, list):
                total = 0
                for entry in classes:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        total += int(entry.get("level") or 0)
                    except Exception:
                        continue
                if total:
                    leveling["level"] = total
        level_value = self._coerce_level_value(leveling)
        if level_value > 0:
            proficiency["bonus"] = self._proficiency_bonus_for_level(level_value)

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

        if "token_color" not in identity:
            normalized_color = self._normalize_token_color(data.get("token_color"))
            if normalized_color:
                identity["token_color"] = normalized_color

        raw_ip = identity.get("ip") if "ip" in identity else data.get("ip")
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
            if "reactions" in data and "reactions" not in resources:
                resources["reactions"] = data.get("reactions")
        else:
            if "actions" in data and "actions" not in resources:
                resources["actions"] = data.get("actions")
            if "bonus_actions" in data and "bonus_actions" not in resources:
                resources["bonus_actions"] = data.get("bonus_actions")
            if "reactions" in data and "reactions" not in resources:
                resources["reactions"] = data.get("reactions")

        for key in ("known_cantrips", "known_spells", "known_spell_names"):
            if key not in spellcasting and key in data:
                spellcasting[key] = data.get(key)
        if "cantrips" not in spellcasting:
            if "cantrips" in data:
                spellcasting["cantrips"] = data.get("cantrips")
            elif "known_cantrips" in spellcasting:
                spellcasting["cantrips"] = spellcasting.get("known_cantrips")
        if "prepared_spells" not in spellcasting and "prepared_spells" in data:
            spellcasting["prepared_spells"] = data.get("prepared_spells")
        cantrips_section = spellcasting.get("cantrips")
        cantrip_list: List[str] = []
        if isinstance(cantrips_section, dict):
            cantrip_list = self._normalize_spell_slug_list(cantrips_section.get("known"))
            if cantrip_list:
                cantrips_section = dict(cantrips_section)
                cantrips_section["known"] = cantrip_list
                spellcasting["cantrips"] = cantrips_section
                if "known_cantrips" not in spellcasting:
                    spellcasting["known_cantrips"] = len(cantrip_list)
        prepared_section = spellcasting.get("prepared_spells")
        prepared_list: List[str] = []
        prepared_limit_formula = ""
        if isinstance(prepared_section, dict):
            prepared_list = self._normalize_spell_slug_list(prepared_section.get("prepared"))
            if prepared_list:
                prepared_section = dict(prepared_section)
                prepared_section["prepared"] = prepared_list
                spellcasting["prepared_spells"] = prepared_section
            prepared_limit_formula = str(prepared_section.get("max_formula") or "").strip()

        known_section = spellcasting.get("known_spells")
        known_limit = None
        known_list: List[str] = []
        if isinstance(known_section, dict):
            known_limit = known_section.get("max")
            known_list = self._normalize_spell_slug_list(known_section.get("known"))

        if "known_enabled" not in spellcasting:
            spellcasting["known_enabled"] = known_section is not None
        spellcasting["known_limit"] = int(known_limit) if str(known_limit).isdigit() else None
        spellcasting["prepared_limit_formula"] = prepared_limit_formula
        spellcasting["known_list"] = known_list
        spellcasting["prepared_list"] = prepared_list
        spellcasting["cantrips_list"] = cantrip_list

        profile = PlayerProfile(
            name=name,
            format_version=fmt,
            identity=identity,
            leveling=leveling,
            abilities=abilities,
            proficiency=proficiency,
            defenses=defenses,
            resources=resources,
            spellcasting=spellcasting,
            inventory=inventory,
        )
        return profile.to_dict()

    def _normalize_spellcasting_ability(self, value: Any) -> Optional[str]:
        raw = str(value or "").strip().lower()
        if not raw:
            return None
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
            "chr": "cha",
            "char": "cha",
        }
        return ability_map.get(raw)

    def _ability_score_modifier(self, abilities: Dict[str, Any], key: Optional[str]) -> int:
        if not key or not isinstance(abilities, dict):
            return 0
        candidates = [key, key.lower(), key.upper(), f"{key}_score"]
        if key == "cha":
            candidates.extend(["chr", "charisma", "CHARISMA"])
        score = None
        for candidate in candidates:
            if candidate in abilities:
                score = abilities.get(candidate)
                break
        try:
            score_value = float(score)
        except Exception:
            score_value = None
        if score_value is not None and math.isfinite(score_value):
            return int(math.floor((score_value - 10) / 2))
        for candidate in (f"{key}_mod", f"{key}_modifier"):
            if candidate in abilities:
                try:
                    mod_value = float(abilities.get(candidate))
                except Exception:
                    continue
                if math.isfinite(mod_value):
                    return int(math.floor(mod_value))
        return 0

    def _evaluate_spell_formula(self, formula: Any, variables: Dict[str, Any]) -> Optional[float]:
        if not isinstance(formula, str):
            return None
        trimmed = formula.strip()
        if not trimmed:
            return None
        if not re.fullmatch(r"[0-9+\-*/(). _a-zA-Z]+", trimmed):
            return None
        expr = trimmed
        for key, value in variables.items():
            try:
                safe_value = float(value)
            except Exception:
                safe_value = 0.0
            if not math.isfinite(safe_value):
                safe_value = 0.0
            expr = re.sub(rf"\\b{re.escape(str(key))}\\b", str(int(safe_value)), expr)
        if re.search(r"[a-zA-Z]", expr):
            return None
        try:
            result = eval(expr, {"__builtins__": {}})
        except Exception:
            return None
        try:
            result_value = float(result)
        except Exception:
            return None
        if not math.isfinite(result_value):
            return None
        return result_value

    def _compute_spell_save_dc(self, profile: Dict[str, Any]) -> Optional[int]:
        if not isinstance(profile, dict):
            return None
        spellcasting = profile.get("spellcasting")
        if not isinstance(spellcasting, dict):
            return None
        formula = spellcasting.get("save_dc_formula")
        if not isinstance(formula, str) or not formula.strip():
            return None
        abilities = profile.get("abilities") if isinstance(profile.get("abilities"), dict) else {}
        leveling = profile.get("leveling") if isinstance(profile.get("leveling"), dict) else {}
        proficiency = profile.get("proficiency") if isinstance(profile.get("proficiency"), dict) else {}
        level_value = self._coerce_level_value(leveling)
        if level_value > 0:
            prof_bonus = self._proficiency_bonus_for_level(level_value)
        else:
            prof_bonus_raw = proficiency.get("bonus")
            try:
                prof_bonus = int(prof_bonus_raw)
            except Exception:
                prof_bonus = 0
        casting_ability = self._normalize_spellcasting_ability(spellcasting.get("casting_ability"))
        casting_mod = self._ability_score_modifier(abilities, casting_ability)
        variables = {
            "prof": prof_bonus,
            "proficiency": prof_bonus,
            "casting_mod": casting_mod,
            "str_mod": self._ability_score_modifier(abilities, "str"),
            "dex_mod": self._ability_score_modifier(abilities, "dex"),
            "con_mod": self._ability_score_modifier(abilities, "con"),
            "int_mod": self._ability_score_modifier(abilities, "int"),
            "wis_mod": self._ability_score_modifier(abilities, "wis"),
            "cha_mod": self._ability_score_modifier(abilities, "cha"),
        }
        result = self._evaluate_spell_formula(formula, variables)
        if result is None:
            return None
        return int(math.floor(result))

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
        cantrip_list: List[str] = []
        cantrips_section = source.get("cantrips")
        if isinstance(cantrips_section, dict):
            cantrip_list = self._normalize_spell_slug_list(cantrips_section.get("known"))
        known_cantrips_source = source.get("known_cantrips")
        if known_cantrips_source is None and cantrip_list:
            known_cantrips_source = len(cantrip_list)
        known_cantrips = normalize_limit(known_cantrips_source, 0)
        known_spells = normalize_limit(source.get("known_spells", source.get("spells")), 15)
        raw_names = source.get("known_spell_names")
        names = self._normalize_spell_slug_list(raw_names)
        if cantrip_list:
            for cantrip in cantrip_list:
                if cantrip not in names:
                    names.append(cantrip)
        known_section = source.get("known_spells")
        known_limit = None
        known_list: List[str] = []
        if isinstance(known_section, dict):
            known_limit = known_section.get("max")
            known_list = self._normalize_spell_slug_list(known_section.get("known"))
        known_enabled = source.get("known_enabled")
        if known_enabled is None and isinstance(known_section, dict):
            known_enabled = True
        if isinstance(known_enabled, str):
            known_enabled = known_enabled.strip().lower() not in ("false", "0", "no", "off")
        known_enabled = bool(known_enabled)
        prepared_payload: Dict[str, Any] = {}
        prepared_spells = source.get("prepared_spells")
        prepared_names: List[str] = []
        prepared_formula = ""
        if isinstance(prepared_spells, dict):
            prepared_names = self._normalize_spell_slug_list(prepared_spells.get("prepared"))
            prepared_payload["prepared"] = prepared_names
            max_formula = prepared_spells.get("max_formula")
            if isinstance(max_formula, str) and max_formula.strip():
                prepared_payload["max_formula"] = max_formula.strip()
                prepared_formula = max_formula.strip()
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
            "known_enabled": known_enabled,
            "known_limit": int(known_limit) if str(known_limit).isdigit() else None,
            "prepared_limit_formula": prepared_formula,
            "known_list": known_list,
            "prepared_list": prepared_names,
            "cantrips_list": cantrip_list,
        }
        if prepared_payload:
            payload["prepared_spells"] = prepared_payload
        spellcasting_payload: Dict[str, Any] = {
            "cantrips": known_cantrips,
            "known_spells": known_spells,
            "known_spell_names": names,
            "known_enabled": known_enabled,
            "known_limit": int(known_limit) if str(known_limit).isdigit() else None,
            "prepared_limit_formula": prepared_formula,
            "known_list": known_list,
            "prepared_list": prepared_names,
            "cantrips_list": cantrip_list,
        }
        if prepared_payload:
            spellcasting_payload["prepared_spells"] = prepared_payload
        payload["spellcasting"] = spellcasting_payload
        return payload

    def _load_player_yaml_cache(self, force_refresh: bool = False) -> None:
        if not force_refresh:
            now = time.monotonic()
            if self._player_yaml_last_refresh and (
                now - self._player_yaml_last_refresh < self._player_yaml_refresh_interval_s
            ):
                return
        if yaml is None:
            self._player_yaml_cache_by_path = {}
            self._player_yaml_meta_by_path = {}
            self._player_yaml_data_by_name = {}
            self._player_yaml_name_map = {}
            self._player_yaml_dir_signature = None
            self._player_yaml_last_refresh = time.monotonic()
            return

        players_dir = self._players_dir()
        if not players_dir.exists():
            self._player_yaml_cache_by_path = {}
            self._player_yaml_meta_by_path = {}
            self._player_yaml_data_by_name = {}
            self._player_yaml_name_map = {}
            self._player_yaml_dir_signature = None
            self._player_yaml_last_refresh = time.monotonic()
            return

        try:
            files = sorted(list(players_dir.glob("*.yaml")) + list(players_dir.glob("*.yml")))
        except Exception:
            files = []
        dir_signature = _directory_signature(players_dir, files)
        if (
            not force_refresh
            and self._player_yaml_cache_by_path
            and dir_signature == self._player_yaml_dir_signature
        ):
            self._player_yaml_last_refresh = time.monotonic()
            return

        data_by_path = dict(self._player_yaml_cache_by_path)
        meta_by_path = dict(self._player_yaml_meta_by_path)
        data_by_name = dict(self._player_yaml_data_by_name)
        name_map = dict(self._player_yaml_name_map)

        def purge_path_entries(target_path: Path) -> None:
            keys_to_remove = [key for key, value in name_map.items() if value == target_path]
            for key in keys_to_remove:
                name_map.pop(key, None)
            if keys_to_remove:
                keys_lower = set(keys_to_remove)
                for name in list(data_by_name.keys()):
                    if name.lower() in keys_lower:
                        data_by_name.pop(name, None)

        valid_paths = set(files)
        for cached_path in list(data_by_path.keys()):
            if cached_path not in valid_paths:
                data_by_path.pop(cached_path, None)
                meta_by_path.pop(cached_path, None)
                purge_path_entries(cached_path)

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
            purge_path_entries(path)
            if isinstance(parsed, dict):
                profile = self._normalize_player_profile(parsed, path.stem)
                name = str(profile.get("name") or path.stem).strip() or path.stem
                data_by_name[name] = profile
                name_map[name.lower()] = path
                name_map[path.stem.lower()] = path

        self._player_yaml_cache_by_path = data_by_path
        self._player_yaml_meta_by_path = meta_by_path
        self._player_yaml_data_by_name = data_by_name
        self._player_yaml_name_map = name_map
        self._player_yaml_dir_signature = dir_signature
        self._player_yaml_last_refresh = time.monotonic()
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
            profile_payload = dict(data)
            spellcasting = profile_payload.get("spellcasting")
            if isinstance(spellcasting, dict):
                save_dc = self._compute_spell_save_dc(profile_payload)
                if save_dc is not None:
                    spellcasting = dict(spellcasting)
                    spellcasting["save_dc"] = save_dc
                    profile_payload["spellcasting"] = spellcasting
            payload[name] = profile_payload
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
        spellcasting_payload = normalized.get("spellcasting")
        normalized_known = {
            k: v for k, v in normalized.items() if k not in ("prepared_spells", "spellcasting")
        }

        if int(existing.get("format_version") or 0) == 1:
            spellcasting = existing.get("spellcasting")
            if not isinstance(spellcasting, dict):
                spellcasting = {}
            spellcasting.update(normalized_known)
            if isinstance(spellcasting_payload, dict):
                spellcasting.update(spellcasting_payload)
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
            spellcasting = existing.get("spellcasting")
            if not isinstance(spellcasting, dict):
                spellcasting = {}
            spellcasting.update(normalized_known)
            if isinstance(spellcasting_payload, dict):
                spellcasting.update(spellcasting_payload)
            if prepared_payload is not None:
                existing_prepared = spellcasting.get("prepared_spells")
                if not isinstance(existing_prepared, dict):
                    existing_prepared = {}
                existing_prepared.update(prepared_payload)
                spellcasting["prepared_spells"] = existing_prepared
            existing["spellcasting"] = spellcasting

        self._write_player_yaml_atomic(path, existing)

        meta = _file_stat_metadata(path)
        self._player_yaml_cache_by_path[path] = existing
        self._player_yaml_meta_by_path[path] = meta
        profile = self._normalize_player_profile(existing, path.stem)
        profile_name = profile.get("name", player_name)
        self._player_yaml_data_by_name[profile_name] = profile
        self._player_yaml_name_map[player_name.lower()] = path
        self._player_yaml_name_map[path.stem.lower()] = path
        self._schedule_player_yaml_refresh()

        return normalized

    def _save_player_spellbook(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if yaml is None:
            raise RuntimeError("PyYAML is required for spell persistence.")
        player_name = str(name or "").strip()
        if not player_name:
            raise ValueError("Player name is required.")
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a dictionary.")

        def normalize_slug_list(value: Any) -> List[str]:
            if isinstance(value, list):
                raw = [str(item).strip() for item in value if str(item or "").strip()]
            elif isinstance(value, str):
                raw = [value.strip()] if value.strip() else []
            else:
                raw = []
            seen = set()
            out: List[str] = []
            for item in raw:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
            return out

        known_enabled = payload.get("known_enabled")
        if isinstance(known_enabled, str):
            known_enabled = known_enabled.strip().lower() not in ("false", "0", "no", "off")
        known_enabled = bool(known_enabled)
        known_list = normalize_slug_list(payload.get("known_list"))
        prepared_list = normalize_slug_list(payload.get("prepared_list"))
        cantrips_list = normalize_slug_list(payload.get("cantrips_list"))

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

        spellcasting = existing.get("spellcasting")
        if not isinstance(spellcasting, dict):
            spellcasting = {}
        spellcasting["known_enabled"] = known_enabled

        cantrips = spellcasting.get("cantrips")
        if not isinstance(cantrips, dict):
            cantrips = {}
        cantrips["known"] = cantrips_list
        spellcasting["cantrips"] = cantrips

        prepared_spells = spellcasting.get("prepared_spells")
        if not isinstance(prepared_spells, dict):
            prepared_spells = {}
        prepared_spells["prepared"] = prepared_list
        spellcasting["prepared_spells"] = prepared_spells

        known_spells = spellcasting.get("known_spells")
        if not isinstance(known_spells, dict):
            known_spells = {}
        if known_enabled:
            known_spells["known"] = known_list
        else:
            known_spells.pop("known", None)
        spellcasting["known_spells"] = known_spells

        existing["spellcasting"] = spellcasting
        if "name" not in existing:
            existing["name"] = player_name
        identity = existing.get("identity")
        if not isinstance(identity, dict):
            identity = {}
        if "name" not in identity:
            identity["name"] = player_name
        existing["identity"] = identity

        self._write_player_yaml_atomic(path, existing)
        meta = _file_stat_metadata(path)
        self._player_yaml_cache_by_path[path] = existing
        self._player_yaml_meta_by_path[path] = meta
        profile = self._normalize_player_profile(existing, path.stem)
        profile_name = profile.get("name", player_name)
        self._player_yaml_data_by_name[profile_name] = profile
        self._player_yaml_name_map[player_name.lower()] = path
        self._player_yaml_name_map[path.stem.lower()] = path
        self._schedule_player_yaml_refresh()

        return profile

    def _save_player_token_color(self, name: str, color: str) -> str:
        if yaml is None:
            raise RuntimeError("PyYAML is required for token color persistence.")
        player_name = str(name or "").strip()
        if not player_name:
            raise ValueError("Player name is required.")
        normalized = self._normalize_token_color(color)
        if not normalized:
            raise ValueError("Token color must be a hex value.")

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

        identity = existing.get("identity")
        if not isinstance(identity, dict):
            identity = {}
        if "name" not in identity:
            identity["name"] = player_name
        identity["token_color"] = normalized
        existing["identity"] = identity

        yaml_text = yaml.safe_dump(existing, sort_keys=False, allow_unicode=True)
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

    def _save_spell_color(self, spell_id: str, color: Any) -> Dict[str, Any]:
        if yaml is None:
            raise RuntimeError("PyYAML is required for spell persistence.")
        slug = str(spell_id or "").strip()
        if not slug:
            raise ValueError("Spell id is required.")
        normalized = self._normalize_spell_color(color)
        if not normalized:
            raise ValueError("Spell color must be a hex value.")
        spells_dir = self._resolve_spells_dir()
        if spells_dir is None:
            raise FileNotFoundError("Spells directory not found.")
        path = spells_dir / f"{slug}.yaml"
        if not path.exists():
            raise FileNotFoundError("Spell not found.")
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Unable to read spell YAML: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Spell YAML did not parse to a dict.")
        parsed["color"] = normalized
        self._write_spell_yaml_atomic(path, parsed)
        self._invalidate_spell_index_cache()
        return {"slug": slug, "color": normalized}

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

    @staticmethod
    def _action_name_key(value: Any) -> str:
        return str(value or "").strip().lower()

    def _iter_combatant_actions(self, c: Any, spend: str) -> List[Dict[str, Any]]:
        if spend == "bonus":
            return self._normalize_action_entries(getattr(c, "bonus_actions", []), "bonus_action")
        return self._normalize_action_entries(getattr(c, "actions", []), "action")

    def _find_action_entry(self, c: Any, spend: str, name: str) -> Optional[Dict[str, Any]]:
        key = self._action_name_key(name)
        if not key:
            return None
        for entry in self._iter_combatant_actions(c, spend):
            entry_name = self._action_name_key(entry.get("name"))
            if entry_name == key:
                return entry
        return None

    def _combatant_can_cast_spell(self, c: Any, spend: str) -> bool:
        spend_list = self._iter_combatant_actions(c, spend)
        if spend == "bonus":
            spend_list = spend_list + self._iter_combatant_actions(c, "action")
        if not spend_list:
            return False
        allowed = {"magic", "cast a spell", "cast spell", "spellcasting"}
        for entry in spend_list:
            name = self._action_name_key(entry.get("name"))
            if name in allowed:
                return True
        return False

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
            player_name = self._pc_name_for(int(cid)) if cid is not None else ""
            if player_name and not player_name.startswith("cid:"):
                try:
                    self._save_player_token_color(player_name, color)
                except Exception:
                    pass
            mw = getattr(self, "_map_window", None)
            if mw is not None and hasattr(mw, "update_unit_token_colors"):
                try:
                    if mw.winfo_exists():
                        mw.update_unit_token_colors()
                except Exception:
                    pass
            return

        # Only allow controlling on your turn (POC)
        if not is_admin and typ not in ("cast_aoe", "aoe_remove"):
            if self.current_cid is None or int(self.current_cid) != int(cid):
                self._lan.toast(ws_id, "Not yer turn yet, matey.")
                return

        if typ == "cast_aoe":
            payload = msg.get("payload") or {}
            shape = str(payload.get("shape") or payload.get("kind") or "").strip().lower()
            if shape not in ("circle", "square", "line", "sphere", "cube", "cone", "cylinder", "wall"):
                self._lan.toast(ws_id, "Pick a valid spell shape, matey.")
                return
            spend_raw = str(msg.get("action_type") or "").strip().lower()
            if spend_raw in ("bonus", "bonus_action"):
                spend = "bonus"
            elif spend_raw == "reaction":
                spend = "reaction"
            else:
                spend = "action"
            c = self.combatants.get(cid) if cid is not None else None
            if c is not None and not is_admin:
                if int(getattr(c, "spell_cast_remaining", 0) or 0) <= 0:
                    self._lan.toast(ws_id, "Already cast a spell this turn, matey.")
                    return
                if not self._combatant_can_cast_spell(c, spend):
                    self._lan.toast(ws_id, "No spellcasting action available, matey.")
                    return
                if spend == "bonus":
                    if not self._use_bonus_action(c):
                        self._lan.toast(ws_id, "No bonus actions left, matey.")
                        return
                elif spend == "reaction":
                    if not self._use_reaction(c):
                        self._lan.toast(ws_id, "No reactions left, matey.")
                        return
                else:
                    if not self._use_action(c):
                        self._lan.toast(ws_id, "No actions left, matey.")
                        return
                c.spell_cast_remaining = max(0, int(getattr(c, "spell_cast_remaining", 0) or 0) - 1)
                self._rebuild_table(scroll_to_current=True)
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
                _, _, _, _, positions = self._lan_live_map_data()
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
            map_ready = mw is not None and mw.winfo_exists()
            aoe_store = getattr(mw, "aoes", {}) if map_ready else (getattr(self, "_lan_aoes", {}) or {})
            d = (aoe_store or {}).get(aid)
            if not d and map_ready:
                d = (getattr(self, "_lan_aoes", {}) or {}).get(aid)
                if d:
                    mw_aoes = getattr(mw, "aoes", None)
                    if mw_aoes is None:
                        mw_aoes = {}
                        setattr(mw, "aoes", mw_aoes)
                    mw_aoes[aid] = dict(d)
                    aoe_store = mw_aoes
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
            if not is_admin:
                if self.current_cid is None or int(self.current_cid) != int(cid):
                    self._lan.toast(ws_id, "Not yer turn yet, matey.")
                    return
                if move_per_turn_ft not in (None, ""):
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
                if map_ready:
                    cols = int(getattr(mw, "cols", 0))
                    rows = int(getattr(mw, "rows", 0))
                else:
                    cols = int(getattr(self, "_lan_grid_cols", 0))
                    rows = int(getattr(self, "_lan_grid_rows", 0))
            except Exception:
                cols = 0
                rows = 0
            if cols and rows:
                cx = max(0.0, min(cx, cols - 1))
                cy = max(0.0, min(cy, rows - 1))
            d["cx"] = float(cx)
            d["cy"] = float(cy)
            try:
                if map_ready and hasattr(mw, "_layout_aoe"):
                    mw._layout_aoe(aid)
            except Exception:
                pass
            try:
                if map_ready:
                    self._lan_aoes = dict(getattr(mw, "aoes", {}) or {})
                else:
                    store = getattr(self, "_lan_aoes", {}) or {}
                    store[aid] = dict(d)
                    self._lan_aoes = store
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
        elif typ == "perform_action":
            c = self.combatants.get(cid)
            if not c:
                return
            spend_raw = str(msg.get("spend") or "action").lower()
            spend = "bonus" if spend_raw in ("bonus", "bonus_action") else "action"
            action_name = str(msg.get("action") or msg.get("name") or "").strip()
            action_entry = self._find_action_entry(c, spend, action_name)
            if not action_entry:
                self._lan.toast(ws_id, "That action ain't in yer sheet, matey.")
                return
            if spend == "bonus":
                if not self._use_bonus_action(c):
                    self._lan.toast(ws_id, "No bonus actions left, matey.")
                    return
                spend_label = "bonus action"
            else:
                if not self._use_action(c):
                    self._lan.toast(ws_id, "No actions left, matey.")
                    return
                spend_label = "action"
            action_key = self._action_name_key(action_name)
            if action_key == "dash":
                try:
                    base_speed = int(self._mode_speed(c))
                except Exception:
                    base_speed = int(getattr(c, "speed", 30) or 30)
                try:
                    total = int(getattr(c, "move_total", 0) or 0)
                    rem = int(getattr(c, "move_remaining", 0) or 0)
                    setattr(c, "move_total", total + base_speed)
                    setattr(c, "move_remaining", rem + base_speed)
                    self._log(
                        f"{c.name} dashed (move {rem}/{total} -> {c.move_remaining}/{c.move_total})",
                        cid=cid,
                    )
                    self._lan.toast(ws_id, f"Dashed ({spend_label}).")
                    self._rebuild_table(scroll_to_current=True)
                except Exception:
                    pass
            else:
                self._log(f"{c.name} used {action_name} ({spend_label})", cid=cid)
                self._lan.toast(ws_id, f"Used {action_name}.")
                self._rebuild_table(scroll_to_current=True)
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
                self._lan.toast(ws_id, "Turn ended.")
            except Exception as exc:
                self._oplog(f"LAN end turn failed: {exc}", level="warning")

    def _lan_try_move(self, cid: int, col: int, row: int) -> Tuple[bool, str, int]:
        # Boundaries
        cols, rows, obstacles, rough_terrain, positions = self._lan_live_map_data()
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

        cost = self._lan_shortest_cost(
            origin,
            (col, row),
            obstacles,
            rough_terrain,
            cols,
            rows,
            max_ft,
            c,
        )
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

    def _lan_live_map_data(
        self,
    ) -> Tuple[int, int, set[Tuple[int, int]], Dict[Tuple[int, int], Dict[str, object]], Dict[int, Tuple[int, int]]]:
        cols = int(self._lan_grid_cols)
        rows = int(self._lan_grid_rows)
        obstacles = set(self._lan_obstacles)
        rough_terrain: Dict[Tuple[int, int], Dict[str, object]] = dict(getattr(self, "_lan_rough_terrain", {}) or {})
        positions = dict(self._lan_positions)

        mw = getattr(self, "_map_window", None)
        try:
            if mw is not None and mw.winfo_exists():
                cols = int(getattr(mw, "cols", cols))
                rows = int(getattr(mw, "rows", rows))
                obstacles = set(getattr(mw, "obstacles", obstacles) or set())
                rough_terrain = dict(getattr(mw, "rough_terrain", rough_terrain) or {})
                for cid, tok in (getattr(mw, "unit_tokens", {}) or {}).items():
                    try:
                        positions[int(cid)] = (int(tok.get("col")), int(tok.get("row")))
                    except Exception:
                        pass
        except Exception:
            pass
        return cols, rows, obstacles, rough_terrain, positions

    def _lan_shortest_cost(
        self,
        origin: Tuple[int, int],
        dest: Tuple[int, int],
        obstacles: set[Tuple[int, int]],
        rough_terrain: Dict[Tuple[int, int], Dict[str, object]],
        cols: int,
        rows: int,
        max_ft: int,
        creature: Optional[base.Combatant] = None,
    ) -> Optional[int]:
        """Dijkstra over (col,row,diagParity) to match 5/10 diagonal rule.

        diagParity toggles when you take a diagonal step; first diagonal costs 5, second costs 10, then 5, etc.
        Orthogonal steps always cost 5 and do not change parity.
        """
        if origin == dest:
            return 0

        import heapq

        mode = self._normalize_movement_mode(getattr(creature, "movement_mode", "normal"))
        water_multiplier = self._water_movement_multiplier(creature, mode)

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

                    target_cell = rough_terrain.get((nc, nr))
                    current_cell = rough_terrain.get((c, r))
                    target_is_rough = bool(target_cell.get("is_rough", False)) if isinstance(target_cell, dict) else False
                    current_type = self._normalize_movement_type(
                        current_cell.get("movement_type") if isinstance(current_cell, dict) else None,
                        is_swim=bool(current_cell.get("is_swim", False)) if isinstance(current_cell, dict) else False,
                    )
                    target_type = self._normalize_movement_type(
                        target_cell.get("movement_type") if isinstance(target_cell, dict) else None,
                        is_swim=bool(target_cell.get("is_swim", False)) if isinstance(target_cell, dict) else False,
                    )
                    if mode == "swim" and target_type != "water":
                        continue
                    if mode == "burrow" and target_type == "water":
                        continue
                    if current_type == "water" or target_type == "water":
                        step = int(math.ceil(step * water_multiplier))
                    if target_is_rough:
                        step *= 2

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
                try:
                    ch = mon.get("challenge") or {}
                    if isinstance(ch, dict) and "cr" in ch:
                        raw_data["challenge_rating"] = ch.get("cr")
                except Exception:
                    pass

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
                    cr = _parse_fractional_cr(cr_val)
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
                speed, swim_speed, fly_speed, burrow_speed, climb_speed = base._parse_speed_data(sp)
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
                "hash": _hash_text(raw),
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
        _write_index_file(index_path, {"version": 1, "entries": new_entries})

    def _monster_names_sorted(self) -> List[str]:
        return [s.name for s in self._monster_specs]

    def _monster_cr_display(self, spec: Optional[MonsterSpec]) -> str:
        if spec is None:
            return ""
        raw = None
        if isinstance(spec.raw_data, dict):
            raw = spec.raw_data.get("challenge_rating")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, (int, float)):
            return str(int(raw)) if float(raw).is_integer() else str(raw)
        if spec.cr is None:
            return ""
        return str(int(spec.cr)) if float(spec.cr).is_integer() else str(spec.cr)

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
                cr_txt = self._monster_cr_display(s)
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
