import unittest
from types import SimpleNamespace

import dnd_initative_tracker as tracker_mod


def _c(
    cid,
    name,
    initiative,
    dex,
    ally=True,
    summoned_by_cid=None,
    summon_controller_mode="",
    summon_shared_turn=False,
):
    return SimpleNamespace(
        cid=cid,
        name=name,
        initiative=initiative,
        dex=dex,
        nat20=False,
        ally=ally,
        summoned_by_cid=summoned_by_cid,
        summon_controller_mode=summon_controller_mode,
        summon_shared_turn=summon_shared_turn,
    )


class LanSharedInitiativeTests(unittest.TestCase):
    def _build_app(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._is_admin_token_valid = lambda token: False
        app.in_combat = True
        app.round_num = 1
        app.turn_num = 1
        app.start_cid = None
        app._turn_group_active_cids = []
        app._turn_group_controller_map = {}
        app._turn_group_done_controllers = set()
        app._turn_group_signature = None
        app._turn_group_skip_next_cleanup_cid = None
        app.cleaned = []
        app.turn_ended = []
        app.next_turn_calls = 0
        app._end_turn_cleanup = lambda cid, skip_decrement_types=None: app.cleaned.append(int(cid))
        app._log_turn_end = lambda cid: app.turn_ended.append(int(cid))
        app._next_turn = lambda: setattr(app, "next_turn_calls", app.next_turn_calls + 1)
        app._lan = type(
            "LanStub",
            (),
            {
                "_claims": {},
                "toast": lambda _self, ws_id, text: app.toasts.append((ws_id, text)),
                "_append_lan_log": lambda *args, **kwargs: None,
            },
        )()
        app.toasts = []
        return app

    def test_two_claimed_pcs_same_initiative_wait_for_both_end_turns(self):
        app = self._build_app()
        app.combatants = {
            1: _c(1, "Alice", 15, 2, ally=True),
            2: _c(2, "Bob", 15, 1, ally=True),
            3: _c(3, "Orc", 10, 0, ally=False),
        }
        app.current_cid = 1
        app._display_order = lambda: [app.combatants[1], app.combatants[2], app.combatants[3]]
        app._lan._claims = {101: 1, 102: 2}

        app._lan_apply_action({"type": "end_turn", "cid": 1, "_claimed_cid": 1, "_ws_id": 101})
        self.assertEqual(app.next_turn_calls, 0)
        self.assertEqual(sorted(app.cleaned), [1])

        app._lan_apply_action({"type": "end_turn", "cid": 2, "_claimed_cid": 2, "_ws_id": 102})
        self.assertEqual(app.next_turn_calls, 1)
        self.assertEqual(sorted(app.cleaned), [1, 2])

    def test_claimed_plus_unclaimed_friendly_requires_dm_end_turn(self):
        app = self._build_app()
        app.combatants = {
            1: _c(1, "Alice", 15, 2, ally=True),
            2: _c(2, "Wolf Ally", 15, 1, ally=True),
            3: _c(3, "Orc", 10, 0, ally=False),
        }
        app.current_cid = 1
        app._display_order = lambda: [app.combatants[1], app.combatants[2], app.combatants[3]]
        app._lan._claims = {101: 1}

        app._lan_apply_action({"type": "end_turn", "cid": 1, "_claimed_cid": 1, "_ws_id": 101})
        self.assertEqual(app.next_turn_calls, 0)

        app._lan_apply_action({"type": "dm_end_turn", "_claimed_cid": None, "_ws_id": 999})
        self.assertEqual(app.next_turn_calls, 1)
        self.assertEqual(sorted(app.cleaned), [1, 2])

    def test_player_end_turn_cleans_shared_turn_summon(self):
        app = self._build_app()
        app.combatants = {
            1: _c(1, "Alice", 15, 2, ally=True),
            2: _c(
                2,
                "Alice Summon",
                15,
                1,
                ally=True,
                summoned_by_cid=1,
                summon_controller_mode="summoner",
                summon_shared_turn=True,
            ),
            3: _c(3, "Orc", 10, 0, ally=False),
        }
        app.current_cid = 1
        app._display_order = lambda: [app.combatants[1], app.combatants[2], app.combatants[3]]
        app._lan._claims = {101: 1}

        app._lan_apply_action({"type": "end_turn", "cid": 1, "_claimed_cid": 1, "_ws_id": 101})

        self.assertEqual(app.next_turn_calls, 1)
        self.assertEqual(sorted(app.cleaned), [1, 2])

    def test_mixed_tie_single_friendly_uses_dex_and_not_simultaneous(self):
        app = self._build_app()
        app.in_combat = True
        app.combatants = {
            1: _c(1, "PC", 14, 2, ally=True),
            2: _c(2, "Enemy", 14, 4, ally=False),
        }
        order = [c.cid for c in app._sorted_combatants()]
        self.assertEqual(order, [2, 1])

        app.current_cid = 2
        app._display_order = lambda: [app.combatants[2], app.combatants[1]]
        status = app._turn_group_status_payload()
        self.assertEqual(status["active_cids"], [2])

    def test_mixed_tie_two_friendlies_first_as_shared_group_then_enemy(self):
        app = self._build_app()
        app.in_combat = True
        app.combatants = {
            1: _c(1, "PC A", 14, 1, ally=True),
            2: _c(2, "PC B", 14, 2, ally=True),
            3: _c(3, "Enemy", 14, 5, ally=False),
        }
        order = [c.cid for c in app._sorted_combatants()]
        self.assertEqual(order[:2], [2, 1])
        self.assertEqual(order[2], 3)

        app.current_cid = 2
        app._display_order = lambda: [app.combatants[2], app.combatants[1], app.combatants[3]]
        status = app._turn_group_status_payload()
        self.assertEqual(status["active_cids"], [2, 1])

        app.current_cid = 3
        app._display_order = lambda: [app.combatants[3], app.combatants[2], app.combatants[1]]
        status = app._turn_group_status_payload()
        self.assertEqual(status["active_cids"], [3])

    def test_dm_end_turn_group_marks_dm_done_without_advance_until_players_done(self):
        app = self._build_app()
        app.combatants = {
            1: _c(1, "Alice", 15, 2, ally=True),
            2: _c(2, "Wolf Ally", 15, 1, ally=True),
            3: _c(3, "Orc", 10, 0, ally=False),
        }
        app.current_cid = 1
        app._display_order = lambda: [app.combatants[1], app.combatants[2], app.combatants[3]]
        app._lan._claims = {101: 1}
        rebuild_calls = []
        app._rebuild_table = lambda scroll_to_current=False: rebuild_calls.append(bool(scroll_to_current))

        result = app._dm_end_turn_group()

        self.assertTrue(result)
        self.assertEqual(app.next_turn_calls, 0)
        self.assertIn(2, app.cleaned)
        self.assertEqual(rebuild_calls, [True])

    def test_dm_end_turn_group_noop_when_dm_not_controller(self):
        app = self._build_app()
        app.combatants = {
            1: _c(1, "Alice", 15, 2, ally=True),
            2: _c(2, "Bob", 15, 1, ally=True),
        }
        app.current_cid = 1
        app._display_order = lambda: [app.combatants[1], app.combatants[2]]
        app._lan._claims = {101: 1, 102: 2}
        def _unexpected_rebuild(scroll_to_current=False):
            raise AssertionError("unexpected rebuild")
        app._rebuild_table = _unexpected_rebuild

        result = app._dm_end_turn_group()

        self.assertFalse(result)
        self.assertEqual(app.next_turn_calls, 0)


if __name__ == "__main__":
    unittest.main()
