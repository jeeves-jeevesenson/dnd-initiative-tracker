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
        self.assertIn('window.confirm(', self.html)
        self.assertIn('Are ye sure ye want to dismiss these summons?', self.html)

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

    def test_small_viewport_auto_compact_hides_optional_controls(self):
        self.assertIn("function shouldAutoCompactLayout()", self.html)
        self.assertIn('document.body.classList.toggle("auto-compact", autoCompact);', self.html)
        self.assertIn('class="btn compact-optional" id="battleLog"', self.html)

    def test_player_hp_bar_ui_and_threshold_classes_present(self):
        self.assertIn('id="playerHpBarWrap"', self.html)
        self.assertIn('id="playerHpBarFill"', self.html)
        self.assertIn('playerHpBarFill.classList.toggle("mid", pct <= 50 && pct > 20);', self.html)
        self.assertIn('playerHpBarFill.classList.toggle("low", pct <= 20);', self.html)


if __name__ == "__main__":
    unittest.main()
