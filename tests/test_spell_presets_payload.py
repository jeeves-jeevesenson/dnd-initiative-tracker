import tempfile
import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


class SpellPresetsPayloadTests(unittest.TestCase):
    def test_spell_presets_payload_loads_from_spells_dir(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._spell_presets_cache = None
        app._spell_dir_signature = None
        app._spell_index_entries = {}
        app._spell_index_loaded = False
        app._load_spell_index_entries = lambda: {}

        with tempfile.TemporaryDirectory() as temp_dir:
            spells_dir = Path(temp_dir)
            spells_dir.joinpath("magic-missile.yaml").write_text(
                "\n".join(
                    [
                        "name: Magic Missile",
                        "schema: dnd5e.spell/v1",
                        "id: magic-missile",
                        "level: 1",
                        "school: Evocation",
                        "casting_time: 1 action",
                        "range: 120 feet",
                        "mechanics: {}",
                    ]
                ),
                encoding="utf-8",
            )
            app._resolve_spells_dir = lambda: spells_dir
            app._spell_index_path = lambda: spells_dir / "spells.index.json"

            presets = app._spell_presets_payload()

        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]["slug"], "magic-missile")


if __name__ == "__main__":
    unittest.main()
