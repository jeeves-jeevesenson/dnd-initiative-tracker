# Armor YAML Schema (Draft)

## Primary format: one file per armor item

Use one YAML file per armor item in this directory. The filename should match the id:

- `chain_mail.yaml` → `id: chain_mail`

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

## Legacy catalog format (optional)

Catalog YAMLs with `armors: []` are still supported for compatibility, but per-item files are preferred.

## How to add a new armor item

1. Create `Items/Armor/<armor_id>.yaml`.
2. Set `id: <armor_id>` in the file.
3. Add armor fields (`name`, `category`, `ac`, etc.).
4. Restart/refresh the app so the registry cache sees the new file.
