# Summon automation assessment (spells + LAN initiative)

## Short assessment

**Moderate**.

- YAML parsing is permissive today, so adding `mechanics.summon` to spell files should not break loading.
- The heavier work is runtime behavior: creating combatants/tokens, initiative behavior (shared-vs-roll), and LAN multi-token control rules.

## Will `automation.summon` break parsing/validation today?

Likely **no parse break**, with one naming caveat:

1. Current spell loader reads YAML via `yaml.safe_load`, stores top-level `mechanics` as a dict, and only reads specific known subkeys (`automation`, `targeting`, `sequence`, `scaling`) for automation hints.
2. Unknown keys under `mechanics` are ignored by behavior code and still preserved in the in-memory `preset["mechanics"]` payload.
3. There is no strict spell JSON schema validation in runtime paths, and CI does not run spell-schema validation.

### Important caveat

The existing schema/docs use `mechanics.automation` as a string enum (`full|partial|manual`).
If you add a block at `automation.summon` **top-level** (outside `mechanics`), runtime code won’t use it. If your intent is spell automation metadata, place it at:

```yaml
mechanics:
  summon:
    ...
```

or add explicit loader support for top-level `automation.summon` aliasing.

## Minimal code change options

### Option A (smallest): support unknown automation keys without behavior change

No functional code change is strictly required for parsing support if data goes under `mechanics.summon`.

If you want explicit forward-compat clarity, add one safe passthrough field in spell preset normalization:

- In `TrackerApp._spell_presets_payload -> parse_spell_file`, include:
  - `preset["summon"] = mechanics.get("summon")` when it is a dict/list.

This keeps all existing behavior unchanged and gives UI/runtime a stable place to read summon config.

### Option B: support top-level `automation.summon` alias

Also in `parse_spell_file`, after loading `parsed`:

- Read `automation_block = parsed.get("automation") if isinstance(parsed.get("automation"), dict) else {}`
- If `mechanics.get("summon")` is missing and `automation_block.get("summon")` is dict/list, copy it into mechanics-derived summon payload.

This remains backward-compatible and still keeps current automation logic untouched.

## Best cast-time hook for summon behavior

Use LAN action handling in `TrackerApp._apply_lan_action` (same place that handles `cast_aoe`).

Recommended hook sequence:

1. Frontend includes spell identity in cast message (`spell_slug` or `spell_id`) when sending `type: "cast_aoe"`.
2. Server `cast_aoe` branch resolves selected spell preset by slug/id.
3. If preset has `mechanics.summon`, call new helper e.g. `_cast_spawn_summons(...)` that:
   - creates combatants from monster YAML ids,
   - places tokens,
   - sets initiative according to summon config,
   - sets control metadata (`summoned_by`, controller mode),
   - logs and broadcasts updated state.

This is minimal-risk because all cast validation/spend checks are already centralized there.

## Shared turn / child entries support status

Current initiative tracker has **no child-entry/grouped-turn data model**.

- Initiative order is flat list from sorted `combatants`.
- Turn order payload is list of cids only.
- Next-turn logic advances by index across the flat list.

Smallest safe enhancement for “summons under caster’s turn”:

1. Add optional combatant fields:
   - `initiative_anchor_cid: Optional[int]`
   - `initiative_mode: Optional[str]` (e.g., `"after_anchor"|"independent"`)
2. Update `_sorted_combatants` ordering key to place anchored summons immediately after anchor while preserving deterministic sort among siblings.
3. Keep `_next_turn` unchanged (still iterates flat ids). Grouping effect comes from sorted order only.

This avoids invasive “nested turns” logic and preserves compatibility with existing UI/state shape.

## LAN control permissions: where enforced + minimal multi-token change

Control enforcement is currently in server-side LAN action gating (`_apply_lan_action`):

- Client claim must match action `cid`.
- Non-admin actions are restricted to claimed token and turn.

Minimal change for summons controlled by caster:

1. Add optional ownership metadata on combatants (or side-map):
   - `summoned_by_cid`, `controller_mode`, `controller_cids`.
2. In `_apply_lan_action`, before rejecting `cid != claimed`, allow if:
   - `claimed` matches `summoned_by_cid` and controller mode allows caster control,
   - OR claimed is in explicit `controller_cids`.
3. Reuse existing AOE owner-override pattern as precedent for “owner can act out of strict token match” logic.

Keep turn gating policy configurable (strict per-token turn vs shared-turn for anchor group).

## Existing code/YAML patterns relevant to summoning

- Spell docs already mention `summon` as a standardized `mechanics.sequence[*].effect` type (concept exists in schema guidance).
- Current summon-family spell YAMLs are mostly `automation: partial` with empty `sequence`, so no runtime summon action exists yet.
- Map UI has **token grouping by same square** (visual grouping), but this is not initiative grouping.
- AOE logic includes owner metadata (`owner_cid`) and permission checks that are a good model for summon controller permissions.

## Recommended incremental implementation plan

1. **Data shape first**
   - Add `mechanics.summon` to target spell YAMLs (summon-*, create-undead, find-familiar).
   - (Optional) loader alias for top-level `automation.summon`.
2. **Non-behavioral plumbing**
   - Surface summon config in spell presets payload (`preset.summon`), no behavior yet.
3. **Runtime spawn MVP (DM/admin only)**
   - On cast, spawn units from monster ids and set `summoned_by_cid` metadata.
4. **Initiative MVP**
   - Implement `share|roll` with flat-order anchor placement (`after_anchor`) before nested/grouped-turn UI.
5. **LAN control MVP**
   - Extend permission gate to allow caster controlling owned summons.
6. **Lifecycle + despawn**
   - Track source spell + concentration linkage; auto-remove on concentration end/death/manual dismiss.
7. **UI polish**
   - Show summon ownership badge and optional grouped chip styling in turn order.
8. **Hardening**
   - Add unit tests for sorting and permission checks; add smoke flow for cast→spawn→control.
