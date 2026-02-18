import unittest

import dnd_initative_tracker as tracker_mod


class LanAuraToggleTests(unittest.TestCase):
    def test_set_auras_enabled_does_not_require_claimed_character(self):
        toasts = []
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._is_admin_token_valid = lambda token: False
        app._summon_can_be_controlled_by = lambda claimed, target: False
        app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        app._lan_auras_enabled = True
        app.in_combat = True
        app.current_cid = 1
        app.round_num = 1
        app.turn_num = 1
        app.start_cid = None
        app.combatants = {}
        app._lan_force_state_broadcast = lambda: None
        app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

        app._lan_apply_action(
            {
                "type": "set_auras_enabled",
                "enabled": False,
                "_ws_id": 1,
                "_claimed_cid": None,
            }
        )

        self.assertFalse(app._lan_auras_enabled)
        self.assertFalse(any("Claim a character first" in text for _ws, text in toasts))


if __name__ == "__main__":
    unittest.main()
