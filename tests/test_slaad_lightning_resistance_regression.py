import unittest

import dnd_initative_tracker as tracker_mod


class SlaadLightningResistanceRegressionTests(unittest.TestCase):
    def test_blue_slaad_lightning_damage_is_halved(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._log = lambda *args, **kwargs: None
        app._monster_specs = []
        app._monsters_by_name = {}
        app._load_monsters_index()

        blue_slaad_spec = app._find_monster_spec_by_slug("blue-slaad")
        self.assertIsNotNone(blue_slaad_spec)
        self.assertIsInstance(getattr(blue_slaad_spec, "raw_data", None), dict)
        self.assertIn("damage_resistances", blue_slaad_spec.raw_data)

        target = type("Target", (), {"monster_spec": blue_slaad_spec, "is_pc": False})()
        adjusted = app._adjust_damage_entries_for_target(target, [{"amount": 40, "type": "Lightning"}])

        self.assertEqual(adjusted.get("entries"), [{"amount": 20, "type": "lightning"}])


if __name__ == "__main__":
    unittest.main()
