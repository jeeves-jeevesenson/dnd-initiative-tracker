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
        self.app._map_window = None
        self.app._lan_aoes = {}
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

    def test_set_facing_syncs_owned_rotatable_aoe_angle(self):
        self.app._lan_aoes = {
            7: {"aid": 7, "kind": "line", "owner_cid": 1, "angle_deg": 0, "length_sq": 4, "ax": 5, "ay": 5, "cx": 7, "cy": 5},
            8: {"aid": 8, "kind": "circle", "owner_cid": 1, "radius_sq": 2, "cx": 5, "cy": 5},
        }
        msg = {"type": "set_facing", "cid": 1, "_claimed_cid": 1, "_ws_id": 9, "facing_deg": 180}

        self.app._lan_apply_action(dict(msg))

        self.assertEqual(self.app._lan_aoes[7].get("angle_deg"), 180.0)
        # anchor(5,5) with length_sq=4 means half-length=2 squares; at 180° center shifts to (3,5)
        self.assertAlmostEqual(float(self.app._lan_aoes[7].get("cx")), 3.0)
        self.assertAlmostEqual(float(self.app._lan_aoes[7].get("cy")), 5.0)
        self.assertIsNone(self.app._lan_aoes[8].get("angle_deg"))

    def test_set_facing_rejects_non_claimed_target(self):
        self.app.combatants[2] = type("C", (), {"cid": 2, "name": "Summon"})()
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        msg = {"type": "set_facing", "cid": 2, "_claimed_cid": 1, "_ws_id": 9, "facing_deg": 180}

        self.app._lan_apply_action(dict(msg))

        self.assertNotIn("facing_deg", vars(self.app.combatants[2]))
        self.assertEqual(self.broadcast_calls, 0)
        self.assertIn((9, "Arrr, that token ain’t yers."), self.toasts)

    def test_set_facing_allows_controlled_summon_target(self):
        self.app.combatants[2] = type("C", (), {"cid": 2, "name": "Summon"})()
        self.app._summon_can_be_controlled_by = lambda claimed, target: claimed == 1 and target == 2
        msg = {"type": "set_facing", "cid": 2, "_claimed_cid": 1, "_ws_id": 9, "facing_deg": 180}

        self.app._lan_apply_action(dict(msg))

        self.assertEqual(getattr(self.app.combatants[2], "facing_deg", None), 180)
        self.assertEqual(self.broadcast_calls, 1)

    def test_set_facing_syncs_map_window_token_facing(self):
        layout_calls = []

        class MapWindowStub:
            def __init__(self):
                self._token_facing = {}

            def winfo_exists(self):
                return True

            def _layout_unit(self, cid):
                layout_calls.append(cid)

        self.app._map_window = MapWindowStub()
        msg = {"type": "set_facing", "cid": 1, "_claimed_cid": 1, "_ws_id": 9, "facing_deg": 270}

        self.app._lan_apply_action(dict(msg))

        self.assertEqual(self.app._map_window._token_facing.get(1), 270.0)
        self.assertEqual(layout_calls, [1])


if __name__ == "__main__":
    unittest.main()
