import queue
import threading
import unittest

import dnd_initative_tracker as tracker_mod


class LanSnapshotStaticTests(unittest.TestCase):
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

        app._lan = type("LanStub", (), {"_cached_snapshot": {
            "spell_presets": [{"name": "cached"}],
            "player_spells": {"Alice": {"spells": []}},
            "player_profiles": {"Alice": {"name": "Alice"}},
            "resource_pools": {"Alice": [{"id": "wild_shape", "current": 1}]},
        }})()

        snap = app._lan_snapshot(include_static=False)
        self.assertEqual(snap["spell_presets"], [{"name": "cached"}])
        self.assertEqual(snap["player_spells"], {"Alice": {"spells": []}})
        self.assertEqual(snap["player_profiles"], {"Alice": {"name": "Alice"}})
        self.assertEqual(snap["resource_pools"], {"Alice": [{"id": "wild_shape", "current": 0}]})

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
        lan._log_lan_exception = lambda *args, **kwargs: None

        scheduled = []
        call_counts = {"snap": 0}

        class AppStub:
            def _lan_snapshot(self, include_static=False):
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


if __name__ == "__main__":
    unittest.main()
