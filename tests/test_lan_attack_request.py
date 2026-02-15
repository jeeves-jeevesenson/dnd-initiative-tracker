import unittest

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
        self.app.current_cid = 1
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Aelar", "ac": 16})(),
            2: type("C", (), {"cid": 2, "name": "Goblin", "ac": 15})(),
        }
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


if __name__ == "__main__":
    unittest.main()
