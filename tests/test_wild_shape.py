import unittest

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
            "learned_wild_shapes": ["wolf", "brown-bear", "reef-shark", "eagle", "cat"],
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
        self.assertNotIn("eagle", lvl2)
        self.assertNotIn("cat", lvl2)

        lvl8 = {f["id"] for f in self.app._wild_shape_available_forms(self._profile(8), known_only=True)}
        self.assertIn("brown-bear", lvl8)
        self.assertIn("eagle", lvl8)
        self.assertNotIn("cat", lvl8)

        lvl11 = {f["id"] for f in self.app._wild_shape_available_forms(self._profile(11), known_only=True)}
        self.assertIn("cat", lvl11)


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


if __name__ == "__main__":
    unittest.main()
