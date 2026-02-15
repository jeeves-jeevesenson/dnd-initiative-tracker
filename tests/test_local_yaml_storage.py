import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dnd_initative_tracker as tracker_mod


class LocalYamlStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base_dir = self.root / "app"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.root / "data"

    def test_seed_players_to_client_data_dir(self):
        source = self.base_dir / "players"
        source.mkdir(parents=True, exist_ok=True)
        (source / "alpha.yaml").write_text("name: Alpha\n", encoding="utf-8")
        with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": str(self.data_dir)}, clear=False):
            with mock.patch.object(tracker_mod, "_app_base_dir", return_value=self.base_dir):
                tracker_mod._seed_user_players_dir()
        self.assertTrue((self.data_dir / "players" / "alpha.yaml").exists())

    def test_seed_spells_and_monsters_without_overwriting_custom(self):
        spells_source = self.base_dir / "Spells"
        spells_source.mkdir(parents=True, exist_ok=True)
        (spells_source / "fire_bolt.yaml").write_text("name: Fire Bolt\n", encoding="utf-8")
        monsters_source = self.base_dir / "Monsters" / "core"
        monsters_source.mkdir(parents=True, exist_ok=True)
        (monsters_source / "wolf.yaml").write_text("monster:\n  name: Wolf\n", encoding="utf-8")

        custom_spells_dir = self.data_dir / "Spells"
        custom_spells_dir.mkdir(parents=True, exist_ok=True)
        custom_spell = custom_spells_dir / "fire_bolt.yaml"
        custom_spell.write_text("name: Fire Bolt Custom\n", encoding="utf-8")

        with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": str(self.data_dir)}, clear=False):
            with mock.patch.object(tracker_mod, "_app_base_dir", return_value=self.base_dir):
                spells_dir = tracker_mod._seed_user_spells_dir()
                monsters_dir = tracker_mod._seed_user_monsters_dir()

        self.assertEqual(spells_dir, self.data_dir / "Spells")
        self.assertEqual(monsters_dir, self.data_dir / "Monsters")
        self.assertEqual(custom_spell.read_text(encoding="utf-8"), "name: Fire Bolt Custom\n")
        self.assertTrue((self.data_dir / "Monsters" / "core" / "wolf.yaml").exists())


if __name__ == "__main__":
    unittest.main()
