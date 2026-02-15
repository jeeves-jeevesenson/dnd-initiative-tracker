import json
import tempfile
import threading
import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


class CustomSummonPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.monsters_dir = Path(self.tmp.name) / "Monsters"
        self.monsters_dir.mkdir(parents=True, exist_ok=True)

        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._log = lambda *args, **kwargs: None
        self.app._monsters_dir_path = lambda: self.monsters_dir
        self.app._monster_specs = []
        self.app._monsters_by_name = {}
        self.app._wild_shape_beast_cache = None
        self.app._wild_shape_available_cache = {}
        self.app._wild_shape_available_cache_source = None

        self.app._next_cid = 2
        caster = tracker_mod.base.Combatant(
            cid=1,
            name="Caster",
            hp=40,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="Normal",
            move_remaining=30,
            initiative=14,
            dex=2,
            ally=True,
            is_pc=True,
            is_spellcaster=True,
        )
        self.app.combatants = {1: caster}
        self.app._lan_positions = {1: (0, 0)}
        self.app._summon_groups = {}
        self.app._summon_group_meta = {}
        self.rebuild_calls = 0
        self.broadcast_calls = 0
        self.app._rebuild_table = lambda **_kwargs: setattr(self, "rebuild_calls", self.rebuild_calls + 1)
        self.app._lan_force_state_broadcast = lambda: setattr(self, "broadcast_calls", self.broadcast_calls + 1)

        def _create_combatant(**kwargs):
            cid = self.app._next_cid
            self.app._next_cid += 1
            c = tracker_mod.base.Combatant(
                cid=cid,
                name=kwargs["name"],
                hp=kwargs["hp"],
                speed=kwargs["speed"],
                swim_speed=kwargs.get("swim_speed", 0),
                fly_speed=kwargs.get("fly_speed", 0),
                burrow_speed=kwargs.get("burrow_speed", 0),
                climb_speed=kwargs.get("climb_speed", 0),
                movement_mode=kwargs.get("movement_mode", "Normal"),
                move_remaining=kwargs["speed"],
                initiative=kwargs["initiative"],
                dex=kwargs["dex"],
                ally=kwargs["ally"],
                is_pc=kwargs.get("is_pc", False),
                is_spellcaster=bool(kwargs.get("is_spellcaster")),
                saving_throws=dict(kwargs.get("saving_throws") or {}),
                ability_mods=dict(kwargs.get("ability_mods") or {}),
                monster_spec=kwargs.get("monster_spec"),
            )
            self.app.combatants[cid] = c
            return cid

        self.app._create_combatant = _create_combatant
        self.app._unique_name = lambda name: str(name)

        def _remove_combatants_with_lan_cleanup(cids):
            for cid in list(cids or []):
                self.app.combatants.pop(int(cid), None)
                self.app._lan_positions.pop(int(cid), None)

        self.app._remove_combatants_with_lan_cleanup = _remove_combatants_with_lan_cleanup

    def test_custom_summon_write_spawn_group_and_dismiss(self):
        payload = {
            "name": "Frost Servitor",
            "hp": 22,
            "abilities": {"str": 14, "dex": 12, "con": 16, "int": 6, "wis": 10, "cha": 8},
            "speeds": {"walk": 30, "swim": 0, "fly": 0, "burrow": 0, "climb": 10},
            "summon_quantity": 2,
            "summon_range_ft": 30,
            "summon_positions": [{"col": 1, "row": 0}, {"col": 2, "row": 0}],
        }

        ok, err, spawned = self.app._spawn_custom_summons_from_payload(1, payload)
        self.assertTrue(ok, err)
        self.assertEqual(len(spawned), 2)

        temp_files = sorted((self.monsters_dir / "temp").glob("*.yaml"))
        self.assertTrue(temp_files)
        yaml_text = temp_files[0].read_text(encoding="utf-8")
        self.assertIn("Frost Servitor", yaml_text)

        group_ids = {getattr(self.app.combatants[cid], "summon_group_id", "") for cid in spawned}
        self.assertEqual(len(group_ids), 1)
        group_id = next(iter(group_ids))
        self.assertIn(group_id, self.app._summon_groups)
        self.assertEqual(self.app._summon_groups[group_id], spawned)
        self.assertEqual(self.app._summon_group_meta[group_id]["spell"], "custom_summon")
        self.assertTrue(self.app._summon_group_meta[group_id].get("custom"))

        removed = self.app._dismiss_summons_for_caster(1)
        self.assertEqual(removed, 2)
        for cid in spawned:
            self.assertNotIn(cid, self.app.combatants)
        self.assertNotIn(group_id, self.app._summon_groups)

    def test_custom_summon_can_import_monster_slug_template(self):
        (self.monsters_dir / "wolf-spirit.yaml").write_text(
            (
                "monster:\n"
                "  name: Wolf Spirit\n"
                "  type: beast\n"
                "  hp: 18\n"
                "  ac: 13\n"
                "  speed:\n"
                "    walk: 40\n"
                "    climb: 20\n"
                "  abilities:\n"
                "    str: 14\n"
                "    dex: 15\n"
                "    con: 12\n"
                "    int: 6\n"
                "    wis: 12\n"
                "    cha: 8\n"
            ),
            encoding="utf-8",
        )
        self.app._load_monsters_index()

        ok, err, spawned = self.app._spawn_custom_summons_from_payload(
            1,
            {
                "monster_slug": "wolf-spirit",
                "summon_quantity": 1,
                "summon_range_ft": 30,
                "summon_positions": [{"col": 1, "row": 0}],
            },
        )
        self.assertTrue(ok, err)
        self.assertEqual(len(spawned), 1)
        summoned = self.app.combatants[spawned[0]]
        self.assertEqual(summoned.name, "Wolf Spirit")
        self.assertEqual(summoned.hp, 18)
        self.assertEqual(summoned.speed, 40)


