"""Character auto-fill helpers shared by web forms and tests."""

from __future__ import annotations

from collections import Counter

SAVE_PROFICIENCIES = {
    "barbarian": ["str", "con"],
    "bard": ["dex", "cha"],
    "cleric": ["wis", "cha"],
    "druid": ["int", "wis"],
    "fighter": ["str", "con"],
    "monk": ["str", "dex"],
    "paladin": ["wis", "cha"],
    "ranger": ["str", "dex"],
    "rogue": ["dex", "int"],
    "sorcerer": ["con", "cha"],
    "warlock": ["wis", "cha"],
    "wizard": ["int", "wis"],
}

HIT_DIE_BY_CLASS = {
    "barbarian": "d12",
    "fighter": "d10",
    "paladin": "d10",
    "ranger": "d10",
    "bard": "d8",
    "cleric": "d8",
    "druid": "d8",
    "monk": "d8",
    "rogue": "d8",
    "warlock": "d8",
    "sorcerer": "d6",
    "wizard": "d6",
}


def total_level(classes: list[dict] | None, fallback_level: int | None = 0) -> int:
    class_total = sum(max(0, int((entry or {}).get("level", 0) or 0)) for entry in (classes or []))
    if class_total:
        return class_total
    return max(0, int(fallback_level or 0))


def proficiency_bonus_for_level(level: int) -> int:
    lvl = max(1, int(level or 1))
    return min(6, 2 + (lvl - 1) // 4)


def highest_class_save_proficiencies(classes: list[dict] | None) -> list[str]:
    if not classes:
        return []
    best_name = ""
    best_level = -1
    for entry in classes:
        name = str((entry or {}).get("name", "")).strip().lower()
        lvl = int((entry or {}).get("level", 0) or 0)
        if lvl > best_level:
            best_level = lvl
            best_name = name
    return SAVE_PROFICIENCIES.get(best_name, [])


def hit_dice_from_classes(classes: list[dict] | None) -> list[dict]:
    dice_counter: Counter[str] = Counter()
    for entry in classes or []:
        name = str((entry or {}).get("name", "")).strip().lower()
        level = max(0, int((entry or {}).get("level", 0) or 0))
        die = HIT_DIE_BY_CLASS.get(name)
        if die and level:
            dice_counter[die] += level
    order = ["d12", "d10", "d8", "d6"]
    return [{"die": die, "total": dice_counter[die], "current": dice_counter[die]} for die in order if dice_counter[die]]


def ability_modifier(score: int) -> int:
    return (int(score or 0) - 10) // 2


def slugify_filename(name: str) -> str:
    text = (name or "").strip().lower()
    cleaned = []
    for ch in text:
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {" ", "'", "-"}:
            cleaned.append("_")
    out = "".join(cleaned)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "character"


def skill_toggle(proficient: list[str] | None, expertise: list[str] | None, skill: str, *, prof_checked: bool | None = None, exp_checked: bool | None = None) -> tuple[list[str], list[str]]:
    prof = {str(v).lower() for v in (proficient or [])}
    exp = {str(v).lower() for v in (expertise or [])}
    key = str(skill or "").lower()
    if prof_checked is not None:
      if prof_checked:
        prof.add(key)
      else:
        prof.discard(key)
        exp.discard(key)
    if exp_checked is not None:
      if exp_checked:
        exp.add(key)
        prof.add(key)
      else:
        exp.discard(key)
    return sorted(prof), sorted(exp)


def passive_perception_value(wis_score: int, proficiency_bonus: int, perception_proficient: bool, perception_expertise: bool) -> int:
    wis_mod = ability_modifier(wis_score)
    return 10 + wis_mod + (proficiency_bonus if perception_proficient else 0) + (proficiency_bonus if perception_expertise else 0)
