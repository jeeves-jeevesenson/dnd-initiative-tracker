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
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: current is None
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

    def test_end_turn_allows_shared_turn_summon_target(self):
        self.app.combatants[10] = type(
            "C",
            (),
            {"cid": 10, "name": "Summon", "summoned_by_cid": 1, "summon_shared_turn": True},
        )()
        self.app._summon_can_be_controlled_by = lambda claimed, target: claimed == 1 and target == 10
        self.app._is_valid_summon_turn_for_controller = (
            lambda controlling, target, current: current is None
            or (controlling == 1 and target == 10 and current == 1)
        )

        self.app._lan_apply_action({"type": "end_turn", "cid": 10, "_claimed_cid": 1, "_ws_id": 7})

        self.assertEqual(self.next_turn_calls, 1)
        self.assertIn((7, "Turn ended."), self.toasts)

    def test_should_skip_turn_for_shared_summon(self):
        self.app.combatants[10] = type(
            "C",
            (),
            {"cid": 10, "name": "Summon", "summoned_by_cid": 1, "summon_shared_turn": True},
        )()

        self.assertTrue(self.app._should_skip_turn(10))


class SummonTurnValidationTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Eldramar"})(),
            2: type("C", (), {"cid": 2, "name": "стихия"})(),
            10: type(
                "C",
                (),
                {"cid": 10, "name": "Owl", "summoned_by_cid": 1, "summon_controller_mode": "summoner"},
            )(),
        }

    def test_current_turn_rejects_other_player(self):
        self.assertFalse(self.app._is_valid_summon_turn_for_controller(1, 2, 2))

    def test_current_turn_allows_active_player(self):
        self.assertTrue(self.app._is_valid_summon_turn_for_controller(2, 2, 2))

    def test_current_turn_allows_summoner_controlled_summon(self):
        self.assertTrue(self.app._is_valid_summon_turn_for_controller(1, 10, 10))


if __name__ == "__main__":
    unittest.main()
