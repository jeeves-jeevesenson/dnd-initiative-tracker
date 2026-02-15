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
1. **B01** ✅ Mounting triggers false “it’s your turn” prompt/sound.
2. **B02** ✅ Initiative prompt modal incorrectly gated behind Cast Spell menu.
3. **B03** ✅ Tip dialog resets old message instead of persisting latest message.
4. **B04** ✅ Mount requests sent to non-player tokens; DM approval flow missing.
5. **B05** ✅ Player mounting logic broken for shared-tile mounting and rider movement rules.
6. **B06** ✅ Zoom-out has hard lower limit.
7. **B07** ✅ Non-modal popup behavior on DM Tkinter app (windows block each other).
8. **B08** ✅ DM initiative tracker columns/order cleanup.
9. **B09** ✅ Spell rotation support incomplete (“cannot rotate all spells”).
10. **B10** Wild Shape quality/regression cleanup.
11. **B11** ✅ Add are you sure warning on dismiss summons. are you sure you want to dismiss (list summons) 
11. **B12** Add are you sure warning on dismiss summons. are you sure you want to dismiss (list summons)
12. **B13** In the heal window on the DM tinkter tracker, add a toggle for if the value is temporary health. Any temp health given to a player overrides the previous temp health. If Gary has 4 temp hp and i open the dialague and Target Gary heals Gary for 8 temp hp, it would just be 8 temp hp. the 4 would be overwritten.
13. **B14** Remove emojis from battle logging

### Phase B — UX improvements (medium impact, low/medium effort)
11. **U01** ✅ Make End Turn more obvious (topbar, stronger visual emphasis, smart highlight conditions).
12. **U02** ✅ Simplify movement mode switching for DM/players.
13. **U03** ✅ Remove unnecessary initiative top dropdown UI in LAN client.
14. **U04** ✅ Remove show/hide initiative button.
15. **U05** ✅ Add hotkey/button to fully hide/show bottom panel (default `Delete`).
16. **U06** ✅ Responsive compact mode for small screens.
17. **U07** ✅ Show HP bar on player screen with color thresholds.
18. **U08** ✅ Show condition duration/details in top initiative tracker chips.
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
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** `maybeShowTurnAlert()` now only triggers when `active_cid` or `round_num` actually changed, preventing mount-related full-state refreshes from retriggering alerts.
- **Investigation context (2026-02-15):**
  - LAN client calls `maybeShowTurnAlert()` on full `"state"` messages and on `"turn_update"` messages (`assets/web/lan/index.html`).
  - Mount completion currently calls `_lan_force_state_broadcast()` in `_accept_mount(...)`, which always emits a fresh `"state"` message (`dnd_initative_tracker.py`).
  - High-confidence repro path to validate first: mount request/approval while rider is already active should not retrigger `showTurnModal()`.

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
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Initiative prompt modal now lives in the global modal stack instead of the Cast Spell overlay, so it opens without the spell UI.
- **Investigation context (2026-02-15):**
  - Client already has a dedicated `initiative_prompt` handler that directly opens `#initiativePromptModal` (`assets/web/lan/index.html`).
  - Server already has dedicated sender `send_initiative_prompt(...)`, and DM trigger `_roll_lan_initiative_for_claimed_pcs(...)` calls it (`dnd_initative_tracker.py`).
  - This item likely needs an updated repro (version-specific or CSS stacking issue), because the current code path is not visibly gated by `#sheetCastView`.

