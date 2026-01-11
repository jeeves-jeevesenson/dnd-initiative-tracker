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
  dice: 8d6
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
  - `dc` (number, optional): Default save DC.
- `dice` (string, optional): `#d#` hit dice for spell damage (die must be 4, 6, 8, 10, or 12).
- `color` (string, optional): Hex color (e.g., `"#6aa9ff"`) used for the cast AoE.
- `duration_turns` (number, optional): Default AoE duration in rounds (0 = indefinite).
- `over_time` (boolean, optional): Whether the AoE applies damage on start/enter triggers.
- `move_per_turn_ft` (number, optional): How far (in feet) the owner can reposition the AoE each turn.
- `trigger_on_start_or_enter` (string, optional): `start`, `enter`, or `start_or_enter` to control when over-time damage triggers.
- `persistent` (boolean, optional): Keep the AoE after applying damage (defaults to true for over-time effects).
- `pinned_default` (boolean, optional): Default pinned state for the AoE in the map UI.
