import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


class InventoryMagicItemPoolsTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.warnings = []
        self.app._oplog = lambda msg, level="info": self.warnings.append((level, msg))
        self.app._find_spell_preset = lambda **_kwargs: None

    def _registry(self):
        return {
            "wand_of_fireballs": {
                "id": "wand_of_fireballs",
                "name": "Wand of Fireballs",
                "requires_attunement": True,
                "grants": {
                    "spells": {
                        "casts": [
                            {
                                "spell": "fireball",
                                "consumes": {"pool": "wand_of_fireballs_fireball_cast", "cost": 1},
                            }
                        ]
                    }
                },
            },
            "tyrs_circlet": {
                "id": "tyrs_circlet",
                "name": "Tyr's Circlet",
                "requires_attunement": True,
                "grants": {
                    "pools": [
                        {
                            "id": "tyrs_circlet_blessing",
                            "label": "Blessed by Tyr",
                            "current": 1,
                            "max": 1,
                            "max_formula": "1",
                            "reset": "long_rest",
                        }
                    ]
                },
            },
        }

    def test_active_attuned_magic_item_projects_pool_from_item_state(self):
        self.app._magic_items_registry_payload = self._registry
        profile = {
            "name": "Johnny",
            "resources": {"pools": [{"id": "wand_of_fireballs_fireball_cast", "current": 1, "max": 1, "reset": "long_rest"}]},
            "inventory": {
                "items": [
                    {
                        "id": "wand_of_fireballs",
                        "equipped": True,
                        "attuned": True,
                        "state": {
                            "pools": [
                                {
                                    "id": "wand_of_fireballs_fireball_cast",
                                    "label": "Wand of Fireballs (Fireball)",
                                    "current": 0,
                                    "max": 1,
                                    "max_formula": "1",
                                    "reset": "long_rest",
                                }
                            ]
                        },
                    }
                ]
            },
        }
        pools = self.app._normalize_player_resource_pools(profile)
        wand_pool = next((p for p in pools if p.get("id") == "wand_of_fireballs_fireball_cast"), None)
        self.assertIsNotNone(wand_pool)
        self.assertEqual(wand_pool.get("current"), 0)
        self.assertEqual(wand_pool.get("source_type"), "inventory_item")
        self.assertEqual(wand_pool.get("source_item_id"), "wand_of_fireballs")

    def test_requires_attunement_item_not_attuned_does_not_project_pool(self):
        self.app._magic_items_registry_payload = self._registry
        profile = {
            "name": "Dorian",
            "inventory": {
                "items": [
                    {
                        "id": "tyrs_circlet",
                        "equipped": True,
                        "attuned": False,
                        "state": {
                            "pools": [
                                {
                                    "id": "tyrs_circlet_blessing",
                                    "current": 1,
                                    "max": 1,
                                    "max_formula": "1",
                                    "reset": "long_rest",
                                }
                            ]
                        },
                    }
                ]
            },
        }
        pools = self.app._normalize_player_resource_pools(profile)
        self.assertFalse(any(p.get("id") == "tyrs_circlet_blessing" for p in pools))

    def test_hidden_when_inactive_but_item_state_persists(self):
        self.app._magic_items_registry_payload = self._registry
        profile = {
            "name": "Dorian",
            "inventory": {
                "items": [
                    {
                        "id": "tyrs_circlet",
                        "equipped": False,
                        "attuned": True,
                        "state": {
                            "pools": [
                                {
                                    "id": "tyrs_circlet_blessing",
                                    "current": 0,
                                    "max": 1,
                                    "max_formula": "1",
                                    "reset": "long_rest",
                                }
                            ]
                        },
                    }
                ]
            },
        }
        pools = self.app._normalize_player_resource_pools(profile)
        self.assertFalse(any(p.get("id") == "tyrs_circlet_blessing" for p in pools))
        item_state_pool = profile["inventory"]["items"][0]["state"]["pools"][0]
        self.assertEqual(item_state_pool.get("current"), 0)

    def test_consume_pool_for_cast_updates_inventory_item_state(self):
        self.app._magic_items_registry_payload = self._registry
        path = Path("players/test.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"johnny": path}
        self.app._player_yaml_cache_by_path = {
            path: {
                "name": "Johnny",
                "inventory": {
                    "items": [
                        {
                            "id": "wand_of_fireballs",
                            "equipped": True,
                            "attuned": True,
                            "state": {
                                "pools": [
                                    {
                                        "id": "wand_of_fireballs_fireball_cast",
                                        "current": 1,
                                        "max": 1,
                                        "max_formula": "1",
                                        "reset": "long_rest",
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
        }
        saved = {}
        self.app._store_character_yaml = lambda target, raw: saved.update({"target": target, "raw": raw})

        ok, err = self.app._consume_resource_pool_for_cast("johnny", "wand_of_fireballs_fireball_cast", 1)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        state_pool = saved["raw"]["inventory"]["items"][0]["state"]["pools"][0]
        self.assertEqual(state_pool.get("current"), 0)

    def test_set_pool_current_updates_inventory_item_state(self):
        self.app._magic_items_registry_payload = self._registry
        self.app._normalize_player_profile = lambda raw, _name: raw
        path = Path("players/test.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"johnny": path}
        self.app._player_yaml_cache_by_path = {
            path: {
                "name": "Johnny",
                "inventory": {
                    "items": [
                        {
                            "id": "wand_of_fireballs",
                            "equipped": True,
                            "attuned": True,
                            "state": {
                                "pools": [
                                    {
                                        "id": "wand_of_fireballs_fireball_cast",
                                        "current": 0,
                                        "max": 1,
                                        "max_formula": "1",
                                        "reset": "long_rest",
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
        }
        saved = {}
        self.app._store_character_yaml = lambda target, raw: saved.update({"target": target, "raw": raw})

        ok, err = self.app._set_player_resource_pool_current("johnny", "wand_of_fireballs_fireball_cast", 1)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        state_pool = saved["raw"]["inventory"]["items"][0]["state"]["pools"][0]
        self.assertEqual(state_pool.get("current"), 1)


if __name__ == "__main__":
    unittest.main()
