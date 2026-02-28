import unittest

import helper_script as helper_mod


class StartTurnAoeAutoSavePromptTests(unittest.TestCase):
    def test_over_time_start_turn_prompt_auto_rolls_saves(self):
        app = helper_mod.InitiativeTracker.__new__(helper_mod.InitiativeTracker)
        c = helper_mod.Combatant(
            cid=1,
            name="Caster",
            hp=30,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="normal",
            move_remaining=30,
            initiative=10,
            ally=False,
            is_pc=False,
        )
        c.condition_stacks = []
        app.combatants = {1: c}
        app.current_cid = 1
        app.start_cid = None
        app._display_order = lambda: [c]
        app._retarget_current_after_removal = lambda removed, pre_order=None: None
        app._roll_dice_dict = lambda dice: 0
        app._apply_damage_to_combatant = lambda target, amount: {"hp_after": int(target.hp)}
        app._queue_concentration_save = lambda target, source: None
        app._effective_speed = lambda target: 30
        app._reset_concentration_prompt_state = lambda target: None

        calls = []

        class MapWindowStub:
            aoes = {
                7: {
                    "over_time": True,
                    "trigger_on_start_or_enter": "enter_or_end",
                    "owner_cid": 1,
                    "move_per_turn_ft": 60,
                }
            }

            @staticmethod
            def winfo_exists():
                return True

            @staticmethod
            def _compute_included_units(aid):
                return [1]

            @staticmethod
            def _open_aoe_damage(**kwargs):
                calls.append(kwargs)

        app._map_window = MapWindowStub()

        skip, _msg, _decremented = helper_mod.InitiativeTracker._process_start_of_turn(app, c)

        self.assertFalse(skip)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].get("aid"), 7)
        self.assertEqual(calls[0].get("included_override"), [1])
        self.assertTrue(calls[0].get("auto_roll_saves"))


if __name__ == "__main__":
    unittest.main()
