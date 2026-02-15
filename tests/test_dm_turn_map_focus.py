import unittest

import helper_script as helper_mod


class DmTurnMapFocusTests(unittest.TestCase):
    def _map_window(self):
        return object.__new__(helper_mod.BattleMapWindow)

    def test_set_active_auto_center_centers_on_active_token(self):
        window = self._map_window()
        calls = []
        window._apply_active_highlight = lambda: None
        window._update_move_highlight = lambda: None
        window._update_groups = lambda: None
        window._center_on_cid = lambda cid: calls.append(cid)

        window.set_active(42, auto_center=True)

        self.assertEqual(window._active_cid, 42)
        self.assertEqual(calls, [42])

    def test_set_active_default_keeps_existing_non_center_behavior(self):
        window = self._map_window()
        calls = []
        window._apply_active_highlight = lambda: None
        window._update_move_highlight = lambda: None
        window._update_groups = lambda: None
        window._center_on_cid = lambda cid: calls.append(cid)

        window.set_active(7)

        self.assertEqual(window._active_cid, 7)
        self.assertEqual(calls, [])

    def test_unmarked_terrain_cell_is_not_rough(self):
        window = self._map_window()

        cell = window._rough_cell_data(None)

        self.assertFalse(cell["is_rough"])
        self.assertEqual(cell["movement_type"], "ground")


if __name__ == "__main__":
    unittest.main()