### B03 — Tip dialog should persist latest message
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Easy
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Technical starting points:** `#note` element updates + any reset timers/state refresh handlers.
- **Acceptance criteria:**
  - Last emitted tip/error remains visible until replaced by a newer message.
  - No automatic fallback reset to default hint text.
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Verified current LAN client behavior already satisfies this: `localToast(...)` writes directly to `#note` with no timeout-based reset in the current code.
- **Investigation context (2026-02-15):**
  - `localToast(...)` and websocket `"toast"`/claim handlers update `#note` and then use unconditional `setTimeout(..., 2500)` resets (`assets/web/lan/index.html`).
  - Multiple overlapping timers can race; an older timer can overwrite a newer status message.
  - This is a straightforward root-cause candidate and one of the easiest fixes in Phase A.

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
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Non-PC mount requests now use DM-hosted `askyesno` approval plus a required Pass/Fail follow-up when denied; no LAN prompt is broadcast for this branch.
- **Investigation context (2026-02-15):**
  - Server `mount_request` handler now branches by target type: if `mount.is_pc`, prompt that client; otherwise broadcast to admin (`to_admin`) (`dnd_initative_tracker.py`).
  - Pending request storage and `mount_response` handling already exist (`self._pending_mount_requests` + `"mount_response"` branch).
  - Resolved in this update: non-player targets now run DM-hosted Allow/Pass/Fail prompts on the tracker host before finalizing mount outcome.

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
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** `_lan_try_move(...)` now enforces rider movement lock directly, so mounted riders cannot be moved through alternate server paths; added regression coverage for direct rider move rejection while mounted.
- **Investigation context (2026-02-15):**
  - Client `mountCandidatePair()` currently allows any same-tile candidate not already in a mount pairing; “true mount” flags are used only for sort priority (`assets/web/lan/index.html`).
  - Server `_accept_mount(...)` already deducts movement cost and marks mount relationships (`rider_cid` / `mounted_by_cid`) (`dnd_initative_tracker.py`).
  - Remaining high-risk area appears to be movement/turn-rule enforcement consistency (rider lock, shared movement mirroring) across client + server.

### B06 — Remove zoom-out lower bound
- **Type:** Bug fix
- **Impact:** Medium
- **Ease:** Easy
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Acceptance criteria:** zoom-out no longer hard-stops at previous minimum; map remains stable (no NaN/negative/zero rendering failures).
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Lower zoom clamp minimum reduced from `12` to `0.1` in `clampZoom(...)`, removing the prior hard stop while still preventing zero/negative zoom.
- **Investigation context (2026-02-15):**
  - Zoom is hard-clamped by `clampZoom(value) { return Math.min(90, Math.max(12, value)); }` (`assets/web/lan/index.html`).
  - `zoomOut` button calls `zoomAt(zoom - 4, ...)`, so users always stop at 12 due to clamp.
  - Easy fix candidate, but map rendering should be spot-checked for very small zoom values before lowering/removing min bound.

### B07 — DM popup windows should not block all other app windows
- **Type:** Bug fix
- **Impact:** High
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Technical starting points:** Tkinter `Toplevel`, `grab_set`, `wait_window`, modal/transient usage.
- **Acceptance criteria:** DM can interact with map, damage, info windows concurrently; no hidden modal grab lock.
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Removed Tk `grab_set` usage across DM popup workflows in `helper_script.py` and made LAN URL display modeless (`Toplevel`) instead of modal `messagebox`, so open utility windows no longer block interacting with underlying tracker windows.
- **Investigation context (2026-02-15):**
  - Several Tk dialogs use modal patterns (`dlg.grab_set()` and/or `self.wait_window(dlg)`), including AoE parameter prompts in `helper_script.py`.
  - This is a strong candidate for the “windows block each other” symptom, especially when multiple utility dialogs are opened in sequence.
  - Any fix should preserve safety for destructive dialogs while removing global input lock behavior for routine tools.

### B08 — DM initiative tracker column layout/order fix
- **Type:** Bug fix
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Required column order:** `Name | Side | HP | Temp HP | AC | Walk | Swim | Fly | Conditions | Initiative`
- **Special rule:** replace nat-20 separate column with star marker beside initiative value.
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Updated DM table schema/order to `Name | Side | HP | Temp HP | AC | Walk | Swim | Fly | Conditions | Initiative`, removed standalone Nat20 column, and now render nat-20 as a `★` suffix in the initiative cell.
- **Investigation context (2026-02-15):**
  - Current tree definition in `helper_script.py` is `name, side, hp, spd, swim, mode, move, effects, init, nat`.
  - The requested `Temp HP`, `AC`, and `Fly` columns are not currently in the table schema.
  - Current `Nat20` is still a dedicated column, so this item is mostly a table-schema + row-render update.

