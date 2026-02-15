import threading
import unittest

import dnd_initative_tracker as tracker_mod


class LanSnapshotStaticTests(unittest.TestCase):
    def test_include_static_false_reuses_cached_static_payload(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app.combatants = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: []
        app._oplog = lambda *args, **kwargs: None

        app._spell_presets_payload = lambda: (_ for _ in ()).throw(AssertionError("spell presets should not be called"))
        app._player_spell_config_payload = lambda: (_ for _ in ()).throw(AssertionError("player spells should not be called"))
        app._player_profiles_payload = lambda: (_ for _ in ()).throw(AssertionError("player profiles should not be called"))
        app._player_resource_pools_payload = lambda: (_ for _ in ()).throw(AssertionError("resource pools should not be called"))

        app._lan = type("LanStub", (), {"_cached_snapshot": {
            "spell_presets": [{"name": "cached"}],
            "player_spells": {"Alice": {"spells": []}},
            "player_profiles": {"Alice": {"name": "Alice"}},
            "resource_pools": {"Alice": [{"id": "wild_shape", "current": 1}]},
        }})()

        snap = app._lan_snapshot(include_static=False)
        self.assertEqual(snap["spell_presets"], [{"name": "cached"}])
        self.assertEqual(snap["player_spells"], {"Alice": {"spells": []}})
        self.assertEqual(snap["player_profiles"], {"Alice": {"name": "Alice"}})
        self.assertEqual(snap["resource_pools"], {"Alice": [{"id": "wild_shape", "current": 1}]})

    def test_view_only_state_payload_includes_grid_and_terrain(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._cached_snapshot = {
            "grid": {"cols": 5, "rows": 6, "feet_per_square": 5},
            "rough_terrain": [{"col": 0, "row": 1}],
            "obstacles": [{"col": 2, "row": 3}],
            "units": [],
        }
        lan._cached_pcs = []
        lan._cid_to_host = {}
        lan._clients_lock = threading.Lock()

        payload = lan._view_only_state_payload({"units": []})

        self.assertEqual(payload["grid"], {"cols": 5, "rows": 6, "feet_per_square": 5})
        self.assertEqual(payload["rough_terrain"], [{"col": 0, "row": 1}])
        self.assertEqual(payload["obstacles"], [{"col": 2, "row": 3}])

    def test_units_include_max_hp_field(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: [1]
        app._oplog = lambda *args, **kwargs: None
        app._name_role_memory = {"alice": "pc"}
        app._lan_marks_for = lambda _c: []
        app._normalize_action_entries = lambda _entries, _kind: []
        app._token_color_payload = lambda _c: None
        app._has_condition = lambda _c, _name: False
        app._lan_seed_missing_positions = lambda positions, *_args: positions
        app._build_you_payload = lambda _ws_id=None: {"claimed_cid": None, "claimed_name": None}
        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: {}
        app._lan = type("LanStub", (), {"_cached_snapshot": None})()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alice", "hp": 7, "max_hp": 22})(),
        }

        snap = app._lan_snapshot(include_static=False)

        self.assertEqual(snap["units"][0]["hp"], 7)
        self.assertEqual(snap["units"][0]["max_hp"], 22)


if __name__ == "__main__":
    unittest.main()
