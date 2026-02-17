import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class LanSpellTargetRequestTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Aelar"
        self.app._profile_for_player_name = lambda name: {}
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.start_cid = None
        self.app.current_cid = 1
        self.app._map_window = None
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Aelar", "ac": 16, "hp": 25})(),
            2: type(
                "C",
                (),
                {
                    "cid": 2,
                    "name": "Goblin",
                    "ac": 15,
                    "hp": 20,
                    "max_hp": 20,
                    "saving_throws": {"wis": 2},
                    "ability_mods": {"wis": 1},
                },
            )(),
        }
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._remove_combatants_with_lan_cleanup = lambda cids: [self.app.combatants.pop(int(cid), None) for cid in cids]
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_spell_target_request_save_passes_without_damage(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 9,
            "target_cid": 2,
            "spell_name": "Toll the Dead",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 13,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=15):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 0)
        self.assertFalse(result.get("hit"))
        self.assertTrue(result.get("save_result", {}).get("passed"))
        self.assertEqual(self.app.combatants[2].hp, 20)

    def test_spell_target_request_save_fail_requests_damage_prompt(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 10,
            "target_cid": 2,
            "spell_name": "Toll the Dead",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 16,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=4):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("needs_damage_prompt"))
        self.assertFalse(result.get("save_result", {}).get("passed"))
        self.assertEqual(self.app.combatants[2].hp, 20)

    def test_spell_target_request_applies_manual_damage(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 11,
            "target_cid": 2,
            "spell_name": "Fire Bolt",
            "spell_mode": "attack",
            "hit": True,
            "damage_entries": [{"amount": 9, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 9)
        self.assertEqual(self.app.combatants[2].hp, 11)
        self.assertIn((11, "Spell hits."), self.toasts)


    def test_spell_target_request_records_manual_critical_hit(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 12,
            "target_cid": 2,
            "spell_name": "Fire Bolt",
            "spell_mode": "attack",
            "hit": True,
            "critical": True,
            "damage_entries": [{"amount": 9, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("critical"))
        self.assertTrue(any("(CRIT)" in message for _, message in self.logs))


if __name__ == "__main__":
    unittest.main()

