# Players YAML Audit + Implementation TODO

Scope: audit current `players/*.yaml` files, identify what is already wired into tracker automation, and define per-player follow-up work to implement unsupported feature logic.

## Current engine support (already automated)

These are the parts already handled by current codepaths in `dnd_initative_tracker.py` and LAN flows:

- Player YAML loading + normalization (`format_version`, core sections, spellcasting lists/slots, attacks.weapons normalization).
- `resources.pools[]` normalization including formula evaluation (`max_formula`) for known variables (level/prof/modifiers plus fighter/druid class levels).
- Action economy spend entries via `actions[]`, `bonus_actions[]`, `reactions[]` with `uses.pool` + `uses.cost`.
- `attacks.weapons[]` data consumed by LAN attack flow.
- Wild Shape lifecycle support (`prepared_wild_shapes`, wild-shape known forms, apply/revert/regain actions).
- Startup summons (`summon_on_start` and aliases) auto-spawn support.
- Aura support for feature payloads that use `features[].grants.aura`.
- Pool-granted spell support for `features[].grants.spells.casts[]` (no current player file uses this shape yet).

## Current engine gaps (not automated yet)

These YAML patterns appear in player files but are not generally executed by the engine today:

- Most `features[].automation` blocks (custom trigger/effect DSL currently treated as data only).
- Most `features[].grants.*` blocks beyond `grants.aura` and `grants.spells.casts`.
- Feature selection gates (`selection`, `enabled_if`, subclass choice routing).
- Conditional/rider systems in feature YAML (`damage_riders`, `modifiers`, `contested_check`, `once_per_turn`, custom status transitions).
- Automatic conversion from feature-granted actions/reactions into executable combat actions.

---

## Per-player audit and TODO (sorted by player file)

### 1) `John_Twilight.yaml` (John Twilight)

**Already automated/useful now**
- `attacks.weapons[hellfire_battleaxe_plus_2]` is normalized and usable by LAN attack requests.
- Resource pools (`action_surge`, `second_wind`, `unleash_incarnation`, `indomitable`, `shadow_martyr`) can be spent by `uses.pool` action/reaction entries.
- Action/reaction/bonus-action entries are visible and spend-capable.

**Not automated yet (high-value)**
- Echo state machine from feature text (`Manifest Echo`, tether distance checks, dismiss/replace lifecycle).
- Echo-origin attack routing and opportunity attack logic from YAML declarations.
- Tactical Mind refund-on-fail behavior and Tactical Shift movement rider.
- Hellfire stack rider automation and turn-tick damage from weapon text (currently descriptive/manual unless separately scripted).

**Cleanup/audit notes**
- Keep current structure; no schema-breaking cleanup needed.
- Ensure future implementation maps existing `notes.echo_state_template` keys to runtime state fields (avoid duplicate state schemas).

**Implementation plan**
1. Add an explicit echo runtime schema (active cid/position/range owner link) and bind it to existing echo LAN actions.
2. Add per-turn limiter for Hellfire stack application + start/end turn rider processing.
3. Wire Tactical Mind/Tactical Shift as optional prompts tied to Second Wind and failed checks.

---

### 2) `dorian_vandergraff.yaml` (Dorian)

**Already automated/useful now**
- `features[].grants.aura` for Aura of Protection matches supported aura parser shape.
- Core action list + spellcasting + slot tracking works.

**Not automated yet**
- No additional advanced feature automation in file.

**Cleanup/audit notes**
- Verify aura remains present in authoritative profile payload used during combatant aura evaluation.
- Optional consistency cleanup later: unify null vs empty-string style for identity fields across player files.

**Implementation plan**
1. Add/extend regression test for this exact aura payload shape from player YAML -> LAN state.
2. Validate save bonus floor (`minimum: 1`) and resistances application against both PCs and allied summons.

---

### 3) `eldramar_thunderclopper.yaml` (Eldramar)

**Already automated/useful now**
- `summon-on-start: owl.yaml` uses supported alias + shorthand path and should auto-spawn.
- Arcane Recovery pool exists and can be spent by `actions[].uses.pool`.
- Spell prep/slots are fully consumed by current spellcasting payload.

**Not automated yet**
- `features[].automation.recover_spell_slots` behavior is not auto-executed from feature DSL.
- Arcane Recovery currently remains mostly manual bookkeeping despite pool spend support.

