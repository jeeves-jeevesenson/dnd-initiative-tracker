import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class LanAttackRequestTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Aelar"
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [
                    {"id": "longsword", "name": "Longsword", "to_hit": 7},
                    {"id": "shortbow", "name": "Shortbow", "to_hit": 6},
                ],
            }
        }
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app._next_stack_id = 1
        self.app.start_cid = None
        self.app.current_cid = 1
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Aelar", "ac": 16, "hp": 25, "condition_stacks": []})(),
            2: type(
                "C",
                (),
                {
                    "cid": 2,
                    "name": "Goblin",
                    "ac": 15,
                    "hp": 20,
                    "condition_stacks": [],
                    "saving_throws": {},
                    "ability_mods": {},
                },
            )(),
        }
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].attack_resource_remaining = 0
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._remove_combatants_with_lan_cleanup = lambda cids: [self.app.combatants.pop(int(cid), None) for cid in cids]
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_attack_request_returns_hit_result_without_exposing_target_ac(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 9,
            "target_cid": 2,
            "weapon_id": "longsword",
            "attack_roll": 10,
            "attack_count": 1,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("total_to_hit"), 17)
        self.assertEqual(result.get("weapon_name"), "Longsword")
        self.assertEqual(result.get("attack_count"), 1)
        self.assertNotIn("target_ac", result)
        self.assertIn((9, "Attack hits."), self.toasts)

    def test_attack_request_requires_configured_weapon(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 10,
            "target_cid": 2,
            "weapon_id": "not-configured",
            "attack_roll": 12,
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn("_attack_result", msg)
        self.assertIn((10, "Pick one of yer configured weapons first, matey."), self.toasts)

    def test_attack_request_defaults_to_equipped_weapon_when_not_specified(self):
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [
                    {"id": "longsword", "name": "Longsword", "to_hit": 7},
                    {"id": "battleaxe", "name": "Battleaxe", "to_hit": 8, "equipped": True},
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 22,
            "target_cid": 2,
            "attack_roll": 10,
            "attack_count": 1,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("weapon_name"), "Battleaxe")
        self.assertEqual(result.get("to_hit"), 8)
        self.assertNotIn((22, "Pick one of yer configured weapons first, matey."), self.toasts)

    def test_attack_request_defaults_attack_count_from_class_configuration(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 11,
            "target_cid": 2,
            "weapon_id": "shortbow",
            "attack_roll": 10,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("attack_count"), 2)

    def test_attack_request_applies_weapon_magic_bonus(self):
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [
                    {"id": "longsword", "name": "Longsword", "to_hit": 5, "magic_bonus": 2},
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 14,
            "target_cid": 2,
            "weapon_id": "longsword",
            "attack_roll": 10,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("to_hit"), 7)
        self.assertEqual(result.get("total_to_hit"), 17)

    def test_attack_request_auto_spends_action_when_no_attack_resource(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 12,
            "target_cid": 2,
            "weapon_id": "longsword",
            "attack_roll": 10,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("ok"))
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 1)
        self.assertEqual(result.get("attack_resource_remaining"), 1)

    def test_attack_request_rejects_when_no_action_and_no_attack_resource(self):
        self.app.combatants[1].action_remaining = 0
        self.app.combatants[1].attack_resource_remaining = 0
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 13,
            "target_cid": 2,
            "weapon_id": "longsword",
            "attack_roll": 10,
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn("_attack_result", msg)
        self.assertIn((13, "No attacks left, matey."), self.toasts)

    def test_attack_request_accepts_manual_miss_without_attack_roll(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 15,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": False,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 0)
        self.assertEqual(self.app.combatants[2].hp, 20)
        self.assertIn((15, "Attack misses."), self.toasts)

    def test_attack_request_applies_manual_damage_entries_on_hit(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 16,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
            "damage_entries": [
                {"amount": 7, "type": "slashing"},
                {"amount": 2, "type": "fire"},
            ],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 9)
        self.assertEqual(self.app.combatants[2].hp, 11)
        self.assertIn((16, "Attack hits."), self.toasts)

    def test_attack_request_auto_resolves_weapon_and_effect_damage_when_hit(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 20},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "hellfire_battleaxe_plus_2",
                        "name": "Hellfire Battleaxe (+2)",
                        "to_hit": 9,
                        "one_handed": {"damage_formula": "1d8 + str_mod + 2", "damage_type": "slashing"},
                        "effect": {
                            "on_hit": "1d6 hellfire damage. Apply Hellfire Stack condition (max 1 stack per target per turn).",
                            "save_ability": "con",
                            "save_dc": 17,
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 17,
            "target_cid": 2,
            "weapon_id": "hellfire_battleaxe_plus_2",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 6, 5]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 17)
        self.assertEqual(result.get("damage_entries"), [{"amount": 11, "type": "slashing"}, {"amount": 6, "type": "hellfire"}])
        self.assertEqual(result.get("on_hit_save"), {"ability": "con", "dc": 17})
        self.assertEqual(result.get("on_hit_save_result", {}).get("passed"), False)
        self.assertEqual(sum(1 for st in self.app.combatants[2].condition_stacks if getattr(st, "ctype", None) == "prone"), 1)
        self.assertEqual(len(getattr(self.app.combatants[2], "end_turn_damage_riders", []) or []), 1)
        self.assertEqual(self.app.combatants[2].hp, 3)

    def test_attack_request_on_hit_save_pass_does_not_apply_prone(self):
        self.app.combatants[2].saving_throws = {"con": 8}
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 20},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "hellfire_battleaxe_plus_2",
                        "name": "Hellfire Battleaxe (+2)",
                        "to_hit": 9,
                        "one_handed": {"damage_formula": "1d8 + str_mod + 2", "damage_type": "slashing"},
                        "effect": {
                            "on_hit": "1d6 hellfire damage. Apply Hellfire Stack condition (max 1 stack per target per turn).",
                            "save_ability": "con",
                            "save_dc": 17,
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 18,
            "target_cid": 2,
            "weapon_id": "hellfire_battleaxe_plus_2",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 6, 10]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("on_hit_save_result", {}).get("passed"))
        self.assertEqual(sum(1 for st in self.app.combatants[2].condition_stacks if getattr(st, "ctype", None) == "prone"), 0)

    def test_end_turn_cleanup_applies_hellfire_rider_damage(self):
        self.app.combatants[2].end_turn_damage_riders = [
            {"dice": "1d6", "type": "hellfire", "remaining_turns": 1, "source": "Hellfire Battleaxe (+2) (Aelar)"}
        ]
        with mock.patch.object(tracker_mod.base.InitiativeTracker, "_end_turn_cleanup", autospec=True) as base_cleanup:
            with mock.patch("dnd_initative_tracker.random.randint", return_value=4):
                self.app._end_turn_cleanup(2)

        base_cleanup.assert_called_once()
        self.assertEqual(self.app.combatants[2].hp, 16)
        self.assertEqual(getattr(self.app.combatants[2], "end_turn_damage_riders", []), [])
        self.assertTrue(any("takes 4 hellfire damage" in message for _, message in self.logs))

    def test_attack_request_removes_target_when_player_damage_drops_hp_to_zero(self):
        self.app.combatants[2].hp = 6
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 19,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
            "damage_entries": [{"amount": 6, "type": "slashing"}],
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn(2, self.app.combatants)
        self.assertTrue(any("dropped to 0 -> removed" in message for _, message in self.logs))

    def test_attack_request_allows_second_attack_when_attack_resource_remaining(self):
        first = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 20,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": False,
        }
        second = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 20,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": False,
        }

        self.app._lan_apply_action(first)
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 1)

        self.app._lan_apply_action(second)
        result = second.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("hit"))
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 0)

    def test_attack_request_nick_mastery_grants_dual_wield_extra_attack_once_per_turn(self):
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Rogue", "level": 10, "attacks_per_action": 1}]},
            "attacks": {
                "weapon_mastery_enabled": True,
                "weapons": [
                    {
                        "id": "scimitar_plus_1",
                        "name": "Scimitar +1",
                        "to_hit": 10,
                        "equipped": True,
                        "properties": ["finesse", "light", "nick"],
                    },
                    {
                        "id": "dagger",
                        "name": "Dagger",
                        "to_hit": 9,
                        "equipped": True,
                        "properties": ["finesse", "light", "thrown", "nick"],
                    },
                ],
            },
        }
        first = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 23,
            "target_cid": 2,
            "weapon_id": "scimitar_plus_1",
            "hit": False,
        }
        second = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 23,
            "target_cid": 2,
            "weapon_id": "dagger",
            "hit": False,
        }
        third = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 23,
            "target_cid": 2,
            "weapon_id": "scimitar_plus_1",
            "hit": False,
        }

        self.app._lan_apply_action(first)
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 1)
        self.assertEqual(first.get("_attack_result", {}).get("attack_count"), 2)

        self.app._lan_apply_action(second)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 0)
        self.assertFalse(second.get("_attack_result", {}).get("hit"))

        self.app.combatants[1].action_remaining = 1
        self.app._lan_apply_action(third)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 0)
        self.assertEqual(third.get("_attack_result", {}).get("attack_count"), 1)


if __name__ == "__main__":
    unittest.main()
