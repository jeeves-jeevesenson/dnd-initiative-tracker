import unittest

import dnd_initative_tracker as tracker_mod


class LanMovementModeCycleTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.toasts = []
        self.rebuild_calls = 0
        self.broadcast_calls = 0
        self.mode_updates = []

        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app.in_combat = True
        self.app.current_cid = 1
        self.app.combatants = {
            1: type(
                "C",
                (),
                {
                    "cid": 1,
                    "name": "Alice",
                    "movement_mode": "normal",
                    "swim_speed": 30,
                    "fly_speed": 60,
                    "burrow_speed": 0,
                },
            )(),
        }
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
            },
        )()
        self.app._set_movement_mode = lambda cid, mode: (
            self.mode_updates.append((cid, mode)),
            setattr(self.app.combatants[cid], "movement_mode", mode),
        )
        self.app._rebuild_table = lambda scroll_to_current=True: setattr(self, "rebuild_calls", self.rebuild_calls + 1)
        self.app._lan_force_state_broadcast = lambda: setattr(self, "broadcast_calls", self.broadcast_calls + 1)

    def test_cycle_movement_mode_rotates_available_speeds(self):
        msg = {"type": "cycle_movement_mode", "cid": 1, "_claimed_cid": 1, "_ws_id": 7}

        self.app._lan_apply_action(dict(msg))
        self.app._lan_apply_action(dict(msg))

        self.assertEqual(self.mode_updates, [(1, "swim"), (1, "fly")])
        self.assertEqual(self.rebuild_calls, 2)
        self.assertIn((7, "Movement mode: Swim."), self.toasts)
        self.assertIn((7, "Movement mode: Fly."), self.toasts)

    def test_set_facing_normalizes_degrees_and_broadcasts(self):
        msg = {"type": "set_facing", "cid": 1, "_claimed_cid": 1, "_ws_id": 9, "facing_deg": 450}

        self.app._lan_apply_action(dict(msg))

        self.assertEqual(getattr(self.app.combatants[1], "facing_deg", None), 90)
        self.assertEqual(self.broadcast_calls, 1)


if __name__ == "__main__":
    unittest.main()
