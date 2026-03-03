import pathlib
import unittest


class LanAttackOverlayMeleeTargetingTests(unittest.TestCase):
    SOURCE_PATH = pathlib.Path("assets/web/lan/index.html")

    def test_attack_overlay_prefers_enemy_when_click_overlap_includes_self(self):
        source = self.SOURCE_PATH.read_text(encoding="utf-8")

        self.assertIn("function hitTestTokens(p){", source)
        self.assertIn("const hitCandidates = hitTestTokens(p);", source)
        self.assertIn('attackOverlay.enemyFallback.self', source)
        self.assertIn("if (preferredEnemy){", source)
        self.assertIn("hit = preferredEnemy;", source)


if __name__ == "__main__":
    unittest.main()
