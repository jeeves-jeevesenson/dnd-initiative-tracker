import unittest

import dnd_initative_tracker as tracker_mod


class LanManualOverrideTests(unittest.TestCase):
    def _build_app(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._is_admin_token_valid = lambda token: False
        app._summon_can_be_controlled_by = lambda claimed, target: False
        app._pc_name_for = lambda cid: "Alyra"
        app._log_messages = []
        app._log = lambda message, cid=None: app._log_messages.append((cid, message))
        app._rebuild_calls = 0
        app._rebuild_table = lambda scroll_to_current=True: setattr(app, "_rebuild_calls", app._rebuild_calls + 1)
        app._broadcast_calls = 0
        app._lan_force_state_broadcast = lambda: setattr(app, "_broadcast_calls", app._broadcast_calls + 1)
        app.in_combat = True
        app.current_cid = 1
        app.round_num = 1
        app.turn_num = 1
        app.start_cid = None
        app._lan_toasts = []
        app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: app._lan_toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()
        return app

    def test_manual_override_hp_clamps_and_logs(self):
        app = self._build_app()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alyra", "hp": 14, "max_hp": 20, "temp_hp": 3})(),
        }

        app._lan_apply_action(
            {"type": "manual_override_hp", "cid": 1, "_claimed_cid": 1, "_ws_id": 15, "hp_delta": 99, "temp_hp_delta": -5}
        )

        self.assertEqual(app.combatants[1].hp, 20)
        self.assertEqual(app.combatants[1].temp_hp, 0)
        self.assertEqual(app._rebuild_calls, 1)
        self.assertEqual(app._broadcast_calls, 1)
        self.assertTrue(any("manual override" in message for _cid, message in app._log_messages))
        self.assertIn((15, "Manual override applied."), app._lan_toasts)

    def test_manual_override_spell_slot_updates_and_saves(self):
        app = self._build_app()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alyra"})(),
        }
        saved_payloads = []
        app._resolve_spell_slot_profile = lambda name: (
            name,
            {"1": {"current": 1, "max": 4}, "2": {"current": 0, "max": 2}},
        )
        app._save_player_spell_slots = lambda name, payload: saved_payloads.append((name, payload))

        app._lan_apply_action(
            {"type": "manual_override_spell_slot", "cid": 1, "_claimed_cid": 1, "_ws_id": 16, "slot_level": 1, "delta": 2}
        )

        self.assertEqual(saved_payloads[0][0], "Alyra")
        self.assertEqual(saved_payloads[0][1]["1"]["current"], 3)
        self.assertEqual(app._rebuild_calls, 1)
        self.assertEqual(app._broadcast_calls, 1)
        self.assertIn((16, "Level 1 spell slots updated."), app._lan_toasts)

    def test_manual_override_resource_pool_updates_and_logs(self):
        app = self._build_app()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alyra"})(),
        }
        app._profile_for_player_name = lambda name: {"resources": {"pools": [{"id": "focus_points"}]}}
        app._normalize_player_resource_pools = lambda profile: [
            {"id": "focus_points", "label": "Focus Points", "current": 2, "max": 4}
        ]
        set_calls = []
        app._set_player_resource_pool_current = lambda name, pool_id, current: (
            set_calls.append((name, pool_id, current)) or True,
            "",
        )

        app._lan_apply_action(
            {"type": "manual_override_resource_pool", "cid": 1, "_claimed_cid": 1, "_ws_id": 17, "pool_id": "focus_points", "delta": -1}
        )

        self.assertEqual(set_calls, [("Alyra", "focus_points", 1)])
        self.assertEqual(app._rebuild_calls, 1)
        self.assertEqual(app._broadcast_calls, 1)
        self.assertTrue(any("Focus Points 2->1 (-1)" in message for _cid, message in app._log_messages))
        self.assertIn((17, "Focus Points updated."), app._lan_toasts)


if __name__ == "__main__":
    unittest.main()
