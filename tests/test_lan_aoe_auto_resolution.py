import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


def _make_combatant(cid: int, name: str, hp: int, *, is_pc: bool = False, ally: bool = False):
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
        ally=ally,
        is_pc=is_pc,
    )
    c.max_hp = hp
    c.move_total = 30
    return c


class LanAoeAutoResolutionTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Aelar"
        self.app._profile_for_player_name = lambda name: {"spellcasting": {"save_dc": 14}}
        self.app._compute_spell_save_dc = lambda profile: 14
        self.app._spell_cast_log_message = lambda caster_name, spell_name, slot_level: f"{caster_name} casts {spell_name}"
        self.app._consume_spell_slot_for_cast = lambda **kwargs: (True, "", kwargs.get("slot_level"))
        self.app._combatant_can_cast_spell = lambda c, spend: True
        self.app._use_action = lambda c, log_message=None: True
        self.app._use_bonus_action = lambda c, log_message=None: True
        self.app._use_reaction = lambda c, log_message=None: True
        self.app._resolve_summon_choice = lambda *args, **kwargs: ({}, 1, None)
        self.app._spawn_summons_from_cast = lambda **kwargs: []
        self.app._spawn_custom_summons_from_payload = lambda caster_cid, payload: (True, "", [])
        self.app._normalize_token_color = lambda value: "#ff0000"
        self.app._normalize_facing_degrees = lambda value: 0.0
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._remove_combatants_with_lan_cleanup = lambda cids: [self.app.combatants.pop(int(cid), None) for cid in cids]
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._lan_force_state_broadcast = lambda: None
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._queue_concentration_save = lambda c, source: None
        self.app._condition_is_immune_for_target = lambda target, condition: False
        self.app._adjust_damage_entries_for_target = lambda target, entries: {"entries": list(entries), "notes": []}
        self.app._evaluate_spell_formula = tracker_mod.InitiativeTracker._evaluate_spell_formula.__get__(self.app, tracker_mod.InitiativeTracker)

        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.current_cid = 1
        self.app.start_cid = None
        self.app._next_stack_id = 1
        self.app._concentration_save_state = {}
        self.app._lan_grid_cols = 20
        self.app._lan_grid_rows = 20
        self.app._lan_obstacles = set()
        self.app._lan_rough_terrain = {}
        self.app._lan_positions = {1: (0, 0), 2: (4, 4), 3: (6, 4)}
        self.app._lan_aoes = {}
        self.app._lan_next_aoe_id = 1
        self.app._map_window = None
        self.app.combatants = {
            1: _make_combatant(1, "Aelar", 35, is_pc=True, ally=True),
            2: _make_combatant(2, "Goblin", 20),
            3: _make_combatant(3, "Orc", 20),
        }
        self.app.combatants[2].saving_throws = {"dex": 0}
        self.app.combatants[2].ability_mods = {"dex": 0}
        self.app.combatants[3].saving_throws = {"dex": 0}
        self.app.combatants[3].ability_mods = {"dex": 0}
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in [1, 2, 3] if cid in self.app.combatants]

        self.preset = {
            "id": "frost-burst",
            "slug": "frost-burst",
            "name": "Frost Burst",
            "automation": "full",
            "tags": ["aoe", "automation_full"],
            "mechanics": {
                "automation": "full",
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "dexterity", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [
                                {"effect": "damage", "damage_type": "cold", "dice": "2d6"},
                                {"effect": "condition", "condition": "prone", "duration_turns": 1},
                            ],
                            "success": [
                                {"effect": "damage", "damage_type": "cold", "dice": "2d6", "multiplier": 0.5},
                            ],
                        },
                    }
                ]
            },
        }
        self.app._find_spell_preset = lambda **kwargs: self.preset
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_cast_aoe_auto_resolves_damage_save_and_condition(self):
        msg = {
            "type": "cast_aoe",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 7,
            "spell_slug": "frost-burst",
            "slot_level": 3,
            "payload": {
                "shape": "sphere",
                "name": "Frost Burst",
                "radius_ft": 20,
                "cx": 5,
                "cy": 4,
            },
        }
        # target2 fail save 5 vs DC14, damage 2+3=5; target3 pass save 15 vs DC14, damage 4+4=8 then half=4
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 2, 3, 15, 4, 4]):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.app.combatants[2].hp, 15)
        self.assertEqual(self.app.combatants[3].hp, 16)
        self.assertTrue(any(st.ctype == "prone" for st in self.app.combatants[2].condition_stacks))
        self.assertFalse(any(st.ctype == "prone" for st in self.app.combatants[3].condition_stacks))
        self.assertEqual(self.app._lan_aoes, {})
        log_text = "\n".join(entry for _cid, entry in self.logs)
        self.assertIn("Frost Burst: Goblin save DEX FAIL", log_text)
        self.assertIn("Frost Burst: Orc save DEX PASS", log_text)
        self.assertIn("Goblin save DEX FAIL (5 vs DC 14) -> 5 Cold damage", log_text)
        self.assertIn("Orc save DEX PASS (15 vs DC 14) -> 4 Cold damage", log_text)


    def test_cast_aoe_manual_damage_override_uses_entries_and_save_multiplier(self):
        msg = {
            "type": "cast_aoe",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 21,
            "spell_slug": "frost-burst",
            "slot_level": 4,
            "damage_entries": [{"amount": 13, "type": "cold"}],
            "payload": {
                "shape": "sphere",
                "name": "Frost Burst",
                "radius_ft": 20,
                "cx": 5,
                "cy": 4,
            },
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 15]):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.app.combatants[2].hp, 7)
        self.assertEqual(self.app.combatants[3].hp, 14)
        log_text = "\n".join(entry for _cid, entry in self.logs)
        self.assertIn("Goblin save DEX FAIL (5 vs DC 14) -> 13 Cold damage", log_text)
        self.assertIn("Orc save DEX PASS (15 vs DC 14) -> 6 Cold damage", log_text)

    def test_cast_aoe_manual_damage_applies_failed_save_push_without_caster_context(self):
        self.preset["name"] = "Thunderwave"
        self.preset["mechanics"]["sequence"][0]["check"] = {"kind": "saving_throw", "ability": "constitution", "dc": 14}
        self.preset["mechanics"]["sequence"][0]["outcomes"] = {
            "fail": [
                {"effect": "damage", "damage_type": "thunder", "dice": "2d8"},
                {"effect": "movement", "kind": "push", "distance_ft": 10, "origin": "caster"},
            ],
            "success": [
                {"effect": "damage", "damage_type": "thunder", "dice": "2d8", "multiplier": 0.5},
            ],
        }
        self.app._is_admin_token_valid = lambda token: token == "adm"
        self.app._lan_positions = {1: (4, 4), 2: (5, 4), 3: (4, 5)}
        for target_cid in (1, 2, 3):
            self.app.combatants[target_cid].saving_throws = {"con": 0}
            self.app.combatants[target_cid].ability_mods = {"con": 0}
        msg = {
            "type": "cast_aoe",
            "admin_token": "adm",
            "_ws_id": 22,
            "spell_slug": "thunderwave",
            "damage_entries": [{"amount": 12, "type": "thunder"}],
            "payload": {
                "shape": "cube",
                "name": "Thunderwave",
                "side_ft": 15,
                "cx": 4,
                "cy": 4,
            },
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[15, 5, 15]):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.app._lan_positions.get(2), (7, 4))
        self.assertEqual(self.app._lan_positions.get(3), (4, 5))
        log_text = "\n".join(entry for _cid, entry in self.logs)
        self.assertIn("Thunderwave: moved Goblin (push)", log_text)

    def test_cast_aoe_non_full_automation_does_not_auto_resolve(self):
        self.preset["automation"] = "manual"
        self.preset["tags"] = ["aoe"]
        msg = {
            "type": "cast_aoe",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 8,
            "spell_slug": "frost-burst",
            "payload": {
                "shape": "sphere",
                "name": "Frost Burst",
                "radius_ft": 20,
                "cx": 5,
                "cy": 4,
            },
        }

        self.app._lan_apply_action(msg)

        self.assertEqual(self.app.combatants[2].hp, 20)
        self.assertEqual(self.app.combatants[3].hp, 20)
        self.assertEqual(len(self.app._lan_aoes), 1)

    def test_cast_aoe_manual_damage_entries_still_apply_failed_save_pushback(self):
        self.preset["automation"] = "manual"
        self.preset["tags"] = ["aoe"]
        self.preset["mechanics"]["sequence"][0]["outcomes"]["fail"].append(
            {"effect": "movement", "kind": "push", "distance_ft": 10, "origin": "caster"}
        )
        self.app._lan_positions[1] = (0, 4)
        self.app._lan_positions[2] = (4, 4)
        self.app._lan_positions[3] = (8, 4)
        self.app.combatants[2].saving_throws = {"dex": -1}
        self.app.combatants[2].ability_mods = {"dex": -1}
        self.app.combatants[3].saving_throws = {"dex": 5}
        self.app.combatants[3].ability_mods = {"dex": 5}
        msg = {
            "type": "cast_aoe",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 22,
            "spell_slug": "frost-burst",
            "damage_entries": [{"amount": 12, "type": "cold"}],
            "payload": {
                "shape": "sphere",
                "name": "Frost Burst",
                "radius_ft": 20,
                "cx": 5,
                "cy": 4,
            },
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 10]):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.app.combatants[2].hp, 8)
        self.assertEqual(self.app.combatants[3].hp, 14)
        self.assertEqual(self.app._lan_positions.get(2), (6, 4))
        self.assertEqual(self.app._lan_positions.get(3), (8, 4))

    def test_monk_elemental_burst_consumes_focus_and_auto_resolves(self):
        consumed = []
        self.app.combatants[1].action_remaining = 1
        self.app._consume_resource_pool_for_cast = (
            lambda player_name, pool_id, cost: (consumed.append((player_name, pool_id, cost)) or True, "")
        )
        self.app._use_action = lambda c, log_message=None: True
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Monk", "level": 10}]},
            "abilities": {"wis": 14},
            "proficiency": {"bonus": 4},
        }
        msg = {
            "type": "monk_elemental_burst",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 18,
            "damage_type": "fire",
            "payload": {"cx": 5, "cy": 4},
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 2, 3, 4, 16, 6, 6, 6]):
            self.app._lan_apply_action(msg)

        self.assertEqual(consumed, [("Aelar", "focus_points", 2)])
        self.assertEqual(self.app.combatants[2].hp, 11)
        self.assertEqual(self.app.combatants[3].hp, 11)
        self.assertIn((18, "Elemental Burst cast."), self.toasts)

    def test_monk_elemental_burst_pushes_targets_on_failed_save(self):
        self.app._consume_resource_pool_for_cast = lambda *_args, **_kwargs: (True, "")
        self.app._use_action = lambda c, log_message=None: True
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Monk", "level": 10}]},
            "abilities": {"wis": 14},
            "proficiency": {"bonus": 4},
        }
        msg = {
            "type": "monk_elemental_burst",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 19,
            "damage_type": "thunder",
            "movement_mode": "push",
            "payload": {"cx": 5, "cy": 4},
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 1, 1, 1, 2, 1, 1, 1]):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.app._lan_positions.get(2), (2, 4))
        self.assertEqual(self.app._lan_positions.get(3), (8, 4))

    def test_evasion_reduces_dex_save_aoe_damage_for_monk_target(self):
        self.app.combatants[2].is_pc = True
        self.app.combatants[2].name = "Monk Ally"
        self.app._pc_name_for = lambda cid: "Aelar" if int(cid) == 1 else "Monk Ally"
        self.app._profile_for_player_name = lambda name: (
            {"leveling": {"classes": [{"name": "Monk", "level": 7}]}, "spellcasting": {"save_dc": 14}}
            if str(name) == "Monk Ally"
            else {"spellcasting": {"save_dc": 14}}
        )
        msg = {
            "type": "cast_aoe",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 20,
            "spell_slug": "frost-burst",
            "payload": {
                "shape": "sphere",
                "name": "Frost Burst",
                "radius_ft": 20,
                "cx": 4,
                "cy": 4,
            },
        }
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 4, 4, 15, 4, 4]):
            self.app._lan_apply_action(msg)
        self.assertEqual(self.app.combatants[2].hp, 16)


    def test_forced_movement_uses_map_tokens_when_lan_positions_missing_target(self):
        class MapWindowStub:
            def __init__(self):
                self.cols = 20
                self.rows = 20
                self.obstacles = set()
                self.rough_terrain = {}
                self.unit_tokens = {2: {"col": 4, "row": 4}}
                self.feet_per_square = 5

            def winfo_exists(self):
                return True

            def _grid_to_pixel(self, col, row):
                return int(col) * 10, int(row) * 10

            def _place_unit_at_pixel(self, cid, x, y):
                self.unit_tokens[int(cid)] = {"col": int(round(x / 10)), "row": int(round(y / 10))}

        self.app._map_window = MapWindowStub()
        self.app._lan_positions[1] = (0, 4)
        self.app._lan_positions.pop(2, None)

        moved = self.app._lan_apply_forced_movement(1, 2, "push", 10)

        self.assertTrue(moved)
        self.assertEqual(self.app._lan_positions.get(2), (6, 4))
        self.assertEqual(self.app._map_window.unit_tokens.get(2), {"col": 6, "row": 4})

    def test_forced_movement_updates_map_window_token_position(self):
        class MapWindowStub:
            def __init__(self):
                self.cols = 20
                self.rows = 20
                self.obstacles = set()
                self.rough_terrain = {}
                self.unit_tokens = {2: {"col": 4, "row": 4}}
                self.feet_per_square = 5

            def winfo_exists(self):
                return True

            def _grid_to_pixel(self, col, row):
                return int(col) * 10, int(row) * 10

            def _place_unit_at_pixel(self, cid, x, y):
                self.unit_tokens[int(cid)] = {"col": int(round(x / 10)), "row": int(round(y / 10))}

        self.app._map_window = MapWindowStub()
        self.app._lan_positions[1] = (0, 4)
        self.app._lan_positions[2] = (4, 4)

        moved = self.app._lan_apply_forced_movement(1, 2, "push", 10)

        self.assertTrue(moved)
        self.assertEqual(self.app._lan_positions.get(2), (6, 4))
        self.assertEqual(self.app._map_window.unit_tokens.get(2), {"col": 6, "row": 4})

if __name__ == "__main__":
    unittest.main()

