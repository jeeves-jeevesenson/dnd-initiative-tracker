#!/usr/bin/env python3
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPELLS_DIR = ROOT / "Spells"
PLAYERS_DIR = ROOT / "players"
REPORT_PATH = SPELLS_DIR / "automation_audit_level_0_6.md"
LEVEL_0_5_REVIEW = SPELLS_DIR / "level-0-5-tag-review.yaml"


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def slugify(text: str) -> str:
    value = str(text or "").strip().lower()
    value = value.replace("'", "")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def gather_spells() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(SPELLS_DIR.glob("*.yaml")):
        data = load_yaml(path)
        if not isinstance(data, dict):
            continue
        level = data.get("level")
        if not isinstance(level, int) or level < 0 or level > 6:
            continue
        mechanics = data.get("mechanics") if isinstance(data.get("mechanics"), dict) else {}
        out.append(
            {
                "path": path,
                "id": str(data.get("id") or path.stem),
                "name": str(data.get("name") or path.stem),
                "level": int(level),
                "automation": str(mechanics.get("automation") or "manual").strip().lower(),
                "tags": {str(t).strip().lower() for t in list(data.get("tags") or []) if str(t).strip()},
                "text": str((((data.get("import") or {}).get("raw") or {}).get("description") or "")).lower(),
                "mechanics": mechanics,
            }
        )
    return out


def classify_partial(spell: dict[str, Any]) -> tuple[str, str]:
    sid = spell["id"]
    text = spell["text"]
    tags = spell["tags"]
    mechanics = spell["mechanics"]

    new_engine_keywords = [
        "teleport",
        "portal",
        "summon",
        "conjure",
        "radius",
        "sphere",
        "cube",
        "cylinder",
        "line",
        "wall",
        "reaction",
        "counterspell",
        "dispel",
        "revive",
        "return to life",
        "raise dead",
        "resurrection",
        "exile",
        "ethereal",
    ]
    if {"summon", "aoe"} & tags:
        return "needs_new_engine_feature", "summon/aoe systems still rely on bespoke flows"
    if any(k in sid for k in ["teleport", "conjure", "summon", "wall-"]):
        return "needs_new_engine_feature", "teleport/summon/persistent-template system gap"
    if any(k in text for k in new_engine_keywords):
        return "needs_new_engine_feature", "description references systems not fully generalized yet"

    supported_checks = {"", "spell_attack", "saving_throw", "auto_hit", "effect"}
    supported_effects = {"damage", "healing", "condition"}
    seq = mechanics.get("sequence") if isinstance(mechanics.get("sequence"), list) else []
    simple_supported = bool(seq)
    for step in seq:
        if not isinstance(step, dict):
            continue
        check = step.get("check") if isinstance(step.get("check"), dict) else {}
        if str(check.get("kind") or "").strip().lower() not in supported_checks:
            simple_supported = False
            break
        outcomes = step.get("outcomes") if isinstance(step.get("outcomes"), dict) else {}
        for bucket in outcomes.values():
            if not isinstance(bucket, list):
                continue
            for effect in bucket:
                if not isinstance(effect, dict):
                    continue
                if str(effect.get("effect") or "").strip().lower() not in supported_effects:
                    simple_supported = False
                    break

    honestly_partial_ids = {
        "charm-person": "missing hostility/friendly-state clause automation",
        "slow": "somatic-component 25% failure rider is not automated",
        "shocking-grasp": "opportunity-attack lockout rider is not encoded in ongoing primitives",
        "cure-wounds": "healing omits spellcasting ability modifier",
        "healing-word": "healing omits spellcasting ability modifier",
        "blur": "blindsight/truesight immunity exceptions are not modeled",
    }
    if sid in honestly_partial_ids:
        return "supported_but_honestly_partial", honestly_partial_ids[sid]

    if simple_supported:
        return "supported_but_honestly_partial", "core effect resolves, but at least one important clause remains manual"
    return "needs_spell_specific_logic", "requires spell-specific hooks beyond current generic sequence support"


