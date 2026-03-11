import unittest
from pathlib import Path


class LanCastModalRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")

    def test_preset_picker_keeps_custom_entries_available(self):
        self.assertIn('customOption.textContent = "Custom";', self.html)
        self.assertIn('customSummonOption.textContent = CUSTOM_SUMMON_PRESET_NAME;', self.html)
        self.assertLess(
            self.html.index('customOption.textContent = "Custom";'),
            self.html.index('customSummonOption.textContent = CUSTOM_SUMMON_PRESET_NAME;'),
        )
        self.assertLess(
            self.html.index('customSummonOption.textContent = CUSTOM_SUMMON_PRESET_NAME;'),
            self.html.index('const availablePresets = cachedSpellPresets.slice();'),
        )
        self.assertNotIn('placeholder.textContent = "Presets unavailable";', self.html)

    def test_custom_summon_ui_includes_monster_yaml_search_and_stats_inputs(self):
        self.assertIn('id="castCustomSummonMonsterSearch"', self.html)
        self.assertIn('id="castCustomSummonMonster"', self.html)
        self.assertIn('id="castCustomSummonHp"', self.html)
        self.assertIn('id="castCustomSummonAc"', self.html)
        self.assertIn('id="castCustomSummonWalk"', self.html)
        self.assertIn('id="castCustomSummonStr"', self.html)
        self.assertIn("refreshCustomSummonMonsterOptions();", self.html)
        self.assertIn("applyCustomSummonTemplate(getSelectedCustomSummonChoice(), true);", self.html)

    def test_custom_summon_selection_routes_to_expected_paths(self):
        self.assertIn('if (name === CUSTOM_SUMMON_PRESET_NAME){', self.html)
        self.assertIn('mode: "custom_summon"', self.html)
        self.assertIn('shape: "summon"', self.html)
        self.assertIn("monster_slug: customMonsterSlug || null,", self.html)
        self.assertIn("abilities,", self.html)
        self.assertIn("speeds,", self.html)
        self.assertIn('const castType = pendingSummonPlacement.mode === "custom_summon" ? "cast_aoe" : "cast_spell";', self.html)

    def test_dismiss_summons_requires_confirmation_with_list(self):
        self.assertIn('cidMatches(u?.summoned_by_cid, claimedCid, "dismissSummons.owner")', self.html)
        self.assertIn('const summonList = summonedUnits.map(u => `- ${u?.name || `#${u?.cid ?? "?"}`}`).join("\\n");', self.html)
        self.assertIn('window.confirm(', self.html)
        self.assertIn("dismiss these summons?\\n${summonList}", self.html)

    def test_config_no_longer_renders_initiative_style_dropdown(self):
        self.assertNotIn('<div class="config-item-title">Initiative strip</div>', self.html)

    def test_move_indicator_click_cycles_movement_mode(self):
        self.assertIn('moveEl.addEventListener("click", () => {', self.html)
        self.assertIn('send({type:"cycle_movement_mode", cid: claimedCid});', self.html)

    def test_bottom_panel_toggle_button_and_hotkey_are_wired(self):
        self.assertIn('id="toggleSheetPanel"', self.html)
        self.assertIn('id="hotkeyToggleSheetPanel"', self.html)
        self.assertIn('inittracker_hotkey_toggleSheetPanel', self.html)
        self.assertIn('localStorage.setItem("inittracker_hotkey_toggleSheetPanel", "Delete");', self.html)

    def test_bottom_panel_height_preference_is_configurable(self):
        self.assertIn('<div class="config-item-title">Bottom panel height</div>', self.html)
        self.assertIn('id="sheetHeight"', self.html)
        self.assertIn("sheetHeightInput.addEventListener(\"input\", () => {", self.html)

    def test_battle_log_has_explicit_text_size_control_and_safe_default_anchor(self):
        self.assertIn('<div class="config-item-title">Battle log text size</div>', self.html)
        self.assertIn('const minTop = Math.max(0, topbarHeight + 8);', self.html)
        self.assertIn('const maxTop = Math.max(minTop, window.innerHeight - sheetHeight - modalRect.height - 8);', self.html)
        self.assertIn('logModal.style.right = "12px";', self.html)

    def test_small_viewport_auto_compact_hides_optional_controls(self):
        self.assertIn("function shouldAutoCompactLayout()", self.html)
        self.assertIn('document.body.classList.toggle("auto-compact", autoCompact);', self.html)
        self.assertIn('class="btn compact-optional" id="battleLog"', self.html)

    def test_concentration_status_chip_and_hud_rendering_are_wired(self):
        self.assertIn('id="concentrationStatus"', self.html)
        self.assertIn('const concentrationStatusEl = document.getElementById("concentrationStatus");', self.html)
        self.assertIn('function formatConcentrationStatus(unit){', self.html)
        self.assertIn('const concentrationSpell = normalizeTextValue(unit?.concentration_spell || unit?.concentrationSpell || "");', self.html)
        self.assertIn('const totalRoundsRaw = Number(unit?.concentration_total_rounds);', self.html)
        self.assertIn('remainingRounds = Math.max(0, totalRounds - elapsedTurns);', self.html)
        self.assertIn('return `Concentration: ${concentrationSpell} · ${totalRounds} rounds total · ${remainingRounds} remaining`;', self.html)
        self.assertIn('return `Concentration: ${concentrationSpell} · duration unknown`;', self.html)
        self.assertIn('concentrationStatusEl.textContent = formatConcentrationStatus(me);', self.html)
        self.assertIn('concentrationStatusEl.textContent = "Concentration: —";', self.html)

    def test_player_hp_bar_ui_and_threshold_classes_present(self):
        self.assertIn('id="playerHpBarWrap"', self.html)
        self.assertIn('id="playerHpBarFill"', self.html)
        self.assertIn('const shieldWidth = Math.min(tempPct, Math.max(0, 100 - pct));', self.html)
        self.assertIn("const shieldLeft = pct;", self.html)
        self.assertIn("updatePlayerHpBar(claimed || null);", self.html)
        self.assertIn('playerHpBarFill.classList.toggle("mid", pct <= 50 && pct > 20);', self.html)
        self.assertIn('playerHpBarFill.classList.toggle("low", pct <= 20);', self.html)

    def test_turn_chip_includes_condition_summary_text(self):
        self.assertIn("const formatTurnChipConditions = (text) => {", self.html)
        self.assertIn("const conditionText = formatTurnChipConditions(unit?.marks);", self.html)
        self.assertIn('nameEl.textContent = conditionText ? `${concentrationLabel} · ${conditionText}` : concentrationLabel;', self.html)

    def test_summon_variants_are_available_for_non_mount_summons(self):
        self.assertIn('const hasVariants = variants.length > 0;', self.html)
        self.assertIn('castSummonVariantField?.classList.toggle("hidden", !hasVariants);', self.html)
        self.assertIn('reason = "Pick a summon variant first, matey.";', self.html)

    def test_aoe_spell_appearance_options_use_variant_field(self):
        self.assertIn("const getSpellAppearanceOptions = (preset) => {", self.html)
        self.assertIn('castSummonVariantLabel.textContent = hasAppearanceOptions ? "Appearance" : "Variant";', self.html)
        self.assertIn("const appearanceSelection = aoeSpell ? String(castSummonVariantInput?.value || \"\").trim() : \"\";", self.html)
        self.assertIn("name: appearanceName || null,", self.html)

    def test_single_target_spell_targeting_flow_is_wired(self):
        self.assertIn("function getSpellTargetingConfig(preset, slotLevel)", self.html)
        self.assertIn('if (tagSet.has("attack") || tagSet.has("spell_attack_target")) return "attack";', self.html)
        self.assertIn('if (tagSet.has("save") || tagSet.has("spell_save_target")) return "save";', self.html)
        self.assertIn('if (tagSet.has("auto_hit") || tagSet.has("spell_auto_hit_target")) return "auto_hit";', self.html)
        self.assertIn('const skipResolveAttack = hasSpellTag(preset, "skip_resolve_attack");', self.html)
        self.assertIn("if (autoHit && pendingSpellTargeting.skipResolveAttack){", self.html)
        self.assertIn('const kind = normalizeLowerValue(step?.check?.kind);', self.html)
        self.assertIn('if (kind === "spell_attack") return "attack";', self.html)
        self.assertIn('const aoeSpell = spellActionTag === "aoe";', self.html)
        self.assertIn('const smiteSpell = hasSpellTag(preset, "smite");', self.html)
        self.assertIn('if (!customSummon && !summonSpell && !smiteSpell && !spellActionTag && !inferredTargetConfig){', self.html)
        self.assertIn('localToast("No tag found for that spell, matey.");', self.html)
        self.assertIn('message: "Spell cast blocked: missing spell action tag",', self.html)
        self.assertIn('const spellTargetConfig = (!aoeSpell && !smiteSpell) ? (inferredTargetConfig || getSpellTargetingConfig(preset, slotLevel)) : null;', self.html)
        self.assertIn('const actionCid = activeControlledUnitCid();', self.html)
        self.assertIn('msg.cid = actionCid;', self.html)
        self.assertIn('type: "spell_target_request",', self.html)
        self.assertIn('} else if (msg.type === "spell_target_result"){', self.html)

    def test_follow_up_only_spell_targeting_and_action_picker_support_are_present(self):
        self.assertIn('const followUpOnly = uiConfig?.follow_up_only === true;', self.html)
        self.assertIn('if (followUpOnly && options.allowFollowUpOnly !== true) return null;', self.html)
        self.assertIn('name: "Hurl Produce Flame",', self.html)
        self.assertIn('kind: "produce_flame_hurl",', self.html)
        self.assertIn('const config = getSpellTargetingConfig(preset, slotLevel, {allowFollowUpOnly: true});', self.html)


    def test_eldritch_blast_inference_regex_includes_beam_scaling_tokens(self):
        self.assertIn(
            'const ebPattern = /two\\s+beams?\\s+at\\s+level\\s+5[^.]*three\\s+beams?\\s+at\\s+level\\s+11[^.]*four\\s+beams?\\s+at\\s+level\\s+17/i;',
            self.html,
        )

    def test_attack_overlay_surfaces_guiding_bolt_and_vicious_mockery_roll_state(self):
        self.assertIn('const hasTargetAdvantage = target?.attackers_have_advantage_against_target === true;', self.html)
        self.assertIn('const hasAttackerDisadvantage = me?.has_attack_disadvantage === true;', self.html)
        self.assertIn('Guiding Bolt: ye have advantage on this attack.', self.html)
        self.assertIn('Vicious Mockery: ye have disadvantage on this attack.', self.html)

    def test_multi_target_queue_does_not_double_advance_after_spell_request_send(self):
        self.assertNotIn(
            'spell_mode: "effect",\n      });\n      consumeSpellTargetingShot();\n      processNextSpellTarget();',
            self.html,
        )
        self.assertNotIn(
            'damage_type: String(pendingSpellTargeting.damageType || "").trim().toLowerCase() || null,\n      });\n      consumeSpellTargetingShot();\n      processNextSpellTarget();',
            self.html,
        )
        self.assertNotIn(
            'damage_type: String(pendingAttackResolve.damageType || "").trim().toLowerCase() || null,\n        });\n        consumeSpellTargetingShot();\n        processNextSpellTarget();',
            self.html,
        )

    def test_spell_inference_contains_no_backspace_control_characters(self):
        self.assertNotIn("\x08", self.html)

    def test_multi_target_selection_queue_wiring_is_present(self):
        self.assertIn('let pendingSpellTargetSelection = null;', self.html)
        self.assertIn('function processNextSpellTarget()', self.html)
        self.assertIn('id="spellTargetSelectionUi"', self.html)
        self.assertIn('id="spellTargetSelectionCounter"', self.html)
        self.assertIn('id="spellTargetSelectionConfirm"', self.html)
        self.assertIn('spell_mode: "effect"', self.html)
        self.assertIn('targetSide: ["friendly", "enemy", "any"].includes', self.html)
        self.assertIn('const shouldBufferSelection = !!(spellTargetConfig && Number(spellTargetConfig.maxTargets || 1) > 1);', self.html)
        self.assertIn('pendingSpellTargeting.queue = selected.slice();', self.html)


    def test_cast_submit_warns_before_replacing_existing_concentration(self):
        self.assertIn("const concentrationSpell = normalizeTextValue(unit?.concentration_spell || unit?.concentrationSpell || \"\");", self.html)
        self.assertIn("preset?.concentration === true", self.html)
        self.assertIn("unit?.concentrating", self.html)
        self.assertIn("Casting ${spellName} will end it. Continue?", self.html)

    def test_turn_alert_round_value_is_normalized_before_repeat_check(self):
        self.assertIn("const roundRaw = state.round_num;", self.html)
        self.assertIn("const lastRound = Number.isFinite(Number(lastTurnRound)) ? Number(lastTurnRound) : lastTurnRound;", self.html)

    def test_turn_notifications_auto_close_without_manual_dismiss(self):
        self.assertIn("const turnNotificationAutoCloseMs = 5000;", self.html)
        self.assertIn("registration.getNotifications({ tag: \"turn-alert\" })", self.html)
        self.assertIn("async function maybeNotifyTurnUpcoming(activeName){", self.html)
        self.assertIn("registration.getNotifications({ tag: \"turn-up-next-alert\" })", self.html)
        self.assertIn("maybeNotifyTurnUpcoming(activeName);", self.html)
        self.assertIn("notification.close();", self.html)
        self.assertNotIn("requireInteraction: true", self.html)

    def test_automated_spell_fields_can_hide_while_damage_type_defaults(self):
        self.assertIn("const updateCastAutomationFields = (preset) => {", self.html)
        self.assertIn("const fullyAutomated = automationLevel === \"full\";", self.html)
        self.assertIn("const showShapeField = !summonSpell && isAoeSpell && !fullyAutomated;", self.html)
        self.assertIn("const showManualDamageFields = !summonSpell && !fullyAutomated;", self.html)
        self.assertIn("const firstType = Array.from(castDamageTypes)[0] || \"\";", self.html)

    def test_reaction_button_and_war_caster_modal_are_wired(self):
        self.assertIn('id="useReaction"', self.html)
        self.assertIn('openActionPicker("reaction");', self.html)
        self.assertIn('function reactionControlledUnitCid()', self.html)
        self.assertIn('const unitCid = mode === "reaction" ? reactionControlledUnitCid() : activeControlledUnitCid();', self.html)
        self.assertIn('id="warCasterModal"', self.html)
        self.assertIn('id="warCasterSpellSelect"', self.html)
        self.assertIn('id="warCasterTargetSelect"', self.html)
        self.assertIn("function playerHasWarCasterFeat()", self.html)
        self.assertIn("function isWarCasterEligibleSpellPreset(preset)", self.html)
        self.assertIn("function runSpellTargetingAgainstTarget(target)", self.html)
        self.assertIn("action_type: \"reaction\"", self.html)
        self.assertIn("spend === \"reaction\"", self.html)

    def test_opportunity_attack_uses_melee_overlay_and_marks_attack_request(self):
        self.assertIn("function getPrimaryMeleeAttackWeapon()", self.html)
        self.assertIn('if (entry.spend === "reaction" && actionName === "opportunity attack")', self.html)
        self.assertIn("pendingOpportunityAttack = true;", self.html)
        self.assertIn("opportunity_attack: !!pendingAttackResolve.opportunityAttack,", self.html)

    def test_weapon_selection_key_uses_unicode_safe_normalized_name(self):
        self.assertIn("const normalized = normalizeCharacterLookupKey(stripped || claimedName || \"\");", self.html)
        self.assertIn("if (normalized) return normalized;", self.html)



    def test_aoe_cast_uses_cursor_follow_placement_mode(self):
        self.assertIn('let pendingAoePlacement = null;', self.html)
        self.assertIn('pendingAoePlacement = {', self.html)
        self.assertIn('"AoE placement: move cursor, click to place (you’ll confirm on placement)."', self.html)
        self.assertIn('"Directional AoE: aim with cursor and click to cast."', self.html)
        self.assertIn('if (pendingAoePlacement){', self.html)
        self.assertIn('const previewAoe = getPendingAoePlacementPreview();', self.html)
        self.assertIn('renderAoeOverlay(previewAoe, {preview: true});', self.html)
        self.assertIn('msg.payload.cx = Number(cursor.col);', self.html)
        self.assertIn('msg.payload.cy = Number(cursor.row);', self.html)
        self.assertIn('if (pendingAoePlacement){\n      if (pendingAoePlacement?.mode !== "aimless_self_centered"){\n        setPendingAoePlacementCursorFromPointer(p);\n      }\n      draw();', self.html)
        self.assertIn('if (pendingAoePlacement){\n      clearPendingAoePlacement();\n      localToast("AoE placement cancelled.");', self.html)

    def test_aoe_target_preview_panel_is_present_and_updates_during_preview(self):
        self.assertIn('id="aoeTargetPreview"', self.html)
        self.assertIn('id="aoeTargetPreviewAllies"', self.html)
        self.assertIn('id="aoeTargetPreviewEnemies"', self.html)
        self.assertIn('function updateAoeTargetPreviewPanel(previewAoe)', self.html)
        self.assertIn('updateAoeTargetPreviewPanel(previewAoe);', self.html)
        self.assertIn('hideAoeTargetPreviewPanel();', self.html)

    def test_aimless_self_range_aoe_confirm_ui_and_mode_gating_are_present(self):
        self.assertIn('id="aimlessAoeConfirm"', self.html)
        self.assertIn('id="aimlessAoeConfirmBtn"', self.html)
        self.assertIn('id="aimlessAoeCancelBtn"', self.html)
        self.assertIn(".aimless-aoe-confirm{", self.html)
        self.assertIn("position:fixed;", self.html)
        self.assertIn("top:calc(var(--topbar-height) + 16px);", self.html)
        self.assertIn("z-index:95;", self.html)
        self.assertIn('mode: "aimless_self_centered"', self.html)
        self.assertIn('pendingAoePlacement?.mode === "aimless_self_centered"', self.html)
        self.assertIn('function isAimlessSelfCenteredAoePlacement()', self.html)


    def test_spell_action_type_prefers_preset_normalized_action_type(self):
        self.assertIn('const normalized = normalizeSpellActionType(preset.action_type || preset.actionType || "");', self.html)
        self.assertIn('return normalizeSpellActionType(castingTime);', self.html)
        self.assertIn('const actionType = preset ? getSpellActionType(preset) : normalizeSpellActionType(entry.action_type || entry.actionType || "action");', self.html)

    def test_pool_granted_aoe_spells_enter_aim_mode_before_spending(self):
        self.assertIn('const spellActionTag = resolveSpellActionTag(entry.preset);', self.html)
        self.assertIn('if (spellActionTag === "aoe"){', self.html)
        self.assertIn('beginForcedPoolAimingCast(entry);', self.html)

    def test_pool_granted_aoe_cast_skips_cast_overlay_and_submits_directly(self):
        self.assertIn('function beginForcedPoolAimingCast(entry)', self.html)
        self.assertIn('if (!castForm){', self.html)
        self.assertIn('castForm.requestSubmit();', self.html)
        self.assertIn('setCastOverlayOpen(false);', self.html)

    def test_wand_of_fireballs_pool_spell_uses_confirmation_modal(self):
        self.assertIn('id="poolSpellConfirmModal"', self.html)
        self.assertIn('id="poolSpellConfirmCast"', self.html)
        self.assertIn('function requiresPoolSpellConfirmation(entry)', self.html)
        self.assertIn('poolId === "wand_of_fireballs_fireball_cast" && spellSlug === "fireball"', self.html)
        self.assertIn('queuePoolSpellCastConfirmation(entry, pool);', self.html)

    def test_lay_on_hands_targeting_overlay_and_modal_are_wired(self):
        self.assertIn('id="layOnHandsOverlay"', self.html)
        self.assertIn('pendingLayOnHandsTargeting = {', self.html)
        self.assertIn('setLayOnHandsOverlayOpen(true);', self.html)
        self.assertIn('const msg = {type:"lay_on_hands_use", cid: claimedCid, target_cid: pendingLayOnHandsResolve.targetCid, amount', self.html)
        self.assertIn('normalizeHexColor(pendingLayOnHandsTargeting ? "#4caf50"', self.html)

    def test_resource_pool_actions_route_bardic_and_mantle_to_targeting_flow(self):
        self.assertIn('if (entry?.spend === "bonus" && normalizedActionKey.startsWith("bardic inspiration")){', self.html)
        self.assertIn('startBardicInspirationGrantTargeting({...entry, sourceCid: actionCid});', self.html)
        self.assertIn('if (entry?.spend === "bonus" && normalizedActionKey.startsWith("mantle of inspiration")){', self.html)
        self.assertIn('startMantleOfInspirationTargeting({...entry, sourceCid: actionCid});', self.html)

    def test_mantle_target_cap_uses_computed_charisma_modifier_and_allows_self_targeting(self):
        self.assertIn('function getUnitAbilityModifier(unit, key){', self.html)
        self.assertIn('const score = Number(source[abilityKey] ?? source[abilityKey.toUpperCase()] ?? source[`${abilityKey}_score`]);', self.html)
        self.assertIn('return getAbilityModifier(profile, abilityKey);', self.html)
        self.assertIn('const chaMod = getUnitAbilityModifier(unit, "cha");', self.html)
        self.assertNotIn('Mantle of Inspiration targets other creatures only.', self.html)
        self.assertNotIn('Choose another creature for Bardic Inspiration.', self.html)



    def test_spell_preset_signature_includes_mechanics_fields(self):
        self.assertIn('JSON.stringify(p.mechanics?.aoe_behavior || {})', self.html)
        self.assertIn('JSON.stringify(p.mechanics?.targeting?.range || {})', self.html)

    def test_relocation_placement_flow_wired_and_non_regressive(self):
        self.assertIn('let pendingRelocationPlacement = null;', self.html)
        self.assertIn('let relocationValidCells = new Set();', self.html)
        self.assertIn('function rebuildRelocationValidCells()', self.html)
        self.assertIn('function clearRelocationPlacementState()', self.html)
        self.assertIn('if (pendingRelocationPlacement && !isMapView && !hasTokenDragMove && !panning && !aoeDragging){', self.html)
        self.assertIn('destination_col: Number(g.col),', self.html)
        self.assertIn('destination_row: Number(g.row),', self.html)
        self.assertIn('if (msg.needs_relocation_destination){', self.html)
        self.assertIn('Relocation placement started. Choose a valid highlighted square.', self.html)
        self.assertIn('if (pendingSummonPlacement && !isMapView && !hasTokenDragMove && !panning && !aoeDragging){', self.html)


    def test_cast_modal_and_spell_changes_clear_active_cast_interaction_state(self):
        self.assertIn('function clearActiveCastInteractionState(showToastMessage = "", options = {}){', self.html)
        self.assertIn('showCastSpellModal(){', self.html)
        self.assertIn('clearActiveCastInteractionState("", {clearAttackOverlay: false});', self.html)
        self.assertIn('hideCastSpellModal(){', self.html)
        self.assertIn('clearActiveCastInteractionState("");', self.html)
        self.assertIn('castPresetInput.addEventListener("change", () => {', self.html)

    def test_map_pointerup_prioritizes_relocation_and_summon_before_attack_overlay(self):
        relocation_idx = self.html.index('if (pendingRelocationPlacement && !isMapView && !hasTokenDragMove && !panning && !aoeDragging){')
        summon_idx = self.html.index('if (pendingSummonPlacement && !isMapView && !hasTokenDragMove && !panning && !aoeDragging){')
        attack_idx = self.html.index('if (attackOverlayMode && !isMapView && !pendingRelocationPlacement && !pendingSummonPlacement && !hasTokenDragMove && !panning && !aoeDragging){')
        self.assertLess(relocation_idx, attack_idx)
        self.assertLess(summon_idx, attack_idx)

    def test_cast_preview_submit_surfaces_invalid_form(self):
        self.assertIn('castForm.requestSubmit();', self.html)
        self.assertIn('localToast("Cast form invalid; check wall dimensions/range.");', self.html)


if __name__ == "__main__":
    unittest.main()
