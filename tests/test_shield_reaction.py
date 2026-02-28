import unittest

import dnd_initative_tracker as tracker_mod


class ShieldReactionTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.toasts = []
        self.logs = []
        self.slot_spend_calls = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._mount_action_is_restricted = lambda *args, **kwargs: False
        self.app._find_action_entry = lambda c, spend, action: {"name": action}
        self.app._action_name_key = lambda v: str(v or "").strip().lower()
        self.app._lan_aura_effects_for_target = lambda target: {}
        self.app._adjust_damage_entries_for_target = lambda target, entries: {"entries": list(entries), "notes": []}
        self.app._apply_damage_to_target_with_temp_hp = lambda target, dmg: {"hp_after": max(0, int(target.hp) - int(dmg))}
        self.app._remove_combatants_with_lan_cleanup = lambda cids: None
        self.app._retarget_current_after_removal = lambda *args, **kwargs: None
        self.app._unit_has_sentinel_feat = lambda unit: False
        self.app._lan_apply_forced_movement = lambda *args, **kwargs: False
        self.app._clear_hide_state = lambda *args, **kwargs: None
        self.app._profile_for_player_name = lambda name: {
            "features": [],
            "attacks": {"weapon_to_hit": 5, "weapons": [{"id": "sword", "name": "Sword", "to_hit": 5, "effect": {}}]},
            "leveling": {"classes": [{"name": "Fighter", "attacks_per_action": 1}]},
            "spellcasting": {"prepared_spells": {"prepared": ["shield"]}},
        }
        self.app._pc_name_for = lambda cid: {1: "Eldramar", 2: "Enemy"}.get(int(cid), "PC")
        self.app._resolve_spell_slot_profile = lambda caster_name: (caster_name, {"1": {"current": 2}})
        self.app._consume_spell_slot_for_cast = lambda caster_name, slot_level, minimum_level: self.slot_spend_calls.append((caster_name, slot_level, minimum_level)) or (True, "", 1)
        self.app._consume_resource_pool_for_cast = lambda *args, **kwargs: (False, "")
        self.app._use_action = lambda c, **kwargs: True
        self.app._use_bonus_action = lambda c, **kwargs: True
        self.app._use_reaction = lambda c, **kwargs: setattr(c, "reaction_remaining", max(0, int(getattr(c, "reaction_remaining", 0)) - 1)) or True
        self.app._rebuild_table = lambda *args, **kwargs: None
        self.app._lan_force_state_broadcast = lambda *args, **kwargs: None
        self.app._log = lambda msg, **kwargs: self.logs.append(msg)
        self.app._find_ws_for_cid = lambda cid: [101] if int(cid) == 1 else [202]
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": object(),
                "_send_async": lambda _self, ws_id, payload: self.sent.append((ws_id, payload)),
                "play_ko": lambda *_args, **_kwargs: None,
            },
        )()
        self.app._name_role_memory = {"Eldramar": "pc", "Enemy": "enemy"}
        self.app._lan_positions = {1: (5, 5), 2: (6, 5)}
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, dict(self.app._lan_positions))
        self.app._map_window = None
        self.app._lan_aoes = {}
        self.app._pending_reaction_offers = {}
        self.app._pending_shield_resolutions = {}
        self.app._reaction_prefs_by_cid = {1: {"shield": "ask"}}
        self.app.in_combat = True
        self.app.current_cid = 2
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.start_cid = None
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Eldramar", "reaction_remaining": 1, "hp": 20, "ac": 12, "condition_stacks": [], "saving_throws": {}, "ability_mods": {}, "exhaustion_level": 0, "is_pc": True})(),
            2: type("C", (), {"cid": 2, "name": "Enemy", "reaction_remaining": 1, "action_remaining": 1, "bonus_action_remaining": 1, "attack_resource_remaining": 1, "move_remaining": 30, "move_total": 30, "hp": 20, "ac": 10, "condition_stacks": [], "is_pc": False})(),
        }

    def _attack_msg(self, attack_roll=11):
        return {
            "type": "attack_request",
            "cid": 2,
            "_claimed_cid": 2,
            "_ws_id": 77,
            "target_cid": 1,
            "weapon_id": "sword",
            "attack_roll": attack_roll,
            "damage_entries": [{"amount": 7, "type": "slashing"}],
        }

    def test_attack_hit_prompts_and_shield_turns_to_miss(self):
        self.app._lan_apply_action(self._attack_msg(11))  # total 16 vs AC 12
        offers = [payload for _ws, payload in self.sent if isinstance(payload, dict) and payload.get("type") == "reaction_offer" and payload.get("trigger") == "shield"]
        self.assertTrue(offers)
        req_id = offers[-1]["request_id"]
        self.assertIn(req_id, self.app._pending_shield_resolutions)

        self.app._lan_apply_action({"type": "reaction_response", "cid": 1, "_claimed_cid": 1, "_ws_id": 101, "request_id": req_id, "choice": "shield_yes"})

        attack_results = [payload for _ws, payload in self.sent if isinstance(payload, dict) and payload.get("type") == "attack_result"]
        self.assertTrue(attack_results)
        self.assertFalse(bool(attack_results[-1].get("hit")))
        self.assertEqual(int(attack_results[-1].get("damage_total") or 0), 0)
        self.assertTrue(bool(getattr(self.app.combatants[1], "_shield_reaction_active", False)))

    def test_magic_missile_shield_negates_damage(self):
        self.app._find_spell_preset = lambda slug, sid: {"slug": "magic-missile", "id": "magic-missile", "name": "Magic Missile", "mechanics": {"sequence": []}}
        self.app._infer_spell_targeting_mode = lambda preset: "auto_hit"
        msg = {"type": "spell_target_request", "cid": 2, "_claimed_cid": 2, "_ws_id": 77, "target_cid": 1, "spell_slug": "magic-missile", "spell_mode": "auto_hit", "damage_entries": [{"amount": 9, "type": "force"}]}
        self.app._lan_apply_action(msg)
        offers = [payload for _ws, payload in self.sent if isinstance(payload, dict) and payload.get("type") == "reaction_offer" and payload.get("trigger") == "shield"]
        self.assertTrue(offers)
        req_id = offers[-1]["request_id"]
        self.app._lan_apply_action({"type": "reaction_response", "cid": 1, "_claimed_cid": 1, "_ws_id": 101, "request_id": req_id, "choice": "shield_yes"})
        results = [payload for _ws, payload in self.sent if isinstance(payload, dict) and payload.get("type") == "spell_target_result"]
        self.assertTrue(results)
        self.assertEqual(int(results[-1].get("damage_total") or 0), 0)

    def test_shield_never_sets_pref(self):
        self.app._lan_apply_action(self._attack_msg(11))
        offers = [payload for _ws, payload in self.sent if isinstance(payload, dict) and payload.get("trigger") == "shield"]
        req_id = offers[-1]["request_id"]
        self.app._lan_apply_action({"type": "reaction_response", "cid": 1, "_claimed_cid": 1, "_ws_id": 101, "request_id": req_id, "choice": "shield_never"})
        self.assertEqual(self.app._reaction_mode_for(1, "shield", default="ask"), "off")


if __name__ == "__main__":
    unittest.main()
