import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


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
    app._map_window = None
    app._monster_specs = []
    app._monsters_by_name = {}
    return app


class MonsterPhaseTests(unittest.TestCase):
    def _load_plantera_spec(self):
        app = _bare_tracker()
        app._monsters_dir_path = lambda: Path("Monsters")
        app._load_monsters_index()
        spec = app._load_monster_details("Plantera")
        self.assertIsNotNone(spec)
        return app, spec

    def test_plantera_yaml_ingestion(self):
        app, spec = self._load_plantera_spec()
        self.assertEqual(spec.turn_schedule_mode, "cadence")
        self.assertEqual(spec.turn_schedule_every_n, 3)
        self.assertEqual(spec.turn_schedule_counts, "normal_turns_only")
        self.assertEqual(spec.raw_data.get("damage_resistances"), ["poison", "necrotic"])
        phases = spec.raw_data.get("phases")
        self.assertIsInstance(phases, dict)
        self.assertEqual(phases.get("base_phase"), "phase1")

    def test_phase_transition_strict_threshold_and_sticky(self):
        app, spec = self._load_plantera_spec()
        cid = app._create_combatant("Plantera", 400, 30, 12, 8, ally=False, monster_spec=spec)
        c = app.combatants[cid]
        self.assertEqual(c.hp, 400)
        self.assertEqual(c.monster_phase_id, "phase1")
        self.assertEqual(app._combatant_ac_display(c), "18")

        defenses = app._combatant_defense_sets(c)
        self.assertIn("poison", defenses["damage_resistances"])
        self.assertIn("necrotic", defenses["damage_resistances"])

        app._set_hp(cid, 200)
        self.assertEqual(c.monster_phase_id, "phase1")
        self.assertEqual(app._combatant_ac_display(c), "18")

        app._set_hp(cid, 199)
        self.assertEqual(c.monster_phase_id, "enraged")
        self.assertEqual(app._combatant_ac_display(c), "21")

        app._set_hp(cid, 260)
        self.assertEqual(c.monster_phase_id, "enraged")
        self.assertEqual(app._combatant_ac_display(c), "21")

    def test_phase_actions_switch_for_map_view(self):
        app, spec = self._load_plantera_spec()
        cid = app._create_combatant("Plantera", 400, 30, 12, 8, ally=False, monster_spec=spec)
        c = app.combatants[cid]

        phase1_actions = app._monster_raw_view_for_combatant(c).get("actions")
        phase1_names = {str(a.get("name")) for a in phase1_actions if isinstance(a, dict)}
        self.assertIn("Seed", phase1_names)
        self.assertIn("Spike Ball", phase1_names)

        app._set_hp(cid, 199)
        enraged_actions = app._monster_raw_view_for_combatant(c).get("actions")
        enraged_names = {str(a.get("name")) for a in enraged_actions if isinstance(a, dict)}
        self.assertIn("Gore", enraged_names)
        self.assertNotIn("Seed", enraged_names)
        self.assertNotIn("Spike Ball", enraged_names)

    def test_snapshot_restore_preserves_enraged_phase(self):
        app, spec = self._load_plantera_spec()
        cid = app._create_combatant("Plantera", 400, 30, 12, 8, ally=False, monster_spec=spec)
        c = app.combatants[cid]
        app._next_stack_id = 1
        app.in_combat = True
        app._turn_snapshots = {}
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
        app._remove_combatants_with_lan_cleanup = lambda _cids: None
        app._load_history_into_log = lambda *args, **kwargs: None
        app._update_turn_ui = lambda *args, **kwargs: None

        app._set_hp(cid, 199)
        payload = app._session_snapshot_payload()

        app._set_hp(cid, 260)
        self.assertEqual(c.monster_phase_id, "enraged")

        app._apply_session_snapshot(payload)
        restored = next(iter(app.combatants.values()))
        self.assertEqual(restored.hp, 199)
        self.assertEqual(restored.monster_phase_id, "enraged")
        self.assertEqual(app._combatant_ac_display(restored), "21")

    def test_phase_state_isolated_between_instances(self):
        app, spec = self._load_plantera_spec()
        cid1 = app._create_combatant("Plantera", 400, 30, 12, 8, ally=False, monster_spec=spec)
        cid2 = app._create_combatant("Plantera", 400, 30, 11, 8, ally=False, monster_spec=spec)
        c1 = app.combatants[cid1]
        c2 = app.combatants[cid2]

        app._set_hp(cid1, 199)
        self.assertEqual(c1.monster_phase_id, "enraged")
        self.assertEqual(c2.monster_phase_id, "phase1")
        self.assertEqual(app._combatant_ac_display(c2), "18")

        actions2 = app._monster_raw_view_for_combatant(c2).get("actions")
        names2 = {str(a.get("name")) for a in actions2 if isinstance(a, dict)}
        self.assertIn("Seed", names2)
        self.assertIn("Spike Ball", names2)

    def test_plantera_cadence_still_works(self):
        app = _bare_tracker()
        # normals
        for cid, init in ((1, 30), (2, 20), (3, 10)):
            c = type("C", (), {})()
            c.cid = cid
            c.name = str(cid)
            c.initiative = init
            c.summoned_by_cid = None
            c.mounted_by_cid = None
            c.mount_shared_turn = False
            c.turn_schedule_mode = None
            c.turn_schedule_every_n = None
            c.turn_schedule_counts = None
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

        app._monsters_dir_path = lambda: Path("Monsters")
        app._load_monsters_index()
        spec = app._load_monster_details("Plantera")
        cid = app._create_combatant("Plantera", 400, 30, 40, 8, ally=False, monster_spec=spec)

        app.current_cid = 1
        app.round_num = 1
        app.turn_num = 1
        app._init_cadence_scheduler_state(reset_history=True)
        app._current_turn_kind = "normal"
        app._record_turn_history()

        for _ in range(3):
            app._next_turn()
        self.assertEqual((app.current_cid, app._current_turn_kind), (cid, "cadence"))


if __name__ == "__main__":
    unittest.main()
