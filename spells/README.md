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
- `default_damage` (string or number, optional): Default damage amount or math expression (e.g. `28` or `5+3`).
- `dice` (string, optional): `#d#` hit dice for spell damage (die must be 4, 6, 8, 10, or 12).
- `upcast` (mapping, optional): Rules for adding dice when cast at a higher slot level.
  - `base_level` (number): Spell slot level the preset is balanced around.
  - `increments` (list of mappings): Each entry describes how often to add dice.
    - `levels_per_increment` (number): Levels per increment (e.g. `1` = every level, `2` = every 2 levels).
    - `add_dice` (string): Dice to add per increment (e.g. `1d10`, `2d6`).
- `color` (string, optional): Hex color (e.g., `"#6aa9ff"`) used for the cast AoE.
- `duration_turns` (number, optional): Default AoE duration in rounds (0 = indefinite).
- `over_time` (boolean, optional): Whether the AoE applies damage on start/enter triggers.
- `move_per_turn_ft` (number, optional): How far (in feet) the owner can reposition the AoE each turn.
- `trigger_on_start_or_enter` (string, optional): Controls when over-time damage triggers and is only used when `over_time: true`.
  - `start`: applies damage at the start of the target's turn.
  - `enter`: applies damage when a target enters the AoE.
  - `start_or_enter`: applies damage on either start of turn or enter; accepts aliases `start-or-enter` and `start/enter`.
- `persistent` (boolean, optional): Keep the AoE after applying damage (defaults to true for over-time effects).
- `pinned_default` (boolean, optional): Default pinned state for the AoE in the map UI.

### Damage dice behavior

- Instant AoE damage: `dice` (or `default_damage`) is used to prefill the AoE damage dialog. If the amount is dice like `8d6`, it is rolled once per Apply Damage action.
- Over-time AoE damage: triggers open the AoE damage dialog and roll the `dice` amount each time you apply damage. Use `default_damage` if you want a fixed value instead of dice rolls.

## Example: over-time AoE

```yaml
spell:
  name: Moonbeam
  shape: circle
  radius_ft: 5
  damage_types:
    - Radiant
  dice: 2d10
  over_time: true
  move_per_turn_ft: 60
  trigger_on_start_or_enter: start_or_enter
```

## Example: upcast dice

```yaml
spell:
  name: Scorching Ray
  shape: line
  length_ft: 60
  width_ft: 5
  damage_types:
    - Fire
  dice: 2d6
  upcast:
    base_level: 2
    increments:
      - levels_per_increment: 1
        add_dice: 1d6
```
