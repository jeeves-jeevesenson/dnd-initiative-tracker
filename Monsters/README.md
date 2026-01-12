# DnD 2024 Monster YAML Pack (AideDD-derived)

A repository of **per-monster YAML files** representing **DnD 2024 (5e 2024 / One D&D)** creature stat blocks.

This repo is **the YAML data**, **not** the generator script.

---

## What’s included

- One YAML file per creature (typically named by slug, e.g. `ancient-red-dragon.yaml`)
- Each YAML includes structured stat-block data:
  - Identity: name, size, type, alignment
  - Core stats: initiative, AC, HP, speed
  - Ability scores: STR/DEX/CON/INT/WIS/CHA
  - Lists: skills, immunities, languages
  - Text fields: senses, challenge rating (CR)
  - Sections: traits, actions, legendary actions
  - Flavor: description, habitat, treasure

### Explicitly excluded

- `source` is intentionally omitted in every YAML.

---

## Directory layout

A common layout:

```
.
├── monsters/
│   ├── ancient-red-dragon.yaml
│   ├── ...
│   └── <many more>.yaml
└── README.md
```

If your YAML files live at repo root, just adjust examples accordingly.

---

## File naming

Files are usually named by a stable **slug**:

- `ancient-red-dragon.yaml`
- `aarakocra-aeromancer.yaml`
- etc.

If you rename files, keep the slug stable or add your own index (see “Indexing” below).

---

## YAML schema

Fields may be omitted when not applicable. Types below describe the *intended* shape; your loader should tolerate strings where numeric fields are sometimes represented as text to preserve formatting.

### Top-level keys

| Key | Type |
|---|---|
| `name` | string |
| `size` | string |
| `type` | string |
| `alignment` | string |
| `initiative` | string |
| `ac` | string \| number |
| `hp` | string |
| `speed` | string |
| `abilities` | map |
| `skills` | list[string] |
| `immunities` | list[string] |
| `senses` | string |
| `languages` | list[string] |
| `challenge_rating` | string |
| `traits` | list[entry] |
| `actions` | list[entry] |
| `legendary_actions` | list[entry] |
| `legendary_uses` | string |
| `description` | string |
| `habitat` | string |
| `treasure` | string |

### `abilities` map

Keys are the standard six ability abbreviations:

- `Str`, `Dex`, `Con`, `Int`, `Wis`, `Cha`

Values are integers.

Example:

```yaml
abilities:
  Str: 30
  Dex: 10
  Con: 29
  Int: 18
  Wis: 15
  Cha: 27
```

### `entry` objects (traits/actions/legendary_actions)

Each section entry is represented as:

| Key | Type |
|---|---|
| `name` | string |
| `desc` | string |

Example:

```yaml
actions:
  - name: Multiattack
    desc: The dragon makes three Rend attacks...
```

---

## Example YAML

A trimmed example to show structure:

```yaml
name: Ancient Red Dragon
size: Gargantuan
type: Dragon (Chromatic)
alignment: Chaotic Evil
initiative: "+14 (24)"
ac: "22"
hp: 507 (26d20 + 234)
speed: 40 ft., Climb 40 ft., Fly 80 ft.

abilities:
  Str: 30
  Dex: 10
  Con: 29
  Int: 18
  Wis: 15
  Cha: 27

skills:
  - Perception +16
  - Stealth +7

immunities:
  - Fire

senses: Blindsight 60 ft., Darkvision 120 ft., Passive Perception 26

languages:
  - Common
  - Draconic

challenge_rating: 24 (XP 62 000, or 75 000 in lair; PB +7)

traits:
  - name: Legendary Resistance (4/Day, or 5/Day in Lair)
    desc: If the dragon fails a saving throw, it can choose to succeed instead.

actions:
  - name: Multiattack
    desc: The dragon makes three Rend attacks...
  - name: Rend
    desc: "Melee Attack Roll: +17, reach 15 ft. Hit: ..."

legendary_uses: "Legendary Action Uses: 3 (4 in Lair)."

legendary_actions:
  - name: Pounce
    desc: The dragon moves up to half its Speed...
```

