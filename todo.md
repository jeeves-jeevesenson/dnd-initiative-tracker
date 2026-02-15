# DnD Initiative Tracker — Agent Planning Backlog

This file is the **working planning board for agents**.

Use it to:
- pick the next task,
- record what was finished,
- record what was attempted but not finished,
- note new findings so the next agent can continue without rediscovery.

---

## 1) Agent update protocol (required)

When an agent touches any backlog item, update that item with:
- **Status:** `Not started` | `In progress` | `Blocked` | `Completed`
- **Last update:** `YYYY-MM-DD` + short context
- **What changed:** concise bullet list of code/test/docs changed
- **What remains:** concise bullet list
- **Handoff notes:** known risks, edge cases, and exact next command/step

Use this template inside the item you worked on:

```md
- **Status:** In progress
- **Last update:** 2026-02-15 (agent-name)
- **What changed:**
  - ...
- **What remains:**
  - ...
- **Handoff notes:**
  - ...
```

If you complete an item, move its ID into **Section 5 (Completed archive)** and leave a one-line implementation note.

---

## 2) Active priority order (complex work first)

> Prioritized for depth/complexity and dependency risk.

1. **F05** — Player weapon schema overhaul + preset model (foundation)
2. **F06** — LAN attack workflow using configured weapons + hidden AC validation
3. **F07** — Spell range overlay + LAN damage prompt integration
7. **F08** — Terrain hazard preset system (DoT + triggers + saves + conditions)
8. **F09** — Monster auto-path suggestion toggle (DM approve/reject)
9. **F10** — Token image overlays for players/monsters
10. **F11** — Custom condition icons
11. **V01** — Broad Wild Shape quality pass (clarify-first bucket)

---

## 3) Deep-dive execution cards (large tasks)

### F05 — Player weapon schema overhaul + preset model
- **Status:** In progress
- **Last update:** 2026-02-15 (copilot-agent, resumed; next implementation step queued)
- **What changed:**
  - Added additive `attacks.weapons[]` schema in `assets/web/new_character/schema.json` with per-weapon proficiency, to-hit, one/two-handed damage mode metadata, and optional effect metadata.
  - Added schema route coverage in `tests/test_edit_character_routes.py` to assert the new `attacks.weapons` model is exposed by `/api/characters/schema`.
  - Added `### Attacks Section` documentation in `players/README.md` describing legacy fields plus the new optional weapon preset model.
- **What remains:**
  - Confirm/create-edit web UX behavior for new nested weapon fields stays intuitive (round-trip through both editors).
  - Add/extend server-side normalization tests for backwards compatibility with missing/partial weapon presets.
  - Implement follow-on LAN attack flow work in F06 after F05 model is fully stabilized.
- **Handoff notes:**
  - Baseline check passed on current branch with `python -m compileall .` before touching this backlog item.
  - Next concrete implementation step: wire `attacks.weapons[]` create/edit form rendering + persistence parity in `assets/web/new_character/app.js` and `assets/web/edit_character/app.js`, then add focused route/normalization tests.
  - Run `PYTHONPATH=. pytest -q tests/test_edit_character_routes.py` and `python -m compileall .` after any follow-up schema edits.
  - Preserve additive compatibility: keep legacy `attacks.melee_attack_mod`, `attacks.ranged_attack_mod`, and `attacks.weapon_to_hit` unchanged while expanding `attacks.weapons`.
- **Impact / Complexity:** Very High / Hard
- **Dependencies:** none (but F06/F07 depend on this)
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/players/README.md`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/new_character/schema.json`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/new_character/app.js`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/edit_character/app.js`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_edit_character_routes.py`
- **Scope:**
  - Add additive weapons schema for player YAML (no breaking rename/removal of existing fields).
  - Support one/two-handed modes, proficiency, to-hit, damage formula/type, and optional effect metadata.
  - Persist cleanly through new/edit character web tools.
- **Out of scope for first PR:**
  - full LAN attack execution logic (belongs to F06/F07),
  - automatic migration of all existing player YAML files.
- **Implementation plan:**
  1. Define schema draft + defaults in `schema.json` (additive only).
  2. Update create/edit web forms to round-trip the new structure.
  3. Update server loader/normalizer to tolerate missing fields and preserve backwards compatibility.
  4. Add/extend tests around parsing and route persistence.
- **Risk notes:**
  - Highest risk is breaking existing player YAML loading; guard with optional fields and defaults.
  - Avoid changing canonical player YAML order except where schema docs require additions.
- **Validation plan:**
  - `python -m compileall .`
  - targeted: `pytest tests/test_edit_character_routes.py`

### F06 — LAN attack workflow using configured weapons + hidden AC validation
- **Status:** Not started
- **Impact / Complexity:** Very High / Hard
- **Dependencies:** F05
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_lan_claimable.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_planning_auth.py`
- **Scope:**
  - Add LAN action flow: pick target + weapon + attack count.
  - Server resolves hit/miss against hidden AC and emits result-safe payloads.
  - Player enters rolled damage; server applies typed damage and logs result.
