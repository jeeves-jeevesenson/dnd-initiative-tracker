import unittest

from helper_script import _active_rotation_target, _facing_degrees_from_points, _normalize_facing_degrees


class MapRotationHelperTests(unittest.TestCase):
    def test_normalize_facing_degrees_wraps(self):
        self.assertEqual(_normalize_facing_degrees(0), 0.0)
        self.assertEqual(_normalize_facing_degrees(360), 0.0)
        self.assertEqual(_normalize_facing_degrees(-90), 270.0)
        self.assertEqual(_normalize_facing_degrees(765), 45.0)

    def test_facing_from_points_uses_screen_up_as_positive_90(self):
        cx, cy = 10.0, 10.0
        self.assertAlmostEqual(_facing_degrees_from_points(cx, cy, 20.0, 10.0), 0.0)
        self.assertAlmostEqual(_facing_degrees_from_points(cx, cy, 10.0, 0.0), 90.0)
        self.assertAlmostEqual(_facing_degrees_from_points(cx, cy, 0.0, 10.0), 180.0)
        self.assertAlmostEqual(_facing_degrees_from_points(cx, cy, 10.0, 20.0), 270.0)

    def test_active_rotation_target_only_allows_active_token(self):
        self.assertEqual(_active_rotation_target(7, 7), 7)
        self.assertEqual(_active_rotation_target("7", "7"), 7)
        self.assertIsNone(_active_rotation_target(7, 8))
        self.assertIsNone(_active_rotation_target(None, 7))
        self.assertIsNone(_active_rotation_target(7, None))


if __name__ == "__main__":
    unittest.main()
