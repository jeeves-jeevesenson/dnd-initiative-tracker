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


if __name__ == "__main__":
    unittest.main()
