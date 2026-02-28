import unittest

import dnd_initative_tracker as tracker_mod


class LanReactionPromptTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.toasts = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: {1: "Sentinel", 2: "Enemy", 3: "Victim"}.get(int(cid), "PC")
        self.app._profile_for_player_name = lambda name: {
            "features": [{"name": "Sentinel"}] if name == "Sentinel" else [],
            "attacks": {"weapon_to_hit": 5, "weapons": [{"id": "sword", "name": "Sword", "to_hit": 6}]},
            "leveling": {"classes": [{"name": "Fighter", "attacks_per_action": 1}]},
        }
        self.app._log = lambda *args, **kwargs: None
        self.app._rebuild_table = lambda *args, **kwargs: None
        self.app._mount_action_is_restricted = lambda *args, **kwargs: False
        self.app._use_action = lambda c: True
        self.app._use_bonus_action = lambda c: True
        self.app._use_reaction = lambda c: setattr(c, "reaction_remaining", max(0, int(getattr(c, "reaction_remaining", 0)) - 1)) or True
        self.app._find_action_entry = lambda c, spend, action: {"name": action}
        self.app._action_name_key = lambda v: str(v or "").strip().lower()
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": object(),
                "_send_async": lambda _self, ws_id, payload: self.sent.append((ws_id, payload)),
            },
        )()
        self.app._name_role_memory = {"Sentinel": "pc", "Enemy": "enemy", "Victim": "enemy"}
        self.app._lan_positions = {1: (5, 5), 2: (6, 5), 3: (10, 10)}
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, dict(self.app._lan_positions))
        self.app._map_window = None
        self.app._lan_aoes = {}
        self.app._find_ws_for_cid = lambda cid: [101] if int(cid) == 1 else []
        self.app._pending_reaction_offers = {}
        self.app._reaction_prefs_by_cid = {1: {"opportunity_attack": "ask", "war_caster": "off"}}
        self.app.in_combat = True
        self.app.current_cid = 2
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.start_cid = None
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Sentinel", "reaction_remaining": 1, "reactions": [{"name": "Opportunity Attack", "type": "reaction"}]})(),
            2: type("C", (), {"cid": 2, "name": "Enemy", "reaction_remaining": 1, "action_remaining": 1, "bonus_action_remaining": 1, "attack_resource_remaining": 0, "move_remaining": 30, "move_total": 30, "hp": 20, "ac": 10, "condition_stacks": []})(),
            3: type("C", (), {"cid": 3, "name": "Victim", "reaction_remaining": 1, "hp": 20, "ac": 10, "condition_stacks": [], "saving_throws": {}, "ability_mods": {}, "exhaustion_level": 0})(),
        }

    def test_move_triggers_reaction_offer(self):
        self.app._lan_apply_action({"type": "move", "cid": 2, "_claimed_cid": 2, "_ws_id": 55, "to": {"col": 8, "row": 5}})
        self.assertTrue(any(payload.get("type") == "reaction_offer" for _ws, payload in self.sent))

    def test_disengage_triggers_sentinel_guardian_offer(self):
        self.app._lan_apply_action({"type": "perform_action", "cid": 2, "_claimed_cid": 2, "_ws_id": 55, "spend": "action", "action": "Disengage"})
        self.assertTrue(any(payload.get("trigger") == "sentinel_disengage" for _ws, payload in self.sent if isinstance(payload, dict)))

    def test_sentinel_oa_hit_halts_target(self):
        req_id = "abc"
        self.app._pending_reaction_offers[req_id] = {"reactor_cid": 1, "target_cid": 2, "expires_at": 9999999999}
        self.app.combatants[1].action_remaining = 1
        self.app.combatants[1].attack_resource_remaining = 0
        self.app._lan_apply_action({"type": "attack_request", "cid": 1, "_claimed_cid": 1, "_ws_id": 77, "target_cid": 2, "weapon_id": "sword", "hit": True, "opportunity_attack": True, "reaction_request_id": req_id})
        self.assertEqual(getattr(self.app.combatants[2], "move_remaining", 0), 0)
        self.assertTrue(bool(getattr(self.app.combatants[2], "speed_zero_until_turn_end", False)))

    def test_invalid_reaction_request_id_rejected(self):
        self.app.combatants[1].action_remaining = 1
        self.app._lan_apply_action({"type": "attack_request", "cid": 1, "_claimed_cid": 1, "_ws_id": 77, "target_cid": 2, "weapon_id": "sword", "hit": True, "opportunity_attack": True, "reaction_request_id": "missing"})
        self.assertIn((77, "That reaction request expired, matey."), self.toasts)


if __name__ == "__main__":
    unittest.main()