---

## Design notes / conventions

### “Stringy” numeric fields
Some fields are kept as strings to preserve original stat-block formatting:

- `initiative` frequently includes parentheses
- `hp` includes dice and bonus text
- `speed` includes multiple movement modes
- `challenge_rating` includes XP and PB text
- `ac` is often numeric, but may be stored as a string for consistency

If your tool wants normalized values, see “Normalization ideas”.

### Sections are lists, not maps
`traits`, `actions`, and `legendary_actions` are lists so ordering is preserved.

### Embedded spell links and references
Descriptions may include spell names or other references in plain text (not links). If you want linkification, do it in your renderer.

---

## Normalization ideas (optional)

If your tool prefers a stricter schema, you can post-process:

- Parse `initiative` into:
  - `initiative_bonus` (int)
  - `initiative_score` (int; if present)
- Parse `ac` into:
  - `ac_value` (int)
  - `ac_notes` (string; if present)
- Parse `hp` into:
  - `hp_average` (int)
  - `hp_formula` (string; dice)
- Parse `speed` into a map:
  - `walk`, `fly`, `climb`, `swim`, `burrow` (each a number)
- Parse `challenge_rating` into:
  - `cr` (string or number)
  - `xp` (int)
  - `pb` (int)
  - `lair_xp` (int; if present)

This repo does **not** enforce a normalized form; it prioritizes preserving the stat-block text in a machine-friendly shape.

---

## Indexing (recommended)

If you need fast lookup without scanning the filesystem, generate an index file in your own build step:

- `index.yaml` or `index.json` mapping `slug -> path`
- Or `name -> slug` for display searches (handle duplicates!)

Example (JSON):

```json
{
  "ancient-red-dragon": "monsters/ancient-red-dragon.yaml",
  "pseudodragon": "monsters/pseudodragon.yaml"
}
```

---

## Loading the YAML (examples)

### Python
```python
import yaml, pathlib

path = pathlib.Path("monsters/ancient-red-dragon.yaml")
data = yaml.safe_load(path.read_text(encoding="utf-8"))
print(data["name"], data["challenge_rating"])
```

### JavaScript (Node)
```js
import fs from "node:fs";
import yaml from "yaml";

const raw = fs.readFileSync("monsters/ancient-red-dragon.yaml", "utf8");
const data = yaml.parse(raw);
console.log(data.name, data.challenge_rating);
```

### Go
```go
package main

import (
  "fmt"
  "os"
  "gopkg.in/yaml.v3"
)

func main() {
  b, _ := os.ReadFile("monsters/ancient-red-dragon.yaml")
  var m map[string]any
  _ = yaml.Unmarshal(b, &m)
  fmt.Println(m["name"], m["challenge_rating"])
}
```

---

## Validation tips

If you want to sanity-check the pack:

- Ensure every file has `name`
- Ensure `abilities` contains all six stats
- Ensure section entries have `name` and `desc`
- Ensure no file includes `source`

---

## Contributing

If you accept contributions:

- Keep formatting consistent (2-space indentation is typical)
- Preserve existing keys unless there’s a clear schema change
- Prefer additive changes (new optional keys) over breaking renames
- If you normalize fields, do it in a separate folder or separate branch/tag to avoid breaking consumers

---

## Legal / attribution note

This repo stores structured representations of monster stat blocks. If you plan to publish or redistribute, review the legal situation for your jurisdiction and intended use. This is especially important if your YAML includes non-SRD content.

---

## Changelog / versioning (suggested)

If you plan releases, consider:

- Tag releases by date, e.g. `2026-01-11`
- Or by upstream snapshot, e.g. `aidedd-2024-<date>`
- Keep a `CHANGELOG.md` noting additions/removals/renames

---

## Support / compatibility

If you’re using these YAMLs in a custom tool:

- Treat unknown keys as forward-compatible
- Treat missing keys as normal
- Avoid strict schema assumptions unless you control your own fork
