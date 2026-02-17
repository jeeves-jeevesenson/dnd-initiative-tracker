# Items YAML Data

Item definitions are split by type to support structured automation:

- `Items/Weapons/` — weapon YAML files
- `Items/Armor/` — armor YAML files

## Preferred format (primary source of truth)

Use **one YAML file per item** where the filename is the item id (for example `longsword.yaml`).

- Weapon files live in `Items/Weapons/`
- Armor files live in `Items/Armor/`
- Each file should contain a single item object with an `id`

This per-item layout is what runtime item loading now expects first.

## Legacy format (optional)

Catalog files with `weapons: []` or `armors: []` are still supported for backward compatibility,
but they are optional and no longer required.

## Non-item definition files

Some YAML files are metadata, not items. For example:

- `properties_*.yaml` files that define shared weapon properties

These files are intentionally ignored by the item registry unless they contain actual item records.
