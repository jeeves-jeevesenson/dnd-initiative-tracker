import unittest
from pathlib import Path

import yaml


class PlayerYamlValidityTests(unittest.TestCase):
    def test_john_twilight_yaml_parses(self):
        path = Path("players/John_Twilight.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertEqual(str(data.get("name") or "").strip(), "John Twilight")


if __name__ == "__main__":
    unittest.main()
