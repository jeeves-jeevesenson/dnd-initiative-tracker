import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dnd_initative_tracker as tracker_mod


class ItemsWeaponResolutionTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._items_registry_cache = None
        self.app._items_dir_signature = None

    def test_items_registry_loads_per_item_and_catalog_with_per_item_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            weapons_dir = items_dir / "Weapons"
            armor_dir = items_dir / "Armor"
            weapons_dir.mkdir(parents=True, exist_ok=True)
            armor_dir.mkdir(parents=True, exist_ok=True)

            (weapons_dir / "longsword.yaml").write_text(
                "id: longsword\nname: Longsword File\ndamage:\n  one_handed:\n    formula: 1d8\n    type: slashing\n",
                encoding="utf-8",
            )
            (weapons_dir / "legacy_catalog.yaml").write_text(
                "weapons:\n  - id: longsword\n    name: Longsword Catalog\n  - id: shortbow\n    name: Shortbow\n",
                encoding="utf-8",
            )
            (weapons_dir / "properties_2024_basic.yaml").write_text(
                "properties:\n  - id: finesse\n",
                encoding="utf-8",
            )
            (armor_dir / "catalog.yaml").write_text(
                "armors:\n  - id: chain_mail\n    name: Chain Mail\n",
                encoding="utf-8",
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                registry = self.app._items_registry_payload()

            self.assertIn("longsword", registry["weapons"])
            self.assertEqual(registry["weapons"]["longsword"]["name"], "Longsword File")
            self.assertIn("shortbow", registry["weapons"])
            self.assertIn("chain_mail", registry["armors"])
            self.assertNotIn("finesse", registry["weapons"])


    def test_items_registry_uses_signature_cache_between_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_dir = Path(tmp) / "Items"
            weapons_dir = items_dir / "Weapons"
            armor_dir = items_dir / "Armor"
            weapons_dir.mkdir(parents=True, exist_ok=True)
            armor_dir.mkdir(parents=True, exist_ok=True)
            (weapons_dir / "dagger.yaml").write_text(
                "id: dagger\nname: Dagger\ndamage:\n  one_handed:\n    formula: 1d4\n    type: piercing\n",
                encoding="utf-8",
            )

            with mock.patch.object(self.app, "_resolve_items_dir", return_value=items_dir):
                first = self.app._items_registry_payload()
                self.assertIn("dagger", first["weapons"])
                with mock.patch.object(tracker_mod.yaml, "safe_load", side_effect=RuntimeError("should not parse again")):
                    second = self.app._items_registry_payload()

            self.assertIn("dagger", second["weapons"])

    def test_normalize_player_weapon_resolves_item_fields_fill_missing_only(self):
        registry = {
            "weapons": {
                "longsword": {
                    "id": "longsword",
                    "name": "Longsword",
                    "category": "martial_melee",
                    "attack_bonus": 1,
                    "damage": {
                        "one_handed": {"formula": "1d8", "type": "slashing"},
                        "versatile": {"formula": "1d10", "type": "slashing"},
                    },
                    "properties": ["versatile", "sap"],
                }
            },
            "armors": {},
        }
        player = {
            "name": "Test",
            "abilities": {"str": 16, "dex": 12},
            "attacks": {
                "weapons": [
                    {
                        "id": "longsword",
                        "to_hit": 7,
                        "one_handed": {"damage_formula": "2d6 + str_mod"},
                    }
                ]
            },
        }
        with mock.patch.object(tracker_mod.InitiativeTracker, "_items_registry_payload", return_value=registry):
            normalized = self.app._normalize_player_profile(player, "Test")

        weapon = normalized["attacks"]["weapons"][0]
        self.assertEqual(weapon["name"], "Longsword")
        self.assertEqual(weapon["one_handed"]["damage_formula"], "2d6 + str_mod")
        self.assertEqual(weapon["one_handed"]["damage_type"], "slashing")
        self.assertEqual(weapon["two_handed"]["damage_formula"], "1d10 + str_mod")
        self.assertEqual(weapon["magic_bonus"], 1)
        self.assertIn("versatile", weapon["properties"])

    def test_normalize_appends_finesse_or_ranged_ability_mod_when_missing(self):
        registry = {
            "weapons": {
                "rapier": {
                    "id": "rapier",
                    "name": "Rapier",
                    "category": "martial_melee",
                    "damage": {"one_handed": {"formula": "1d8", "type": "piercing"}},
                    "properties": ["finesse"],
                },
                "shortbow": {
                    "id": "shortbow",
                    "name": "Shortbow",
                    "category": "martial_ranged",
                    "damage": {"one_handed": {"formula": "1d6", "type": "piercing"}},
                },
            },
            "armors": {},
        }
        player = {
            "name": "Archer",
            "abilities": {"str": 10, "dex": 18},
            "attacks": {"weapons": [{"id": "rapier"}, {"id": "shortbow"}]},
        }
        with mock.patch.object(tracker_mod.InitiativeTracker, "_items_registry_payload", return_value=registry):
            normalized = self.app._normalize_player_profile(player, "Archer")

        rapier, shortbow = normalized["attacks"]["weapons"]
        self.assertEqual(rapier["one_handed"]["damage_formula"], "1d8 + max(str_mod, dex_mod)")
        self.assertEqual(shortbow["one_handed"]["damage_formula"], "1d6 + dex_mod")

    def test_resolve_weapon_from_items_maps_versatile_to_two_handed_formula(self):
        registry = {
            "weapons": {
                "inazuma": {
                    "id": "inazuma",
                    "name": "Inazuma",
                    "damage": {
                        "one_handed": {"formula": "1d8", "type": "slashing"},
                        "versatile": {"formula": "1d10", "type": "slashing"},
                    },
                    "properties": ["versatile"],
                }
            },
            "armors": {},
        }
        weapon = {"id": "inazuma", "one_handed": {}, "two_handed": {}}
        resolved = self.app._resolve_weapon_from_items(weapon, registry["weapons"])

        self.assertEqual(resolved["two_handed"]["damage_formula"], "1d10 + str_mod")

    def test_resolve_weapon_from_items_maps_two_handed_damage_without_one_handed(self):
        registry = {
            "weapons": {
                "bardiche_plus_2": {
                    "id": "bardiche_plus_2",
                    "name": "Bardiche (+2)",
                    "damage": {
                        "two_handed": {"formula": "1d12 + 2", "type": "force"},
                    },
                    "properties": ["two_handed"],
                }
            },
            "armors": {},
        }
        weapon = {"id": "bardiche_plus_2", "one_handed": {}, "two_handed": {}}
        resolved = self.app._resolve_weapon_from_items(weapon, registry["weapons"])

        self.assertEqual(resolved["one_handed"].get("damage_formula", ""), "")
        self.assertEqual(resolved["two_handed"]["damage_formula"], "1d12 + 2 + str_mod")



if __name__ == "__main__":
    unittest.main()
