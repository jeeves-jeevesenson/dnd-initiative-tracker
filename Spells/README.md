# YAML Reference for the DnD Initiative Tracker

This repo stores **combat data** (monsters, spells, player defaults) as **YAML** so your Python/Tkinter initiative tracker can load it without hardcoding stat blocks.

The goal is:

- **Human-editable** files (easy to add a monster or tweak a spell)
- **Safe to parse** (no “text where a number is expected” in logic fields)
- **Forward-compatible** (unknown keys are ignored; missing keys are normal)

---

## Directory layout

A common layout:

```text
.
├── dnd_initative_tracker.py
├── helper_script.py
├── startingplayers.yaml
├── players/
│   ├── Alice.yaml
│   └── Bob.yaml
├── Monsters/
│   ├── goblin.yaml
│   └── ...
└── Spells/
    ├── fireball.yaml
    └── ...
```

Notes:

- The app typically looks for **`Monsters/`** relative to the working directory.
- For spells, you can mirror this pattern with **`Spells/`** (recommended).

---

## YAML conventions used in this project

### Indentation and encoding

- Use **2 spaces** for indentation.
- Avoid tabs.
- Save as UTF‑8.

### Filenames

- Prefer stable **slugs**:
  - `ancient-red-dragon.yaml`
  - `fireball.yaml`
  - `chain-lightning.yaml`

### “Stringy” display fields vs strict logic fields

You will see two styles of fields:

- **Display strings**: preserve formatting from a stat block or spell text.
  - Example: `hp: "150 (20d10 + 40)"`
- **Logic fields**: structured values that the tracker can compute from.
  - Example: `mechanics.targeting.range.distance_ft: 150`

If a field is used in calculations, keep it strictly typed (numbers, enums, structured maps) and put the prose somewhere else (`text`, `import.raw`, `notes`).

---

# Player YAML

## `startingplayers.yaml` (optional)

Used to seed a roster of PCs (when your autoseed option is enabled).

```yaml
players:
  - Alice
  - Bob
  - Cleric
```

## `players/<Name>.yaml` (optional)

Optional per-PC defaults.

Supported keys (typical):

- `base_movement` or `speed` (int, feet)
- `swim_speed` (int, feet)
- `hp` (int)

Example:

```yaml
base_movement: 30
swim_speed: 15
hp: 27
```

---

# Monster YAML

Monster YAMLs are **stat-block shaped** and optimized for rendering + quick DM reference.

## File location

Place monster files in `Monsters/*.yaml` or `Monsters/*.yml`.

## Common schema

Top-level keys (typical):

| Key | Type | Notes |
|---|---|---|
| `name` | string | Display name |
| `size` | string | e.g., Small, Medium |
| `type` | string | e.g., Humanoid, Dragon |
| `alignment` | string | Display text |
| `initiative` | string | Often includes bonus + score |
| `ac` | string \| number | Often kept as a string |
| `hp` | string | Includes dice formula |
| `speed` | string | Multiple movement modes |
| `abilities` | map | Six abilities, ints |
| `skills` | list[string] | Display strings |
| `immunities` | list[string] | Display strings |
| `senses` | string | Display text |
| `languages` | list[string] | Display strings |
| `challenge_rating` | string | Display text |
| `traits` | list[entry] | Ordered |
| `actions` | list[entry] | Ordered |
| `legendary_actions` | list[entry] | Ordered |

### `abilities`

```yaml
abilities:
  Str: 10
  Dex: 14
  Con: 12
  Int: 8
  Wis: 10
  Cha: 8
```

### `entry` objects

Traits/actions/legendary actions use a simple `{name, desc}` shape:

```yaml
actions:
  - name: Scimitar
    desc: "Melee Attack Roll: +4, reach 5 ft. Hit: 5 (1d6 + 2) Slashing damage."
```

---

# Spell YAML

Spells are more varied than monsters, so the schema is split into:

- **Header fields** (good for display and filtering)
- **`mechanics`** (structured, computation-friendly information)

## Spell file naming

Use the spell slug as the filename:

- `Spells/fireball.yaml`
- `Spells/fire-bolt.yaml`

## Spell schema: `dnd55.spell.v1`

### Top-level keys

| Key | Type | Notes |
|---|---|---|
| `schema` | string | Should be `dnd55.spell.v1` |
| `id` | string | Stable slug |
| `name` | string | Display name |
| `color` | string | Hex color for UI display (e.g., `#6aa9ff`) |
| `edition` | string | e.g., `2024` |
| `source` | map | Book/page metadata (optional) |
| `level` | int | 0 = cantrip |
| `school` | string | e.g., evocation |
| `tags` | list[string] | Optional classifier tags |
| `casting_time` | string | Display text |
| `range` | string | Display text |
| `components` | string | Display text |
| `duration` | string | Display text |
| `ritual` | bool | |
| `concentration` | bool | |
| `lists` | map | spell lists: classes/subclasses |
| `import` | map | provenance + raw text captured from source |
| `text` | map | optional curated summary/rules text |
| `mechanics` | map | structured logic for the app |

### Example (header-only)

