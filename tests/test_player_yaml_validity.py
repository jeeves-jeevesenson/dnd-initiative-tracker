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


if __name__ == "__main__":
    unittest.main()
