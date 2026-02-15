import unittest

import dnd_initative_tracker as tracker_mod


class PlayerAcCalculationTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)

    def test_ac_sources_formula_uses_ability_modifiers(self):
        profile = {
            "abilities": {"dex": 16},
            "defenses": {
                "ac": {
                    "sources": [{"id": "unarmored", "when": "always", "base_formula": "10 + dex_mod"}],
                    "bonuses": [],
                }
            },
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 13)

    def test_ac_chooses_highest_source_and_applies_always_bonus(self):
        profile = {
            "abilities": {"dex": 14},
            "defenses": {
                "ac": {
                    "sources": [
                        {"id": "armor", "when": "always", "base_formula": "16"},
                        {"id": "unarmored", "when": "always", "base_formula": "10 + dex_mod"},
                    ],
                    "bonuses": [{"when": "always", "value": 1}],
                }
            },
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 17)

    def test_ac_source_applies_magic_bonus_when_present(self):
        profile = {
            "abilities": {"dex": 12},
            "defenses": {
                "ac": {
                    "sources": [{"id": "plate_armor", "when": "always", "base_formula": "18", "magic_bonus": 1}],
                    "bonuses": [],
                }
            },
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 19)


if __name__ == "__main__":
    unittest.main()
