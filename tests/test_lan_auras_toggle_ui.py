import pathlib
import unittest


class LanAuraToggleUiTests(unittest.TestCase):
    def test_aura_toggle_filters_aura_overlays_when_disabled(self):
        source = pathlib.Path("assets/web/lan/index.html").read_text(encoding="utf-8")

        self.assertIn("function shouldRenderAoe(aoe)", source)
        self.assertIn("if (!areAurasEnabled() && isAuraAoe(aoe)) return false;", source)
        self.assertIn("if (!shouldRenderAoe(a)) return;\n        renderAoeOverlay(a);", source)
        self.assertIn("if (!shouldRenderAoe(aoe)) continue;\n      if (!canInteractWithAoe(aoe)) continue;", source)


if __name__ == "__main__":
    unittest.main()
