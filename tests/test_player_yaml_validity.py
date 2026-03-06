import unittest
from pathlib import Path

import yaml


class PlayerYamlValidityTests(unittest.TestCase):
    @staticmethod
    def _load(path: str):
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    def test_john_twilight_yaml_parses(self):
        data = self._load("players/John_Twilight.yaml")
        self.assertIsInstance(data, dict)
        self.assertEqual(str(data.get("name") or "").strip(), "John Twilight")
        speed = ((data.get("vitals") or {}).get("speed") or {})
        self.assertEqual(set(speed.keys()), {"walk", "climb", "fly", "swim"})

    def test_john_twilight_default_equipment_slots(self):
        data = self._load("players/John_Twilight.yaml")
        inventory = data.get("inventory") or {}
        items = inventory.get("items") or []
        by_id = {str((item or {}).get("id") or ""): (item or {}) for item in items if isinstance(item, dict)}
        self.assertEqual(set(inventory.get("equipped") or []), {"hellish_platemail", "hellfire_battleaxe_plus_2", "crown_of_twilight"})
        self.assertEqual(by_id.get("hellish_platemail", {}).get("equip_slot"), "armour")
        self.assertEqual(by_id.get("crown_of_twilight", {}).get("equip_slot"), "head")
        self.assertEqual(by_id.get("hellfire_battleaxe_plus_2", {}).get("slot"), "main_hand")
        self.assertEqual(by_id.get("hellfire_battleaxe_plus_2", {}).get("equip_slot"), "off_hand")
        self.assertTrue(all(bool(by_id.get(item_id, {}).get("equipped")) for item_id in ("hellish_platemail", "hellfire_battleaxe_plus_2", "crown_of_twilight")))
        weapons = (((data.get("attacks") or {}).get("weapons")) or [])
        battleaxe = next((entry for entry in weapons if (entry or {}).get("id") == "hellfire_battleaxe_plus_2"), {})
        self.assertTrue(bool(battleaxe.get("main_hand")))
        self.assertTrue(bool(battleaxe.get("off_hand")))

    def test_oldahhman_leveling_and_speed_schema(self):
        data = self._load("players/oldahhman.yaml")
        leveling = data.get("leveling") or {}
        classes = leveling.get("classes") or []
        class_level_sum = sum(int((entry or {}).get("level") or 0) for entry in classes if isinstance(entry, dict))
        self.assertEqual(int(leveling.get("level") or 0), class_level_sum)
        speed = ((data.get("vitals") or {}).get("speed") or {})
        self.assertEqual(set(speed.keys()), {"walk", "climb", "fly", "swim"})

    def test_vicnor_ac_source_and_language_typo_cleanup(self):
        data = self._load("players/vicnor.yaml")
        ac_sources = (((data.get("defenses") or {}).get("ac") or {}).get("sources") or [])
        self.assertTrue(ac_sources)
        first_source = ac_sources[0]
        self.assertTrue(str(first_source.get("id") or "").strip())
        self.assertTrue(str(first_source.get("label") or "").strip())
        languages = ((data.get("proficiency") or {}).get("languages") or [])
        self.assertNotIn("Theives Cant", languages)
        self.assertIn("Thieves Cant", languages)
        spellcasting = data.get("spellcasting") or {}
        self.assertEqual((spellcasting.get("pact_magic_slots") or {}).get("level"), 1)
        self.assertEqual((spellcasting.get("pact_magic_slots") or {}).get("count"), 1)
        self.assertEqual(((spellcasting.get("spell_slots") or {}).get("1") or {}).get("max"), 1)
        self.assertEqual(((spellcasting.get("cantrips") or {}).get("known") or []), ["eldritch-blast", "mage-hand"])
        self.assertEqual(((spellcasting.get("prepared_spells") or {}).get("prepared") or []), ["hex", "armor-of-agathys"])


    def test_dorian_paladins_smite_feature_present(self):
        data = self._load("players/dorian_vandergraff.yaml")
        features = data.get("features") or []
        paladins_smite = next((entry for entry in features if (entry or {}).get("id") == "paladins_smite"), {})
        self.assertEqual((paladins_smite.get("grants") or {}).get("always_prepared_spells"), ["divine-smite"])
        casts = ((((paladins_smite.get("grants") or {}).get("spells") or {}).get("casts")) or [])
        divine_smite_cast = next((entry for entry in casts if (entry or {}).get("spell") == "divine-smite"), {})
        self.assertEqual((divine_smite_cast.get("consumes") or {}).get("pool"), "paladins_smite")
        self.assertEqual((divine_smite_cast.get("consumes") or {}).get("cost"), 1)
        pools = (((data.get("resources") or {}).get("pools")) or [])
        paladins_smite_pool = next((entry for entry in pools if (entry or {}).get("id") == "paladins_smite"), {})
        self.assertEqual(paladins_smite_pool.get("max"), 1)
        self.assertEqual(paladins_smite_pool.get("current"), 1)
        self.assertEqual(paladins_smite_pool.get("reset"), "long_rest")

    def test_stikhiya_save_abbreviation_uses_cha(self):
        data = self._load("players/стихия.yaml")
        saves = ((data.get("proficiency") or {}).get("saves") or [])
        self.assertIn("CHA", saves)
        self.assertNotIn("CHR", saves)

    def test_stikhiya_default_equipment_items(self):
        data = self._load("players/стихия.yaml")
        weapons = ((data.get("attacks") or {}).get("weapons") or [])
        bardiche = next((entry for entry in weapons if (entry or {}).get("id") == "bardiche_plus_2"), {})
        self.assertTrue(bardiche.get("equipped"))
        self.assertTrue(bardiche.get("main_hand"))

        inventory_items = ((data.get("inventory") or {}).get("items") or [])
        by_name = {str((entry or {}).get("name") or ""): (entry or {}) for entry in inventory_items if isinstance(entry, dict)}
        self.assertEqual(by_name.get("гром", {}).get("slot"), "head")
        self.assertTrue(by_name.get("гром", {}).get("equipped"))
        self.assertEqual(by_name.get("Gauntlets of Lesser Hill Giant Strength", {}).get("slot"), "gloves")
        self.assertTrue(by_name.get("Gauntlets of Lesser Hill Giant Strength", {}).get("equipped"))
        self.assertEqual(by_name.get("Bane Platemail +1", {}).get("slot"), "armour")
        self.assertTrue(by_name.get("Bane Platemail +1", {}).get("equipped"))
    def test_malagrou_defaults_to_two_handed_axe_mode(self):
        data = self._load("players/malagrou.yaml")
        weapons = (((data.get("attacks") or {}).get("weapons")) or [])
        axe = next((entry for entry in weapons if str((entry or {}).get("id") or "").strip() == "big_ass_axe_plus_1"), {})
        self.assertEqual(str(axe.get("selected_mode") or "").strip().lower(), "two")

    def test_player_yaml_guardrails(self):
        valid_save_keys = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
        required_speed_keys = {"walk", "climb", "fly", "swim"}
        for path in sorted(Path("players").glob("*.yaml")):
            data = self._load(str(path))
            with self.subTest(player=path.name):
                leveling = data.get("leveling") if isinstance(data.get("leveling"), dict) else {}
                classes = leveling.get("classes") if isinstance(leveling.get("classes"), list) else []
                if classes:
                    class_level_sum = sum(int((entry or {}).get("level") or 0) for entry in classes if isinstance(entry, dict))
                    self.assertEqual(
                        int(leveling.get("level") or 0),
                        class_level_sum,
                        msg=f"{path.name}: leveling.level must equal sum(leveling.classes[].level)",
                    )
                speed = ((data.get("vitals") or {}).get("speed") or {})
                self.assertEqual(
                    set(speed.keys()),
                    required_speed_keys,
                    msg=f"{path.name}: vitals.speed must define walk/climb/fly/swim keys",
                )
                saves = ((data.get("proficiency") or {}).get("saves") or [])
                bad_saves = [entry for entry in saves if str(entry or "").strip().upper() not in valid_save_keys]
                self.assertFalse(bad_saves, msg=f"{path.name}: unsupported save abbreviations {bad_saves}")
                ac_sources = (((data.get("defenses") or {}).get("ac") or {}).get("sources") or [])
                for source in ac_sources:
                    if not isinstance(source, dict):
                        continue
                    self.assertTrue(str(source.get("id") or "").strip(), msg=f"{path.name}: defenses.ac.sources[] entries need an id")
                    self.assertTrue(str(source.get("label") or "").strip(), msg=f"{path.name}: defenses.ac.sources[] entries need a label")


if __name__ == "__main__":
    unittest.main()
