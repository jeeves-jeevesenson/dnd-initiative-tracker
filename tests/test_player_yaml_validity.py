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

    def test_stikhiya_save_abbreviation_uses_cha(self):
        data = self._load("players/стихия.yaml")
        saves = ((data.get("proficiency") or {}).get("saves") or [])
        self.assertIn("CHA", saves)
        self.assertNotIn("CHR", saves)

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
