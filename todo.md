# DnD Initiative Tracker — Agent Fix/Feature Backlog

This file converts the provided bug/feature list into an execution-ready backlog for coding agents.

## How to use this backlog (important for agents)
- Follow IDs in order unless dependencies explicitly allow parallel work.
- Treat each ID as a separate PR-sized change unless marked as part of an epic.
- Keep compatibility with existing LAN protocol/state snapshots (`dnd_initative_tracker.py` + `assets/web/lan/index.html`).
- Prefer adding optional fields over renaming/removing existing payload fields.

---

## 1) Prioritized implementation order (impact × ease × dependency)

### Phase A — High-impact bug fixes, low/medium effort (do first)
1. **B01** Mounting triggers false “it’s your turn” prompt/sound.
2. **B02** Initiative prompt modal incorrectly gated behind Cast Spell menu.
3. **B03** Tip dialog resets old message instead of persisting latest message.
4. **B04** Mount requests sent to non-player tokens; DM approval flow missing.
5. **B05** Player mounting logic broken for shared-tile mounting and rider movement rules.
6. **B06** Zoom-out has hard lower limit.
7. **B07** Non-modal popup behavior on DM Tkinter app (windows block each other).
8. **B08** DM initiative tracker columns/order cleanup.
9. **B09** Spell rotation support incomplete (“cannot rotate all spells”).
10. **B10** Wild Shape quality/regression cleanup.

### Phase B — UX improvements (medium impact, low/medium effort)
11. **U01** Make End Turn more obvious (topbar, stronger visual emphasis, smart highlight conditions).
12. **U02** Simplify movement mode switching for DM/players.
13. **U03** Remove unnecessary initiative top dropdown UI in LAN client.
14. **U04** Remove show/hide initiative button.
15. **U05** Add hotkey/button to fully hide/show bottom panel (default `Delete`).
16. **U06** Responsive compact mode for small screens.
17. **U07** Show HP bar on player screen with color thresholds.
18. **U08** Show condition duration/details in top initiative tracker chips.
19. **U09** Auto-center DM map to active ally/enemy turn + clear turn notice.

### Phase C — Summon/mount system expansion (larger feature work)
20. **F01** LAN custom cast: add summon preset creator (temp YAML in `Monsters/temp/`).
21. **F02** Summon preset import from existing monster YAML for autofill/edit.
22. **F03** DM-side “Assign Summon” flow for linking summon to player.
23. **F04** John Twilight custom Echo bonus-action summon + swap/teleport (15 ft range).

### Phase D — Combat automation overhaul epics (highest complexity)
24. **F05** Player weapon schema overhaul + presets in player YAML.
25. **F06** LAN attack mode using weapon config, hit-check vs hidden AC, damage logging.
26. **F07** Spell range overlay + LAN-side damage window flow integration.
27. **F08** Terrain DoT hazard preset system (enter/leave/start/end turn triggers + saves + conditions).
28. **F09** Simple monster auto-path suggestion toggle (DM confirm/revert behavior).
29. **F10** Token image overlays (player + monster profile images with proper crop/mask).
30. **F11** Custom condition icons (emoji replacement via image/icon assets).

### Phase E — Vague / needs design clarification (park at bottom)
31. **V01** “Wildshaping needs fixed it sucks” (broad quality pass beyond concrete bugs).

---

## 2) Detailed task cards

## Bug fixes

### B01 — Mounting triggers false turn prompt/sound
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_mounting.py`
- **Technical starting points:** `mountPromptModal`, `pendingMount*`, turn/active combatant UI/audio handlers.
- **Acceptance criteria:**
  - Mount action (request/approve/complete) does **not** trigger turn-start audio/“your turn” prompt unless turn actually changed to that player.
  - No regression in real turn-start notification.

### B02 — Initiative prompt should render independent of spell menu
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_lan_initiative_prompt.py`
- **Technical starting points:** `initiativePromptModal` and message type `initiative_prompt`.
- **Acceptance criteria:**
  - DM button triggers LAN initiative modal centered over map (same UX class as character chooser modal behavior).
  - Player can submit initiative without opening spell UI.

### B03 — Tip dialog should persist latest message
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Easy
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Technical starting points:** `#note` element updates + any reset timers/state refresh handlers.
- **Acceptance criteria:**
  - Last emitted tip/error remains visible until replaced by a newer message.
  - No automatic fallback reset to default hint text.

