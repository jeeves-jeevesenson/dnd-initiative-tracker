import unittest
from pathlib import Path


class SpellRotationParityTests(unittest.TestCase):
    def test_lan_rotate_mode_supports_wall_and_square(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn(
            'kind !== "line" && kind !== "cone" && kind !== "cube" && kind !== "wall" && kind !== "square"',
            html,
        )

    def test_server_aoe_move_applies_angle_for_wall_and_square(self):
        py = Path("dnd_initative_tracker.py").read_text(encoding="utf-8")
        self.assertIn('if kind in ("line", "cone", "cube", "wall", "square"):', py)

    def test_dm_map_drag_rotation_supports_wall_and_square(self):
        py = Path("helper_script.py").read_text(encoding="utf-8")
        self.assertIn(
            'if kind in ("line", "cone", "cube", "wall", "square") and shift_held:',
            py,
        )


if __name__ == "__main__":
    unittest.main()
