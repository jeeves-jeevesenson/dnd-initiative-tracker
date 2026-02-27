import queue
import threading
import unittest

import dnd_initative_tracker as tracker_mod


class LanSnapshotStaticTests(unittest.TestCase):
    def test_monster_choices_payload_cache_uses_monster_specs_id_and_len(self):
        lan = object.__new__(tracker_mod.LanController)

        class Spec:
            def __init__(self, name, filename):
                self.name = name
                self.filename = filename
                self.mtype = "beast"
                self.hp = 9
                self.speed = 30
                self.swim_speed = 0
                self.fly_speed = 0
                self.burrow_speed = 0
                self.climb_speed = 0
                self.raw_data = {"ac": 12, "abilities": {"str": 14, "dex": 13, "con": 12, "int": 10, "wis": 11, "cha": 8}}

        class AppStub:
            def __init__(self):
                self._monster_specs = [Spec("Wolf", "wolf.yaml")]

        lan._tracker = AppStub()
        lan._monster_choices_cache = []
        lan._monster_choices_cache_key = None

        first = lan._monster_choices_payload()
        second = lan._monster_choices_payload()
        self.assertIs(first, second)

        lan._tracker._monster_specs = list(lan._tracker._monster_specs)
        third = lan._monster_choices_payload()
        self.assertIsNot(third, second)

        lan._tracker._monster_specs.append(Spec("Bear", "bear.yaml"))
        fourth = lan._monster_choices_payload()
        self.assertIsNot(fourth, third)
        self.assertEqual(len(fourth), 2)

    def test_next_turn_notification_target_skips_skipped_combatants(self):
        lan = object.__new__(tracker_mod.LanController)

        combatants = [
            type("C", (), {"cid": 1})(),
            type("C", (), {"cid": 2})(),
            type("C", (), {"cid": 3})(),
        ]

        class TrackerStub:
            def _display_order(self):
                return combatants

            def _should_skip_turn(self, cid):
                return int(cid) == 2

        lan._tracker = TrackerStub()

        self.assertEqual(lan._next_turn_notification_target(1), 3)

    def test_dispatch_turn_notification_sends_active_and_up_next_payloads(self):
        lan = object.__new__(tracker_mod.LanController)
        sent_payloads = []
        removed = []

        class TrackerStub:
            def _pc_name_for(self, cid):
                return {1: "Alice", 2: "Bob"}.get(int(cid), f"#{cid}")

            def _display_order(self):
                return [type("C", (), {"cid": 1})(), type("C", (), {"cid": 2})()]

            def _should_skip_turn(self, _cid):
                return False

        lan._tracker = TrackerStub()
        lan._subscriptions_for_cid = lambda cid: [{"endpoint": f"https://example.com/{cid}", "keys": {"p256dh": "a", "auth": "b"}}]
        lan._send_push_notifications = lambda subs, payload: sent_payloads.append((subs, payload)) or []
        lan._remove_push_subscription = lambda cid, endpoint: removed.append((cid, endpoint))

        lan._dispatch_turn_notification(1, 2, 4)

        self.assertEqual(len(sent_payloads), 2)
        self.assertEqual(sent_payloads[0][1]["title"], "Your turn!")
        self.assertEqual(sent_payloads[0][1]["body"], "Alice is up (round 2, turn 4).")
        self.assertEqual(sent_payloads[1][1]["title"], "You're up next")
        self.assertEqual(sent_payloads[1][1]["body"], "Alice's turn started — you're next. Plan your move.")
        self.assertEqual(removed, [])


    def test_dispatch_turn_notification_still_sends_when_next_lookup_fails(self):
        lan = object.__new__(tracker_mod.LanController)
        sent_payloads = []

        class TrackerStub:
            def _pc_name_for(self, cid):
                return {1: "Alice"}.get(int(cid), f"#{cid}")

        lan._tracker = TrackerStub()
        lan._subscriptions_for_cid = lambda cid: [{"endpoint": f"https://example.com/{cid}", "keys": {"p256dh": "a", "auth": "b"}}]
        lan._send_push_notifications = lambda subs, payload: sent_payloads.append((subs, payload)) or []
        lan._remove_push_subscription = lambda *_args, **_kwargs: None
        lan._next_turn_notification_target = lambda _cid: (_ for _ in ()).throw(RuntimeError("boom"))

        lan._dispatch_turn_notification(1, 2, 4)

        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0][1]["title"], "Your turn!")

    def test_include_static_false_reuses_cached_static_payload(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app.combatants = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: []
        app._oplog = lambda *args, **kwargs: None

        app._spell_presets_payload = lambda: (_ for _ in ()).throw(AssertionError("spell presets should not be called"))
        app._player_spell_config_payload = lambda: (_ for _ in ()).throw(AssertionError("player spells should not be called"))
        app._player_profiles_payload = lambda: (_ for _ in ()).throw(AssertionError("player profiles should not be called"))
        app._player_resource_pools_payload = lambda: {"Alice": [{"id": "wild_shape", "current": 0}]}
        app._load_beast_forms = lambda: (_ for _ in ()).throw(AssertionError("beast forms should not be called"))

        app._lan = type("LanStub", (), {"_cached_snapshot": {
            "spell_presets": [{"name": "cached"}],
            "player_spells": {"Alice": {"spells": []}},
            "player_profiles": {"Alice": {"name": "Alice"}},
            "resource_pools": {"Alice": [{"id": "wild_shape", "current": 1}]},
            "beast_forms": [{"id": "wolf"}],
        }})()

        snap = app._lan_snapshot(include_static=False)
        self.assertEqual(snap["spell_presets"], [{"name": "cached"}])
        self.assertEqual(snap["player_spells"], {"Alice": {"spells": []}})
        self.assertEqual(snap["player_profiles"], {"Alice": {"name": "Alice"}})
        self.assertEqual(snap["resource_pools"], {"Alice": [{"id": "wild_shape", "current": 0}]})
        self.assertEqual(snap["beast_forms"], [{"id": "wolf"}])

    def test_include_static_false_without_hydration_skips_static_builders(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app.combatants = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: []
        app._oplog = lambda *args, **kwargs: None
        app._player_yaml_refresh_interval_s = 1.0
        app._lan_resource_pools_last_build = 0.0

        app._spell_presets_payload = lambda: (_ for _ in ()).throw(AssertionError("spell presets should not be called"))
        app._player_spell_config_payload = lambda: (_ for _ in ()).throw(AssertionError("player spells should not be called"))
        app._player_profiles_payload = lambda: (_ for _ in ()).throw(AssertionError("player profiles should not be called"))
        app._player_resource_pools_payload = lambda: (_ for _ in ()).throw(AssertionError("resource pools should not be called"))
        app._load_beast_forms = lambda: (_ for _ in ()).throw(AssertionError("beast forms should not be called"))

        app._lan = type("LanStub", (), {"_cached_snapshot": {}})()

        snap = app._lan_snapshot(include_static=False, hydrate_static=False)
        self.assertEqual(snap["spell_presets"], [])
        self.assertEqual(snap["player_spells"], {})
        self.assertEqual(snap["player_profiles"], {})
        self.assertEqual(snap["resource_pools"], {})
        self.assertEqual(snap["beast_forms"], [])

    def test_include_static_false_reuses_cached_resource_pools_within_refresh_interval(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app.combatants = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: []
        app._oplog = lambda *args, **kwargs: None
        app._player_yaml_refresh_interval_s = 1.0
        app._lan_resource_pools_last_build = tracker_mod.time.monotonic()

        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: (_ for _ in ()).throw(AssertionError("resource pools should not be called"))
        app._load_beast_forms = lambda: []

        cached_resource_pools = {"Alice": [{"id": "wild_shape", "current": 1}]}
        app._lan = type("LanStub", (), {"_cached_snapshot": {"resource_pools": cached_resource_pools}})()

        snap = app._lan_snapshot(include_static=False)
        self.assertIs(snap["resource_pools"], cached_resource_pools)

    def test_view_only_state_payload_includes_grid_and_terrain(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._cached_snapshot = {
            "grid": {"cols": 5, "rows": 6, "feet_per_square": 5},
            "rough_terrain": [{"col": 0, "row": 1}],
            "obstacles": [{"col": 2, "row": 3}],
            "units": [],
        }
        lan._cached_pcs = []
        lan._cid_to_host = {}
        lan._clients_lock = threading.Lock()

        payload = lan._view_only_state_payload({"units": []})

        self.assertEqual(payload["grid"], {"cols": 5, "rows": 6, "feet_per_square": 5})
        self.assertEqual(payload["rough_terrain"], [{"col": 0, "row": 1}])
        self.assertEqual(payload["obstacles"], [{"col": 2, "row": 3}])

    def test_units_include_max_hp_field(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: [1]
        app._oplog = lambda *args, **kwargs: None
        app._name_role_memory = {"alice": "pc"}
        app._lan_marks_for = lambda _c: []
        app._normalize_action_entries = lambda _entries, _kind: []
        app._token_color_payload = lambda _c: None
        app._has_condition = lambda _c, _name: False
        app._lan_seed_missing_positions = lambda positions, *_args: positions
        app._build_you_payload = lambda _ws_id=None: {"claimed_cid": None, "claimed_name": None}
        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: {}
        app._lan = type("LanStub", (), {"_cached_snapshot": None})()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alice", "hp": 7, "max_hp": 22})(),
        }

        snap = app._lan_snapshot(include_static=False)

        self.assertEqual(snap["units"][0]["hp"], 7)
        self.assertEqual(snap["units"][0]["max_hp"], 22)
        self.assertEqual(snap["units"][0]["facing_deg"], 0)
        self.assertEqual(snap["units"][0]["reactions"], [])
        self.assertEqual(snap["units"][0]["action_total"], 1)


    def test_units_include_action_total_from_combatant(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: [1]
        app._oplog = lambda *args, **kwargs: None
        app._name_role_memory = {"alice": "pc"}
        app._lan_marks_for = lambda _c: []
        app._normalize_action_entries = lambda _entries, _kind: []
        app._token_color_payload = lambda _c: None
        app._has_condition = lambda _c, _name: False
        app._lan_seed_missing_positions = lambda positions, *_args: positions
        app._build_you_payload = lambda _ws_id=None: {"claimed_cid": None, "claimed_name": None}
        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: {}
        app._lan = type("LanStub", (), {"_cached_snapshot": None})()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alice", "hp": 7, "max_hp": 22, "action_total": 3})(),
        }

        snap = app._lan_snapshot(include_static=False)

        self.assertEqual(snap["units"][0]["action_total"], 3)


    def test_tick_uses_idle_interval_without_clients(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._actions = queue.Queue()
        lan._clients_lock = threading.Lock()
        lan._clients = {}
        lan._polling = True
        lan._active_poll_interval_ms = 120
        lan._idle_poll_interval_ms = 350
        lan._idle_cache_refresh_interval_s = 1.0
        lan._last_idle_cache_refresh = 0.0
        lan._cached_snapshot = {}
        lan._cached_pcs = []
        lan._battle_log_subscribers = set()
        lan._log_lan_exception = lambda *args, **kwargs: None

        scheduled = []
        call_counts = {"snap": 0}

        class AppStub:
            def _lan_snapshot(self, include_static=False, hydrate_static=True):
                call_counts["snap"] += 1
                return {"grid": {}}

            def _lan_claimable(self):
                return []

            def after(self, ms, fn):
                scheduled.append((ms, fn))

        lan._tracker = AppStub()

        lan._tick()

        self.assertEqual(call_counts["snap"], 1)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 350)

    def test_tick_throttles_static_payload_checks_when_idle_with_clients(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._actions = queue.Queue()
        lan._clients_lock = threading.Lock()
        lan._clients = {1: object()}
        lan._polling = False
        lan._active_poll_interval_ms = 120
        lan._idle_poll_interval_ms = 350
        lan._idle_cache_refresh_interval_s = 1.0
        lan._last_idle_cache_refresh = 0.0
        lan._cached_snapshot = {"grid": {"cols": 8, "rows": 8}, "units": [], "obstacles": []}
        lan._cached_pcs = []
        lan._battle_log_subscribers = set()
        lan._log_lan_exception = lambda *args, **kwargs: None
        lan._move_debug_log = lambda *args, **kwargs: None
        lan._broadcast_grid_update = lambda *_args, **_kwargs: None
        lan._build_turn_update = lambda *_args, **_kwargs: {}
        lan._build_unit_updates = lambda *_args, **_kwargs: (None, [])
        lan._build_terrain_patch = lambda *_args, **_kwargs: None
        lan._apply_terrain_patch_to_map = lambda *_args, **_kwargs: None
        lan._build_aoe_patch = lambda *_args, **_kwargs: None
        lan._broadcast_payload = lambda *_args, **_kwargs: None
        lan._grid_last_sent = None
        lan._grid_version = 0
        lan._last_snapshot = None
        lan._last_static_json = None
        lan._last_static_check_ts = 0.0
        lan._static_check_interval_s = 10.0

        static_call_count = {"count": 0}

        def _fake_static_data_payload():
            static_call_count["count"] += 1
            return {
                "spell_presets": [],
                "player_spells": {},
                "player_profiles": {},
                "resource_pools": {},
                "monster_choices": [],
                "conditions": [],
                "dice_types": [],
                "token_colours": [],
            }

        lan._static_data_payload = _fake_static_data_payload

        class AppStub:
            def _lan_snapshot(self, include_static=False, hydrate_static=True):
                return {
                    "grid": {"cols": 8, "rows": 8},
                    "units": [],
                    "obstacles": [],
                    "rough_terrain": [],
                    "active_cid": None,
                    "round_num": 1,
                }

            def _lan_claimable(self):
                return []

            def _lan_apply_action(self, _msg):
                return None

            def after(self, _ms, _fn):
                return None

        lan._tracker = AppStub()

        lan._tick()
        lan._tick()
        self.assertEqual(static_call_count["count"], 1)

        lan._actions.put({"type": "noop"})
        lan._tick()
        self.assertEqual(static_call_count["count"], 2)


if __name__ == "__main__":
    unittest.main()
