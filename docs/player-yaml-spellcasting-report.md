# Player YAML spellcasting pipeline audit

## Scope
This report traces how `players/*.yaml` is loaded, normalized, sent to the LAN client, and used to gate spellcasting + render spell slots.

## End-to-end flow

1. **YAML discovery + parse**
   - `players/*.yaml` and `players/*.yml` files are scanned.
   - Files disabled in the YAML players index are skipped.
   - Each file is parsed with `yaml.safe_load`; parse failure stores `None` and silently drops profile data for that file.
2. **Normalization**
   - Parsed payload goes through `_normalize_player_profile`.
   - Top-level `actions`/`bonus_actions` are copied into `resources` for both legacy and v2 formats.
   - `spellcasting.spell_slots` is normalized to levels 1..9. Missing slots become `0/0` for every level.
   - `known_enabled` defaults from presence of `known_spells` object.
3. **Combatant creation**
   - `_create_pc_from_profile` builds the combatant from normalized profile.
   - `is_spellcaster` is set to `bool(spellcasting)` (true whenever spellcasting dict exists).
   - Actions used for spellcasting checks come from normalized `resources.actions`.
4. **Snapshot broadcast to web client**
   - LAN snapshot includes `units`, `player_spells`, and `player_profiles`.
5. **Web client lookup + render**
   - Client resolves the claimed unit name and does exact key lookup in `state.player_profiles[name]`.
   - Spell slot monitor only renders levels where `max > 0`; if all are zero, UI appears empty.
6. **Cast gating (client + server)**
   - Client and server both require a spell action name (`magic`, `cast a spell`, `cast spell`, `spellcasting`) in action lists.
   - Slot spend checks look up profile by current combatant name and decrement `spell_slots[level].current`.

## Key gating rules that matter for your symptom

- **Spell slots shown only when max > 0**
  - If YAML has no `spell_slots`, backend normalizes all levels to `max: 0`; slot monitor shows nothing.
- **Casting requires a matching spell action name**
  - If action list misses one of the accepted names, casting is blocked with “No spellcasting action available”.
- **Profile lookup is exact by combatant name in browser**
  - If combatant name differs from YAML profile key (e.g., duplicate got renamed to `Name 2`), profile lookup fails and slots/spellbook data won’t bind.
- **`spellcasting.enabled` is currently not used as a gate**
  - This flag is present in YAML but not consulted in cast/slot logic; practical gating is actions + slot data + name match.

## Why `стихия.yaml` works while some “similar” YAMLs may not

- `стихия.yaml` has explicit non-zero `spell_slots`, so monitor has levels to render.
- Several other YAMLs either omit `spell_slots` entirely or have no non-zero slot max values; they normalize to empty-looking slot UI.
- Some files set `spellcasting.enabled: false`, which is visually similar schema-wise but currently ignored by code (can confuse expectations).

## Concrete likely failure modes to verify in your environment

1. **Missing/non-positive slots**: YAML lacks `spell_slots` or all `max` values are 0.
2. **Name mismatch**: claimed unit name does not exactly match `player_profiles` key (common after duplicate-name auto-suffixing).
3. **Action mismatch**: spell action list doesn’t include one of the accepted spell-action names.
4. **Disabled profile file**: file marked disabled in YAML players index and never loaded.
5. **Parse failure**: malformed YAML silently omitted from profile map.

## Suggested hardening (future code changes)

- Add exact-match fallback in client `getPlayerProfile` (case-insensitive map walk).
- Prefer CID-indexed profile binding over name string matching.
- Respect `spellcasting.enabled` consistently (or remove from schema/UI to avoid ambiguity).
- Emit warning logs when a YAML parse fails or when claimed unit has no matching profile.
- Surface a “no slots configured” hint in UI when all slot levels are zero.