**Cleanup/audit notes**
- Optional data quality pass: cantrip list includes non-cantrip slugs (`lightning-bolt`) and duplicates in known/prepared context; not blocking loader, but should be cleaned for rules correctness.

**Implementation plan**
1. Introduce generic “recover spell slots” action effect engine reusable by Arcane Recovery/Natural Recovery-like features.
2. Map feature action metadata to the existing action execution pipeline with explicit validation and user feedback.

---

### 4) `fred_figglehorn.yaml` (Fred)

**Already automated/useful now**
- Core action/reaction/bonus-action handling works.
- Spellcasting/prepared list/slot state works.

**Not automated yet**
- No feature automation is currently defined in this file.

**Cleanup/audit notes**
- Prepared spell list includes off-class/likely test/homebrew entries; acceptable for now but should be flagged for character-sheet correctness review if gameplay parity is required.

**Implementation plan**
1. No engine work required specific to this file right now.
2. Revisit only if custom Warlock feature DSL entries are added later.

---

### 5) `johnny_morris.yaml` (Johnny)

**Already automated/useful now**
- `prepared_wild_shapes` is supported and integrated with wild shape known-form limits.
- Wild Shape pool/resource operations and apply/revert/regain LAN actions exist.
- Spellcasting payload and standard action economy entries work.

**Not automated yet (major backlog)**
- Most PHB2024 feature blocks in `features[].grants` are data-only today:
  - `always_prepared_spells`
  - `actions` with `effect` semantics (Wild Companion, Land’s Aid, Wild Resurgence, Natural Recovery)
  - `modifiers`, `damage_riders`, `selection`, `enabled_if`, `resistance_by_land`
  - dynamic land-type spell switching and subclass gating logic

**Cleanup/audit notes**
- YAML structure is rich and internally consistent; avoid churn until engine support lands.
- Keep `prepared_wild_shapes` as source of truth (legacy `learned_wild_shapes` should remain compatibility-only).

**Implementation plan**
1. Build feature-granted action ingestion (`grants.actions[]` -> normalized executable actions).
2. Implement shared effect handlers: cast-without-slot, recover-slots, consume one-of (slot/pool), conditional damage/heal formulas.
3. Add feature-selection state persistence (`selection`, land type) and use it in dynamic spell grants/resistances.
4. Add targeted tests for wild-shape + circle feature interactions.

---

### 6) `malagrou.yaml` (Malagrou)

**Already automated/useful now**
- Resource pools and manual spend actions work (`rage` via bonus action entry).
- Core profile loading and action economy work.

**Not automated yet (major backlog)**
- Extensive Barbarian feature DSL under `features[].automation` is currently non-executable.
- Complex trigger/rider logic unimplemented: rage maintenance, reckless toggles, once-per-turn riders, retaliation trigger, movement riders, condition immunity while raging, etc.

**Cleanup/audit notes**
- Data includes both `reset` and `reset_all` patterns; confirm intended semantics before implementing reset engine extensions.
- Preserve formulas exactly; they are likely intentional and should be parsed rather than rewritten.

**Implementation plan**
1. Add phased feature-trigger engine for common trigger points (attack roll, hit, damage taken, turn boundaries).
2. Implement Rage lifecycle first (highest gameplay impact, prerequisite for many downstream features).
3. Layer Reckless Attack + Brutal Strike + Frenzy + Retaliation with deterministic ordering and tests.

---

### 7) `oldahhman.yaml` (Old Man)

**Already automated/useful now**
- Core stats/actions load successfully.

**Not automated yet**
- No feature automation currently present.

**Cleanup/audit notes (high priority data cleanup)**
- `leveling.level` is 10 but Monk class `level` is 0 (inconsistent).
- `vitals.speed` uses non-standard keys (`Normal/Climb/Fly/Swim`) unlike most files (`walk/climb/fly/swim`).
- Notes field contains malformed-looking escaped text; loads as string but should be cleaned for maintainability.

**Implementation plan**
1. ✅ Completed (2026-02-17): performed data-correction pass for class levels/speed keys/notes hygiene (no engine change required).
2. Add a lightweight player YAML validation command/check for class-level sum and speed key normalization.

---

### 8) `throat_goat.yaml` (Throat Goat)

