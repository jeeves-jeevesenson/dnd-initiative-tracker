# Consumables YAML Schema (Draft)

## Primary format: one file per consumable

Use one YAML file per consumable in this directory. The filename should match the id:

- `healing_potion.yaml` → `id: healing_potion`

```yaml
format_version: 1
id: healing_potion
name: Healing Potion
type: consumable
consumable_type: potion
subtype: healing
description: Restores hit points when consumed.
effect_hint: Heal 2d4 + 2 HP.
```

## Purpose

Files in `Items/Consumables/` define catalog items that can be offered by future shop/inventory flows.
These are item definitions, not player-owned inventory instances.

Potion-style consumables may remain simple descriptive entries (for example with `description` and `effect_hint`).
Spell scrolls should also be consumable item definitions, but they should reference spells by slug via
`grants.spells.casts[].spell` and point to an existing `Spells/<slug>.yaml` definition.
Spell YAML is the source of truth for spell automation behavior.

## How to add a new consumable

1. Create `Items/Consumables/<consumable_id>.yaml`.
2. Set `id: <consumable_id>` in the file.
3. Add core fields (`name`, `type`, and `consumable_type` or `category`).
4. Add optional fields (`subtype`, `description`, `effect_hint`) as needed.
