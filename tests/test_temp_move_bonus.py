import types
import unittest

import helper_script as helper_mod


class TempMoveBonusTests(unittest.TestCase):
    def _tracker(self):
        tracker = object.__new__(helper_mod.InitiativeTracker)
        tracker.combatants = {}
        tracker.current_cid = None
        tracker._tick_aoe_durations = lambda: None
        return tracker

    def _combatant(self):
        return types.SimpleNamespace(
            cid=1,
            name="PC",
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            movement_mode="normal",
            condition_stacks=[],
            temp_move_bonus=0,
            temp_move_turns_remaining=0,
            move_total=30,
            move_remaining=30,
        )

    def test_apply_temp_move_bonus_increases_current_turn_budget(self):
        tracker = self._tracker()
        logs = []
        tracker._log = lambda message, cid=None: logs.append((message, cid))
        combatant = self._combatant()
        combatant.move_total = 60
        combatant.move_remaining = 45
        tracker.combatants = {1: combatant}
        tracker.current_cid = 1

        self.assertTrue(tracker._apply_temp_move_bonus(1, 10, 2))
        self.assertEqual(combatant.temp_move_bonus, 10)
        self.assertEqual(combatant.temp_move_turns_remaining, 2)
        self.assertEqual(tracker._effective_speed(combatant), 40)
        self.assertEqual(combatant.move_total, 70)
        self.assertEqual(combatant.move_remaining, 55)
        self.assertIn(("temporary movement +10 ft for 2 turns", 1), logs)

    def test_end_turn_cleanup_decrements_and_expires_temp_bonus(self):
        tracker = self._tracker()
        logs = []
        tracker._log = lambda message, cid=None: logs.append((message, cid))
        combatant = self._combatant()
        combatant.temp_move_bonus = 10
        combatant.temp_move_turns_remaining = 1
        tracker.combatants = {1: combatant}

        tracker._end_turn_cleanup(1)

        self.assertEqual(combatant.temp_move_bonus, 0)
        self.assertEqual(combatant.temp_move_turns_remaining, 0)
        self.assertEqual(combatant.move_total, 30)
        self.assertEqual(combatant.move_remaining, 30)
        self.assertIn(("temporary movement bonus ended", 1), logs)

    def test_end_turn_cleanup_keeps_bonus_when_turns_remain(self):
        tracker = self._tracker()
        tracker._log = lambda *args, **kwargs: None
        combatant = self._combatant()
        combatant.temp_move_bonus = 10
        combatant.temp_move_turns_remaining = 2
        tracker.combatants = {1: combatant}

        tracker._end_turn_cleanup(1)

        self.assertEqual(combatant.temp_move_bonus, 10)
        self.assertEqual(combatant.temp_move_turns_remaining, 1)
        self.assertEqual(combatant.move_total, 40)
        self.assertEqual(combatant.move_remaining, 40)


if __name__ == "__main__":
    unittest.main()