**Already automated/useful now**
- Weapon definition (`sword_of_wounding`) is consumable by current attack flow.
- Resource pools + `uses.pool` on bonus/actions are spend-capable.
- Spellcasting payload works.

**Not automated yet**
- Most class/subclass effects in descriptions are manual only (Countercharm behavior, Mantle/Beguiling side effects, wound stacking).
- No feature DSL entries currently provided for engine execution.

**Cleanup/audit notes**
- Data is structurally valid; no required cleanup.

**Implementation plan**
1. If desired, migrate key subclass mechanics from free-text action descriptions into structured feature/grant DSL after engine support exists.
2. Add optional wound-stack standardized rider format reusable with John’s Hellfire stacks.

---

### 9) `vicnor.yaml` (Vicnor)

**Already automated/useful now**
- `attacks.weapons[]` entries are in supported schema and usable by LAN attack flow.
- Resource pools (`sneak_attack_dice`, `steady_aim`) exist and can be manually consumed by actions if wired.
- Core spellcasting and action handling works.

**Not automated yet (major backlog)**
- Rogue/Swashbuckler feature DSL in `features[].automation` is currently data-only.
- Not implemented: Sneak Attack trigger checks, Cunning Strike options, Uncanny Dodge reactive mitigation, Evasion conditionals, Panache contested checks, etc.

**Cleanup/audit notes**
- `defenses.ac.sources[0].id/label` are `null`; acceptable to loader but should be normalized to stable IDs for maintainability.
- Typo in language value (`Theives Cant`) should be normalized in data cleanup pass.

**Implementation plan**
1. Build reusable contested-check and attack-trigger framework (needed for Panache/Sneak Attack/Cunning Strike).
2. Add reaction middleware for damage interception (Uncanny Dodge) and save-result post-processing (Evasion).
3. Add per-turn/once-per-turn spending guardrails for sneak attack and strike options.
4. ✅ Completed (2026-02-17): cleaned data quality issues called out in audit (`defenses.ac.sources[0].id/label`, `Theives Cant` typo).

---

### 10) `стихия.yaml` (стихия)

**Already automated/useful now**
- Weapon definition and pool-backed actions/reactions are structurally compatible.
- Cleric spellcasting config and slots are supported.

**Not automated yet (major backlog)**
- Most `features[].grants` content is not executable except potential aura-like patterns (none used here).
- Not implemented from DSL: channel-divinity action effects, damage maximization modifier, subclass-triggered push/rider logic, etc.

**Cleanup/audit notes**
- Save proficiency uses `CHR` instead of `CHA`; normalize for consistency with common abbreviations.
- Keep unicode filename/name support; this file verifies non-ASCII handling and should remain in test coverage.

**Implementation plan**
1. Implement generic feature-granted actions/reactions ingestion (for Divine Spark/Turn Undead/Wrath of the Storm).
2. Add damage pipeline hooks for modifier-style effects (Destructive Wrath maximize).
3. Add subtype-aware trigger hooks (lightning/thunder damage conditions for Tempest features).
4. ✅ Completed (2026-02-17): normalized save proficiency abbreviation from `CHR` to `CHA`.

---

## Cross-player implementation roadmap (recommended order)

1. **Schema execution foundation**
   - Add explicit parser/normalizer for `features[].grants.actions|reactions|modifiers|damage_riders`.
   - Keep backward compatibility by treating unknown keys as passive metadata.

2. **Reusable effect handlers**
   - Pool/slot consumption, recover slots, temporary condition application, movement riders, contested checks, per-turn limits.

3. **Class slices with highest value/risk**
   - Druid (Johnny), Barbarian (Malagrou), Rogue (Vicnor), Cleric (стихия), then Fighter Echo (John).

4. **Data quality guardrails**
   - Add validator for player YAML consistency (class level sums, proficiency abbreviations, speed keys, null IDs where IDs are expected).
   - ✅ Completed (2026-02-17): added focused regression checks in `tests/test_player_yaml_validity.py` covering class-level sum/speed schema (`oldahhman.yaml`), proficiency abbreviation (`стихия.yaml`), and null AC source IDs/language typo cleanup (`vicnor.yaml`).

5. **Regression coverage**
   - Add focused tests per implemented feature family before enabling automatic execution globally.
