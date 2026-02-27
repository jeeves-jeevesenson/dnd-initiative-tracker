import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dnd_initative_tracker as tracker_mod


class SpellbookFreeSpellsTests(unittest.TestCase):
    def test_save_spellbook_filters_free_spells_to_current_lists(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        with tempfile.TemporaryDirectory() as tmpdir:
            player_path = Path(tmpdir) / "mage.yaml"
            player_path.write_text("name: Mage\n", encoding="utf-8")

            app._load_player_yaml_cache = lambda: None
            app._find_player_profile_path = lambda _name: player_path
            app._players_dir = lambda: player_path.parent
            app._sanitize_player_filename = lambda value: str(value or "player")
            app._normalize_character_lookup_key = lambda value: str(value or "").strip().lower()
            app._schedule_player_yaml_refresh = lambda: None
            app._player_yaml_cache_by_path = {
                player_path: {
                    "name": "Mage",
                    "spellcasting": {
                        "known_spells": {"known": ["magic-missile", "shield"], "free": ["shield", "sleep"]},
                        "prepared_spells": {"prepared": ["mage-armor", "shield"], "free": ["shield", "sleep"]},
                    },
                }
            }
            app._player_yaml_meta_by_path = {}
            app._player_yaml_data_by_name = {}
            app._player_yaml_name_map = {}
            app._write_player_yaml_atomic = lambda path, payload: app._player_yaml_cache_by_path.__setitem__(path, payload)
            app._normalize_player_profile = lambda payload, _stem: {
                "name": payload.get("name", "Mage"),
                "spellcasting": payload.get("spellcasting", {}),
            }
            app._all_active_features = lambda profile: profile.get("features", []) if isinstance(profile, dict) else []
            app._normalize_spell_slug_list = lambda value: [str(item).strip().lower() for item in (value if isinstance(value, list) else [value] if isinstance(value, str) else []) if str(item).strip()]

            with mock.patch.object(tracker_mod, "_file_stat_metadata", return_value={}):
                app._save_player_spellbook(
                    "Mage",
                    {
                        "known_enabled": True,
                        "known_list": ["magic-missile"],
                        "prepared_list": ["shield"],
                        "cantrips_list": [],
                    },
                )

            saved = app._player_yaml_cache_by_path[player_path]
            self.assertEqual(saved["spellcasting"]["known_spells"]["known"], ["magic-missile"])
            self.assertNotIn("free", saved["spellcasting"]["known_spells"])
            self.assertEqual(saved["spellcasting"]["prepared_spells"]["prepared"], ["shield"])
            self.assertEqual(saved["spellcasting"]["prepared_spells"]["free"], ["shield"])

    def test_save_spellbook_reinserts_feature_always_prepared_spells(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        with tempfile.TemporaryDirectory() as tmpdir:
            player_path = Path(tmpdir) / "glamour.yaml"
            player_path.write_text("name: Throat Goat\n", encoding="utf-8")

            app._load_player_yaml_cache = lambda: None
            app._find_player_profile_path = lambda _name: player_path
            app._players_dir = lambda: player_path.parent
            app._sanitize_player_filename = lambda value: str(value or "player")
            app._normalize_character_lookup_key = lambda value: str(value or "").strip().lower()
            app._schedule_player_yaml_refresh = lambda: None
            app._all_active_features = lambda profile: profile.get("features", []) if isinstance(profile, dict) else []
            app._normalize_spell_slug_list = lambda value: [str(item).strip().lower() for item in (value if isinstance(value, list) else [value] if isinstance(value, str) else []) if str(item).strip()]
            app._player_yaml_cache_by_path = {
                player_path: {
                    "name": "Throat Goat",
                    "features": [
                        {
                            "name": "Mantle of Majesty",
                            "grants": {"always_prepared_spells": ["command"]},
                        }
                    ],
                    "spellcasting": {
                        "prepared_spells": {
                            "prepared": ["command", "healing-word"],
                            "free": ["command"],
                        }
                    },
                }
            }
            app._player_yaml_meta_by_path = {}
            app._player_yaml_data_by_name = {}
            app._player_yaml_name_map = {}
            app._write_player_yaml_atomic = lambda path, payload: app._player_yaml_cache_by_path.__setitem__(path, payload)
            app._normalize_player_profile = lambda payload, _stem: {
                "name": payload.get("name", "Throat Goat"),
                "spellcasting": payload.get("spellcasting", {}),
            }

            with mock.patch.object(tracker_mod, "_file_stat_metadata", return_value={}):
                app._save_player_spellbook(
                    "Throat Goat",
                    {
                        "known_enabled": False,
                        "known_list": [],
                        "prepared_list": ["healing-word"],
                        "cantrips_list": [],
                    },
                )

            saved = app._player_yaml_cache_by_path[player_path]
            prepared = saved["spellcasting"]["prepared_spells"]["prepared"]
            free = saved["spellcasting"]["prepared_spells"]["free"]
            self.assertIn("command", prepared)
            self.assertIn("command", free)


if __name__ == "__main__":
    unittest.main()
