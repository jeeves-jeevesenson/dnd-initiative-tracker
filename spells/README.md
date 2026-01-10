# Spell Preset YAML Schema

Spell presets power the LAN cast panel "Preset" dropdown. Each YAML file may contain
one spell definition. The loader accepts either a top-level `spell:` mapping or a
flat mapping at the top level.

## Example

```yaml
spell:
  name: Fireball
  shape: circle
  radius_ft: 20
  damage_types:
    - Fire
  save:
    type: dex
    dc: 15
  color: "#ff6a2a"
```

## Fields

- `name` (string, required): Spell name shown in the preset dropdown.
- `shape` (string, required): `circle`, `square`, or `line`.
- `radius_ft` (number, optional): Radius in feet for circle spells.
- `side_ft` (number, optional): Side length in feet for square spells.
- `length_ft` (number, optional): Line length in feet for line spells.
- `width_ft` (number, optional): Line width in feet for line spells.
- `damage_types` (list of strings, optional): One or more damage types.
- `save` (mapping, optional):
  - `type` (string): Save type, e.g. `dex`, `con`, `wis`.
  - `dc` (number): Default save DC.
- `color` (string, optional): Hex color (e.g., `"#6aa9ff"`) used for the cast AoE.
