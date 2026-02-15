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


if __name__ == "__main__":
    unittest.main()
