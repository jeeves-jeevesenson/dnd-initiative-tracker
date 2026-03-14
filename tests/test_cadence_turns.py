import tempfile
import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod
import helper_script


class _Var:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


def _bare_tracker():
    app = object.__new__(tracker_mod.InitiativeTracker)
    app.combatants = {}
    app._next_id = 1
    app.round_num = 1
    app.turn_num = 0
    app.current_cid = None
    app.start_cid = None
    app._lan_aoes = {}
    app.start_last_var = _Var()
    app._remember_role = lambda _c: None
    app._apply_pending_pre_summons = lambda: None
    app._normalize_summons_shared_turn_state = lambda: None
    app._claimed_cids_snapshot = lambda: set()
    app._end_turn_cleanup = lambda *_args, **_kwargs: None
    app._log_turn_end = lambda *_args, **_kwargs: None
    app._should_show_dm_up_alert = lambda *_args, **_kwargs: False
    app._show_dm_up_alert_dialog = lambda: None
    app._enter_turn_with_auto_skip = lambda starting=False: None
    app._rebuild_table = lambda scroll_to_current=False: None
    app._log = lambda *_args, **_kwargs: None
    app._oplog = lambda *_args, **_kwargs: None
    app._display_order = lambda: sorted(app.combatants.values(), key=lambda c: -int(c.initiative))
    app._turn_timing_active = False
    app._turn_timing_current_cid = None
    app._turn_timing_start_ts = None
    app._turn_timing_last_round = 1
    app._turn_timing_round_totals = {}
    app._turn_timing_pc_order = []
    app._cadence_counters = {}
    app._cadence_pending_queue = []
    app._cadence_resume_normal_cid = None
    app._normal_turns_completed = 0
    app._turn_history = []
    app._current_turn_kind = "normal"
    app._lan_auras_enabled = True
    app._lan_active_aura_contexts = lambda positions=None, feet_per_square=5.0: []
    app._name_role_memory = {}
    return app


def _add_basic_combatant(app, cid, name, initiative, cadence_every=None):
    c = type("C", (), {})()
    c.cid = cid
    c.name = name
    c.initiative = initiative
    c.summoned_by_cid = None
    c.mounted_by_cid = None
    c.mount_shared_turn = False
    c.turn_schedule_mode = "cadence" if cadence_every else None
    c.turn_schedule_every_n = cadence_every
    c.turn_schedule_counts = "normal_turns_only" if cadence_every else None
    c.condition_stacks = []
    c.exhaustion_level = 0
    c.ally = False
    c.is_pc = False
    c.hp = 1
    c.move_remaining = 0
    c.move_total = 0
    c.movement_mode = "normal"
    c.speed = 30
    c.swim_speed = 0
    c.fly_speed = 0
    c.burrow_speed = 0
    c.climb_speed = 0
    app.combatants[cid] = c


