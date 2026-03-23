import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import dnd_initative_tracker as tracker_mod


class ShopCatalogLoaderTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None

    def _write_yaml(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _seed_item_definitions(self, items_dir: Path):
        self._write_yaml(
            items_dir / "Weapons" / "longsword.yaml",
            {
                "id": "longsword",
                "name": "Longsword",
                "type": "weapon",
                "category": "martial_melee",
                "description": "A classic sword.",
            },
        )
        self._write_yaml(
            items_dir / "Armor" / "leather.yaml",
            {
                "id": "leather",
                "name": "Leather Armor",
                "type": "armor",
                "category": "light",
            },
        )
        self._write_yaml(
            items_dir / "Magic_Items" / "wand_of_sparking.yaml",
            {
                "id": "wand_of_sparking",
                "name": "Wand of Sparking",
                "type": "wand",
                "requires_attunement": True,
                "description": "Crackles with static.",
            },
        )
        self._write_yaml(
            items_dir / "Consumables" / "healing_potion.yaml",
            {
                "id": "healing_potion",
                "name": "Healing Potion",
                "type": "consumable",
                "consumable_type": "potion",
                "description": "Restore hit points.",
            },
        )

    def test_load_shop_catalog_normalized_success_for_each_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            self._seed_item_definitions(items_dir)
            self._write_yaml(
                items_dir / "Shop" / "catalog.yaml",
                {
                    "format_version": 1,
                    "entries": [
                        {
                            "item_id": "longsword",
                            "item_bucket": "weapon",
                            "shop_category": "weapons",
                            "enabled": True,
                            "price": {"gp": 15},
                        },
                        {
                            "item_id": "leather",
                            "item_bucket": "armor",
                            "shop_category": "armor",
                            "enabled": True,
                            "price": {"gp": 10},
                        },
                        {
                            "item_id": "wand_of_sparking",
                            "item_bucket": "magic_item",
                            "shop_category": "magic_items",
                            "enabled": True,
                            "price": {"gp": 250},
                        },
                        {
                            "item_id": "healing_potion",
                            "item_bucket": "consumable",
                            "shop_category": "consumables",
                            "enabled": False,
                            "price": {"sp": 30},
                        },
                    ],
                },
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                normalized = self.app._load_shop_catalog_normalized()

            self.assertEqual(4, len(normalized))
            by_key = {(row["item_bucket"], row["item_id"]): row for row in normalized}
            self.assertEqual({"gp": 15}, by_key[("weapon", "longsword")]["price"])
            self.assertEqual("A classic sword.", by_key[("weapon", "longsword")]["description"])
            self.assertEqual("light", by_key[("armor", "leather")]["category"])
            self.assertTrue(by_key[("magic_item", "wand_of_sparking")]["requires_attunement"])
            self.assertEqual("potion", by_key[("consumable", "healing_potion")]["consumable_type"])
            for row in normalized:
                self.assertTrue(row["definition_path"].endswith(".yaml"))

    def test_load_shop_catalog_normalized_fails_when_item_definition_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            self._seed_item_definitions(items_dir)
            self._write_yaml(
                items_dir / "Shop" / "catalog.yaml",
                {
                    "entries": [
                        {
                            "item_id": "not_real",
                            "item_bucket": "weapon",
                            "shop_category": "weapons",
                            "enabled": True,
                            "price": {"gp": 1},
                        }
                    ]
                },
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                with self.assertRaisesRegex(ValueError, "missing definition"):
                    self.app._load_shop_catalog_normalized()

    def test_load_shop_catalog_normalized_fails_on_invalid_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            self._seed_item_definitions(items_dir)
            self._write_yaml(
                items_dir / "Shop" / "catalog.yaml",
                {
                    "entries": [
                        {
                            "item_id": "longsword",
                            "item_bucket": "trinket",
                            "shop_category": "weapons",
                            "enabled": True,
                            "price": {"gp": 1},
                        }
                    ]
                },
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                with self.assertRaisesRegex(ValueError, "unknown item_bucket"):
                    self.app._load_shop_catalog_normalized()

    def test_load_shop_catalog_normalized_fails_on_duplicate_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            self._seed_item_definitions(items_dir)
            self._write_yaml(
                items_dir / "Shop" / "catalog.yaml",
                {
                    "entries": [
                        {
                            "item_id": "longsword",
                            "item_bucket": "weapon",
                            "shop_category": "weapons",
                            "enabled": True,
                            "price": {"gp": 10},
                        },
                        {
                            "item_id": "longsword",
                            "item_bucket": "weapon",
                            "shop_category": "weapons",
                            "enabled": True,
                            "price": {"gp": 11},
                        },
                    ]
                },
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                with self.assertRaisesRegex(ValueError, "duplicates"):
                    self.app._load_shop_catalog_normalized()

    def test_load_shop_catalog_normalized_fails_on_malformed_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            self._seed_item_definitions(items_dir)
            self._write_yaml(
                items_dir / "Shop" / "catalog.yaml",
                {
                    "entries": [
                        {
                            "item_id": "longsword",
                            "item_bucket": "weapon",
                            "shop_category": "weapons",
                            "enabled": True,
                            "price": {"gp": -1},
                        }
                    ]
                },
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                with self.assertRaisesRegex(ValueError, "negative price"):
                    self.app._load_shop_catalog_normalized()

    def test_load_shop_catalog_normalized_loads_repo_starter_catalog(self):
        with mock.patch.object(self.app, "_resolve_items_dir", return_value=Path("Items")):
            normalized = self.app._load_shop_catalog_normalized()
        self.assertTrue(normalized)


if __name__ == "__main__":
    unittest.main()
