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

    def test_player_hp_bar_ui_and_threshold_classes_present(self):
        self.assertIn('id="playerHpBarWrap"', self.html)
        self.assertIn('id="playerHpBarFill"', self.html)
        self.assertIn('playerHpBarFill.classList.toggle("mid", pct <= 50 && pct > 20);', self.html)
        self.assertIn('playerHpBarFill.classList.toggle("low", pct <= 20);', self.html)

    def test_turn_chip_includes_condition_summary_text(self):
        self.assertIn("const formatTurnChipConditions = (text) => {", self.html)
        self.assertIn("const conditionText = formatTurnChipConditions(unit?.marks);", self.html)
        self.assertIn('nameEl.textContent = conditionText ? `${concentrationLabel} · ${conditionText}` : concentrationLabel;', self.html)

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


    def test_eldritch_blast_inference_regex_includes_beam_scaling_tokens(self):
        self.assertIn(
            'const ebPattern = /two\\s+beams?\\s+at\\s+level\\s+5[^.]*three\\s+beams?\\s+at\\s+level\\s+11[^.]*four\\s+beams?\\s+at\\s+level\\s+17/i;',
            self.html,
        )

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

    def test_automated_spell_fields_can_hide_while_damage_type_defaults(self):
        self.assertIn("const updateCastAutomationFields = (preset) => {", self.html)
        self.assertIn("const fullyAutomated = automationLevel === \"full\";", self.html)
        self.assertIn("const showShapeField = !summonSpell && isAoeSpell && !fullyAutomated;", self.html)
        self.assertIn("const showManualDamageFields = !summonSpell && !fullyAutomated;", self.html)
        self.assertIn("const firstType = Array.from(castDamageTypes)[0] || \"\";", self.html)

    def test_reaction_button_and_war_caster_modal_are_wired(self):
        self.assertIn('id="useReaction"', self.html)
        self.assertIn('openActionPicker("reaction");', self.html)
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



    def test_aoe_cast_uses_cursor_follow_placement_mode(self):
        self.assertIn('let pendingAoePlacement = null;', self.html)
        self.assertIn('pendingAoePlacement = {', self.html)
        self.assertIn('localToast("AoE placement: move cursor, click to place (you’ll confirm on placement).");', self.html)
        self.assertIn('if (pendingAoePlacement){', self.html)
        self.assertIn('const previewAoe = getPendingAoePlacementPreview();', self.html)
        self.assertIn('renderAoeOverlay(previewAoe, {preview: true});', self.html)
        self.assertIn('msg.payload.cx = Math.round(Number(cursor.col));', self.html)
        self.assertIn('msg.payload.cy = Math.round(Number(cursor.row));', self.html)
        self.assertIn('if (pendingAoePlacement){\n      if (pendingAoePlacement?.mode !== "aimless_self_centered"){\n        setPendingAoePlacementCursorFromPointer(p);\n      }\n      draw();', self.html)
        self.assertIn('if (pendingAoePlacement){\n        clearPendingAoePlacement();\n        localToast("AoE placement cancelled.");', self.html)

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

    def test_lay_on_hands_targeting_overlay_and_modal_are_wired(self):
        self.assertIn('id="layOnHandsOverlay"', self.html)
        self.assertIn('pendingLayOnHandsTargeting = {', self.html)
        self.assertIn('setLayOnHandsOverlayOpen(true);', self.html)
        self.assertIn('const msg = {type:"lay_on_hands_use", cid: claimedCid, target_cid: pendingLayOnHandsResolve.targetCid, amount};', self.html)
        self.assertIn('normalizeHexColor(pendingLayOnHandsTargeting ? "#4caf50"', self.html)


    def test_spell_preset_signature_includes_mechanics_fields(self):
        self.assertIn('JSON.stringify(p.mechanics?.aoe_behavior || {})', self.html)
        self.assertIn('JSON.stringify(p.mechanics?.targeting?.range || {})', self.html)

    def test_cast_preview_submit_surfaces_invalid_form(self):
        self.assertIn('castForm.requestSubmit();', self.html)
        self.assertIn('localToast("Cast form invalid; check wall dimensions/range.");', self.html)


if __name__ == "__main__":
    unittest.main()
