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


if __name__ == "__main__":
    unittest.main()
