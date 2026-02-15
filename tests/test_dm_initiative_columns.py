import types
import unittest

import helper_script as helper_mod


class DmInitiativeColumnsTests(unittest.TestCase):
    def _tracker(self):
        return object.__new__(helper_mod.InitiativeTracker)

    def test_ac_display_uses_combatant_or_monster_data(self):
        tracker = self._tracker()
        combatant = types.SimpleNamespace(ac=17, monster_spec=None)
        self.assertEqual(tracker._combatant_ac_display(combatant), "17")

        monster = types.SimpleNamespace(raw_data={"ac": {"value": 15}})
        combatant = types.SimpleNamespace(monster_spec=monster)
        self.assertEqual(tracker._combatant_ac_display(combatant), "15")

    def test_initiative_display_adds_star_for_nat20(self):
        tracker = self._tracker()
        normal = types.SimpleNamespace(initiative=12, nat20=False)
        nat20 = types.SimpleNamespace(initiative=20, nat20=True)

        self.assertEqual(tracker._initiative_display(normal), "12")
        self.assertEqual(tracker._initiative_display(nat20), "20★")

    def test_tree_double_click_supports_temp_hp_and_ac_editing(self):
        tracker = self._tracker()
        combatant = types.SimpleNamespace(name="PC", hp=10, initiative=2, speed=30, swim_speed=0, temp_hp=3, ac=14)
        tracker.combatants = {1: combatant}
        calls = []

        def _inline(item, column, initial, _caster, setter, rebuild=True):
            calls.append((item, column, initial, rebuild))
            setter(7 if column == "#4" else 18)

        tracker._inline_edit_cell = _inline

        class _Tree:
            def identify_row(self, _y):
                return "1"

            def identify_column(self, _x):
                return tracker._column_to_test

        tracker.tree = _Tree()
        event = types.SimpleNamespace(x=0, y=0)

        tracker._column_to_test = "#4"
        tracker._on_tree_double_click(event)
        tracker._column_to_test = "#5"
        tracker._on_tree_double_click(event)

        self.assertEqual(calls[0][1], "#4")
        self.assertEqual(calls[0][2], "3")
        self.assertEqual(calls[1][1], "#5")
        self.assertEqual(calls[1][2], "14")
        self.assertEqual(combatant.temp_hp, 7)
        self.assertEqual(combatant.ac, 18)


if __name__ == "__main__":
    unittest.main()
