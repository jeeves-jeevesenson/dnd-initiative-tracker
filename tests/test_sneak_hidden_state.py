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

        enemy = type("C", (), {"cid": 1, "name": "Goblin", "hp": 7, "ability_mods": {"dex": 2}})()
        hero = type("C", (), {"cid": 2, "name": "Hero", "hp": 12, "ability_mods": {"wis": 1}})()
        self.app.combatants = {1: enemy, 2: hero}
        self.positions = {1: (0, 0), 2: (3, 0)}
        self.obstacles = set()
        self.app._lan_live_map_data = lambda: (10, 10, set(self.obstacles), {}, dict(self.positions))

    def test_sneak_attempt_hide_requires_active_enemy_turn(self):
        self.app.current_cid = 2
        result = self.app._sneak_attempt_hide(1)
        self.assertFalse(result.get("ok"))
        self.assertIn("active enemy", result.get("reason", ""))

    def test_sneak_attempt_hide_with_no_los_sets_hidden(self):
        self.obstacles.add((1, 0))

        result = self.app._sneak_attempt_hide(1)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("hidden"))
        self.assertTrue(self.app.combatants[1].is_hidden)

    def test_sneak_attempt_hide_seen_rolls_vs_passive_perception(self):
        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            result = self.app._sneak_attempt_hide(1)

        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("hidden"))
        self.assertFalse(getattr(self.app.combatants[1], "is_hidden", False))
        self.assertIn("Hero", result.get("spotted_by", []))

    def test_hidden_movement_checks_each_observer_once_per_turn(self):
        self.app.combatants[1].is_hidden = True
        self.obstacles.add((1, 0))
        self.positions[1] = (2, 0)

        with mock.patch("dnd_initative_tracker.random.randint", return_value=20) as mocked_roll:
            first = self.app._sneak_handle_hidden_movement(1, (0, 0), (2, 0))
            second = self.app._sneak_handle_hidden_movement(1, (0, 0), (2, 0))

        self.assertTrue(first.get("ok"))
        self.assertTrue(first.get("hidden"))
        self.assertTrue(second.get("ok"))
        self.assertTrue(second.get("hidden"))
        self.assertEqual(mocked_roll.call_count, 1)

    def test_hidden_enemy_reveals_on_map_attack(self):
        self.app._name_role_memory = {"Goblin": "enemy", "Hero": "pc"}
        self.app.combatants[1].is_hidden = True
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


if __name__ == "__main__":
    unittest.main()
