import unittest

import dnd_initative_tracker as tracker_mod


class LanEndTurnGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.toasts = []
        self.next_turn_calls = 0

        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app.in_combat = True
        self.app.current_cid = 1
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alice"})(),
            2: type("C", (), {"cid": 2, "name": "Bob"})(),
        }
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
            },
        )()

        def _next_turn():
            self.next_turn_calls += 1
            self.app.current_cid = 2

        self.app._next_turn = _next_turn

    def test_end_turn_is_ignored_after_turn_already_advanced(self):
        msg = {"type": "end_turn", "cid": 1, "_claimed_cid": 1, "_ws_id": 7}

        self.app._lan_apply_action(dict(msg))
        self.app._lan_apply_action(dict(msg))

        self.assertEqual(self.next_turn_calls, 1)
        self.assertIn((7, "Turn ended."), self.toasts)
        self.assertIn((7, "Not yer turn yet, matey."), self.toasts)


if __name__ == "__main__":
    unittest.main()