### B04 — Mount requests to non-player tokens should route to DM approval flow
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Medium
- **Dependencies:** B01 (notification correctness)
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_mounting.py`
- **Required behavior:**
  - If player attempts to mount NPC/non-player token:
    1) DM receives modal: `"<player> is trying to mount <creature>. Allow?" (Yes/No)`
    2) If **Yes**: mount succeeds.
    3) If **No**: second DM modal asks `Pass or Fail?` (saving throw outcome).
    4) Pass => mount succeeds; Fail => mount denied.
- **Acceptance criteria:**
  - No mount request popup to NPC clients.
  - DM mediation is always authoritative for this branch.

### B05 — Player mounting rules (shared tile + rider movement lock) are broken
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Medium/Hard
- **Dependencies:** B04
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_mounting.py`
- **Core rules to implement:**
  - If two creatures share tile, mount button appears (loosen mount target restrictions for this mode).
  - Rider spends 15 ft movement when mounting.
  - Mounted non-mount creatures keep separate turns.
  - Rider cannot move on rider turn while mounted unless unmounting.
  - When mount moves on its turn, rider position mirrors automatically.
- **Acceptance criteria:** explicit test coverage for mount/unmount/move sync + movement consumption.

### B06 — Remove zoom-out lower bound
- **Type:** Bug fix
- **Impact:** Medium
- **Ease:** Easy
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Acceptance criteria:** zoom-out no longer hard-stops at previous minimum; map remains stable (no NaN/negative/zero rendering failures).

### B07 — DM popup windows should not block all other app windows
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Technical starting points:** Tkinter `Toplevel`, `grab_set`, `wait_window`, modal/transient usage.
- **Acceptance criteria:** DM can interact with map, damage, info windows concurrently; no hidden modal grab lock.

### B08 — DM initiative tracker column layout/order fix
- **Type:** Bug fix
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Required column order:** `Name | Side | HP | Temp HP | AC | Walk | Swim | Fly | Conditions | Initiative`
- **Special rule:** replace nat-20 separate column with star marker beside initiative value.

### B09 — Ensure all spells can rotate
- **Type:** Bug fix
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - Spell handling in `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Acceptance criteria:** every placeable spell template honors rotation controls uniformly.

### B10 — Wild Shape concrete fixes/regressions
- **Type:** Bug fix
- **Impact:** Medium/High
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_wild_shape.py`
- **Scope note:** only concrete reproducible defects first; broad UX complaints belong in V01.

---

## UX-focused features/improvements

### U01 — End Turn button prominence + state-based emphasis
- **Type:** New feature (UX)
- **Impact:** High
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:**
  - move to top bar,
  - larger/bolder/red styling,
  - visually “pop” when action + bonus action + movement are exhausted.

### U02 — Simplify movement mode switching
- **Type:** New feature (UX)
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Goal:** fewer clicks and clearer current mode (walk/swim/fly/etc).

### U03 — Remove initiative top dropdown clutter
- **Type:** New feature (cleanup)
- **Impact:** Medium
- **Ease:** Easy
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Technical starting points:** `initiativeStyleSelect` + related topbar controls.

### U04 — Remove show/hide initiative button
- **Type:** New feature (cleanup)
- **Impact:** Low/Medium
- **Ease:** Easy
- **Dependencies:** U03
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Technical starting points:** `initiativeToggleBtn`, `toggleInitiativeBar`.

### U05 — Hotkey/button to hide entire bottom panel
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:**
  - configurable hotkey (default Delete),
  - one press hides full bottom tray,
  - second press restores.

### U06 — Small-screen compact mode
- **Type:** New feature
- **Impact:** High
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:** detect smaller viewports and auto-compact (smaller fonts, hide low-priority controls by default).