### B09 — Ensure all spells can rotate
- **Type:** Bug fix
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - Spell handling in `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Acceptance criteria:** every placeable spell template honors rotation controls uniformly.
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Expanded rotation handling parity to include `wall` and `square` AoEs across LAN gesture gating, LAN/server AoE move persistence, and DM map shift-drag rotation logic; added focused regression coverage in `tests/test_spell_rotation_parity.py`.
- **Investigation context (2026-02-15):**
  - LAN client rotation gesture gate is explicit: `isAoeRotateMode(...)` currently returns true only for `line`, `cone`, and `cube` AoEs (`assets/web/lan/index.html`).
  - AoE payload/render paths already carry `angle_deg`, so base rotation plumbing exists.
  - Likely bug scope: template-type parity in UI controls/interaction rules rather than missing core angle serialization.

### B10 — Wild Shape concrete fixes/regressions
- **Type:** Bug fix
- **Impact:** Medium/High
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/tests/test_wild_shape.py`
- **Scope note:** only concrete reproducible defects first; broad UX complaints belong in V01.
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** `_revert_wild_shape(...)` now restores the pre-shape temporary HP when the player still has the exact Wild Shape temp-HP grant at revert time, preventing silent loss of existing temp HP.
- **Investigation context (2026-02-15):**
  - There is already dedicated wild-shape coverage in `tests/test_wild_shape.py` (apply/revert, known/prepared forms, pool handling, LAN handlers).
  - Given existing coverage and broad problem wording, this card should be split into concrete repros before implementation.
  - Suggested first pass is to collect failing scenarios tied to explicit functions (`_apply_wild_shape`, `_revert_wild_shape`, LAN `wild_shape_apply` action path).

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
- **Investigation context (2026-02-15):**
  - LAN already has a top-bar end-turn button (`#endTurn`) plus dedicated emphasis classes (`.end-turn-ready`, `.end-turn-pop`) in `assets/web/lan/index.html`.
  - Current logic already toggles highlight based on action/bonus/movement state, so this card is likely polish/tuning more than new plumbing.
  - Recommended first step is design validation (size/contrast/animation timing) before code churn.

### U02 — Simplify movement mode switching
- **Type:** New feature (UX)
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Goal:** fewer clicks and clearer current mode (walk/swim/fly/etc).
- **Investigation context (2026-02-15):**
  - Movement mode normalization/parsing exists across DM + LAN logic, but the UX still appears distributed across several controls/contexts.
  - Speeds and mode-related fields are present in combatant state, so data support exists.
  - Main risk is desync between DM and LAN mode state if a “quick switch” UI is added without a single authoritative update path.

### U03 — Remove initiative top dropdown clutter
- **Type:** New feature (cleanup)
- **Impact:** Medium
- **Ease:** Easy
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Technical starting points:** `initiativeStyleSelect` + related topbar controls.
- **Investigation context (2026-02-15):**
  - `initiativeStyleSelect` is still present and wired to style persistence/handlers in `assets/web/lan/index.html`.
  - This is a straightforward UI cleanup candidate with low protocol risk.
  - Dependency note with U04 remains valid because both controls touch initiative visibility state.

### U04 — Remove show/hide initiative button
- **Type:** New feature (cleanup)
- **Impact:** Low/Medium
- **Ease:** Easy
- **Dependencies:** U03
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Technical starting points:** `initiativeToggleBtn`, `toggleInitiativeBar`.
- **Status (2026-02-15):** ✅ Completed
- **Implementation note (2026-02-15):** Removed topbar `initiativeToggleBtn` entrypoint from LAN markup; internal initiative state/render logic remains intact for compatibility.
- **Investigation context (2026-02-15):**
  - `initiativeToggleBtn` and `toggleInitiativeBar()` are still active in LAN UI code.
  - Removing this safely likely means preserving internal style state handling while deleting the control entrypoint.
  - Best done in same PR as U03 to avoid temporary inconsistent visibility UX.

