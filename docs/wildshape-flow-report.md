# Wild Shape flow report

## Scope
This report covers how Wild Shape is managed in LAN UI, saved to player YAML, and applied/reverted on active combatants.

## 1) Managing Wild Shape forms (player-facing flow)

1. **LAN client opens Wild Shape tools from resource pools**
   - The Wild Shape resource chip appears from `resources.pools` and opens the Wild Shape menu.
2. **Manage Wildshapes overlay**
   - Client reads:
     - `profile.wild_shape_available_forms` (all level-eligible forms, with `allowed` flags),
     - `profile.learned_wild_shapes` (known/prepared list),
     - `profile.wild_shape_known_limit` (cap).
   - Player can add/remove known forms in a draft list, then save.
3. **Save known forms action**
   - Client sends: `{"type":"wild_shape_set_known","cid":...,"known":[...]}`
   - Server validates:
     - claimed profile exists,
     - druid level is 2+,
     - each requested ID exists in available forms,
     - limit is enforced and duplicates removed.

## 2) Saving and persistence model

- **Input schema**
  - Player YAML supports `prepared_wild_shapes` (canonical) and still reads legacy `learned_wild_shapes`.
- **Normalization**
  - On profile load, Wild Shape IDs are trimmed/lowercased/deduped and capped by level-based known limit.
- **On save from LAN**
  - `wild_shape_set_known` writes both fields for compatibility:
    - `prepared_wild_shapes`
    - `learned_wild_shapes`
  - Player YAML cache is refreshed immediately after write.
- **What is *not* persisted**
  - Active combat overlay state (temporary transformed stats/name/actions/flags) is runtime-only on the combatant object.

## 3) Actually Wild Shaping (runtime apply/revert)

1. **Apply request**
   - Client sends: `{"type":"wild_shape_apply","cid":...,"beast_id":"..."}`
   - In combat, server requires an available bonus action before proceeding.
2. **Server-side apply checks**
   - Combatant exists and has a player profile.
   - Requested form is in the player’s currently known list and is level-legal.
   - Wild Shape resource pool has at least one use.
3. **Resource spend**
   - Server decrements `wild_shape` pool via `_set_wild_shape_pool_current(...)`, which also persists updated pool current to YAML.
4. **Transformation**
   - Server snapshots base combatant fields (`name`, movement speeds/mode, STR/DEX/CON, actions/bonus actions, temp HP, spellcaster flag).
   - Server applies beast form stats/actions and sets flags:
     - `is_wild_shaped = True`
     - `wild_shape_form_id` / `wild_shape_form_name`
     - runtime temp HP = druid level
   - Name becomes `"Base Name (Form Name)"`.
5. **Revert**
   - Client can send `wild_shape_revert`.
   - Server restores snapshot fields, clears wild shape runtime flags, and restores prior temp HP when applicable.

## 4) Related Wild Resurgence exchanges

- `wild_shape_regain_use`: spend lowest available spell slot to gain 1 Wild Shape use (once per turn while shaped).
- `wild_shape_regain_spell`: spend 1 Wild Shape use to recover one level 1 spell slot (once per long rest while shaped).
- These exchange counters are runtime flags on combatants and are reset during long rest handling.

## 5) LAN sync and visibility

- Snapshot payload exposes Wild Shape state to clients through unit fields:
  - `is_wild_shaped`
  - `wild_shape_form`
- Profile payload exposes management data:
  - `prepared_wild_shapes` / `learned_wild_shapes`
  - `wild_shape_known_limit`
  - `wild_shape_available_forms`
- Long rest clears active Wild Shape overlays on combatants and resets Wild Resurgence gating flags.
