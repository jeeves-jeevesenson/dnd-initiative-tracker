import copy
import unittest
from pathlib import Path

import yaml

import dnd_initative_tracker as tracker_mod


class PactMagicSpellSlotRegressionTests(unittest.TestCase):
    @staticmethod
    def _load_vicnor_profile():
        return yaml.safe_load(Path("players/vicnor.yaml").read_text(encoding="utf-8"))

    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)

    def test_progression_inference_does_not_default_rogue_warlock_to_full(self):
        progression = self.app._spell_slot_progression_from_profile(
            {
                "classes": [
                    {"name": "Rogue", "subclass": "Swashbuckler", "level": 3},
                    {"name": "Warlock", "subclass": "The Noble Genie", "level": 7},
                ]
            },
            {"enabled": True},
        )
        self.assertEqual(progression, "none")

    def test_normalization_keeps_standard_slots_zero_for_pact_only_profile(self):
        raw = self._load_vicnor_profile()
        normalized = self.app._normalize_player_profile(copy.deepcopy(raw), "Vicnor")
        slots = (((normalized.get("spellcasting") or {}).get("spell_slots")) or {})
        self.assertEqual(
            {str(level): int((slots.get(str(level), {}) or {}).get("max", -1)) for level in range(1, 10)},
            {str(level): 0 for level in range(1, 10)},
        )
        pact = ((normalized.get("spellcasting") or {}).get("pact_magic_slots")) or {}
        self.assertEqual(int(pact.get("level") or 0), 4)
        self.assertEqual(int(pact.get("count") or 0), 2)

    def test_cast_attempt_with_standard_slot_does_not_persist_fake_slots(self):
        raw = self._load_vicnor_profile()
        normalized = self.app._normalize_player_profile(copy.deepcopy(raw), "Vicnor")
        saved_payloads = []

        self.app._profile_for_player_name = lambda _name: normalized
        self.app._save_player_spell_slots = lambda _name, slots: saved_payloads.append(copy.deepcopy(slots))

        ok, err, spent = self.app._consume_spell_slot_for_cast("Vicnor", 5, 4)
        self.assertFalse(ok)
        self.assertIn("No spell slots left", err)
        self.assertIsNone(spent)
        self.assertEqual(saved_payloads, [])

        slots = (((normalized.get("spellcasting") or {}).get("spell_slots")) or {})
        self.assertTrue(all(int((slots.get(str(level), {}) or {}).get("max", 0)) == 0 for level in range(1, 10)))


if __name__ == "__main__":
    unittest.main()
