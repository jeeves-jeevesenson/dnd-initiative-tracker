import unittest

import dnd_initative_tracker as tracker_mod


class LanHiddenTokensSnapshotTests(unittest.TestCase):
    def test_lan_snapshot_includes_invisible_and_unseen_flags_for_units(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._lan_grid_cols = 10
        app._lan_grid_rows = 10
        app._lan_obstacles = set()
        app._lan_positions = {1: (1, 1), 2: (2, 2)}
        app._lan_aoes = {}
        app._lan_rough_terrain = {}
        app._lan_next_aoe_id = 1
        app.current_cid = None
        app.round_num = 1
        app._display_order = lambda: []
        app._oplog = lambda *args, **kwargs: None
        app._name_role_memory = {"Goblin": "enemy", "Hero": "pc"}
        app._lan_marks_for = lambda _c: []
        app._normalize_action_entries = lambda _entries, _kind: []
        app._token_color_payload = lambda _c: None
        app._token_border_color_payload = lambda _c: None
        app._has_condition = lambda c, name: any(getattr(st, "ctype", "") == name for st in getattr(c, "condition_stacks", []))
        app._lan_seed_missing_positions = lambda positions, *_args: positions
        app._spell_presets_payload = lambda: []
        app._player_spell_config_payload = lambda: {}
        app._player_profiles_payload = lambda: {}
        app._player_resource_pools_payload = lambda: {}
        app._lan_active_aura_contexts = lambda **_kwargs: []
        app._lan = type("LanStub", (), {"_cached_snapshot": {}})()

        enemy = type(
            "C",
            (),
            {
                "cid": 1,
                "name": "Goblin",
                "hp": 7,
                "is_hidden": False,
                "condition_stacks": [tracker_mod.base.ConditionStack(sid=1, ctype="invisible", remaining_turns=None)],
            },
        )()
        hero = type("C", (), {"cid": 2, "name": "Hero", "hp": 15, "condition_stacks": []})()
        app.combatants = {1: enemy, 2: hero}

        snap = app._lan_snapshot(include_static=False)
        by_cid = {int(unit["cid"]): unit for unit in snap["units"]}

        self.assertFalse(by_cid[1]["is_hidden"])
        self.assertTrue(by_cid[1]["is_invisible"])
        self.assertTrue(by_cid[1]["is_unseen"])
        self.assertFalse(by_cid[2]["is_hidden"])
        self.assertFalse(by_cid[2]["is_invisible"])
        self.assertFalse(by_cid[2]["is_unseen"])


if __name__ == "__main__":
    unittest.main()