class CadenceTurnTests(unittest.TestCase):
    def test_create_combatant_inherits_yaml_cadence_schedule(self):
        app = _bare_tracker()
        spec = tracker_mod.MonsterSpec(
            filename="boss.yaml",
            name="Boss",
            mtype="fiend",
            cr=10,
            hp=100,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=12,
            init_mod=1,
            saving_throws={},
            ability_mods={},
            raw_data={"turn_schedule": {"mode": "cadence", "every_n_turns": 3, "counts": "normal_turns_only"}},
            turn_schedule_mode="cadence",
            turn_schedule_every_n=3,
            turn_schedule_counts="normal_turns_only",
        )
        cid = app._create_combatant("Boss", 100, 30, 5, 12, ally=False, monster_spec=spec)
        created = app.combatants[cid]
        self.assertEqual(created.turn_schedule_mode, "cadence")
        self.assertEqual(created.turn_schedule_every_n, 3)
        self.assertEqual(created.turn_schedule_counts, "normal_turns_only")

    def test_cadence_turn_insert_and_round_semantics(self):
        app = _bare_tracker()
        _add_basic_combatant(app, 1, "A", 30)
        _add_basic_combatant(app, 2, "B", 20)
        _add_basic_combatant(app, 3, "C", 10)
        _add_basic_combatant(app, 4, "Boss", 40, cadence_every=3)

        app.current_cid = 1
        app.round_num = 1
        app.turn_num = 1
        app._init_cadence_scheduler_state(reset_history=True)
        app._current_turn_kind = "normal"
        app._record_turn_history()

        seen = []
        for _ in range(4):
            app._next_turn()
            seen.append((app.current_cid, app._current_turn_kind, app.round_num))

        self.assertEqual(seen[0][0], 2)
        self.assertEqual(seen[1][0], 3)
        self.assertEqual(seen[2], (4, "cadence", 2))
        self.assertEqual(seen[3], (1, "normal", 2))
        self.assertEqual(app._normal_turns_completed, 3)

    def test_prev_turn_uses_history_across_inserted_cadence(self):
        app = _bare_tracker()
        _add_basic_combatant(app, 1, "A", 30)
        _add_basic_combatant(app, 2, "B", 20)
        _add_basic_combatant(app, 3, "C", 10)
        _add_basic_combatant(app, 4, "Boss", 40, cadence_every=3)

        app.current_cid = 1
        app.round_num = 1
        app.turn_num = 1
        app._init_cadence_scheduler_state(reset_history=True)
        app._current_turn_kind = "normal"
        app._record_turn_history()
        for _ in range(4):
            app._next_turn()

        self.assertEqual((app.current_cid, app._current_turn_kind), (1, "normal"))
        app._prev_turn()
        self.assertEqual((app.current_cid, app._current_turn_kind), (4, "cadence"))
        app._prev_turn()
        self.assertEqual((app.current_cid, app._current_turn_kind), (3, "normal"))

    def test_session_payload_includes_cadence_scheduler_state(self):
        app = _bare_tracker()
        _add_basic_combatant(app, 1, "A", 30)
        app.current_cid = 1
        app._current_turn_kind = "cadence"
        app._cadence_counters = {9: 2}
        app._cadence_pending_queue = [9]
        app._cadence_resume_normal_cid = 1
        app._normal_turns_completed = 5
        app._turn_history = [{"current_cid": 1}]
        app._next_stack_id = 1
        app.in_combat = True
        app._turn_snapshots = {}
        app._name_role_memory = {}
        app._summon_groups = {}
        app._summon_group_meta = {}
        app._pending_pre_summons = {}
        app._pending_mount_requests = {}
        app._reaction_prefs_by_cid = {}
        app._pending_reaction_offers = {}
        app._pending_shield_resolutions = {}
        app._pending_absorb_elements_resolutions = {}
        app._concentration_save_state = {}
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_positions = {}
        app._lan_obstacles = set()
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app._session_bg_images = []
        app._session_next_bg_id = 1
        app._lan_battle_log_lines = lambda limit=0: []

        payload = app._session_snapshot_payload()
        scheduler = payload["combat"]["cadence_scheduler"]
        self.assertEqual(scheduler["current_turn_kind"], "cadence")
        self.assertEqual(scheduler["cadence_counters"], {"9": 2})
        self.assertEqual(scheduler["cadence_pending_queue"], [9])

    def test_lan_snapshot_and_notification_target_respect_cadence(self):
        app = _bare_tracker()
        _add_basic_combatant(app, 1, "A", 30)
        _add_basic_combatant(app, 2, "B", 20)
        _add_basic_combatant(app, 99, "Boss", 50, cadence_every=3)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app.round_num = 2
        app.current_cid = 99
        app._current_turn_kind = "cadence"
        app._cadence_pending_queue = []
        app._cadence_resume_normal_cid = 1
        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: {}
        app._load_beast_forms = lambda: []
        app._lan = type("Lan", (), {"_cached_snapshot": {}})()

        snap = app._lan_snapshot(include_static=False)
        self.assertEqual(snap["active_turn_kind"], "cadence")
        self.assertEqual(snap["up_next_cid"], 1)

        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = app
        self.assertEqual(lan._next_turn_notification_target(99), 1)