### U05 — Hotkey/button to hide entire bottom panel
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:**
  - configurable hotkey (default Delete),
  - one press hides full bottom tray,
  - second press restores.
- **Investigation context (2026-02-15):**
  - A configurable hotkey framework already exists in `assets/web/lan/index.html` (`hotkeyConfig`, conflict validation, persisted bindings).
  - Bottom tray wrapper exists as `#sheetWrap`, which gives a clear target for full-panel show/hide.
  - This is likely medium effort because defaults, settings UI, and discoverability messaging must all be updated together.

### U06 — Small-screen compact mode
- **Type:** New feature
- **Impact:** High
- **Ease:** Medium
- **Likely files:** `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:** detect smaller viewports and auto-compact (smaller fonts, hide low-priority controls by default).
- **Investigation context (2026-02-15):**
  - Compact-related styles already exist (`.initiative-compact`, responsive media blocks) in LAN CSS.
  - Missing piece appears to be automatic runtime viewport detection + mode switching policy.
  - Likely low-risk implementation path: additive auto-compact toggle with manual override preserved.

### U07 — Player HP bar with thresholds
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py` (if payload expansion needed)
- **Rules:** green >50%, yellow <=50%, red <=20%.
- **Investigation context (2026-02-15):**
  - HP/max-HP values are already present in combatant snapshots, so server payload expansion may be minimal or unnecessary.
  - No dedicated player HP-bar component is currently visible in LAN client UI.
  - Main work is client rendering + threshold styling, with edge-case handling for unknown/zero max HP.

### U08 — Condition details in initiative chip/selection
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Target output example:** `Prone (2)`, `Blind (5)`.
- **Investigation context (2026-02-15):**
  - Conditions and durations are already represented server-side; LAN initiative chip currently emphasizes token/name/turn status.
  - This looks primarily like a presentation-layer enhancement, not core combat-rule work.
  - Important compatibility point: keep format additive (new optional display text) so older clients do not break.

### U09 — DM map auto-focus active ally/enemy turn
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Requirements:** on ally/enemy turn start, center map on unit and show clear turn-start notification.
- **Investigation context (2026-02-15):**
  - Active-turn state is already explicit (`active_cid`) in LAN/DM state paths.
  - Manual centering controls already exist, so auto-focus can likely reuse existing camera/center helpers.
  - Key UX risk is over-aggressive recentering; this item may need a DM toggle to avoid interrupting planning workflows.

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
- **Investigation context (2026-02-15):**
  - Server-side custom summon spawning already exists (`_spawn_custom_summons_from_payload(...)`) and writes/loads temp summon data.
  - Summon grouping metadata is already tracked (`_summon_groups`, `_summon_group_meta`) in `dnd_initative_tracker.py`.
  - Primary missing piece appears to be LAN-side summon preset/form UX wiring.

### F02 — Import existing monster YAML to prefill summon form
- **Type:** New feature
- **Impact:** High
- **Ease:** Medium
- **Dependencies:** F01
- **Likely files:** same as F01.
- **Investigation context (2026-02-15):**
  - Server static payload already includes `monster_choices` for LAN consumers.
  - Monster indexing/spec resolution infrastructure exists, including temp-friendly lookup behavior.
  - This card is likely UI/form integration on top of existing data sources introduced/used by F01.