### U07 — Player HP bar with thresholds
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py` (if payload expansion needed)
- **Rules:** green >50%, yellow <=50%, red <=20%.

### U08 — Condition details in initiative chip/selection
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Target output example:** `Prone (2)`, `Blind (5)`.

### U09 — DM map auto-focus active ally/enemy turn
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Requirements:** on ally/enemy turn start, center map on unit and show clear turn-start notification.

---

## Summon/mount expansion features

### F01 — LAN custom summon preset creation (temp YAML pipeline)
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Dependencies:** none (foundation)
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/Monsters/temp/` (new files generated at runtime)
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_custom_summon_pipeline.py`
- **Requirements:**
  - Add `summon` in custom casting presets.
  - Custom form captures base stats/movement/hp/name.
  - Writes temp monster YAML to `Monsters/temp/` for later DM review/promotion.

### F02 — Import existing monster YAML to prefill summon form
- **Type:** New feature
- **Impact:** High
- **Ease:** Medium
- **Dependencies:** F01
- **Likely files:** same as F01.

### F03 — DM-side assign summon to player flow
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Dependencies:** F01, F02
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:** “Assign Summon” button in DM initiative tracker, player picker, summon editor/import.

### F04 — John Twilight “Johns Echo” bonus action summon + swap teleport
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium/Hard
- **Dependencies:** existing echo/summon action support in tracker
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_echo_knight.py`
  - possibly `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/players/*.yaml` for ability wiring
- **Rules:**
  - summon name `Johns Echo`, light blue token,
  - HP 1, DEX 0, other stats 0, speed 35,
  - bonus action summon by John Twilight only,
  - swap positions with John Twilight within 15 ft.

---

## Combat automation epics

### F05 — Player YAML weapons schema + preset model
- **Type:** New feature (major)
- **Impact:** Very High
- **Ease:** Hard
- **Dependencies:** design RFC first
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/players/README.md`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/new_character/schema.json`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/new_character/app.js`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/edit_character/app.js`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Must include:** one/two-handed mode, proficiency, to-hit, damage formula + type, conditions/saves/effects, feat/race/class interactions.

### F06 — LAN attack workflow using configured weapons + hidden AC validation
- **Type:** New feature (major)
- **Impact:** Very High
- **Ease:** Hard
- **Dependencies:** F05
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Rules:**
  - player selects target + weapon + attack count,
  - server checks hit/miss vs target AC (AC hidden from player),
  - miss logged in battle log (`attacker missed target`),
  - player enters damage rolled, damage type resolved from weapon config.

### F07 — Spell range overlay + LAN player damage prompt integration
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Dependencies:** partial overlap with F06 (shared attack/damage UI)
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`

### F08 — Terrain hazard preset system (DoT + triggers + saves + conditions)
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/presets/`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Requirements:** trigger toggles (enter/leave/start/end), damage roll config, save type/DC, on-fail conditions.

### F09 — Monster auto-path suggestion toggle
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Behavior:** when monster turn starts and toggle on, compute nearest ally/summon/player and queue suggested destination using move+dash budget; DM approve/reject (reject reverts start position).

### F10 — Token image overlays for players/monsters
- **Type:** New feature
- **Impact:** Medium/High
- **Ease:** Hard
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - schema/docs for `assets/pfps/players` + `assets/pfps/monsters`
- **Requirements:** PNG/JPG, auto scale/crop/mask to token shape/size.

### F11 — Custom condition icons
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium/Hard
- **Dependencies:** may share asset-loader infra with F10
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - condition rendering pipeline in tracker server/client state.

---

## Vague / clarify-first bucket

### V01 — Broad Wild Shape quality pass
- **Type:** Undefined (bug(s) + UX)
- **Impact:** Unknown (likely high)
- **Ease:** Unknown
- **Why parked:** issue statement is broad; needs concrete repro list first.
- **Suggested clarification template:**
  - exact action sequence,
  - expected vs actual,
  - whether DM-side, LAN-side, or both,
  - relevant player YAML/spell/preset used.

---

## 3) Dependency map (quick reference)
- **Mounting chain:** B01 → B04 → B05
- **Initiative topbar cleanup chain:** U03 → U04
- **Summon workflow chain:** F01 → F02 → F03
- **Weapon/combat automation chain:** F05 → F06; F07 can partially parallelize but should share F06 primitives
- **Asset icon/image chain:** F10 ↔ F11 (shared infra advisable)

---

## 4) Suggested execution slices for future agents
- **Slice 1 (stability):** B01+B02+B03 with targeted tests (`test_mounting.py`, `test_lan_initiative_prompt.py`).
- **Slice 2 (mount rules):** B04+B05 with mount behavior tests expanded.
- **Slice 3 (UI cleanup):** U01+U03+U04+U05+U06.
- **Slice 4 (summons):** F01+F02 then F03.
- **Slice 5 (combat overhaul):** F05 design/spec PR, then F06/F07 implementation PRs.

