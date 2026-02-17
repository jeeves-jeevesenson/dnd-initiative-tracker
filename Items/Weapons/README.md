# Weapons YAML Schema (Draft)

## Primary format: one file per weapon

Use one YAML file per weapon in this directory. The filename should match the id:

- `longsword.yaml` → `id: longsword`

```yaml
format_version: 1
id: "stable_weapon_id"
name: "Display Name"
type: "weapon"
category: "martial_melee"
proficient: true
attack_bonus: 0
range: 5
damage:
  one_handed:
    formula: "1d8"
    type: "slashing"
riders:
  - id: "extra_damage"
    trigger: "on_hit"
    formula: "1d6"
    type: "fire"
```

## Legacy catalog format (optional)

Catalog YAMLs with `weapons: []` are still supported:

```yaml
format_version: 1
weapons:
  - id: "longsword"
    name: "Longsword"
    category: "martial_melee"
    damage:
      one_handed:
        formula: "1d8"
        type: "slashing"
      versatile:
        formula: "1d10"
        type: "slashing"
    properties: ["sap", "versatile"]
```

## Shared property definition files

`properties_*.yaml` files are for property metadata (names/descriptions) and are **not** weapon items.
They can coexist here and are ignored by the item loader when building weapon records.

## How to add a new weapon

1. Create `Items/Weapons/<weapon_id>.yaml`.
2. Set `id: <weapon_id>` in the file.
3. Add fields (`name`, `category`, `damage`, `properties`, etc.) as needed.
4. Restart/refresh the app so the registry cache sees the new file.

`type` values for damage/riders should use standard damage types when possible. If a custom
type is needed (for example `hellfire`), document its rules in `notes` so automation can
interpret special handling.

`damage.one_handed` is the default/base damage slot used by current schemas, even for
weapons that are effectively two-handed-only. Add `properties: ["two_handed"]` to capture
that usage constraint, and use `damage.versatile` only when alternate two-hand damage exists.
