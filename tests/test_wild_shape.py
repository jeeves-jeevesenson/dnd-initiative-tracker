import tempfile
import unittest
from pathlib import Path

import yaml

import dnd_initative_tracker as tracker_mod


class WildShapeTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._wild_shape_beast_cache = [
            {
                "id": "wolf",
                "name": "Wolf",
                "challenge_rating": 0.25,
                "size": "Medium",
                "ac": 13,
                "speed": {"walk": 40, "swim": 0, "fly": 0, "climb": 0},
                "abilities": {"str": 12, "dex": 15, "con": 12, "int": 3, "wis": 12, "cha": 6},
                "actions": [{"name": "Bite", "type": "action"}],
            },
            {
                "id": "reef-shark",
                "name": "Reef Shark",
                "challenge_rating": 0.5,
                "size": "Medium",
                "ac": 12,
                "speed": {"walk": 0, "swim": 40, "fly": 0, "climb": 0},
                "abilities": {"str": 14, "dex": 13, "con": 13, "int": 1, "wis": 10, "cha": 4},
                "actions": [{"name": "Bite", "type": "action"}],
            },
            {
                "id": "brown-bear",
                "name": "Brown Bear",
                "challenge_rating": 1.0,
                "size": "Large",
                "ac": 11,
                "speed": {"walk": 40, "swim": 0, "fly": 0, "climb": 30},
                "abilities": {"str": 17, "dex": 12, "con": 15, "int": 2, "wis": 13, "cha": 7},
                "actions": [{"name": "Claw", "type": "action"}],
            },
            {
                "id": "giant-scorpion",
                "name": "Giant Scorpion",
                "challenge_rating": 3.0,
                "size": "Large",
                "ac": 15,
                "speed": {"walk": 40, "swim": 0, "fly": 0, "climb": 0},
                "abilities": {"str": 15, "dex": 13, "con": 15, "int": 1, "wis": 9, "cha": 3},
                "actions": [],
            },
            {
                "id": "eagle",
                "name": "Eagle",
                "challenge_rating": 0.0,
                "size": "Small",
                "ac": 12,
                "speed": {"walk": 10, "swim": 0, "fly": 60, "climb": 0},
                "abilities": {"str": 6, "dex": 15, "con": 10, "int": 2, "wis": 14, "cha": 7},
                "actions": [],
            },
            {
                "id": "cat",
                "name": "Cat",
                "challenge_rating": 0.0,
                "size": "Tiny",
                "ac": 12,
                "speed": {"walk": 40, "swim": 0, "fly": 0, "climb": 30},
                "abilities": {"str": 3, "dex": 15, "con": 10, "int": 3, "wis": 12, "cha": 7},
                "actions": [],
            },
        ]

    def _profile(self, level):
        return {
            "leveling": {"classes": [{"name": "Druid", "level": level}]},
            "resources": {"pools": []},
            "prepared_wild_shapes": ["wolf", "brown-bear", "reef-shark", "eagle", "cat"],
        }

    def test_resource_pool_auto_added(self):
        pools = self.app._normalize_player_resource_pools(self._profile(2))
        wild = next((p for p in pools if p["id"] == "wild_shape"), None)
        self.assertIsNotNone(wild)
        self.assertEqual(wild["max"], 2)
        self.assertEqual(wild["gain_on_short"], 1)

    def test_available_forms_gating(self):
        lvl2 = {f["id"] for f in self.app._wild_shape_available_forms(self._profile(2), known_only=True)}
        self.assertIn("wolf", lvl2)
        self.assertNotIn("brown-bear", lvl2)
        self.assertNotIn("reef-shark", lvl2)
        self.assertNotIn("eagle", lvl2)
        self.assertNotIn("cat", lvl2)

        lvl8 = {f["id"] for f in self.app._wild_shape_available_forms(self._profile(8), known_only=True)}
        self.assertIn("brown-bear", lvl8)
        self.assertIn("eagle", lvl8)
        self.assertNotIn("cat", lvl8)

        lvl11 = {f["id"] for f in self.app._wild_shape_available_forms(self._profile(11), known_only=True)}
        self.assertIn("cat", lvl11)
        self.assertNotIn("giant-scorpion", lvl11)

    def test_available_forms_excludes_above_cr_two_even_when_include_locked(self):
        forms = self.app._wild_shape_available_forms(self._profile(20), known_only=False, include_locked=True)
        ids = {f["id"] for f in forms}
        self.assertNotIn("giant-scorpion", ids)

    def test_load_beast_forms_prefers_monster_index_and_caches(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._wild_shape_beast_cache = None
        app._monster_specs = [
            tracker_mod.MonsterSpec(
                filename="wolf.yaml",
                name="Wolf",
                mtype="beast",
                cr=0.25,
                hp=11,
                speed=40,
                swim_speed=0,
                fly_speed=0,
                burrow_speed=0,
                climb_speed=0,
                dex=15,
                init_mod=2,
                saving_throws={},
                ability_mods={},
                raw_data={
                    "name": "Wolf",
                    "type": "Beast",
                    "challenge_rating": "1/4",
                    "size": "Medium",
                    "ac": 13,
                    "hp": 11,
                    "speed": "40 ft.",
                    "abilities": {"Str": 12, "Dex": 15, "Con": 12, "Int": 3, "Wis": 12, "Cha": 6},
                    "actions": [{"name": "Bite", "type": "action"}],
                },
            ),
            tracker_mod.MonsterSpec(
                filename="bandit.yaml",
                name="Bandit",
                mtype="humanoid",
                cr=0.125,
                hp=11,
                speed=30,
                swim_speed=0,
                fly_speed=0,
                burrow_speed=0,
                climb_speed=0,
                dex=12,
                init_mod=1,
                saving_throws={},
                ability_mods={},
                raw_data={
                    "name": "Bandit",
                    "type": "Humanoid",
                    "challenge_rating": "1/8",
                    "actions": [{"name": "Scimitar", "type": "action"}],
                },
            ),
        ]

        first = app._load_beast_forms()
        self.assertEqual([entry["id"] for entry in first], ["wolf"])
        second = app._load_beast_forms()
        self.assertIs(first, second)

    def test_apply_and_revert_wild_shape(self):
        self.app.combatants = {
            1: type("C", (), {
                "cid": 1,
                "name": "Alice",
                "speed": 30,
                "swim_speed": 0,
                "fly_speed": 0,
                "climb_speed": 0,
                "burrow_speed": 0,
                "movement_mode": "Normal",
                "dex": 14,
                "con": 12,
                "str": 10,
                "temp_hp": 5,
                "actions": [{"name": "Magic", "type": "action"}],
                "bonus_actions": [],
                "is_spellcaster": True,
            })()
        }
        self.app._pc_name_for = lambda _cid: "Alice"
        self.app._load_player_yaml_cache = lambda force_refresh=False: None
        self.app._player_yaml_data_by_name = {"Alice": self._profile(8)}
        self.app._set_wild_shape_pool_current = lambda _name, value: (True, "", value)
        ok, err = self.app._apply_wild_shape(1, "brown-bear")
        self.assertTrue(ok, err)
        c = self.app.combatants[1]
        self.assertTrue(c.is_wild_shaped)
        self.assertFalse(c.is_spellcaster)
        self.assertEqual(c.str, 17)
        self.assertIn("Brown Bear", c.name)

        ok2, err2 = self.app._revert_wild_shape(1)
        self.assertTrue(ok2, err2)
        self.assertFalse(c.is_wild_shaped)
        self.assertEqual(c.name, "Alice")
        self.assertTrue(c.is_spellcaster)

    def test_wild_resurgence_slot_exchange(self):
        self.app._resolve_spell_slot_profile = lambda _name: (
            "Alice",
            {
                "1": {"max": 2, "current": 1},
                "2": {"max": 0, "current": 0},
                "3": {"max": 0, "current": 0},
                "4": {"max": 0, "current": 0},
                "5": {"max": 0, "current": 0},
                "6": {"max": 0, "current": 0},
                "7": {"max": 0, "current": 0},
                "8": {"max": 0, "current": 0},
                "9": {"max": 0, "current": 0},
            },
        )
        saved = {}
        self.app._save_player_spell_slots = lambda _name, slots: saved.setdefault("slots", slots)

        ok, err, spent = self.app._consume_spell_slot_for_wild_shape_regain("Alice")
        self.assertTrue(ok, err)
        self.assertEqual(spent, 1)

        saved.clear()
        self.app._resolve_spell_slot_profile = lambda _name: (
            "Alice",
            {
                "1": {"max": 2, "current": 1},
                "2": {"max": 0, "current": 0},
                "3": {"max": 0, "current": 0},
                "4": {"max": 0, "current": 0},
                "5": {"max": 0, "current": 0},
                "6": {"max": 0, "current": 0},
                "7": {"max": 0, "current": 0},
                "8": {"max": 0, "current": 0},
                "9": {"max": 0, "current": 0},
            },
        )
        ok2, err2 = self.app._regain_first_level_spell_slot("Alice")
        self.assertTrue(ok2, err2)

    def test_normalize_profile_preserves_prepared_wild_shapes(self):
        payload = {
            "name": "Leaf",
            "leveling": {"classes": [{"name": "Druid", "level": 2}]},
            "prepared_wild_shapes": [" Wolf ", "wolf", "brown-bear", "reef-shark"],
        }
        normalized = self.app._normalize_player_profile(payload, "Leaf")
        self.assertEqual(normalized.get("prepared_wild_shapes"), ["wolf", "brown-bear", "reef-shark"])

    def test_player_profiles_payload_uses_persisted_shapes_without_runtime_override(self):
        self.app._load_player_yaml_cache = lambda force_refresh=False: None
        self.app._player_yaml_data_by_name = {
            "Leaf": {
                "name": "Leaf",
                "leveling": {"classes": [{"name": "Druid", "level": 2}]},
                "prepared_wild_shapes": ["wolf", "brown-bear"],
            }
        }
        self.app._wild_shape_known_by_player = {}
        self.app._wild_shape_available_cache = {}
        self.app._wild_shape_available_cache_source = self.app._wild_shape_beast_cache

        payload = self.app._player_profiles_payload()
        self.assertEqual(payload["Leaf"]["learned_wild_shapes"], ["wolf", "brown-bear"])
        self.assertEqual(payload["Leaf"]["prepared_wild_shapes"], ["wolf", "brown-bear"])

    def test_wild_shape_set_known_persists_to_yaml(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app.in_combat = False
        app.combatants = {1: object()}
        app._pc_name_for = lambda _cid: "Leaf"
        app._is_admin_token_valid = lambda _token: True
        app._summon_can_be_controlled_by = lambda claimed, cid: False
        app._load_player_yaml_cache = lambda force_refresh=False: None
        app._rebuild_table = lambda scroll_to_current=False: None
        app._wild_shape_known_by_player = {}
        app._player_yaml_data_by_name = {
            "Leaf": {
                "name": "Leaf",
                "leveling": {"classes": [{"name": "Druid", "level": 2}]},
                "prepared_wild_shapes": ["wolf"],
            }
        }
        app._wild_shape_available_forms = lambda profile, known_only=False, include_locked=False: [
            {"id": "wolf"},
            {"id": "reef-shark"},
        ]
        app._lan = type("Lan", (), {"toast": lambda self, ws_id, text: None, "_append_lan_log": lambda self, msg, level='warning': None})()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "leaf.yaml"
            path.write_text("""name: Leaf
prepared_wild_shapes:
  - wolf
""", encoding="utf-8")
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            app._player_yaml_cache_by_path = {path: raw}
            app._player_yaml_meta_by_path = {}
            app._player_yaml_name_map = {"leaf": path}
            app._player_yaml_lock = tracker_mod.threading.Lock()
            app._schedule_player_yaml_refresh = lambda: None

            app._lan_apply_action({
                "type": "wild_shape_set_known",
                "cid": 1,
                "_ws_id": 100,
                "admin_token": "ok",
                "known": ["reef-shark", "wolf", "wolf"],
            })

            updated = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(updated.get("prepared_wild_shapes"), ["reef-shark", "wolf"])
            self.assertNotIn("learned_wild_shapes", updated)

    def test_wild_shape_apply_requires_bonus_action(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app.in_combat = True
        app.combatants = {1: type("C", (), {"cid": 1})()}
        app._is_admin_token_valid = lambda _token: True
        app._summon_can_be_controlled_by = lambda claimed, cid: False
        app._use_bonus_action = lambda _c: False
        calls = {"apply": 0, "rebuild": 0}
        app._apply_wild_shape = lambda _cid, _beast_id: (calls.__setitem__("apply", calls["apply"] + 1) or True, "")
        app._rebuild_table = lambda scroll_to_current=False: calls.__setitem__("rebuild", calls["rebuild"] + 1)
        toasts = []
        app._lan = type("Lan", (), {"toast": lambda self, ws_id, text: toasts.append(text), "_append_lan_log": lambda self, msg, level='warning': None})()

        app._lan_apply_action({"type": "wild_shape_apply", "cid": 1, "beast_id": "wolf", "_ws_id": 10, "admin_token": "ok"})

        self.assertEqual(calls["apply"], 0)
        self.assertTrue(any("No bonus actions left" in msg for msg in toasts))

    def test_wild_shape_apply_out_of_combat_does_not_require_bonus_action(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app.in_combat = False
        app.combatants = {1: type("C", (), {"cid": 1})()}
        app._is_admin_token_valid = lambda _token: True
        app._summon_can_be_controlled_by = lambda claimed, cid: False
        app._use_bonus_action = lambda _c: False
        calls = {"apply": 0}
        app._apply_wild_shape = lambda _cid, _beast_id: (calls.__setitem__("apply", calls["apply"] + 1) or True, "")
        app._rebuild_table = lambda scroll_to_current=False: None
        app._lan = type("Lan", (), {"toast": lambda self, ws_id, text: None, "_append_lan_log": lambda self, msg, level='warning': None})()

        app._lan_apply_action({"type": "wild_shape_apply", "cid": 1, "beast_id": "wolf", "_ws_id": 10, "admin_token": "ok"})

        self.assertEqual(calls["apply"], 1)

    def test_wild_shape_pool_set_current_handler_clamps_and_persists(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app.in_combat = False
        app.combatants = {1: type("C", (), {"cid": 1})()}
        app._pc_name_for = lambda _cid: "Leaf"
        app._is_admin_token_valid = lambda _token: True
        app._summon_can_be_controlled_by = lambda claimed, cid: False
        app._set_wild_shape_pool_current = lambda _name, value: (True, "", max(0, min(2, int(value))))
        calls = {"rebuild": 0}
        app._rebuild_table = lambda scroll_to_current=False: calls.__setitem__("rebuild", calls["rebuild"] + 1)
        toasts = []
        app._lan = type("Lan", (), {"toast": lambda self, ws_id, text: toasts.append(text), "_append_lan_log": lambda self, msg, level='warning': None})()

        app._lan_apply_action({"type": "wild_shape_pool_set_current", "cid": 1, "current": 99, "_ws_id": 10, "admin_token": "ok"})

        self.assertEqual(getattr(app.combatants[1], "wild_shape_pool_current", None), 2)
        self.assertEqual(calls["rebuild"], 1)
        self.assertTrue(any("uses updated" in msg for msg in toasts))


if __name__ == "__main__":
    unittest.main()
