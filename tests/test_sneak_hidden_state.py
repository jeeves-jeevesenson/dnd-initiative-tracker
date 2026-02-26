import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class SneakHiddenStateTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._lan_force_state_broadcast = lambda: None
        self.app._profile_for_player_name = lambda _name: {}
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.current_cid = 1
        self.app._name_role_memory = {"Goblin": "enemy", "Hero": "pc"}

        enemy = type("C", (), {"cid": 1, "name": "Goblin", "hp": 7, "ability_mods": {"dex": 2}, "condition_stacks": []})()
        hero = type("C", (), {"cid": 2, "name": "Hero", "hp": 12, "ability_mods": {"wis": 1}, "condition_stacks": []})()
        self.app.combatants = {1: enemy, 2: hero}
        self.positions = {1: (0, 0), 2: (3, 0)}
        self.obstacles = set()
        self.app._lan_live_map_data = lambda: (10, 10, set(self.obstacles), {}, dict(self.positions))

    def test_sneak_attempt_hide_requires_active_enemy_turn(self):
        self.app.current_cid = 2
        result = self.app._sneak_attempt_hide(1)
        self.assertFalse(result.get("ok"))
        self.assertIn("active enemy", result.get("reason", ""))

    def test_sneak_attempt_hide_fails_dc15_when_not_seen(self):
        self.obstacles.add((1, 0))
        with mock.patch("dnd_initative_tracker.random.randint", return_value=5):
            result = self.app._sneak_attempt_hide(1)

        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("hidden"))
        self.assertFalse(getattr(self.app.combatants[1], "is_hidden", False))
        self.assertEqual(result.get("total"), 5)

    def test_sneak_attempt_hide_success_sets_hidden_stealth_dc_and_invisible(self):
        self.obstacles.add((1, 0))
        with mock.patch("dnd_initative_tracker.random.randint", return_value=15):
            result = self.app._sneak_attempt_hide(1)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("hidden"))
        self.assertTrue(self.app.combatants[1].is_hidden)
        self.assertEqual(getattr(self.app.combatants[1], "hide_stealth_dc", None), 15)
        self.assertTrue(self.app._has_condition(self.app.combatants[1], "invisible"))

    def test_hidden_movement_uses_passive_perception_vs_stored_stealth_dc(self):
        self.app.combatants[1].is_hidden = True
        self.app.combatants[1].hide_stealth_dc = 12
        self.app.combatants[1].condition_stacks = [tracker_mod.base.ConditionStack(sid=1, ctype="invisible", remaining_turns=None)]
        self.app.combatants[1].hide_invisible_sid = 1
        self.obstacles.add((1, 0))
        self.positions[1] = (2, 0)

        first = self.app._sneak_handle_hidden_movement(1, (0, 0), (2, 0))
        self.assertTrue(first.get("ok"))
        self.assertTrue(first.get("hidden"))
        self.app.turn_num = 2
        self.app.combatants[1].is_hidden = True
        self.app.combatants[1].hide_stealth_dc = 10
        second = self.app._sneak_handle_hidden_movement(1, (0, 0), (2, 0))
        self.assertTrue(second.get("ok"))
        self.assertFalse(second.get("hidden"))
        self.assertIn("Hero", second.get("spotted_by", []))

    def test_hidden_enemy_reveals_on_map_attack_only_removes_hide_invisible(self):
        self.app._name_role_memory = {"Goblin": "enemy", "Hero": "pc"}
        self.app.combatants[1].is_hidden = True
        self.app.combatants[1].hide_stealth_dc = 17
        self.app.combatants[1].hide_invisible_sid = 11
        self.app.combatants[1].condition_stacks = [
            tracker_mod.base.ConditionStack(sid=10, ctype="invisible", remaining_turns=None),
            tracker_mod.base.ConditionStack(sid=11, ctype="invisible", remaining_turns=None),
        ]
        self.app.combatants[2].ac = 10
        self.app.combatants[2].hp = 10

        attack_option = {"name": "Scimitar", "key": "scimitar", "to_hit": 4, "damage_entries": [{"formula": "1d6+2", "type": "slashing"}]}
        with mock.patch("dnd_initative_tracker.random.randint", return_value=10):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [{"attack_option": attack_option, "attack_key": "scimitar", "count": 1, "roll_mode": "normal"}],
            )

        self.assertTrue(result.get("ok"))
        self.assertFalse(self.app.combatants[1].is_hidden)
        self.assertIsNone(getattr(self.app.combatants[1], "hide_stealth_dc", None))
        self.assertIsNone(getattr(self.app.combatants[1], "hide_invisible_sid", None))
        remaining_sids = {int(st.sid) for st in self.app.combatants[1].condition_stacks}
        self.assertEqual(remaining_sids, {10})


if __name__ == "__main__":
    unittest.main()
