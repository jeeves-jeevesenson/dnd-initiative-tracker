import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


class ResourcePoolSpellTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.warnings = []
        self.app._oplog = lambda msg, level="info": self.warnings.append((level, msg))

    def test_pool_granted_spells_collected_with_metadata(self):
        profile = {
            "name": "Cleric",
            "leveling": {"level": 5},
            "resources": {
                "pools": [
                    {"id": "channel_divinity", "label": "Channel Divinity", "current": 1, "max_formula": "1", "reset": "short_rest"}
                ]
            },
            "features": [
                {
                    "name": "Domain Magic",
                    "grants": {
                        "spells": {
                            "casts": [
                                {"spell": "guiding-bolt", "action_type": "action", "consumes": {"pool": "channel_divinity", "cost": 1}}
                            ]
                        }
                    },
                }
            ],
        }
        spells = self.app._player_pool_granted_spells(profile)
        self.assertEqual(len(spells), 1)
        self.assertEqual(spells[0]["spell"], "guiding-bolt")
        self.assertEqual(spells[0]["consumes_pool"]["id"], "channel_divinity")
        self.assertEqual(spells[0]["consumes_pool"]["cost"], 1)

    def test_pool_grants_warn_on_unknown_pool(self):
        profile = {
            "name": "Monk",
            "resources": {"pools": []},
            "features": [
                {"name": "Ki", "grants": {"spells": {"casts": [{"spell": "misty-step", "consumes": {"pool": "ki_points", "cost": 2}}]}}}
            ],
        }
        spells = self.app._player_pool_granted_spells(profile)
        self.assertEqual(spells, [])
        self.assertTrue(any("unknown consumes.pool" in msg for _level, msg in self.warnings))

    def test_consume_pool_reduces_current(self):
        path = Path("players/test.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"cleric": path}
        self.app._player_yaml_cache_by_path = {
            path: {
                "resources": {
                    "pools": [
                        {"id": "channel_divinity", "current": 1, "max_formula": "1", "reset": "short_rest"}
                    ]
                }
            }
        }
        saved = {}

        def _save(target, raw):
            saved["target"] = target
            saved["raw"] = raw

        self.app._store_character_yaml = _save

        ok, err = self.app._consume_resource_pool_for_cast("cleric", "channel_divinity", 1)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(saved["raw"]["resources"]["pools"][0]["current"], 0)

    def test_consume_spell_slot_allows_cantrip_level_zero(self):
        ok, err, spent = self.app._consume_spell_slot_for_cast("wizard", 0, 0)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(spent, 0)


    def test_normalize_pool_formula_supports_barbarian_level_variable(self):
        profile = {
            "name": "Malagrou",
            "leveling": {"classes": [{"name": "Barbarian", "level": 10}]},
            "resources": {
                "pools": [
                    {
                        "id": "rage",
                        "label": "Rage",
                        "current": 4,
                        "max_formula": "2 if barbarian_level < 3 else 3 if barbarian_level < 6 else 4 if barbarian_level < 12 else 5 if barbarian_level < 17 else 6",
                        "reset": "short_rest",
                    }
                ]
            },
        }
        pools = self.app._normalize_player_resource_pools(profile)
        rage = next((entry for entry in pools if entry.get("id") == "rage"), None)
        self.assertIsNotNone(rage)
        self.assertEqual(rage["max"], 4)
        self.assertEqual(rage["current"], 4)

    def test_normalize_adds_second_wind_pool_for_level_10_fighter(self):
        profile = {
            "name": "John Twilight",
            "leveling": {"classes": [{"name": "Fighter", "level": 10}]},
            "resources": {"pools": []},
        }
        pools = self.app._normalize_player_resource_pools(profile)
        second_wind = next((entry for entry in pools if entry.get("id") == "second_wind"), None)
        self.assertIsNotNone(second_wind)
        self.assertEqual(second_wind["current"], 4)
        self.assertEqual(second_wind["max"], 4)
        self.assertEqual(second_wind["reset"], "short_rest")
        self.assertEqual(second_wind["gain_on_short"], 1)

    def test_normalize_adds_lay_on_hands_pool_for_level_10_paladin(self):
        profile = {
            "name": "Dorian",
            "leveling": {"classes": [{"name": "Paladin", "level": 10}]},
            "resources": {"pools": []},
        }
        pools = self.app._normalize_player_resource_pools(profile)
        lay_on_hands = next((entry for entry in pools if entry.get("id") == "lay_on_hands"), None)
        self.assertIsNotNone(lay_on_hands)
        self.assertEqual(lay_on_hands["current"], 50)
        self.assertEqual(lay_on_hands["max"], 50)
        self.assertEqual(lay_on_hands["reset"], "long_rest")


if __name__ == "__main__":
    unittest.main()
