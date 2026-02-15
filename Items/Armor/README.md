# Armor YAML Schema (Draft)

Use either:
- one YAML file per armor item, or
- a catalog YAML with `armors: []` entries.

```yaml
format_version: 1
id: "stable_armor_id"
name: "Display Name"
type: "armor"
category: "heavy"
ac:
  base_formula: "18"
  dex_cap: 0
properties:
  stealth_disadvantage: true
```