def gather_prepared_spell_ids() -> set[str]:
    ids: set[str] = set()
    for path in sorted(PLAYERS_DIR.glob("*.yaml")):
        data = load_yaml(path)
        if not isinstance(data, dict):
            continue
        spellcasting = data.get("spellcasting") if isinstance(data.get("spellcasting"), dict) else {}
        prepared = spellcasting.get("prepared_spells") if isinstance(spellcasting.get("prepared_spells"), dict) else {}
        for key in ("prepared", "free"):
            values = prepared.get(key)
            if isinstance(values, list):
                for item in values:
                    if item:
                        ids.add(slugify(str(item)))
        for feat in list(data.get("features") or []):
            if not isinstance(feat, dict):
                continue
            grants = feat.get("grants") if isinstance(feat.get("grants"), dict) else {}
            vals = grants.get("always_prepared_spells")
            if isinstance(vals, list):
                for item in vals:
                    if item:
                        ids.add(slugify(str(item)))
    return ids


def write_level_0_5_review(spells: list[dict[str, Any]]) -> None:
    not_full = sorted(s["id"] for s in spells if s["level"] <= 5 and s["automation"] != "full")
    payload = {
        "schema": "dnd55.spell_tag_review.v1",
        "levels_included": [0, 1, 2, 3, 4, 5],
        "category_tags": ["attack", "save", "auto_hit", "aoe", "summon", "heal", "damage", "condition", "utility"],
        "automation_tag": "automation_full",
        "not_fully_automated_spell_ids": not_full,
    }
    LEVEL_0_5_REVIEW.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    spells = gather_spells()
    prepared_ids = gather_prepared_spell_ids()

    promoted = sorted(
        [
            s
            for s in spells
            if s["automation"] == "full"
            and s["id"] in {"greater-invisibility", "shield-of-faith", "longstrider", "protection-from-energy", "haste"}
        ],
        key=lambda x: (x["level"], x["id"]),
    )

    categorized: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for s in spells:
        if s["automation"] == "full":
            continue
        cat, reason = classify_partial(s)
        categorized[cat].append((s["id"], reason, s["level"]))

    for vals in categorized.values():
        vals.sort(key=lambda x: (x[2], x[0]))

    prepared_non_full = []
    by_id = {s["id"]: s for s in spells}
    for pid in sorted(prepared_ids):
        s = by_id.get(pid)
        if not s or s["automation"] == "full":
            continue
        cat, reason = classify_partial(s)
        prepared_non_full.append((pid, s["level"], cat, reason))

    write_level_0_5_review(spells)

    full_count = sum(1 for s in spells if s["automation"] == "full")
    partial_count = sum(1 for s in spells if s["automation"] != "full")
    lines = [
        "# Spell automation audit (levels 0–6)",
        "",
        "## Audit rubric",
        "- **supported_full_now**: YAML behavior is fully covered by existing generic spell resolution + ongoing-effect primitives.",
        "- **supported_but_honestly_partial**: core sequence resolves, but at least one important clause is still missing/manual.",
        "- **needs_new_engine_feature**: depends on unsupported system slices (teleport/summon/persistent templates/reaction-heavy flows/etc.).",
        "- **needs_spell_specific_logic**: requires dedicated per-spell hooks beyond current generic primitives.",
        "",
        f"## Coverage snapshot",
        f"- Level 0–6 spells audited: **{len(spells)}**",
        f"- Marked full now: **{full_count}**",
        f"- Remaining non-full: **{partial_count}**",
        "",
        "## Newly promoted to full in this pass",
    ]
    if promoted:
        for s in promoted:
            lines.append(f"- `{s['id']}` (level {s['level']})")
    else:
        lines.append("- None")

    lines.extend(["", "## Remaining non-full spells by category"])
    for cat in ("supported_but_honestly_partial", "needs_new_engine_feature", "needs_spell_specific_logic"):
        entries = categorized.get(cat, [])
        lines.append("")
        lines.append(f"### {cat} ({len(entries)})")
        for sid, reason, level in entries:
            lines.append(f"- `{sid}` (L{level}): {reason}")

    lines.extend(["", "## Prepared non-full spells after this pass"])
    if prepared_non_full:
        for sid, level, cat, reason in prepared_non_full:
            lines.append(f"- `{sid}` (L{level}, {cat}): {reason}")
    else:
        lines.append("- None")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"Wrote {LEVEL_0_5_REVIEW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
