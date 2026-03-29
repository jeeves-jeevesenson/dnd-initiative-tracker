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

    def test_bracers_of_defense_bonus_applies_when_attuned_equipped_no_armor_no_shield(self):
        self.app._magic_items_registry_payload = lambda: {
            "bracers_of_defense": {
                "id": "bracers_of_defense",
                "requires_attunement": True,
                "grants": {
                    "modifiers": [
                        {
                            "id": "bracers_of_defense_ac_bonus",
                            "target": "ac",
                            "effect": "ac_bonus",
                            "amount": 2,
                            "requires_no_armor": True,
                            "requires_no_shield": True,
                        }
                    ]
                },
            }
        }
        profile = {
            "abilities": {"dex": 16, "wis": 16},
            "defenses": {
                "ac": {
                    "sources": [{"id": "unarmored", "when": "always", "base_formula": "10 + dex_mod + wis_mod"}],
                    "bonuses": [],
                }
            },
            "inventory": {"items": [{"id": "bracers_of_defense", "equipped": True, "attuned": True}]},
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 18)

    def test_bracers_of_defense_no_bonus_when_armor_equipped(self):
        self.app._magic_items_registry_payload = lambda: {
            "bracers_of_defense": {
                "id": "bracers_of_defense",
                "requires_attunement": True,
                "grants": {
                    "modifiers": [
                        {"target": "ac", "effect": "ac_bonus", "amount": 2, "requires_no_armor": True, "requires_no_shield": True}
                    ]
                },
            }
        }
        profile = {
            "abilities": {"dex": 16, "wis": 16},
            "defenses": {"ac": {"sources": [{"id": "unarmored", "when": "always", "base_formula": "10 + dex_mod + wis_mod"}], "bonuses": []}},
            "inventory": {
                "items": [
                    {"id": "chain_mail", "name": "Chain Mail", "category": "armor", "equipped": True},
                    {"id": "bracers_of_defense", "equipped": True, "attuned": True},
                ]
            },
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 16)

    def test_bracers_of_defense_no_bonus_when_shield_equipped(self):
        self.app._magic_items_registry_payload = lambda: {
            "bracers_of_defense": {
                "id": "bracers_of_defense",
                "requires_attunement": True,
                "grants": {
                    "modifiers": [
                        {"target": "ac", "effect": "ac_bonus", "amount": 2, "requires_no_armor": True, "requires_no_shield": True}
                    ]
                },
            }
        }
        profile = {
            "abilities": {"dex": 16, "wis": 16},
            "defenses": {"ac": {"sources": [{"id": "unarmored", "when": "always", "base_formula": "10 + dex_mod + wis_mod"}], "bonuses": []}},
            "inventory": {
                "items": [
                    {"id": "shield", "name": "Shield", "category": "shield", "equipped": True},
                    {"id": "bracers_of_defense", "equipped": True, "attuned": True},
                ]
            },
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 16)

    def test_bracers_of_defense_no_bonus_when_not_attuned_or_equipped(self):
        self.app._magic_items_registry_payload = lambda: {
            "bracers_of_defense": {
                "id": "bracers_of_defense",
                "requires_attunement": True,
                "grants": {
                    "modifiers": [
                        {"target": "ac", "effect": "ac_bonus", "amount": 2, "requires_no_armor": True, "requires_no_shield": True}
                    ]
                },
            }
        }
        profile = {
            "abilities": {"dex": 16, "wis": 16},
            "defenses": {"ac": {"sources": [{"id": "unarmored", "when": "always", "base_formula": "10 + dex_mod + wis_mod"}], "bonuses": []}},
            "inventory": {"items": [{"id": "bracers_of_defense", "equipped": False, "attuned": False}]},
        }
        self.assertEqual(self.app._resolve_player_ac(profile, profile["defenses"]), 16)


if __name__ == "__main__":
    unittest.main()
