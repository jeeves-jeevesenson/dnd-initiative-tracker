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


class DmMapMiddleClickDamageTests(unittest.TestCase):
    def _map_window(self):
        return object.__new__(helper_mod.BattleMapWindow)

    def test_open_damage_for_target_can_preserve_damage_mode(self):
        window = self._map_window()
        calls = []

        class Var:
            def __init__(self):
                self.value = True
            def set(self, value):
                self.value = value

        class App:
            def __init__(self):
                self.current_cid = 8
            def _open_damage_tool(self, attacker_cid=None, target_cid=None):
                calls.append((attacker_cid, target_cid))

        window.app = App()
        window.damage_mode_var = Var()
        window._active_cid = 5

        window._open_damage_for_target(22, consume_mode=False)

        self.assertEqual(calls, [(5, 22)])
        self.assertTrue(window.damage_mode_var.value)

    def test_open_damage_for_target_middle_click_uses_current_turn_holder(self):
        window = self._map_window()
        calls = []

        class App:
            def __init__(self):
                self.current_cid = 11
                self.combatants = {3: object()}
            def _open_damage_tool(self, attacker_cid=None, target_cid=None):
                calls.append((attacker_cid, target_cid))

        class Canvas:
            def canvasx(self, x):
                return x
            def canvasy(self, y):
                return y
            def find_overlapping(self, *_args):
                return [42]
            def gettags(self, _item):
                return ("unit:3",)

        window.app = App()
        window.canvas = Canvas()
        window._is_enemy_cid = lambda cid: cid == 3
        window._open_damage_for_target = lambda target_cid, attacker_cid=None, consume_mode=True: calls.append((attacker_cid, target_cid, consume_mode))

        event = type('Event', (), {'x': 10, 'y': 20})()
        window._on_canvas_middle_click(event)

        self.assertEqual(calls, [(11, 3, False)])

    def test_open_damage_for_target_middle_click_ignores_friendlies(self):
        window = self._map_window()
        calls = []

        class App:
            def __init__(self):
                self.current_cid = 11
                self.combatants = {3: object()}

        class Canvas:
            def canvasx(self, x):
                return x
            def canvasy(self, y):
                return y
            def find_overlapping(self, *_args):
                return [42]
            def gettags(self, _item):
                return ("unit:3",)

        window.app = App()
        window.canvas = Canvas()
        window._is_enemy_cid = lambda _cid: False
        window._open_damage_for_target = lambda *args, **kwargs: calls.append((args, kwargs))

        event = type('Event', (), {'x': 10, 'y': 20})()
        window._on_canvas_middle_click(event)

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
