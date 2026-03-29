import unittest

import dnd_initative_tracker as tracker_mod


class InventoryItemInstanceIdTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)

    def test_normalization_preserves_explicit_instance_id(self):
        profile = {
            "inventory": {
                "items": [
                    {"id": "wand_of_fireballs", "instance_id": "wand_of_fireballs__007", "quantity": 1},
                ]
            }
        }
        normalized = self.app._normalize_inventory_item_entries(profile)
        self.assertEqual(normalized[0].get("instance_id"), "wand_of_fireballs__007")

    def test_normalization_generates_deterministic_fallback_instance_ids(self):
        profile = {
            "inventory": {
                "items": [
                    {"id": "wand_of_fireballs"},
                    {"id": "wand_of_fireballs"},
                    {"name": "Ring of Greater Invisibility"},
                ]
            }
        }
        normalized = self.app._normalize_inventory_item_entries(profile)
        self.assertEqual(normalized[0].get("instance_id"), "derived:wand_of_fireballs__001")
        self.assertEqual(normalized[1].get("instance_id"), "derived:wand_of_fireballs__002")
        self.assertEqual(normalized[2].get("instance_id"), "derived:ring_of_greater_invisibility__001")

    def test_normalized_owned_magic_items_expose_instance_ids(self):
        self.app._magic_items_registry_payload = lambda: {
            "wand_of_fireballs": {"id": "wand_of_fireballs", "name": "Wand of Fireballs", "requires_attunement": True},
        }
        profile = {"inventory": {"items": [{"id": "wand_of_fireballs", "equipped": True, "attuned": True}]}}
        normalized = self.app._normalize_owned_magic_inventory_items(profile)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].get("instance_id"), "derived:wand_of_fireballs__001")


if __name__ == "__main__":
    unittest.main()