```yaml
schema: dnd55.spell.v1
id: fireball
name: Fireball
color: "#6aa9ff"
edition: "2024"
source:
  book: "Player's Handbook 2024"
  page: null
  srd: false
level: 3
school: evocation
casting_time: "Action"
range: "150 feet"
components: "V, S, M (bat guano and sulfur)"
duration: "Instantaneous"
ritual: false
concentration: false
lists:
  classes: [sorcerer, wizard]
  subclasses: []
import:
  source: aidedd
  aidedd_slug: fireball
  url: "https://www.aidedd.org/spell/fireball"
  raw:
    description: null
    higher_level: null
text:
  summary: null
  rules: null
  higher_level: null
mechanics:
  automation: manual
  targeting: null
  sequence: []
  scaling: null
  ui: {}
  notes: []
```

---

## `mechanics` section

`mechanics` is what your initiative tracker should rely on for calculations.

### Automation status

`mechanics.automation` is one of:

- `full` – mechanically complete for your engine
- `partial` – some pieces parsed; needs manual completion
- `manual` – only the header/raw text exists; mechanics not parsed

Important: **A spell can have a YAML file generated and still appear in `exceptions.txt`.**
That usually means it was generated with `automation: partial` or `manual`.

### Targeting

```yaml
mechanics:
  targeting:
    origin: point_within_range  # self | touch | point_within_range | target_creature | special
    range:
      kind: distance            # distance | self | touch | sight | unlimited | special
      distance_ft: 150
    area:
      shape: sphere             # sphere | cone | line | cube | cylinder | wall | special
      radius_ft: 20
    target_selection:
      mode: area                # single | multiple | area
      max_targets: null
      friendly_fire: true
```

### Resolution sequence (steps)

Spells resolve as one or more steps. Each step has a `check` and `outcomes`.

Saving throw example:

```yaml
mechanics:
  sequence:
    - id: explosion
      check:
        kind: saving_throw
        ability: dex
        dc: spell_save_dc
      outcomes:
        fail:
          - effect: damage
            damage_type: fire
            dice: "8d6"
        success:
          - effect: damage
            damage_type: fire
            dice: "8d6"
            multiplier: 0.5
```

Spell attack example (why *Fire Bolt* needs explicit support):

```yaml
mechanics:
  sequence:
    - id: bolt
      check:
        kind: spell_attack
        attack_type: ranged
      outcomes:
        hit:
          - effect: damage
            damage_type: fire
            dice: "1d10"
        miss: []
```

### Effects

Common effect types to standardize:

- `damage`
- `healing`
- `condition`
- `movement` (push/pull/teleport)
- `area_persistent` (hazard zones)
- `summon`
- `note` (fallback when automation is not possible)

Damage effect example:

```yaml
- effect: damage
  damage_type: lightning
  dice: "10d8"
```

Movement effect example:

```yaml
- effect: movement
  kind: push
  distance_ft: 10
  forced: true
```

### Scaling

There are two main scaling patterns:

#### Slot-level scaling (upcasting)

```yaml
scaling:
  kind: slot_level
  base_slot: 3
  add_per_slot_above: "1d6"
```

You can also attach scaling directly to a damage effect.

#### Cantrip scaling (character level)

```yaml
scaling:
  kind: character_level
  thresholds:
    "5":  {add: "1d10"}
    "11": {add: "1d10"}
    "17": {add: "1d10"}
```

---

# Generating spell YAMLs from AideDD

A typical workflow:

1. Export or assemble `spell-list.xml` containing `<spell>slug</spell>` entries.
2. Run your generator script (e.g., `generate_spells_yaml.py`).
3. Inspect `exceptions.txt`.
4. For exceptions:
   - either move them to `Spells/exceptions/`
   - or edit the YAML to fill in `mechanics` and set `automation: full`

## Why “exceptions” can be large

Spell text is diverse. Even among “simple” spells, there are multiple mechanics classes:

- Save-based AoE (easy)
- Attack roll single-target (requires `spell_attack` support)
- Multi-target jump rules (e.g., chain lightning)
- Persistent zones with triggers
- Summons / conjurations (often not worth automating fully)

It’s normal for a first-pass generator to mark many spells as `partial`.

---

# Validation and safety checks

## Fast validation script

Run this in your repo root to catch malformed YAML and missing required keys:

```python
import pathlib, yaml

paths = list(pathlib.Path("Spells").glob("**/*.yaml")) + list(pathlib.Path("Monsters").glob("**/*.yaml"))

for p in paths:
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"YAML parse error in {p}: {e}")

    # basic spell checks
    if data.get("schema") == "dnd55.spell.v1":
        for k in ("id", "name", "level", "school"):
            if k not in data:
                print(f"Missing {k} in {p}")

print(f"OK: parsed {len(paths)} files")
```

## Avoiding bad data in logic fields

- If a field is used for math (range feet, radius feet, dice expressions), keep it structured.
- Put descriptive prose in `import.raw.description`, `text.rules`, or `mechanics.notes`.

---

# Legal / attribution

If you plan to publish or redistribute YAMLs containing non‑SRD spell/monster text, review licensing and copyright considerations for your jurisdiction and intended use.
