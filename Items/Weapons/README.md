# Weapons YAML Schema (Draft)

Use one YAML file per weapon.

```yaml
format_version: 1
id: "stable_weapon_id"
name: "Display Name"
type: "weapon"
category: "martial_melee"
proficient: true
attack_bonus: 0
range: "5"
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
