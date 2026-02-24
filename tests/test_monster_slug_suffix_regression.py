import unittest

import dnd_initative_tracker as tracker_mod


class MonsterSlugSuffixRegressionTests(unittest.TestCase):
    def test_find_monster_spec_accepts_yaml_suffix_and_monsters_prefix(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._log = lambda *args, **kwargs: None
        app._monster_specs = []
        app._monsters_by_name = {}
        app._load_monsters_index()

        bare = app._find_monster_spec_by_slug("gray-ooze")
        with_yaml = app._find_monster_spec_by_slug("gray-ooze.yaml")
        with_yml = app._find_monster_spec_by_slug("gray-ooze.yml")
        with_prefix = app._find_monster_spec_by_slug("Monsters/gray-ooze.yaml")

        self.assertIsNotNone(bare)
        self.assertIsNotNone(with_yaml)
        self.assertIsNotNone(with_yml)
        self.assertIsNotNone(with_prefix)


if __name__ == "__main__":
    unittest.main()
