import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


def _c(cid, name, hp):
    c = tracker_mod.base.Combatant(
        cid=cid,
        name=name,
        hp=hp,
        speed=30,
        swim_speed=0,
        fly_speed=0,
        burrow_speed=0,
        climb_speed=0,
        movement_mode="normal",
        move_remaining=30,
        initiative=10,
        ally=False,
        is_pc=False,
    )
    c.max_hp = hp
    c.move_total = 30
    c.action_remaining = 1
    c.bonus_action_remaining = 1
    return c


class LanAoeOverTimeTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.toasts = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Caster"
        self.app._profile_for_player_name = lambda name: {"spellcasting": {"save_dc": 14}}
        self.app._compute_spell_save_dc = lambda profile: 14
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._lan_force_state_broadcast = lambda: None
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._queue_concentration_save = lambda c, source: None
        self.app._condition_is_immune_for_target = lambda target, condition: False
        self.app._adjust_damage_entries_for_target = lambda target, entries: {"entries": list(entries), "notes": []}
        self.app._evaluate_spell_formula = tracker_mod.InitiativeTracker._evaluate_spell_formula.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._normalize_token_color = lambda value: "#ff0000"
        self.app._normalize_facing_degrees = lambda value: 0.0
        self.app._remove_combatants_with_lan_cleanup = lambda cids: None
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._append_lan_log = lambda *args, **kwargs: None
        self.app._lan = type("LanStub", (), {"toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)), "_loop": None})()
        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.current_cid = 1
        self.app._next_stack_id = 1
        self.app._lan_grid_cols = 20
        self.app._lan_grid_rows = 20
        self.app._lan_obstacles = set()
        self.app._lan_rough_terrain = {}
        self.app._lan_positions = {1: (0, 0), 2: (0, 3), 3: (8, 8)}
        self.app._lan_aoes = {}
        self.app._lan_next_aoe_id = 1
        self.app._map_window = None
        self.app.combatants = {1: _c(1, "Caster", 35), 2: _c(2, "Target", 30), 3: _c(3, "Other", 30)}
        self.app.combatants[2].saving_throws = {"con": 0}
        self.app.combatants[2].ability_mods = {"con": 0}
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in [1, 2, 3] if cid in self.app.combatants]

        self.preset = {
            "id": "moonbeam",
            "slug": "moonbeam",
            "name": "Moonbeam",
            "automation": "full",
            "tags": ["aoe", "automation_full"],
            "mechanics": {
                "automation": "full",
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "constitution", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [{"effect": "damage", "damage_type": "radiant", "dice": "2d10"}],
                            "success": [{"effect": "damage", "damage_type": "radiant", "dice": "2d10", "multiplier": 0.5}],
                        },
                    }
                ],
            },
        }
        self.cloud_preset = {
            "id": "cloud-of-daggers",
            "slug": "cloud-of-daggers",
            "name": "Cloud of Daggers",
            "automation": "full",
            "tags": ["aoe", "automation_full"],
            "mechanics": {
                "automation": "full",
                "sequence": [
                    {"check": {"kind": "none"}, "outcomes": {"fail": [{"effect": "damage", "damage_type": "slashing", "dice": "4d4"}]}}
                ],
            },
        }
        self.app._find_spell_preset = lambda spell_slug="", spell_id="": self.cloud_preset if "cloud" in (spell_slug or spell_id) else self.preset

    def _base_aoe(self):
        return {
            "kind": "sphere",
            "name": "Moonbeam",
            "cx": 0.0,
            "cy": 0.0,
            "radius_sq": 1.5,
            "owner": "Caster",
            "owner_cid": 1,
            "owner_ws_id": 7,
            "over_time": True,
            "persistent": True,
            "trigger_on_start_or_enter": "enter_or_end",
            "spell_slug": "moonbeam",
            "spell_id": "moonbeam",
            "slot_level": 2,
            "dc": 14,
            "save_type": "con",
            "move_per_turn_ft": 60,
            "move_remaining_ft": 60,
            "move_action_type": "bonus_action",
        }

    def test_over_time_aoe_not_removed_after_initial_auto_resolve(self):
        aoe = self._base_aoe()
        self.app._lan_aoes[1] = aoe
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 3]):
            resolved = self.app._lan_auto_resolve_cast_aoe(1, aoe, caster=self.app.combatants[1], spell_slug="moonbeam", spell_id="moonbeam", slot_level=2, preset=self.preset)
        self.assertTrue(resolved)
        self.assertIn(1, self.app._lan_aoes)

    def test_enter_and_end_turn_once_per_turn(self):
        aoe = self._base_aoe()
        self.app._lan_aoes[1] = aoe
        self.app._lan_positions[2] = (0, 3)
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[1, 1, 1, 1, 1, 1]):
            ok, _, _ = self.app._lan_try_move(2, 0, 0)
            self.assertTrue(ok)
            hp_after_enter = self.app.combatants[2].hp
            self.app._end_turn_cleanup(2)
            self.assertEqual(self.app.combatants[2].hp, hp_after_enter)
            self.app.turn_num += 1
            self.app.current_cid = 2
            self.app._end_turn_cleanup(2)
        self.assertLess(self.app.combatants[2].hp, hp_after_enter)

    def test_aoe_move_triggers_enter(self):
        aoe = self._base_aoe()
        aoe["cx"], aoe["cy"] = (6.0, 6.0)
        self.app._lan_aoes[1] = aoe
        self.app._lan_positions[2] = (1, 1)
        before = self.app._lan_compute_included_units_for_aoe(aoe)
        aoe["cx"], aoe["cy"] = (1.0, 1.0)
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[1] * 20):
            self.app._lan_handle_aoe_enter_triggers_for_aoe_move(1, aoe, before)
        self.assertLess(self.app.combatants[2].hp, 30)

    def test_move_remaining_resets_on_owner_turn(self):
        aoe = self._base_aoe()
        aoe["move_remaining_ft"] = 5
        self.app._lan_aoes[1] = aoe
        self.app._should_skip_turn = lambda cid: False
        self.app._first_non_skipped_turn_cid = lambda ordered: 1
        self.app._enter_turn_with_auto_skip = lambda starting=False: None
        self.app._log_turn_end = lambda cid: None
        self.app._claimed_cids_snapshot = lambda: set()
        self.app._should_show_dm_up_alert = lambda *args, **kwargs: False
        self.app._display_order = lambda: [self.app.combatants[1], self.app.combatants[2], self.app.combatants[3]]
        self.app.current_cid = 3
        self.app._next_turn()
        self.assertEqual(self.app._lan_aoes[1]["move_remaining_ft"], 60)

    def test_cloud_of_daggers_no_save_auto_damage(self):
        aoe = self._base_aoe()
        aoe.update({"spell_slug": "cloud-of-daggers", "spell_id": "cloud-of-daggers", "save_type": "", "dc": None})
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 2, 2, 2]):
            self.app._lan_apply_aoe_trigger_to_targets(1, aoe, target_cids=[2])
        self.assertEqual(self.app.combatants[2].hp, 22)


if __name__ == "__main__":
    unittest.main()
