#!/usr/bin/env python3
"""Backfill monster section text from AideDD 2024 with 5eTools JSON fallback."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml

AIDEDD_MONSTER_URL = "https://www.aidedd.org/monster/{slug}"
SECTION_KEYS: Sequence[str] = ("traits", "actions", "legendary_actions")
HEADING_ALIASES = {
    "traits": {"traits", "trait", "features", "capacites", "capacités"},
    "actions": {"actions", "action"},
    "legendary_actions": {
        "legendary actions",
        "legendary action",
        "actions legendaires",
        "actions légendaires",
    },
}


@dataclass(frozen=True)
class Entry:
    name: str
    desc: str

    def as_dict(self) -> Dict[str, str]:
        return {"name": self.name, "desc": self.desc}


class AideddSectionParser(HTMLParser):
    """Best-effort parser for heading + paragraph-style AideDD sections."""

    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "strong", "b"}
    _BLOCK_TAGS = {"p", "li", "div", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._current_heading_tag: Optional[str] = None
        self._heading_chunks: List[str] = []
        self._current_section: Optional[str] = None

        self._current_block_tag: Optional[str] = None
        self._block_chunks: List[str] = []

        self.sections: Dict[str, List[Entry]] = {key: [] for key in SECTION_KEYS}

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        low_tag = tag.lower()
        if low_tag in self._HEADING_TAGS:
            self._current_heading_tag = low_tag
            self._heading_chunks = []
        if low_tag in self._BLOCK_TAGS and low_tag != "br":
            self._current_block_tag = low_tag
            self._block_chunks = []
        if low_tag == "br" and self._current_block_tag:
            self._block_chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        low_tag = tag.lower()
        if self._current_heading_tag == low_tag:
            heading = _normalize_whitespace("".join(self._heading_chunks))
            detected = _detect_section_from_heading(heading)
            if detected:
                self._current_section = detected
            self._current_heading_tag = None
            self._heading_chunks = []

        if self._current_block_tag == low_tag:
            text = _normalize_whitespace("".join(self._block_chunks))
            self._ingest_block_text(text)
            self._current_block_tag = None
            self._block_chunks = []

    def handle_data(self, data: str) -> None:
        if self._current_heading_tag:
            self._heading_chunks.append(data)
        if self._current_block_tag:
            self._block_chunks.append(data)

    def _ingest_block_text(self, text: str) -> None:
        if not text or not self._current_section:
            return
        name_desc = _split_name_desc(text)
        if name_desc:
            name, desc = name_desc
            self.sections[self._current_section].append(Entry(name=name, desc=desc))
        elif self.sections[self._current_section]:
            tail = self.sections[self._current_section][-1]
            self.sections[self._current_section][-1] = Entry(
                name=tail.name,
                desc=f"{tail.desc} {text}".strip(),
            )


def _normalize_whitespace(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _slug_from_path(path: Path) -> str:
    return path.stem


def _normalize_heading_text(text: str) -> str:
    normalized = _normalize_whitespace(text).lower()
    normalized = normalized.replace("’", "'")
    normalized = normalized.replace("é", "e")
    normalized = normalized.replace("è", "e")
    return normalized


def _detect_section_from_heading(heading: str) -> Optional[str]:
    normalized = _normalize_heading_text(heading)
    if not normalized:
        return None
    for section, names in HEADING_ALIASES.items():
        if normalized in names:
            return section
    return None


def _split_name_desc(text: str) -> Optional[tuple[str, str]]:
    candidate = _normalize_whitespace(text)
    if not candidate:
        return None

    for pattern in (
        r"^(?P<name>[^\n]{1,120}?)\.\s+(?P<desc>.+)$",
        r"^(?P<name>[^\n]{1,120}?)\s*:\s+(?P<desc>.+)$",
        r"^(?P<name>[^\n]{1,120}?)\s+[-—]\s+(?P<desc>.+)$",
    ):
        match = re.match(pattern, candidate)
        if not match:
            continue
        name = _normalize_whitespace(match.group("name")).rstrip(".")
        desc = _normalize_whitespace(match.group("desc"))
        if name and desc:
            return name, desc
    return None


def _entry_list(entries: Iterable[Entry]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for entry in entries:
        key = (entry.name, entry.desc)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry.as_dict())
    return out


def extract_sections_from_aidedd_html(raw_html: str) -> Dict[str, List[Dict[str, str]]]:
    parser = AideddSectionParser()
    parser.feed(raw_html)
    parser.close()
    return {section: _entry_list(parser.sections[section]) for section in SECTION_KEYS}


def _flatten_5etools_entry_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _normalize_whitespace(value)
    if isinstance(value, list):
        parts = [_flatten_5etools_entry_text(v) for v in value]
        return _normalize_whitespace(" ".join(part for part in parts if part))
    if isinstance(value, dict):
        if "entries" in value:
            return _flatten_5etools_entry_text(value.get("entries"))
        if "entry" in value:
            return _flatten_5etools_entry_text(value.get("entry"))
        if "items" in value:
            return _flatten_5etools_entry_text(value.get("items"))
        if "headerEntries" in value:
            return _flatten_5etools_entry_text(value.get("headerEntries"))
        pieces = [_flatten_5etools_entry_text(v) for v in value.values()]
        return _normalize_whitespace(" ".join(piece for piece in pieces if piece))
    return _normalize_whitespace(str(value))


def extract_sections_from_5etools_monster(monster: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    section_map = {
        "traits": "trait",
        "actions": "action",
        "legendary_actions": "legendary",
    }
    output: Dict[str, List[Dict[str, str]]] = {section: [] for section in SECTION_KEYS}

    for section, source_key in section_map.items():
        source_entries = monster.get(source_key)
        if not isinstance(source_entries, list):
            continue
        normalized_entries: List[Entry] = []
        for source in source_entries:
            if not isinstance(source, dict):
                continue
            name = _normalize_whitespace(str(source.get("name") or ""))
            desc = _flatten_5etools_entry_text(source.get("entries"))
            if name and desc:
                normalized_entries.append(Entry(name=name, desc=desc))
        output[section] = _entry_list(normalized_entries)

    return output


def _monster_lookup_key(slug: str) -> str:
    return slug.lower().replace("_", "-")


def build_5etools_lookup(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    monsters = data.get("monster") if isinstance(data, dict) else None
    if not isinstance(monsters, list):
        return {}

    lookup: Dict[str, Dict[str, Any]] = {}
    for monster in monsters:
        if not isinstance(monster, dict):
            continue
        slug = _monster_lookup_key(str(monster.get("name") or ""))
        slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
        if slug and slug not in lookup:
            lookup[slug] = monster
    return lookup


def _fetch_aidedd_html(slug: str, timeout: float = 15.0) -> str:
    url = AIDEDD_MONSTER_URL.format(slug=slug)
    request = urllib.request.Request(url, headers={"User-Agent": "dnd-init-tracker-monster-backfill/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _apply_sections(
    existing: Dict[str, Any],
    primary: Dict[str, List[Dict[str, str]]],
    fallback: Dict[str, List[Dict[str, str]]],
) -> bool:
    changed = False
    for section in SECTION_KEYS:
        selected = primary.get(section) or fallback.get(section) or []
        if existing.get(section) != selected:
            existing[section] = selected
            changed = True
    return changed


def backfill_monster_sections(
    monsters_dir: Path,
    fiveetools_lookup: Dict[str, Dict[str, Any]],
    dry_run: bool = False,
) -> int:
    updated = 0
    for path in sorted(monsters_dir.glob("*.yaml")):
        slug = _slug_from_path(path)
        try:
            raw_html = _fetch_aidedd_html(slug)
            primary = extract_sections_from_aidedd_html(raw_html)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"[warn] AideDD fetch failed for {slug}: {exc}", file=sys.stderr)
            primary = {section: [] for section in SECTION_KEYS}

        fallback_monster = fiveetools_lookup.get(_monster_lookup_key(slug), {})
        fallback = extract_sections_from_5etools_monster(fallback_monster)

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            print(f"[warn] Skipping non-mapping YAML: {path}", file=sys.stderr)
            continue

        if _apply_sections(data, primary=primary, fallback=fallback):
            updated += 1
            if not dry_run:
                path.write_text(
                    yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
                    encoding="utf-8",
                )

    return updated


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--monsters-dir",
        default="Monsters",
        help="Directory containing monster YAML files (default: Monsters)",
    )
    parser.add_argument(
        "--fiveetools-json",
        required=True,
        help="Path to structured 5eTools bestiary JSON (must include top-level 'monster' list)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute updates without writing files")

    args = parser.parse_args(argv)
    monsters_dir = Path(args.monsters_dir)
    fiveetools_json = Path(args.fiveetools_json)

    if not monsters_dir.exists():
        parser.error(f"Monsters directory does not exist: {monsters_dir}")
    if not fiveetools_json.exists():
        parser.error(f"5eTools JSON does not exist: {fiveetools_json}")

    fiveetools_lookup = build_5etools_lookup(_load_json(fiveetools_json))
    updated = backfill_monster_sections(
        monsters_dir=monsters_dir,
        fiveetools_lookup=fiveetools_lookup,
        dry_run=args.dry_run,
    )
    mode = "would update" if args.dry_run else "updated"
    print(f"{mode} {updated} monster files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
