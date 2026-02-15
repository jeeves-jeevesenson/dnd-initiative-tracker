# Weapons YAML Schema (Draft)

Use either:
- one YAML file per weapon, or
- a catalog YAML with `weapons: []` entries.

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

Catalog example:

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

Shared property definitions can be stored in `properties_*.yaml` and referenced by id.

`type` values for damage/riders should use standard damage types when possible. If a custom
type is needed (for example `hellfire`), document its rules in `notes` so automation can
interpret special handling.

`damage.one_handed` is the default/base damage slot used by current schemas, even for
weapons that are effectively two-handed-only. Add `properties: ["two_handed"]` to capture
that usage constraint, and use `damage.versatile` only when alternate two-hand damage exists.