class CadenceYamlAndAutoskipTests(unittest.TestCase):
    def test_real_yaml_index_detail_flow_preserves_turn_schedule(self):
        app = _bare_tracker()
        with tempfile.TemporaryDirectory() as td:
            monsters_dir = Path(td) / "Monsters"
            monsters_dir.mkdir(parents=True, exist_ok=True)
            (monsters_dir / "boss.yaml").write_text(
                """
name: Cadence Boss
type: fiend
hp: 200
speed: 30
turn_schedule:
  mode: cadence
  every_n_turns: 3
  counts: normal_turns_only
""".strip()
                + "\n",
                encoding="utf-8",
            )
            app._monsters_dir_path = lambda: monsters_dir
            app._load_monsters_index()
            indexed = app._monsters_by_name.get("Cadence Boss")
            self.assertIsNotNone(indexed)
            self.assertEqual(indexed.raw_data.get("turn_schedule", {}).get("mode"), "cadence")
            self.assertEqual(indexed.turn_schedule_mode, "cadence")
            self.assertEqual(indexed.turn_schedule_every_n, 3)
            self.assertEqual(indexed.turn_schedule_counts, "normal_turns_only")

            detailed = app._load_monster_details("Cadence Boss")
            self.assertIsNotNone(detailed)
            self.assertEqual(detailed.turn_schedule_mode, "cadence")

            cid = app._create_combatant("Cadence Boss", 200, 30, 15, 10, ally=False, monster_spec=detailed)
            created = app.combatants[cid]
            self.assertEqual(created.turn_schedule_mode, "cadence")
            self.assertEqual(created.turn_schedule_every_n, 3)
            self.assertEqual(created.turn_schedule_counts, "normal_turns_only")

    def test_helper_monster_index_does_not_reference_undefined_cadence_locals(self):
        app = object.__new__(helper_script.InitiativeTracker)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            monsters_dir = root / "Monsters"
            monsters_dir.mkdir(parents=True, exist_ok=True)
            (monsters_dir / "boss.yaml").write_text(
                """
name: Helper Boss
type: fiend
hp: 111
speed: 30
turn_schedule:
  mode: cadence
  every_n_turns: 2
  counts: normal_turns_only
""".strip()
                + "\n",
                encoding="utf-8",
            )
            app._monsters_dir_path = lambda: monsters_dir
            app._index_file_path = lambda name: root / name
            app._read_index_file = lambda _path: {"version": 1, "entries": {}}
            app._write_index_file = lambda _path, _payload: None
            app._file_stat_metadata = helper_script.InitiativeTracker._file_stat_metadata.__get__(app, helper_script.InitiativeTracker)
            app._metadata_matches = helper_script.InitiativeTracker._metadata_matches.__get__(app, helper_script.InitiativeTracker)
            app._hash_text = helper_script.InitiativeTracker._hash_text.__get__(app, helper_script.InitiativeTracker)
            app._monster_int_from_value = helper_script.InitiativeTracker._monster_int_from_value.__get__(app, helper_script.InitiativeTracker)
            app._parse_fractional_cr = helper_script.InitiativeTracker._parse_fractional_cr.__get__(app, helper_script.InitiativeTracker)
            app._log = lambda *_args, **_kwargs: None
            app._load_monsters_index()
            spec = app._monsters_by_name.get("Helper Boss")
            self.assertIsNotNone(spec)
            self.assertEqual(spec.turn_schedule_mode, "cadence")
            self.assertEqual(spec.turn_schedule_every_n, 2)

    def test_auto_skip_advances_via_cadence_scheduler_not_raw_order(self):
        app = _bare_tracker()
        _add_basic_combatant(app, 1, "A", 30)
        _add_basic_combatant(app, 2, "B", 20)
        _add_basic_combatant(app, 99, "Boss", 40, cadence_every=1)

        app._enter_turn_with_auto_skip = helper_script.InitiativeTracker._enter_turn_with_auto_skip.__get__(app, tracker_mod.InitiativeTracker)
        app._update_turn_ui = lambda: None
        app._map_window = None
        app._lan = None
        app._current_turn_kind = "normal"
        app.current_cid = 1
        app.turn_num = 1
        app.round_num = 1
        app._init_cadence_scheduler_state(reset_history=True)

        seen = {"a": 0}

        def _start_of_turn(c):
            if c.cid == 1 and seen["a"] == 0:
                seen["a"] += 1
                return True, "skip", set()
            return False, "", set()

        app._process_start_of_turn = _start_of_turn

        app._enter_turn_with_auto_skip(starting=False)
        self.assertEqual(app.current_cid, 99)
        self.assertEqual(app._current_turn_kind, "cadence")

    def test_lan_prediction_infers_due_cadence_after_current_normal_turn(self):
        app = _bare_tracker()
        _add_basic_combatant(app, 1, "A", 30)
        _add_basic_combatant(app, 2, "B", 20)
        _add_basic_combatant(app, 99, "Boss", 50, cadence_every=3)
        app.current_cid = 1
        app._current_turn_kind = "normal"
        app._cadence_pending_queue = []
        app._cadence_counters = {99: 2}
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: {}
        app._load_beast_forms = lambda: []
        app._lan = type("Lan", (), {"_cached_snapshot": {}})()

        self.assertEqual(app._peek_next_turn_cid(1), 99)
        snap = app._lan_snapshot(include_static=False)
        self.assertEqual(snap["up_next_cid"], 99)

        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = app
        self.assertEqual(lan._next_turn_notification_target(1), 99)


if __name__ == "__main__":
    unittest.main()
