import unittest

import dnd_initative_tracker as tracker_mod


class MountHarness:
    _accept_mount = tracker_mod.InitiativeTracker._accept_mount
    _apply_mount_initiative = tracker_mod.InitiativeTracker._apply_mount_initiative
    _restore_mount_initiative = tracker_mod.InitiativeTracker._restore_mount_initiative
    _mount_cost = tracker_mod.InitiativeTracker._mount_cost
    _mount_uses_rider_movement = tracker_mod.InitiativeTracker._mount_uses_rider_movement
    _lan_try_move = tracker_mod.InitiativeTracker._lan_try_move
    _lan_live_map_data = tracker_mod.InitiativeTracker._lan_live_map_data

    def __init__(self):
        self.combatants = {}
        self._lan_positions = {}
        self._lan_grid_cols = 20
        self._lan_grid_rows = 20
        self._lan_obstacles = set()
        self._lan_rough_terrain = {}
        self._map_window = None
        self._lan = type("LanStub", (), {"toast": lambda *args, **kwargs: None})()
        self._log = lambda *args, **kwargs: None
        self._rebuild_table = lambda *args, **kwargs: None
        self._lan_force_state_broadcast = lambda: None
        self._mode_speed = lambda c: int(getattr(c, "speed", 0) or 0)
        self._lan_shortest_cost = lambda *args, **kwargs: 5


def _make_combatant(
    cid: int,
    name: str,
    speed: int,
    initiative: int,
    can_be_mounted: bool = False,
    is_mount: bool = False,
):
    c = tracker_mod.base.Combatant(
        cid=cid,
        name=name,
        hp=20,
        speed=speed,
        swim_speed=0,
        fly_speed=0,
        burrow_speed=0,
        climb_speed=0,
        movement_mode="Normal",
        move_remaining=speed,
        initiative=initiative,
        dex=2,
        ally=True,
        is_pc=True,
    )
    setattr(c, "can_be_mounted", can_be_mounted)
    setattr(c, "is_mount", is_mount)
    setattr(c, "mount_controller_mode", "independent")
    setattr(c, "mount_shared_turn", False)
    setattr(c, "rider_cid", None)
    setattr(c, "mounted_by_cid", None)
    return c


class MountingTests(unittest.TestCase):
    def test_accept_mount_true_mount_and_non_mount_behaviors(self):
        app = MountHarness()
        rider = _make_combatant(1, "Rider", speed=30, initiative=14)
        true_mount = _make_combatant(2, "Steed", speed=60, initiative=8, can_be_mounted=True)
        carrier = _make_combatant(3, "Carrier", speed=30, initiative=11)
        app.combatants = {1: rider, 2: true_mount, 3: carrier}

        app._accept_mount(1, 2, ws_id=None)
        self.assertEqual(rider.rider_cid, 2)
        self.assertEqual(true_mount.mounted_by_cid, 1)
        self.assertTrue(true_mount.mount_shared_turn)
        self.assertEqual(true_mount.mount_controller_mode, "rider")
        self.assertEqual(true_mount.initiative, rider.initiative)
        self.assertEqual(rider.move_remaining, 15)

        rider.move_remaining = rider.speed
        rider.has_mounted_this_turn = False
        rider.rider_cid = None
        true_mount.mounted_by_cid = None
        true_mount.mount_shared_turn = False
        true_mount.mount_controller_mode = "independent"

        app._accept_mount(1, 3, ws_id=None)
        self.assertEqual(rider.rider_cid, 3)
        self.assertEqual(carrier.mounted_by_cid, 1)
        self.assertFalse(carrier.mount_shared_turn)
        self.assertEqual(carrier.mount_controller_mode, "independent")
        self.assertEqual(carrier.initiative, 11)
        self.assertEqual(rider.move_remaining, 15)

    def test_lan_try_move_charges_rider_for_true_mount_and_carrier_for_non_mount(self):
        app = MountHarness()
        rider = _make_combatant(1, "Rider", speed=30, initiative=12)
        mount = _make_combatant(2, "Mount", speed=60, initiative=10, can_be_mounted=True)
        app.combatants = {1: rider, 2: mount}
        app._lan_positions = {1: (0, 0), 2: (0, 0)}
        rider.move_remaining = 20
        mount.move_remaining = 30
        mount.mounted_by_cid = 1
        mount.mount_shared_turn = True
        mount.mount_controller_mode = "rider"

        ok, reason, cost = app._lan_try_move(2, 1, 0)
        self.assertTrue(ok, reason)
        self.assertEqual(cost, 5)
        self.assertEqual(rider.move_remaining, 15)
        self.assertEqual(mount.move_remaining, 30)
        self.assertEqual(app._lan_positions[2], (1, 0))
        self.assertEqual(app._lan_positions[1], (1, 0))

        rider.move_remaining = 20
        mount.move_remaining = 30
        mount.mount_shared_turn = False
        mount.mount_controller_mode = "independent"
        app._lan_positions = {1: (0, 0), 2: (0, 0)}

        ok, reason, cost = app._lan_try_move(2, 2, 0)
        self.assertTrue(ok, reason)
        self.assertEqual(cost, 5)
        self.assertEqual(rider.move_remaining, 20)
        self.assertEqual(mount.move_remaining, 25)
        self.assertEqual(app._lan_positions[2], (2, 0))
        self.assertEqual(app._lan_positions[1], (2, 0))


if __name__ == "__main__":
    unittest.main()