- **Out of scope for first PR:**
  - advanced reactions/opportunity attacks,
  - full automation of multi-target spell damage (F07 overlap).
- **Implementation plan:**
  1. Define additive LAN message contract (`attack_request`, `attack_result`, `damage_apply`).
  2. Implement server-side validation and AC check (never expose raw AC to LAN client).
  3. Add LAN UI controls and error states.
  4. Add regression tests for authorization and hidden-AC behavior.
- **Risk notes:**
  - Authorization boundaries are critical; only claimed actor can attack.
  - Battle-log wording should remain stable and avoid leaking hidden stats.
- **Validation plan:**
  - `python -m compileall .`
  - targeted LAN/auth tests relevant to touched paths

### F07 — Spell range overlay + LAN damage prompt integration
- **Status:** Not started
- **Impact / Complexity:** High / Hard
- **Dependencies:** Partial overlap with F06 (reuse targeting/damage primitives)
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_spell_rotation_parity.py`
- **Scope:**
  - Show spell range/radius overlays during targeting.
  - Connect range-confirm flow to a player-facing damage prompt path.
- **Plan:**
  1. Reuse existing AoE overlay math/render primitives.
  2. Add spell-range metadata pass-through where missing.
  3. Wire prompt lifecycle to a server-authoritative damage apply action.
- **Risk notes:**
  - Do not regress existing AoE placement/rotation behavior.
  - Keep payload additive for older clients.
- **Validation plan:**
  - `python -m compileall .`
  - targeted spell/aoe regression tests

### F08 — Terrain hazard preset system (DoT + triggers + saves + conditions)
- **Status:** Not started
- **Impact / Complexity:** High / Hard
- **Dependencies:** none
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/presets/`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_temp_move_bonus.py`
- **Scope:**
  - Preset schema for hazard triggers (enter/leave/start/end),
  - damage + save config,
  - fail/pass effect application hooks.
- **Plan:**
  1. Define additive hazard schema (no global preset reformatting).
  2. Implement trigger evaluation hooks at movement + turn boundaries.
  3. Add deterministic logging and tests for trigger timing.
- **Risk notes:**
  - Trigger timing bugs can cause repeated damage applications; idempotence checks required.

### F09 — Monster auto-path suggestion toggle (DM confirm/reject)
- **Status:** Not started
- **Impact / Complexity:** High / Hard
- **Dependencies:** none
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Scope:**
  - Optional suggestion engine at monster turn start,
  - non-destructive preview + DM approve/reject + revert.
- **Plan:**
  1. Calculate candidate endpoint from movement/dash budget.
  2. Stage suggestion without mutating final combat position.
  3. Apply or discard on DM decision.
- **Risk notes:**
  - Never auto-commit movement without explicit DM approval.

### F10 — Token image overlays for players/monsters
- **Status:** Not started
- **Impact / Complexity:** Medium-High / Hard
- **Dependencies:** recommended to coordinate with F11
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - asset docs for profile image directories
- **Scope:**
  - Optional token image metadata and rendering support,
  - crop/mask/scale fallback to current color token style.
- **Plan:**
  1. Define additive payload field for optional image reference.
  2. Add client image loader/cache with robust fallback.
  3. Add DM-side selector/mapping flow if required.
- **Risk notes:**
  - Keep map performance stable; image loading must not freeze turn updates.

### F11 — Custom condition icons
- **Status:** Not started
- **Impact / Complexity:** Medium / Medium-Hard
- **Dependencies:** may share infra with F10
- **Primary files likely touched:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - condition rendering/state paths server+client
- **Scope:**
  - Optional icon mapping for conditions,
  - deterministic fallback to current text/emoji output.
- **Plan:**
  1. Introduce icon key/lookup model.
  2. Render icon when available; fallback otherwise.
  3. Add focused rendering regression checks.

### V01 — Broad Wild Shape quality pass (clarify-first)
- **Status:** Blocked (needs concrete repro list)
- **Impact / Complexity:** Unknown
- **Blocker details:**
  - issue wording is broad and not directly implementable without reproducible defects.
- **Required triage output before coding:**
  1. exact action sequence,
  2. expected vs actual,
  3. DM-side vs LAN-side location,
  4. sample player YAML/spell/preset.
- **Likely files after triage:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_wild_shape.py`

---

## 4) Dependency map (quick reference)
- **Weapons/combat chain:** F05 → F06; F07 should reuse F06 primitives where possible.
- **Summon chain:** F01 → F02 → F03.
- **Asset rendering chain:** F10 ↔ F11 (shared loader/fallback strategy recommended).
- **Clarification gate:** V01 should be split into concrete bug cards before implementation.

---

## 5) Completed archive (condensed)

Completed as of 2026-02-15:
- **Bug fixes:** B01, B02, B03, B04, B05, B06, B07, B08, B09, B10, B11, B12, B13, B14.
- **UX:** U01, U02, U03, U04, U05, U06, U07, U08, U09.

Implementation notes and earlier investigation context were trimmed from this planning file to keep active work discoverable.
If details are needed for a completed item, use git history for `todo.md` and the associated test files.
