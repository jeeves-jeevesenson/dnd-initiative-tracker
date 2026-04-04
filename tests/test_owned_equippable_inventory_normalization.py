import unittest

import dnd_initative_tracker as tracker_mod


class OwnedEquippableInventoryNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None

    def test_explicit_owned_id_is_preserved_when_valid(self):
        self.app._items_registry_payload = lambda: {
            "weapons": {"spear": {"id": "spear", "name": "Spear"}},
            "armors": {},
        }
        profile = {"inventory": {"items": [{"id": "SPEAR", "instance_id": "spear__001", "equipped": True, "quantity": 1}]}}
        normalized = self.app._normalize_inventory_item_entries(profile)
        self.assertEqual(normalized[0].get("id"), "spear")
        self.assertEqual(normalized[0].get("instance_id"), "spear__001")
        self.assertTrue(normalized[0].get("equipped"))

    def test_missing_id_exact_name_resolves_weapon(self):
        self.app._items_registry_payload = lambda: {
            "weapons": {"quarterstaff": {"id": "quarterstaff", "name": "Quarterstaff"}},
            "armors": {},
        }
        profile = {"inventory": {"items": [{"name": "Quarterstaff", "quantity": 1}]}}
        normalized = self.app._normalize_inventory_item_entries(profile)
        self.assertEqual(normalized[0].get("id"), "quarterstaff")

    def test_missing_id_exact_name_resolves_armor(self):
        self.app._items_registry_payload = lambda: {
            "weapons": {},
            "armors": {"plate_armor": {"id": "plate_armor", "name": "Plate Armor"}},
        }
        profile = {"inventory": {"items": [{"name": "Plate Armor", "equipped": True, "instance_id": "plate_armor__001"}]}}
        normalized = self.app._normalize_inventory_item_entries(profile)
        self.assertEqual(normalized[0].get("id"), "plate_armor")
        self.assertEqual(normalized[0].get("instance_id"), "plate_armor__001")
        self.assertTrue(normalized[0].get("equipped"))

    def test_unresolved_or_ambiguous_names_do_not_invent_ids(self):
        warnings = []
        self.app._oplog = lambda message, level="info": warnings.append((level, str(message)))
        self.app._items_registry_payload = lambda: {
            "weapons": {"duplicate_a": {"id": "duplicate_a", "name": "Duplicate Name"}},
            "armors": {"duplicate_b": {"id": "duplicate_b", "name": "Duplicate Name"}},
        }
        profile = {"name": "Tester", "inventory": {"items": [{"name": "Unknown Item"}, {"name": "Duplicate Name"}]}}
        normalized = self.app._normalize_inventory_item_entries(profile)
        self.assertFalse(normalized[0].get("id"))
        self.assertFalse(normalized[1].get("id"))
        self.assertTrue(any(level == "warning" and "missing id" in message for level, message in warnings))

    def test_shield_exists_in_armor_registry(self):
        registry = self.app._items_registry_payload()
        shield = (registry.get("armors") or {}).get("shield") or {}
        self.assertEqual(shield.get("id"), "shield")
        self.assertEqual(shield.get("name"), "Shield")
        self.assertEqual(shield.get("category"), "shield")

    def test_normalized_profile_omits_legacy_top_level_magic_items(self):
        profile = self.app._normalize_player_profile(
            {
                "name": "No Legacy Magic",
                "magic_items": {"legacy": True},
                "inventory": {"items": []},
            },
            "No Legacy Magic",
        )
        self.assertNotIn("magic_items", profile)


if __name__ == "__main__":
    unittest.main()
