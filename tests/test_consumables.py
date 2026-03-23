import unittest
from pathlib import Path
from types import SimpleNamespace

import dnd_initative_tracker as tracker_mod
import yaml


class ConsumableTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *_args, **_kwargs: None

    def test_consumables_registry_loads_healing_potions(self):
        registry = self.app._consumables_registry_payload()
        self.assertTrue(
            {
                "lesser_healing_potion",
                "healing_potion",
                "greater_healing_potion",
                "supreme_healing_potion",
                "scroll_of_magic_missile",
                "antitoxin",
            }.issubset(set(registry.keys()))
        )

    def test_derived_consumable_pools_track_inventory_quantity(self):
        profile = {
            "inventory": {
                "items": [
                    {"id": "lesser_healing_potion", "name": "Lesser Healing Potion", "quantity": 2},
                    {"id": "rope", "name": "Rope", "quantity": 1},
                ]
            }
        }
        pools = self.app._derive_consumable_resource_pools_from_inventory(profile)
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["id"], "consumable:lesser_healing_potion")
        self.assertEqual(pools[0]["current"], 2)

    def test_adjust_consumable_quantity_updates_and_removes_entry(self):
        path = Path("players/test_consumable_adjust.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"cleric": path}
        self.app._player_yaml_cache_by_path = {
            path: {
                "inventory": {
                    "items": [
                        {"id": "lesser_healing_potion", "name": "Lesser Healing Potion", "quantity": 2}
                    ]
                }
            }
        }
        saved = {}

        def _save(target, raw):
            saved["target"] = target
            saved["raw"] = raw
            self.app._player_yaml_cache_by_path[target] = raw

        self.app._store_character_yaml = _save

        ok, err, qty = self.app._adjust_inventory_consumable_quantity("cleric", "lesser_healing_potion", -1)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(qty, 1)

        ok, err, qty = self.app._adjust_inventory_consumable_quantity("cleric", "lesser_healing_potion", -1)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(qty, 0)
        self.assertEqual(saved["raw"]["inventory"]["items"], [])

    def test_use_healing_potion_spends_bonus_action_and_heals(self):
        path = Path("players/test_consumable_use.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"cleric": path}
        self.app._player_yaml_cache_by_path = {
            path: {
                "inventory": {
                    "items": [
                        {"id": "lesser_healing_potion", "name": "Lesser Healing Potion", "quantity": 1}
                    ]
                }
            }
        }
        self.app._store_character_yaml = lambda target, raw: self.app._player_yaml_cache_by_path.__setitem__(target, raw)
        self.app.in_combat = True
        self.app._use_bonus_action = lambda combatant: setattr(combatant, "bonus_action_remaining", max(0, int(getattr(combatant, "bonus_action_remaining", 0)) - 1)) or True

        combatant = SimpleNamespace(hp=5, max_hp=20, bonus_action_remaining=1)
        self.app._roll_healing_formula = lambda _formula: 7

        ok, err, healed = self.app._use_inventory_consumable("cleric", "lesser_healing_potion", combatant)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(healed, 7)
        self.assertEqual(combatant.hp, 12)
        self.assertEqual(combatant.bonus_action_remaining, 0)

        items = self.app._player_yaml_cache_by_path[path]["inventory"]["items"]
        self.assertEqual(items, [])

    def test_use_healing_potion_does_not_consume_when_bonus_action_blocked(self):
        path = Path("players/test_consumable_bonus_blocked.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"cleric": path}
        self.app._player_yaml_cache_by_path = {
            path: {
                "inventory": {
                    "items": [
                        {"id": "lesser_healing_potion", "name": "Lesser Healing Potion", "quantity": 1}
                    ]
                }
            }
        }
        self.app._store_character_yaml = lambda target, raw: self.app._player_yaml_cache_by_path.__setitem__(target, raw)
        self.app.in_combat = True
        self.app._use_bonus_action = lambda _combatant: False

        combatant = SimpleNamespace(hp=5, max_hp=20, bonus_action_remaining=1)
        self.app._roll_healing_formula = lambda _formula: 7

        ok, err, healed = self.app._use_inventory_consumable("cleric", "lesser_healing_potion", combatant)
        self.assertFalse(ok)
        self.assertIn("bonus action", err.lower())
        self.assertEqual(healed, 0)
        self.assertEqual(combatant.hp, 5)

        items = self.app._player_yaml_cache_by_path[path]["inventory"]["items"]
        self.assertEqual(items[0]["quantity"], 1)

    def test_use_healing_potion_fails_at_zero_quantity(self):
        path = Path("players/test_consumable_zero.yaml")
        self.app._load_player_yaml_cache = lambda: None
        self.app._normalize_character_lookup_key = lambda v: str(v).strip().lower()
        self.app._player_yaml_name_map = {"cleric": path}
        self.app._player_yaml_cache_by_path = {path: {"inventory": {"items": []}}}
        self.app._store_character_yaml = lambda *_args, **_kwargs: None
        self.app.in_combat = True

        combatant = SimpleNamespace(hp=5, max_hp=20, bonus_action_remaining=1)
        ok, err, healed = self.app._use_inventory_consumable("cleric", "lesser_healing_potion", combatant)
        self.assertFalse(ok)
        self.assertIn("No such consumable", err)
        self.assertEqual(healed, 0)

    def test_scroll_of_magic_missile_references_existing_spell_yaml(self):
        scroll_path = Path("Items/Consumables/scroll_of_magic_missile.yaml")
        scroll_data = yaml.safe_load(scroll_path.read_text(encoding="utf-8"))
        spell_ids = set()
        for spell_path in Path("Spells").glob("*.yaml"):
            spell_data = yaml.safe_load(spell_path.read_text(encoding="utf-8")) or {}
            spell_ids.add(str(spell_data.get("id") or "").strip())

        self.assertEqual(str(scroll_data.get("type") or "").strip(), "consumable")
        casts = (((scroll_data.get("grants") or {}).get("spells") or {}).get("casts") or [])
        self.assertTrue(casts)

        first_cast = casts[0] if isinstance(casts[0], dict) else {}
        self.assertEqual(str(first_cast.get("spell") or "").strip(), "magic-missile")
        self.assertIn(str(first_cast.get("spell") or "").strip(), spell_ids)


if __name__ == "__main__":
    unittest.main()