### F03 — DM-side assign summon to player flow
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Dependencies:** F01, F02
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
- **Requirements:** “Assign Summon” button in DM initiative tracker, player picker, summon editor/import.
- **Investigation context (2026-02-15):**
  - Summon ownership/source data is already tracked server-side (`summoned_by_cid`, summon group metadata).
  - No obvious DM-facing assign flow was found yet in current UI.
  - Likely requires both new DM interaction surfaces and explicit reassignment semantics in LAN protocol/messages.

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
- **Investigation context (2026-02-15):**
  - Echo-related summon scaffolding and targeted tests (`tests/test_echo_knight.py`) already exist.
  - Existing summon control/ownership logic likely covers part of the gating requirements.
  - Highest-risk gap appears to be explicit “swap within 15 ft” action validation and turn-resource enforcement.

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
- **Investigation context (2026-02-15):**
  - This repo already uses schema-driven character YAML/editor flows, giving a clear extension point for a weapons model.
  - No canonical weapons schema appears to be established yet, so this remains an RFC-first task.
  - Backwards compatibility risk is high: schema rollout should be additive with safe defaults for existing player files.

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
- **Investigation context (2026-02-15):**
  - Core prerequisites (combatants with AC, battle-log system, LAN action handlers) already exist.
  - No full weapon-driven LAN attack flow is currently obvious in protocol/UI.
  - This card depends on F05 data model stabilization to avoid redesigning message formats twice.

### F07 — Spell range overlay + LAN player damage prompt integration
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Dependencies:** partial overlap with F06 (shared attack/damage UI)
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Investigation context (2026-02-15):**
  - Spell/AoE placement and rotation infrastructure is mature in LAN client code.
  - Missing link appears to be integrated range visualization + downstream damage prompt workflow.
  - This should likely share primitives with F06 (targeting/damage UX) to avoid duplicate interaction systems.

### F08 — Terrain hazard preset system (DoT + triggers + saves + conditions)
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/presets/`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
- **Requirements:** trigger toggles (enter/leave/start/end), damage roll config, save type/DC, on-fail conditions.
- **Investigation context (2026-02-15):**
  - Terrain, condition, and ongoing-effect building blocks already exist separately.
  - There is no consolidated hazard preset pipeline yet that combines trigger timing + saves + effect application.
  - Likely architecture task: define a normalized hazard schema first, then wire trigger engine hooks.

### F09 — Monster auto-path suggestion toggle
- **Type:** New feature
- **Impact:** High
- **Ease:** Hard
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
- **Behavior:** when monster turn starts and toggle on, compute nearest ally/summon/player and queue suggested destination using move+dash budget; DM approve/reject (reject reverts start position).
- **Investigation context (2026-02-15):**
  - Movement/cost logic and turn state are already centralized, which is a workable base for suggestions.
  - Missing pieces are suggestion generation UX, approval/reject flow, and reversible move staging.
  - This is high complexity because “helpful suggestion” must not silently mutate combat state without DM confirmation.

### F10 — Token image overlays for players/monsters
- **Type:** New feature
- **Impact:** Medium/High
- **Ease:** Hard
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/dnd_initative_tracker.py`
  - schema/docs for `assets/pfps/players` + `assets/pfps/monsters`
- **Requirements:** PNG/JPG, auto scale/crop/mask to token shape/size.
- **Investigation context (2026-02-15):**
  - Current token rendering is primarily color/label driven; no established token-image payload or renderer contract was found.
  - This likely needs both server-side optional image metadata and client-side async image caching/masking.
  - F11 should be coordinated here since both rely on shared asset-loading/fallback behavior.

### F11 — Custom condition icons
- **Type:** New feature
- **Impact:** Medium
- **Ease:** Medium/Hard
- **Dependencies:** may share asset-loader infra with F10
- **Likely files:**
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/assets/web/lan/index.html`
  - `/home/runner/work/dnd-initiative-tracker/dnd-initiative-tracker/helper_script.py`
  - condition rendering pipeline in tracker server/client state.
- **Investigation context (2026-02-15):**
  - Conditions currently map cleanly to text/emoji-style displays, so compatibility fallback exists.
  - No custom icon asset pipeline was identified yet.
  - Best implementation path is additive: optional icon key/URL with deterministic fallback to current emoji/text rendering.

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
- **Investigation context (2026-02-15):**
  - Wild-shape internals already have focused test coverage and concrete handlers, but complaint text here is still non-specific.
  - To keep implementation PRs safe/small, convert this bucket into numbered reproducible defects first (then map each defect to B10 or new B-cards).
  - Suggested triage source order: LAN action flow (`wild_shape_apply`) → stat-restore/revert paths → player-resource persistence.

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