class MonsterIndexTempResolutionTests(unittest.TestCase):
    def test_nested_temp_index_and_slug_resolution_are_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            monsters_dir = Path(td) / "Monsters"
            (monsters_dir / "temp").mkdir(parents=True, exist_ok=True)
            (monsters_dir / "goblin.yaml").write_text(
                "monster:\n  name: Root Goblin\n  type: humanoid\n  hp: 7\n  speed: 30\n  abilities: {str: 8, dex: 14, con: 10, int: 10, wis: 8, cha: 8}\n",
                encoding="utf-8",
            )
            (monsters_dir / "temp" / "goblin.yaml").write_text(
                "monster:\n  name: Temp Goblin\n  type: construct\n  hp: 11\n  speed: 25\n  abilities: {str: 10, dex: 12, con: 12, int: 3, wis: 6, cha: 5}\n",
                encoding="utf-8",
            )

            app = object.__new__(tracker_mod.InitiativeTracker)
            app._oplog = lambda *args, **kwargs: None
            app._log = lambda *args, **kwargs: None
            app._monsters_dir_path = lambda: monsters_dir
            app._monster_specs = []
            app._monsters_by_name = {}
            app._wild_shape_beast_cache = None
            app._wild_shape_available_cache = {}
            app._wild_shape_available_cache_source = None

            app._load_monsters_index()

            filenames = {spec.filename for spec in app._monster_specs}
            self.assertIn("goblin.yaml", filenames)
            self.assertIn("temp/goblin.yaml", filenames)

            resolved_root = app._find_monster_spec_by_slug("goblin")
            resolved_temp = app._find_monster_spec_by_slug("temp/goblin")
            self.assertIsNotNone(resolved_root)
            self.assertIsNotNone(resolved_temp)
            self.assertEqual(resolved_root.name, "Root Goblin")
            self.assertEqual(resolved_temp.name, "Temp Goblin")

            cache_path = tracker_mod._ensure_logs_dir() / "monster_index.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(cache.get("version"), 2)
            self.assertIn("goblin.yaml", cache.get("entries", {}))
            self.assertIn("temp/goblin.yaml", cache.get("entries", {}))

            lan = object.__new__(tracker_mod.LanController)
            object.__setattr__(lan, "_tracker", app)
            lan._cached_snapshot = {
                "spell_presets": [],
                "player_spells": {},
                "player_profiles": {},
                "resource_pools": {},
            }
            lan._clients_lock = threading.Lock()
            lan._cid_to_host = {}

            static_payload = lan._static_data_payload(planning=False)
            choice_slugs = {entry.get("slug") for entry in static_payload.get("monster_choices", [])}
            self.assertIn("goblin", choice_slugs)
            self.assertIn("temp/goblin", choice_slugs)
            choice_by_slug = {entry.get("slug"): entry for entry in static_payload.get("monster_choices", [])}
            goblin_template = choice_by_slug["goblin"].get("template", {})
            self.assertEqual(goblin_template.get("hp"), 7)
            self.assertEqual(goblin_template.get("speeds", {}).get("walk"), 30)


if __name__ == "__main__":
    unittest.main()
