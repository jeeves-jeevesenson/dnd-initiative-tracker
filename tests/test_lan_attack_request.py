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
        self.app._map_window = None
        self.app._name_role_memory = {"Aelar": "pc", "Goblin": "enemy"}
        self.app._lan_positions = {1: (5, 5), 2: (5, 4)}
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, dict(self.app._lan_positions))
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
                    "exhaustion_level": 0,
                    "saving_throws": {},
                    "ability_mods": {},
                },
            )(),
        }
        self.app.combatants[1].exhaustion_level = 0
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].reaction_remaining = 1
        self.app.combatants[1].bonus_action_remaining = 1
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

    def test_wild_shape_attack_request_accepts_inline_weapon_payload(self):
        self.app.combatants[1].is_wild_shaped = True
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Druid", "level": 8}]},
            "attacks": {"weapon_to_hit": 0, "weapons": []},
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 44,
            "target_cid": 2,
            "weapon_id": "bite",
            "weapon_name": "Bite",
            "weapon": {
                "id": "bite",
                "name": "Bite",
                "to_hit": 5,
                "range": "5 ft",
                "category": "melee_weapon",
                "one_handed": {"damage_formula": "1d8 + 3", "damage_type": "piercing"},
            },
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("weapon_name"), "Bite")
        self.assertEqual(result.get("damage_total"), 7)
        self.assertEqual(result.get("damage_entries", [])[0].get("type"), "piercing")

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

    def test_wild_shape_attack_count_grants_matching_attack_resources(self):
        self.app.combatants[1].is_wild_shaped = True
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].attack_resource_remaining = 0
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Druid", "level": 8}]},
            "attacks": {"weapon_to_hit": 0, "weapons": []},
        }
        base_msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 45,
            "target_cid": 2,
            "weapon": {
                "id": "claw",
                "name": "Claw",
                "to_hit": 5,
                "range": "5 ft",
                "category": "melee_weapon",
                "one_handed": {"damage_formula": "1d4 + 3", "damage_type": "slashing"},
            },
            "attack_count": 2,
            "hit": True,
        }

        self.app._lan_apply_action(dict(base_msg))
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 1)

        self.app._lan_apply_action(dict(base_msg))
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 0)

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

    def test_echo_attack_uses_owner_weapon_profile(self):
        self.app.combatants[3] = type(
            "C",
            (),
            {
                "cid": 3,
                "name": "Johns Echo",
                "ac": 14,
                "hp": 1,
                "condition_stacks": [],
                "exhaustion_level": 0,
                "summoned_by_cid": 1,
                "summon_source_spell": "echo_knight",
                "summon_shared_turn": True,
            },
        )()
        self.app._summon_can_be_controlled_by = lambda claimed, target: int(claimed) == 1 and int(target) == 3
        self.app._pc_name_for = lambda cid: "John Twilight" if int(cid) == 1 else "Unknown"
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 11, "attacks_per_action": 3}]},
            "attacks": {
                "weapon_to_hit": 6,
                "weapons": [
                    {"id": "greatsword", "name": "Greatsword", "to_hit": 9},
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 3,
            "_claimed_cid": 1,
            "_ws_id": 52,
            "target_cid": 2,
            "attack_roll": 10,
            "weapon_id": "greatsword",
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("weapon_name"), "Greatsword")
        self.assertEqual(result.get("to_hit"), 9)

    def test_echo_attack_consumes_owner_action_and_attack_resources(self):
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].attack_resource_remaining = 0
        self.app.combatants[3] = type(
            "C",
            (),
            {
                "cid": 3,
                "name": "Johns Echo",
                "ac": 14,
                "hp": 1,
                "condition_stacks": [],
                "exhaustion_level": 0,
                "summoned_by_cid": 1,
                "summon_source_spell": "echo_knight",
                "summon_shared_turn": True,
                "action_remaining": 1,
                "attack_resource_remaining": 0,
            },
        )()
        self.app._summon_can_be_controlled_by = lambda claimed, target: int(claimed) == 1 and int(target) == 3
        self.app._pc_name_for = lambda cid: "John Twilight" if int(cid) == 1 else "Unknown"
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 5, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [
                    {"id": "longsword", "name": "Longsword", "to_hit": 7},
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 3,
            "_claimed_cid": 1,
            "_ws_id": 53,
            "target_cid": 2,
            "attack_roll": 11,
            "weapon_id": "longsword",
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 1)
        self.assertEqual(self.app.combatants[3].action_remaining, 1)
        self.assertEqual(self.app.combatants[3].attack_resource_remaining, 0)
        self.assertEqual(result.get("attack_resource_remaining"), 1)

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

    def test_attack_request_bonus_spend_succeeds_without_action_and_does_not_consume_action(self):
        self.app.combatants[1].action_remaining = 0
        self.app.combatants[1].attack_resource_remaining = 0
        self.app.combatants[1].bonus_action_remaining = 1
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 131,
            "target_cid": 2,
            "weapon_id": "longsword",
            "attack_spend": "bonus",
            "bonus_sequence_total": 1,
            "bonus_sequence_start": True,
            "hit": False,
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn((131, "No attacks left, matey."), self.toasts)
        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(self.app.combatants[1].bonus_action_remaining, 0)
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 0)

    def test_attack_request_bonus_spend_rejects_when_no_bonus_action(self):
        self.app.combatants[1].action_remaining = 0
        self.app.combatants[1].attack_resource_remaining = 0
        self.app.combatants[1].bonus_action_remaining = 0
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 132,
            "target_cid": 2,
            "weapon_id": "longsword",
            "attack_spend": "bonus",
            "bonus_sequence_total": 1,
            "bonus_sequence_start": True,
            "hit": False,
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn("_attack_result", msg)
        self.assertIn((132, "No bonus actions left, matey."), self.toasts)

    def test_attack_request_consumes_pool_always_consumes_even_when_hit_with_zero_damage(self):
        calls = []

        def consume_pool(_owner_name, pool_id, cost):
            calls.append((pool_id, cost))
            return True, ""

        self.app._consume_resource_pool_for_cast = consume_pool
        self.app._profile_for_player_name = lambda _name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [
                    {
                        "id": "empty_strike",
                        "name": "Empty Strike",
                        "to_hit": 7,
                        "one_handed": {"damage_formula": "", "damage_type": "bludgeoning"},
                    },
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 133,
            "target_cid": 2,
            "weapon_id": "empty_strike",
            "hit": True,
            "consumes_pool": {"id": "focus_points", "cost": 1},
            "consumes_pool_always": True,
        }

        self.app._lan_apply_action(msg)

        self.assertIsInstance(msg.get("_attack_result"), dict)
        self.assertEqual(calls, [("focus_points", 1)])

    def test_opportunity_attack_can_resolve_out_of_turn_without_spending_action(self):
        self.app.current_cid = 2
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: target == current
        self.app.combatants[1].action_remaining = 0
        self.app.combatants[1].attack_resource_remaining = 0
        self.app.combatants[1].reaction_remaining = 1
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 30,
            "target_cid": 2,
            "weapon_id": "longsword",
            "opportunity_attack": True,
            "hit": False,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("hit"))
        self.assertEqual(self.app.combatants[1].reaction_remaining, 0)
        self.assertEqual(self.app.combatants[1].action_remaining, 0)
        self.assertEqual(self.app.combatants[1].attack_resource_remaining, 0)
        self.assertNotIn((30, "Not yer turn yet, matey."), self.toasts)

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
        self.assertTrue(
            any(
                "Aelar deals 9 total damage with Longsword to Goblin (7 slashing, 2 fire)." in message
                for _, message in self.logs
            )
        )

    def test_attack_request_includes_critical_flag_and_logs_crit(self):
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 24,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
            "critical": True,
            "damage_entries": [{"amount": 4, "type": "slashing"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("critical"))
        self.assertTrue(any("(CRIT)" in message for _, message in self.logs))


    def test_attack_request_auto_roll_adds_magic_bonus_to_damage_once(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "longsword_plus_1",
                        "name": "Longsword (+1)",
                        "to_hit": 7,
                        "magic_bonus": 1,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "slashing"},
                    }
                ]
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 61,
            "target_cid": 2,
            "weapon_id": "longsword_plus_1",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 10)
        self.assertEqual(result.get("damage_entries"), [{"amount": 9, "type": "slashing"}, {"amount": 1, "type": "slashing"}])

    def test_attack_request_auto_roll_does_not_double_add_magic_bonus_when_embedded(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "hellfire_battleaxe_plus_2",
                        "name": "Hellfire Battleaxe (+2)",
                        "to_hit": 9,
                        "magic_bonus": 2,
                        "one_handed": {"damage_formula": "1d8 + str_mod + 2", "damage_type": "slashing"},
                    }
                ]
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 62,
            "target_cid": 2,
            "weapon_id": "hellfire_battleaxe_plus_2",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 10)
        self.assertEqual(result.get("damage_entries"), [{"amount": 10, "type": "slashing"}])

    def test_attack_request_auto_crit_doubles_dice_not_modifiers(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "flame_blade",
                        "name": "Flame Blade",
                        "to_hit": 8,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "slashing"},
                        "effect": {"on_hit": "1d6 fire damage."},
                    }
                ]
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 63,
            "target_cid": 2,
            "weapon_id": "flame_blade",
            "hit": True,
            "critical": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 5, 2, 6]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("critical"))
        self.assertEqual(result.get("damage_entries"), [{"amount": 13, "type": "slashing"}, {"amount": 8, "type": "fire"}])
        self.assertEqual(result.get("damage_total"), 21)
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

    def test_attack_request_sword_of_wounding_applies_one_wound_stack_per_turn(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 20},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "sword_of_wounding",
                        "name": "Sword of Wounding",
                        "to_hit": 9,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "slashing"},
                        "effect": {"on_hit": "", "save_ability": "", "save_dc": 0},
                    }
                ]
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 21,
            "target_cid": 2,
            "weapon_id": "sword_of_wounding",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 5]):
            self.app._lan_apply_action(msg)
            self.app._lan_apply_action(dict(msg))

        self.assertEqual(len(getattr(self.app.combatants[2], "start_turn_damage_riders", []) or []), 1)
        self.assertTrue(any("wounds Goblin" in message for _, message in self.logs))

    def test_process_start_of_turn_sword_of_wounding_rolls_save_and_ends_stacks(self):
        self.app.combatants[2].saving_throws = {"con": 5}
        self.app.combatants[2].start_turn_damage_riders = [
            {
                "dice": "1d4",
                "type": "necrotic",
                "source": "Sword of Wounding (Aelar)",
                "save_ability": "con",
                "save_dc": 15,
                "clear_group": "sword_of_wounding",
            },
            {
                "dice": "1d4",
                "type": "necrotic",
                "source": "Sword of Wounding (Aelar)",
                "save_ability": "con",
                "save_dc": 15,
                "clear_group": "sword_of_wounding",
            },
        ]

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[3, 2, 10]):
            _, msg, _ = self.app._process_start_of_turn(self.app.combatants[2])

        self.assertEqual(self.app.combatants[2].hp, 15)
        self.assertEqual(getattr(self.app.combatants[2], "start_turn_damage_riders", []), [])
        self.assertIn("takes 3 necrotic", msg)
        self.assertIn("takes 2 necrotic", msg)
        self.assertIn("CON save DC 15: 10 + 5 = 15 (PASS)", msg)

    def test_smite_cast_sets_charge_and_next_melee_hit_consumes_it(self):
        self.app._find_spell_preset = lambda **_kwargs: {
            "slug": "searing-smite",
            "id": "searing-smite",
            "name": "Searing Smite",
            "level": 1,
            "action_type": "bonus_action",
            "tags": ["smite"],
            "summon": None,
        }
        self.app._consume_spell_slot_for_cast = lambda **_kwargs: (True, "", 1)
        self.app._combatant_can_cast_spell = lambda *_args, **_kwargs: True
        self.app._use_bonus_action = lambda *_args, **_kwargs: True
        self.app._use_action = lambda *_args, **_kwargs: True
        self.app._use_reaction = lambda *_args, **_kwargs: True
        self.app._rebuild_table = lambda *args, **kwargs: None
        self.app._lan_force_state_broadcast = lambda: None
        self.app._profile_for_player_name = lambda _name: {
            "abilities": {"str": 16},
            "leveling": {"classes": [{"name": "Paladin", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "longsword",
                        "name": "Longsword",
                        "to_hit": 7,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "slashing"},
                    }
                ]
            },
        }
        self.app.combatants[1].spell_cast_remaining = 1
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].bonus_action_remaining = 1

        self.app._lan_apply_action(
            {
                "type": "cast_spell",
                "cid": 1,
                "_claimed_cid": 1,
                "_ws_id": 52,
                "spell_slug": "searing-smite",
                "slot_level": 1,
                "action_type": "bonus_action",
                "payload": {"spell_slug": "searing-smite", "slot_level": 1, "action_type": "bonus_action"},
            }
        )

        self.assertEqual((getattr(self.app.combatants[1], "pending_smite_charge", {}) or {}).get("slug"), "searing-smite")
        self.assertEqual(self.app.combatants[1].bonus_action_remaining, 1)
        self.assertEqual(self.app.combatants[1].action_remaining, 1)

        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 53,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 5]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result") or {}
        self.assertEqual(result.get("smite", {}).get("slug"), "searing-smite")
        self.assertEqual(result.get("damage_total"), 12)
        self.assertIsNone(getattr(self.app.combatants[1], "pending_smite_charge", None))
        self.assertEqual(len(getattr(self.app.combatants[2], "start_turn_damage_riders", []) or []), 1)

    def test_blinding_smite_start_turn_save_ends_condition(self):
        self.app._profile_for_player_name = lambda _name: {
            "abilities": {"str": 16},
            "leveling": {"classes": [{"name": "Paladin", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapons": [
                    {
                        "id": "longsword",
                        "name": "Longsword",
                        "to_hit": 7,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "slashing"},
                    }
                ]
            },
        }
        self.app.combatants[1].pending_smite_charge = {
            "slug": "blinding-smite",
            "name": "Blinding Smite",
            "slot_level": 3,
            "save_dc": 13,
        }
        self.app.combatants[2].hp = 80
        self.app.combatants[1].spell_cast_remaining = 1
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].bonus_action_remaining = 1
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 54,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 6, 5, 3, 3]):
            self.app._lan_apply_action(msg)

        self.assertTrue(any(getattr(st, "ctype", None) == "blinded" for st in self.app.combatants[2].condition_stacks))
        self.assertEqual(len(getattr(self.app.combatants[2], "start_turn_save_riders", []) or []), 1)

        self.app.combatants[2].saving_throws = {"con": 4}
        with mock.patch("dnd_initative_tracker.random.randint", return_value=9):
            _, start_msg, _ = self.app._process_start_of_turn(self.app.combatants[2])

        self.assertIn("CON save DC 13: 9 + 4 = 13 (PASS)", start_msg)
        self.assertFalse(any(getattr(st, "ctype", None) == "blinded" for st in self.app.combatants[2].condition_stacks))
        self.assertEqual(getattr(self.app.combatants[2], "start_turn_save_riders", []), [])

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

    def test_attack_request_graze_mastery_deals_damage_on_miss(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_mastery_enabled": True,
                "weapons": [
                    {
                        "id": "greatsword",
                        "name": "Greatsword",
                        "to_hit": 8,
                        "one_handed": {"damage_formula": "2d6 + str_mod", "damage_type": "slashing"},
                        "properties": ["graze", "heavy", "two_handed"],
                    }
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 24,
            "target_cid": 2,
            "weapon_id": "greatsword",
            "hit": False,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 4)
        self.assertEqual(result.get("damage_entries"), [{"amount": 4, "type": "slashing"}])
        self.assertIn("Graze deals 4 damage on the miss.", result.get("weapon_property_notes", []))
        self.assertEqual(self.app.combatants[2].hp, 16)

    def test_attack_request_push_mastery_adds_hit_note(self):
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_mastery_enabled": True,
                "weapons": [
                    {
                        "id": "greatclub",
                        "name": "Greatclub",
                        "to_hit": 8,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "bludgeoning"},
                        "properties": ["push", "two_handed"],
                    }
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 25,
            "target_cid": 2,
            "weapon_id": "greatclub",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=5):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertIn("Push: move that Large-or-smaller target up to 10 ft away.", result.get("weapon_property_notes", []))

    def test_attack_request_push_mastery_moves_target_two_squares_in_facing_direction(self):
        self.app.combatants[1].facing_deg = 0
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_mastery_enabled": True,
                "weapons": [
                    {
                        "id": "greatclub",
                        "name": "Greatclub",
                        "to_hit": 8,
                        "one_handed": {"damage_formula": "1d8 + str_mod", "damage_type": "bludgeoning"},
                        "properties": ["push", "two_handed"],
                    }
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 26,
            "target_cid": 2,
            "weapon_id": "greatclub",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=5):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.app._lan_positions.get(2), (5, 2))

    def test_attack_request_cleave_mastery_exposes_nearby_free_attack_candidates(self):
        self.app.combatants[3] = type("C", (), {"cid": 3, "name": "Orc", "ac": 13, "hp": 12, "condition_stacks": []})()
        self.app._lan_positions[3] = (6, 5)
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"str": 18},
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_mastery_enabled": True,
                "weapons": [
                    {
                        "id": "greataxe",
                        "name": "Greataxe",
                        "to_hit": 8,
                        "one_handed": {"damage_formula": "1d12 + str_mod", "damage_type": "slashing"},
                        "properties": ["cleave", "heavy", "two_handed"],
                    }
                ],
            },
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 27,
            "target_cid": 2,
            "weapon_id": "greataxe",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=6):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        candidates = result.get("cleave_candidates", [])
        self.assertTrue(any(int(entry.get("cid")) == 3 for entry in candidates))

    def test_attack_request_applies_once_per_turn_feature_rider_once(self):
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Rogue", "level": 10, "attacks_per_action": 1}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [
                    {
                        "id": "rapier",
                        "name": "Rapier",
                        "to_hit": 7,
                        "properties": ["finesse"],
                        "one_handed": {"damage_formula": "1d8 + dex_mod", "damage_type": "piercing"},
                    }
                ],
            },
            "feature_effects": {
                "damage_riders": [
                    {
                        "id": "sneak_attack",
                        "trigger": ["finesse_weapon_attack"],
                        "once_per_turn": True,
                        "damage_formula": "1d6",
                        "damage_type": "same_as_attack",
                    }
                ]
            },
        }
        first = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 33,
            "target_cid": 2,
            "weapon_id": "rapier",
            "hit": True,
            "damage_entries": [{"amount": 3, "type": "piercing"}],
        }
        second = dict(first)
        second["_ws_id"] = 34
        with mock.patch("dnd_initative_tracker.random.randint", return_value=1):
            self.app._lan_apply_action(first)
            self.app.combatants[1].action_remaining = 1
            self.app._lan_apply_action(second)
        self.assertEqual((first.get("_attack_result") or {}).get("damage_total"), 4)
        self.assertEqual((second.get("_attack_result") or {}).get("damage_total"), 3)


    def test_attack_request_applies_dorian_aura_bonus_to_saves(self):
        self.app.combatants[3] = type(
            "C",
            (),
            {
                "cid": 3,
                "name": "Dorian",
                "ac": 18,
                "hp": 80,
                "condition_stacks": [],
                "ability_mods": {"cha": 4},
            },
        )()
        self.app.combatants[4] = type(
            "C",
            (),
            {
                "cid": 4,
                "name": "Lyra",
                "ac": 14,
                "hp": 30,
                "condition_stacks": [],
                "saving_throws": {"con": 1},
                "ability_mods": {"con": 1},
            },
        )()
        self.app._name_role_memory.update({"Aelar": "enemy", "Dorian": "pc", "Lyra": "ally", "Goblin": "enemy"})
        self.app._lan_positions[3] = (5, 5)
        self.app._lan_positions[4] = (6, 5)
        def _profile_for_name(name):
            if str(name).strip().lower() == "dorian":
                return {
                    "abilities": {"cha": 18},
                    "features": [
                        {
                            "id": "aura_of_protection_2024",
                            "grants": {
                                "aura": {
                                    "id": "aura_of_protection_2024",
                                    "name": "Aura of Protection",
                                    "radius_ft": 10,
                                    "save_bonus": {"ability_mod": "cha", "minimum": 1},
                                    "damage_resistances": ["necrotic", "psychic", "radiant"],
                                }
                            },
                        }
                    ],
                }
            return {
                "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
                "attacks": {
                    "weapons": [
                        {
                            "id": "test-weapon",
                            "name": "Test Weapon",
                            "to_hit": 7,
                            "one_handed": {"damage_formula": "1d6", "damage_type": "slashing"},
                            "effect": {"on_hit": "", "save_ability": "con", "save_dc": 30},
                        }
                    ]
                },
            }

        self.app._profile_for_player_name = _profile_for_name
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 28,
            "target_cid": 4,
            "weapon_id": "test-weapon",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 10]):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        save_result = result.get("on_hit_save_result")
        self.assertIsInstance(save_result, dict)
        self.assertEqual(save_result.get("modifier"), 5)

    def test_attack_request_applies_dorian_aura_damage_resistance(self):
        self.app.combatants[3] = type(
            "C",
            (),
            {
                "cid": 3,
                "name": "Dorian",
                "ac": 18,
                "hp": 80,
                "condition_stacks": [],
                "ability_mods": {"cha": 4},
            },
        )()
        self.app.combatants[4] = type(
            "C",
            (),
            {
                "cid": 4,
                "name": "Lyra",
                "ac": 14,
                "hp": 30,
                "condition_stacks": [],
                "saving_throws": {},
                "ability_mods": {},
            },
        )()
        self.app._name_role_memory.update({"Aelar": "enemy", "Dorian": "pc", "Lyra": "ally"})
        self.app._lan_positions[3] = (5, 5)
        self.app._lan_positions[4] = (6, 5)
        self.app._profile_for_player_name = lambda name: {
            "abilities": {"cha": 18},
            "features": [
                {
                    "id": "aura_of_protection_2024",
                    "grants": {
                        "aura": {
                            "id": "aura_of_protection_2024",
                            "name": "Aura of Protection",
                            "radius_ft": 10,
                            "save_bonus": {"ability_mod": "cha", "minimum": 1},
                            "damage_resistances": ["necrotic", "psychic", "radiant"],
                        }
                    },
                }
            ],
        } if str(name).strip().lower() == "dorian" else {
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {"weapon_to_hit": 5, "weapons": [{"id": "longsword", "name": "Longsword", "to_hit": 7}]},
        }
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 29,
            "target_cid": 4,
            "weapon_id": "longsword",
            "hit": True,
            "damage_entries": [{"amount": 9, "type": "radiant"}],
        }

        self.app._lan_apply_action(msg)

        self.assertEqual(self.app.combatants[4].hp, 26)
        result = msg.get("_attack_result")
        self.assertEqual(result.get("damage_entries"), [{"amount": 4, "type": "radiant"}])

    def test_attack_request_applies_monster_spec_damage_resistance_and_immunity(self):
        self.app.combatants[2].monster_spec = type(
            "Spec",
            (),
            {"raw_data": {"damage_resistances": ["slashing"], "damage_immunities": ["fire"]}},
        )()
        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 30,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
            "damage_entries": [{"amount": 10, "type": "slashing"}, {"amount": 10, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 5)
        self.assertEqual(result.get("damage_entries"), [{"amount": 5, "type": "slashing"}])
        self.assertEqual(self.app.combatants[2].hp, 15)

    def test_attack_request_logs_total_damage_and_resistance_adjustments_for_gray_ooze(self):
        self.app._monster_specs = []
        self.app._monsters_by_name = {}
        self.app._load_monsters_index()
        ooze_spec = self.app._find_monster_spec_by_slug("Monsters/gray-ooze.yaml")
        self.assertIsNotNone(ooze_spec)
        self.app.combatants[2].monster_spec = ooze_spec
        self.app.combatants[2].name = "Gray Ooze"

        msg = {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
            "damage_entries": [
                {"amount": 1, "type": "slashing"},
                {"amount": 1, "type": "lightning"},
                {"amount": 6, "type": "acid"},
                {"amount": 6, "type": "cold"},
            ],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 8)
        self.assertEqual(
            result.get("damage_entries"),
            [
                {"amount": 1, "type": "slashing"},
                {"amount": 1, "type": "lightning"},
                {"amount": 3, "type": "acid"},
                {"amount": 3, "type": "cold"},
            ],
        )
        self.assertEqual(self.app.combatants[2].hp, 12)
        self.assertTrue(
            any(
                "Aelar deals 8 total damage with Longsword to Gray Ooze (1 slashing, 1 lightning, 3 acid (resist!), 3 cold (resist!))."
                in message
                for _, message in self.logs
            )
        )


if __name__ == "__main__":
    unittest.main()
