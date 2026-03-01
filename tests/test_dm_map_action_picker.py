import unittest

import helper_script as base


class DmMapActionPickerTests(unittest.TestCase):
    def test_action_entries_include_sheet_and_custom_actions(self):
        combatant = base.Combatant(
            cid=9,
            name="Mind Flayer",
            hp=71,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="normal",
            move_remaining=30,
            initiative=12,
            actions=[{"name": "Psychic Detonation", "description": "Boom."}],
            bonus_actions=[{"name": "Misty Step", "description": "Teleport."}],
            reactions=[{"name": "Parry", "description": "Reduce damage."}],
        )

        entries = base.BattleMapWindow._dm_action_entries_for(object(), combatant)

        self.assertIn(
            {"name": "Psychic Detonation", "description": "Boom.", "spend": "action", "kind": "sheet"},
            entries,
        )
        self.assertIn(
            {"name": "Misty Step", "description": "Teleport.", "spend": "bonus", "kind": "sheet"},
            entries,
        )
        self.assertIn(
            {"name": "Parry", "description": "Reduce damage.", "spend": "reaction", "kind": "sheet"},
            entries,
        )
        self.assertIn(
            {"name": "Custom Action…", "description": "Spend 1 action and log a custom ability.", "spend": "action", "kind": "custom"},
            entries,
        )


if __name__ == "__main__":
    unittest.main()
