import json
import tempfile
import types
import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


class SessionSaveLoadTests(unittest.TestCase):
    def _make_app(self, history_path: Path):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app.combatants = {}
        app._next_id = 1
        app._next_stack_id = 7
        app.current_cid = None
        app.start_cid = None
        app.round_num = 1
        app.turn_num = 0
        app.in_combat = False
        app._turn_snapshots = {}
        app._name_role_memory = {}
        app._summon_groups = {}
        app._summon_group_meta = {}
        app._pending_pre_summons = {}
        app._pending_mount_requests = {}
        app._concentration_save_state = {}

        app._lan_grid_cols = 20
        app._lan_grid_rows = 20
        app._lan_positions = {}
        app._lan_obstacles = set()
        app._lan_rough_terrain = {}
        app._lan_aoes = {}
        app._lan_next_aoe_id = 1
        app._lan_auras_enabled = True
        app._session_bg_images = []
        app._session_next_bg_id = 1

        app._map_window = None
        app._monsters_by_name = {}

        def _create_combatant(**kwargs):
            cid = int(app._next_id)
            app._next_id += 1
            c = types.SimpleNamespace(
                cid=cid,
                name=kwargs["name"],
                hp=int(kwargs["hp"]),
                speed=int(kwargs["speed"]),
                swim_speed=int(kwargs.get("swim_speed", 0)),
                fly_speed=int(kwargs.get("fly_speed", 0)),
                burrow_speed=int(kwargs.get("burrow_speed", 0)),
                climb_speed=int(kwargs.get("climb_speed", 0)),
                movement_mode=str(kwargs.get("movement_mode", "normal")),
                move_remaining=int(kwargs.get("speed", 0)),
                move_total=int(kwargs.get("speed", 0)),
                initiative=int(kwargs.get("initiative", 0)),
                dex=kwargs.get("dex"),
                roll=None,
                nat20=False,
                ally=bool(kwargs.get("ally", False)),
                is_pc=bool(kwargs.get("is_pc", False)),
                is_spellcaster=bool(kwargs.get("is_spellcaster", False)),
                saving_throws=dict(kwargs.get("saving_throws") or {}),
                ability_mods=dict(kwargs.get("ability_mods") or {}),
                actions=list(kwargs.get("actions") or []),
                bonus_actions=list(kwargs.get("bonus_actions") or []),
                reactions=list(kwargs.get("reactions") or []),
                monster_spec=kwargs.get("monster_spec"),
            )
            app.combatants[cid] = c
            return cid

        app._create_combatant = _create_combatant
        app._find_monster_spec_by_slug = lambda _slug: None
        app._remove_combatants_with_lan_cleanup = lambda cids: [app.combatants.pop(int(cid), None) for cid in list(cids)]
        app._history_file_path = lambda: history_path
        app._load_history_into_log = lambda max_lines=2000: None
        app._update_turn_ui = lambda: None
        app._rebuild_table = lambda scroll_to_current=True: None
        app._lan_force_state_broadcast = lambda: None
        app._log = lambda *_args, **_kwargs: None
        app._lan_battle_log_lines = lambda limit=0: ["[2026-01-01 00:00:00]\tFirst", "[2026-01-01 00:00:01]\tSecond"]
        return app

    def test_session_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "battle.log"
            app = self._make_app(history_path)

            app._next_id = 3
            c1 = types.SimpleNamespace(
                cid=1,
                name="Alice",
                hp=23,
                speed=30,
                swim_speed=15,
                fly_speed=0,
                burrow_speed=0,
                climb_speed=10,
                movement_mode="normal",
                move_remaining=10,
                move_total=30,
                initiative=18,
                dex=3,
                roll=15,
                nat20=False,
                ally=True,
                is_pc=True,
                is_spellcaster=True,
                saving_throws={"con": 5},
                ability_mods={"dex": 3},
                actions=[{"name": "Attack", "remaining": 0}],
                bonus_actions=[{"name": "Misty Step", "remaining": 1}],
                reactions=[{"name": "Shield", "remaining": 1}],
                monster_spec=None,
                condition_stacks=[tracker_mod.base.ConditionStack(sid=4, ctype="prone", remaining_turns=1)],
                concentration_started_turn=(2, 5),
                concentration_aoe_ids=[10],
                concentrating=True,
                concentration_spell="web",
                token_color="#123456",
                token_border_color="#ffffff",
                temp_hp=4,
                action_remaining=0,
                bonus_action_remaining=1,
                reaction_remaining=1,
                spell_cast_remaining=0,
                attack_resource_remaining=2,
                facing_deg=180,
                summon_group_id="grp-1",
                summoned_by_cid=None,
            )
            c2 = types.SimpleNamespace(
                cid=2,
                name="Goblin",
                hp=7,
                speed=30,
                swim_speed=0,
                fly_speed=0,
                burrow_speed=0,
                climb_speed=0,
                movement_mode="normal",
                move_remaining=30,
                move_total=30,
                initiative=12,
                dex=2,
                roll=10,
                nat20=False,
                ally=False,
                is_pc=False,
                is_spellcaster=False,
                saving_throws={},
                ability_mods={},
                actions=[],
                bonus_actions=[],
                reactions=[],
                monster_spec=None,
                condition_stacks=[],
                concentration_started_turn=None,
                concentration_aoe_ids=[],
                concentrating=False,
                concentration_spell=None,
            )
            app.combatants = {1: c1, 2: c2}
            app.current_cid = 1
            app.start_cid = 2
            app.round_num = 3
            app.turn_num = 6
            app.in_combat = True
            app._turn_snapshots = {"1": {"move_remaining": 10}}
            app._name_role_memory = {"Alice": "pc", "Goblin": "enemy"}
            app._summon_groups = {"grp-1": [1]}
            app._summon_group_meta = {"grp-1": {"name": "Summons"}}
            app._pending_pre_summons = {"1": {"spell": "summon beast"}}
            app._pending_mount_requests = {"req": {"rider": 1}}
            app._concentration_save_state = {"1": {"dc": 10}}

            app._lan_grid_cols = 40
            app._lan_grid_rows = 25
            app._lan_positions = {1: (4, 5), 2: (10, 3)}
            app._lan_obstacles = {(1, 1), (2, 2)}
            app._lan_rough_terrain = {(3, 3): {"color": "#ff0000", "movement_type": "ground", "is_swim": False, "is_rough": True}}
            app._lan_aoes = {10: {"kind": "circle", "name": "Web", "cx": 4.0, "cy": 5.0, "radius_sq": 4.0, "owner_cid": 1}}
            app._lan_next_aoe_id = 11
            app._lan_auras_enabled = False
            app._session_bg_images = [{"bid": 1, "path": "/tmp/missing.png", "x": 1.0, "y": 2.0, "scale_pct": 50.0, "trans_pct": 30.0, "locked": True}]
            app._session_next_bg_id = 2

            snap_path = Path(tmpdir) / "session.json"
            app._save_session_to_path(snap_path, label="roundtrip")

            payload = json.loads(snap_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["metadata"]["label"], "roundtrip")

            app.combatants = {}
            app.current_cid = None
            app.start_cid = None
            app.round_num = 1
            app.turn_num = 0
            app.in_combat = False
            app._lan_positions = {}
            app._lan_obstacles = set()
            app._lan_rough_terrain = {}
            app._lan_aoes = {}

            app._load_session_from_path(snap_path)

            self.assertEqual(sorted(app.combatants.keys()), [1, 2])
            self.assertEqual(app.combatants[1].name, "Alice")
            self.assertEqual(app.combatants[1].hp, 23)
            self.assertEqual(app.combatants[1].temp_hp, 4)
            self.assertEqual(app.combatants[1].concentration_aoe_ids, [10])
            self.assertEqual(app.combatants[1].condition_stacks[0].ctype, "prone")
            self.assertEqual(app.current_cid, 1)
            self.assertEqual(app.round_num, 3)
            self.assertEqual(app.turn_num, 6)
            self.assertTrue(app.in_combat)

            self.assertEqual(app._lan_grid_cols, 40)
            self.assertEqual(app._lan_grid_rows, 25)
            self.assertEqual(app._lan_positions[1], (4, 5))
            self.assertIn((1, 1), app._lan_obstacles)
            self.assertEqual(app._lan_rough_terrain[(3, 3)]["color"], "#ff0000")
            self.assertIn(10, app._lan_aoes)
            self.assertEqual(app._lan_next_aoe_id, 11)
            self.assertFalse(app._lan_auras_enabled)
            self.assertEqual(app._session_next_bg_id, 2)

            log_text = history_path.read_text(encoding="utf-8")
            self.assertIn("First", log_text)
            self.assertIn("Second", log_text)

    def test_apply_saved_positions_to_map_window_creates_and_moves_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._make_app(Path(tmpdir) / "battle.log")
            app.combatants = {1: types.SimpleNamespace(cid=1), 2: types.SimpleNamespace(cid=2)}
            app._lan_positions = {1: (4, 5), 2: (7, 8)}

            created = []
            laid_out = []

            mw = types.SimpleNamespace(
                unit_tokens={1: {"col": 0, "row": 0}},
                _create_unit_token=lambda cid, col, row: created.append((cid, col, row)),
                _layout_unit=lambda cid: laid_out.append(cid),
                _update_groups=lambda: None,
                _update_move_highlight=lambda: None,
                _update_included_for_selected=lambda: None,
                winfo_exists=lambda: True,
            )

            app._apply_saved_positions_to_map_window(mw)

            self.assertEqual(mw.unit_tokens[1]["col"], 4)
            self.assertEqual(mw.unit_tokens[1]["row"], 5)
            self.assertEqual(laid_out, [1])
            self.assertEqual(created, [(2, 7, 8)])

    def test_reset_map_state_clears_stored_and_live_map_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._make_app(Path(tmpdir) / "battle.log")
            app._lan_positions = {1: (1, 2)}
            app._lan_obstacles = {(0, 0)}
            app._lan_rough_terrain = {(1, 1): {"color": "#fff"}}
            app._lan_aoes = {1: {"kind": "circle"}}
            app._session_bg_images = [{"bid": 1, "path": "x"}]
            app._session_next_bg_id = 3
            app._lan_force_state_broadcast = lambda: None

            deleted_items = []

            class _Canvas:
                def delete(self, item):
                    deleted_items.append(item)

            mw = types.SimpleNamespace(
                obstacles={(3, 3)},
                rough_terrain={(4, 4): {"color": "#000"}},
                aoes={9: {"kind": "cone"}},
                unit_tokens={10: {"col": 1, "row": 1}},
                _token_facing={10: 0},
                bg_images={5: {"item": 88}},
                _next_aoe_id=12,
                _next_bg_id=6,
                _redraw_all=lambda: None,
                refresh_units=lambda: None,
                _refresh_aoe_list=lambda: None,
                canvas=_Canvas(),
                winfo_exists=lambda: True,
            )
            app._map_window = mw

            app._reset_map_state()

            self.assertEqual(app._lan_positions, {})
            self.assertEqual(app._lan_obstacles, set())
            self.assertEqual(app._lan_rough_terrain, {})
            self.assertEqual(app._lan_aoes, {})
            self.assertEqual(app._lan_next_aoe_id, 1)
            self.assertEqual(app._session_bg_images, [])
            self.assertEqual(app._session_next_bg_id, 1)
            self.assertEqual(mw.unit_tokens, {})
            self.assertEqual(mw.obstacles, set())
            self.assertEqual(mw.rough_terrain, {})
            self.assertEqual(mw.aoes, {})
            self.assertEqual(mw.bg_images, {})
            self.assertEqual(deleted_items, [88])

    def test_open_map_mode_keeps_prompted_grid_size_and_syncs_lan_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._make_app(Path(tmpdir) / "battle.log")
            app._lan_grid_cols = 20
            app._lan_grid_rows = 20
            app._lan_obstacles = set()
            app._lan_rough_terrain = {}
            app._lan_aoes = {}
            app._lan_next_aoe_id = 1
            app._session_next_bg_id = 1
            app._session_bg_images = []
            app._apply_saved_positions_to_map_window = lambda _mw: None
            app._restore_map_backgrounds = lambda _images: None

            map_window = types.SimpleNamespace(
                cols=100,
                rows=100,
                obstacles=set(),
                rough_terrain={},
                aoes={},
                _next_aoe_id=1,
                _next_bg_id=1,
                _redraw_all=lambda: None,
                refresh_units=lambda: None,
                _refresh_aoe_list=lambda: None,
                winfo_exists=lambda: True,
            )

            original_open_map_mode = tracker_mod.base.InitiativeTracker._open_map_mode
            try:
                tracker_mod.base.InitiativeTracker._open_map_mode = lambda self: setattr(self, "_map_window", map_window)
                tracker_mod.InitiativeTracker._open_map_mode(app)
            finally:
                tracker_mod.base.InitiativeTracker._open_map_mode = original_open_map_mode

            self.assertEqual(map_window.cols, 100)
            self.assertEqual(map_window.rows, 100)
            self.assertEqual(app._lan_grid_cols, 100)
            self.assertEqual(app._lan_grid_rows, 100)


if __name__ == "__main__":
    unittest.main()
