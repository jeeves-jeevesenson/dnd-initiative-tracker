import unittest
from pathlib import Path


class LanCastModalRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")

    def test_preset_picker_keeps_custom_entries_available(self):
        self.assertIn('customOption.textContent = "Custom";', self.html)
        self.assertIn('customSummonOption.textContent = CUSTOM_SUMMON_PRESET_NAME;', self.html)
        self.assertNotIn('placeholder.textContent = "Presets unavailable";', self.html)

    def test_custom_summon_selection_routes_to_expected_paths(self):
        self.assertIn('if (name === CUSTOM_SUMMON_PRESET_NAME){', self.html)
        self.assertIn('mode: "custom_summon"', self.html)
        self.assertIn('shape: "summon"', self.html)
        self.assertIn('const castType = pendingSummonPlacement.mode === "custom_summon" ? "cast_aoe" : "cast_spell";', self.html)


if __name__ == "__main__":
    unittest.main()
