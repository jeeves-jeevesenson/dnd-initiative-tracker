import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class RandomEnemyBuilderTests(unittest.TestCase):
    def _tracker(self):
        return object.__new__(tracker_mod.InitiativeTracker)

    def _spec(self, name: str, cr: float, raw_cr=None):
        raw_data = {}
        if raw_cr is not None:
            raw_data["challenge_rating"] = raw_cr
        return tracker_mod.MonsterSpec(
            filename=f"{name.lower().replace(' ', '-')}.yaml",
            name=name,
            mtype="test",
            cr=cr,
            hp=10,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=10,
            init_mod=0,
            saving_throws={},
            ability_mods={},
            raw_data=raw_data,
        )

    def test_monster_spec_cr_value_parses_fractional_raw_values(self):
        tracker = self._tracker()
        self.assertEqual(tracker._monster_spec_cr_value(self._spec("Wolf", 0.25, raw_cr="1/2")), 0.5)

    def test_random_monster_specs_respects_max_cr_and_total_cr(self):
        tracker = self._tracker()
        tracker._monster_specs = [
            self._spec("Rat", 0.25),
            self._spec("Bandit", 1.0),
            self._spec("Ogre", 2.0),
        ]

        with mock.patch("helper_script.random.choice", side_effect=lambda choices: choices[-1]):
            picks = tracker._random_monster_specs_for_encounter(max_individual_cr=1.0, total_cr=2.5)

        pick_crs = [tracker._monster_spec_cr_value(spec) for spec in picks]
        self.assertTrue(picks)
        self.assertTrue(all(cr <= 1.0 for cr in pick_crs))
        self.assertLessEqual(sum(pick_crs), 2.5 + 1e-9)
        self.assertEqual(sum(pick_crs), 2.5)

    def test_random_monster_specs_ignores_zero_cr(self):
        tracker = self._tracker()
        tracker._monster_specs = [
            self._spec("Commoner", 0.0, raw_cr=0),
            self._spec("Scout", 0.5),
        ]
        picks = tracker._random_monster_specs_for_encounter(max_individual_cr=1.0, total_cr=1.0)
        self.assertEqual(len(picks), 2)
        self.assertTrue(all(spec.name == "Scout" for spec in picks))


if __name__ == "__main__":
    unittest.main()
