import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


def _combatant(cid: int, name: str, *, ally: bool = False, is_pc: bool = False):
    c = tracker_mod.base.Combatant(
        cid=cid,
        name=name,
        hp=30,
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
    c.move_total = 30
    c.ac = 15
    c.max_hp = 30
    return c


class ConcentrationEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: token == "admin"
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Caster"
        self.app._profile_for_player_name = lambda name: {}
        self.app._combatant_can_cast_spell = lambda c, spend: True
        self.app._use_action = lambda c, log_message=None: True
        self.app._use_bonus_action = lambda c, log_message=None: True
        self.app._use_reaction = lambda c, log_message=None: True
        self.app._spell_cast_log_message = lambda *args, **kwargs: "cast"
        self.app._spell_label_from_identifiers = lambda *args, **kwargs: "Spell"
        self.app._smite_slug_from_preset = lambda preset: ""
        self.app._lan_auto_resolve_cast_aoe = lambda *args, **kwargs: False
        self.app._spawn_summons_from_cast = lambda *args, **kwargs: []
        self.app._spawn_custom_summons_from_payload = lambda **kwargs: (True, "", [])
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._lan_force_state_broadcast = lambda: None
        self.app._remove_combatants_with_lan_cleanup = lambda cids: None
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._run_combatant_turn_hooks = lambda c, when: None
        self.app._log = lambda *args, **kwargs: None
        self.app._queue_concentration_save = lambda c, source: None
        self.app._condition_is_immune_for_target = lambda target, condition: False
        self.app._adjust_damage_entries_for_target = lambda target, entries: {"entries": list(entries), "notes": []}
        self.app._evaluate_spell_formula = tracker_mod.InitiativeTracker._evaluate_spell_formula.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._consume_spell_slot_for_cast = lambda **kwargs: (True, "", 1)
        self.app._find_spell_preset = lambda spell_slug="", spell_id="": {
            "slug": "moonbeam" if "moon" in (spell_slug or spell_id) else "sickening-radiance",
            "id": "moonbeam" if "moon" in (spell_slug or spell_id) else "sickening-radiance",
            "name": "Moonbeam" if "moon" in (spell_slug or spell_id) else "Sickening Radiance",
            "concentration": True,
            "level": 2,
        }

        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.current_cid = 1
        self.app._next_stack_id = 1
        self.app._concentration_save_state = {}
        self.app._lan_grid_cols = 20
        self.app._lan_grid_rows = 20
        self.app._lan_obstacles = set()
        self.app._lan_rough_terrain = {}
        self.app._lan_positions = {1: (1, 1), 2: (5, 5)}
        self.app._lan_aoes = {}
        self.app._lan_next_aoe_id = 1
        self.app._map_window = None
        self.app._summon_groups = {}
        self.app._summon_group_meta = {}
        self.app.combatants = {
            1: _combatant(1, "Caster", ally=True, is_pc=True),
            2: _combatant(2, "Target"),
        }
        self.app.combatants[2].saving_throws = {"wis": 0, "con": 0}
        self.app.combatants[2].ability_mods = {"wis": 0, "con": 0}

        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: None,
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_cast_aoe_replaces_existing_concentration_and_removes_old_aoe(self):
        caster = self.app.combatants[1]
        caster.concentrating = True
        caster.concentration_spell = "moonbeam"
        caster.concentration_aoe_ids = [99]
        self.app._lan_aoes[99] = {
            "kind": "sphere",
            "name": "Moonbeam",
            "concentration_bound": True,
            "owner_cid": 1,
        }

        msg = {
            "type": "cast_aoe",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 7,
            "spell_slug": "sickening-radiance",
            "spell_id": "sickening-radiance",
            "admin_token": "admin",
            "payload": {
                "shape": "sphere",
                "name": "Sickening Radiance",
                "cx": 3,
                "cy": 3,
                "radius_ft": 10,
                "concentration": True,
            },
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn(99, self.app._lan_aoes)
        self.assertTrue(caster.concentrating)
        self.assertEqual(caster.concentration_spell, "sickening-radiance")
        self.assertEqual(len(caster.concentration_aoe_ids), 1)

    def test_removing_concentration_bound_aoe_ends_concentration(self):
        caster = self.app.combatants[1]
        self.app._start_concentration(caster, "moonbeam", spell_level=2, aoe_ids=[10])
        self.app._lan_aoes[10] = {
            "kind": "sphere",
            "name": "Moonbeam",
            "owner_cid": 1,
            "concentration_bound": True,
        }

        self.app._lan_apply_action({"type": "aoe_remove", "cid": 1, "_claimed_cid": 1, "aid": 10})

        self.assertFalse(caster.concentrating)
        self.assertEqual(caster.concentration_spell, "")

    def test_haste_expiry_ends_caster_concentration(self):
        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.app._start_concentration(caster, "haste", spell_level=3, targets=[target.cid])
        self.app._register_target_spell_effect(
            caster.cid,
            target.cid,
            "haste",
            spell_level=3,
            concentration_bound=True,
            clear_group="haste_1_2",
            primitives={
                "modifiers": {"ac_bonus": 2, "speed_multiplier": 2, "save_advantage_by_ability": ["dex"]},
                "turn_state": {"extra_action_profile": "haste_limited"},
            },
            adapter="haste",
            adapter_payload={"duration_turns": 1},
        )

        self.app._end_turn_cleanup(target.cid)

        self.assertFalse(caster.concentrating)
        self.assertEqual(caster.concentration_spell, "")

    def test_polymorph_temp_hp_depletion_ends_caster_concentration(self):
        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.app._start_concentration(caster, "polymorph", spell_level=4, targets=[target.cid])
        target.wild_shape_form_name = "Wolf"
        target.wild_shape_form_id = "wolf"
        target.polymorph_source_cid = caster.cid
        target.polymorph_remaining_turns = 10
        target.polymorph_duration_turns = 10
        target.polymorph_base = {"name": "Target", "speed": 30, "swim_speed": 0, "fly_speed": 0, "climb_speed": 0, "burrow_speed": 0, "movement_mode": "normal", "str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10, "is_spellcaster": False, "ability_mods": {}, "saving_throws": {}, "actions": [], "monster_slug": None}
        target.temp_hp = 5

        self.app._apply_damage_to_target_with_temp_hp(target, 6)

        self.assertEqual(target.temp_hp, 0)
        self.assertFalse(caster.concentrating)
        self.assertEqual(caster.concentration_spell, "")

    def test_silence_blocks_verbal_spellcasting_via_shared_environment_helper(self):
        caster = self.app.combatants[1]
        self.app._lan_aoes[77] = {
            "map_effect": True,
            "kind": "sphere",
            "cx": 1.0,
            "cy": 1.0,
            "radius_sq": 3.0,
            "environment": {"silence": True},
            "name": "Silence",
        }
        blocked, message = self.app._spellcast_blocked_by_environment(caster, {"components": "V, S"})
        self.assertTrue(blocked)
        self.assertIn("silence", message.lower())

    def test_cast_spell_rejects_verbal_components_inside_silence_zone(self):
        caster = self.app.combatants[1]
        caster.spell_cast_remaining = 1
        toasts: list[str] = []
        self.app._lan.toast = lambda _ws_id, message: toasts.append(str(message))
        self.app._find_spell_preset = lambda spell_slug="", spell_id="": {
            "slug": "guiding-bolt",
            "id": "guiding-bolt",
            "name": "Guiding Bolt",
            "components": "V, S",
            "concentration": False,
            "level": 1,
        }
        self.app._lan_aoes[79] = {
            "map_effect": True,
            "kind": "sphere",
            "cx": 1.0,
            "cy": 1.0,
            "radius_sq": 2.0,
            "environment": {"silence": True},
            "name": "Silence",
        }
        self.app._lan_apply_action(
            {
                "type": "cast_spell",
                "cid": 1,
                "_claimed_cid": 1,
                "_ws_id": 5,
                "spell_slug": "guiding-bolt",
                "spell_id": "guiding-bolt",
                "action_type": "action",
                "payload": {},
            }
        )
        self.assertTrue(any("silence" in item.lower() for item in toasts))
        self.assertEqual(int(getattr(caster, "spell_cast_remaining", 0) or 0), 1)

    def test_environment_visibility_state_registers_and_clears_with_map_effect_cleanup(self):
        self.app._register_map_spell_effect(
            55,
            {
                "map_effect": True,
                "kind": "sphere",
                "cx": 1.0,
                "cy": 1.0,
                "radius_sq": 4.0,
                "owner_cid": 1,
                "concentration_bound": True,
                "environment": {"obscured": True, "magical_darkness": True},
            },
        )
        state_before = self.app._cell_visibility_state(1, 1)
        self.assertTrue(state_before.get("obscured"))
        self.assertTrue(state_before.get("magical_darkness"))

        self.app._clear_map_spell_effect(55)
        state_after = self.app._cell_visibility_state(1, 1)
        self.assertFalse(state_after.get("obscured"))
        self.assertFalse(state_after.get("magical_darkness"))

    def test_movement_cost_multiplier_uses_shared_environment_state(self):
        mover = self.app.combatants[1]
        self.app._lan_positions[1] = (0, 0)
        self.app._lan_aoes = {
            1: {
                "map_effect": True,
                "kind": "cube",
                "cx": 1.0,
                "cy": 0.0,
                "side_sq": 1.0,
                "environment": {"difficult_terrain": True},
            },
            2: {
                "map_effect": True,
                "kind": "cube",
                "cx": 0.0,
                "cy": 1.0,
                "side_sq": 1.0,
                "environment": {"movement_cost_multiplier": 4},
            },
        }
        self.assertEqual(self.app._movement_cost_multiplier_for_step(0, 0, 1, 0, combatant=mover), 2.0)
        self.assertEqual(self.app._movement_cost_multiplier_for_step(0, 0, 0, 1, combatant=mover), 4.0)

    def test_spike_growth_move_damage_uses_shared_environment_hook(self):
        mover = self.app.combatants[2]
        mover.hp = 30
        self.app._lan_aoes[88] = {
            "map_effect": True,
            "name": "Spike Growth",
            "kind": "sphere",
            "cx": 5.0,
            "cy": 5.0,
            "radius_sq": 2.0,
            "environment": {
                "difficult_terrain": True,
                "move_damage_trigger": {"per_feet": 5, "dice": "2d4", "damage_type": "piercing"},
            },
        }
        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._apply_environmental_move_damage(mover, (4, 5), (5, 5), 10)
        self.assertLess(mover.hp, 30)

    def test_cast_aoe_persists_environment_metadata_from_spell_preset(self):
        self.app._find_spell_preset = lambda spell_slug="", spell_id="": {
            "slug": "fog-cloud",
            "id": "fog-cloud",
            "name": "Fog Cloud",
            "concentration": True,
            "level": 1,
            "mechanics": {
                "aoe_behavior": {"map_effect": True, "persistent_default": True, "trigger_mode": "none"},
                "map_environment": {"obscured": True},
            },
        }
        self.app._lan_apply_action(
            {
                "type": "cast_aoe",
                "cid": 1,
                "_claimed_cid": 1,
                "_ws_id": 9,
                "spell_slug": "fog-cloud",
                "spell_id": "fog-cloud",
                "admin_token": "admin",
                "payload": {
                    "shape": "sphere",
                    "name": "Fog Cloud",
                    "cx": 3,
                    "cy": 3,
                    "radius_ft": 20,
                    "concentration": True,
                },
            }
        )
        self.assertTrue(self.app._lan_aoes)
        created = next(iter(self.app._lan_aoes.values()))
        self.assertEqual((created.get("environment") or {}).get("obscured"), True)


    def test_cast_ensnaring_strike_auto_targets_self_and_sets_concentration(self):
        caster = self.app.combatants[1]
        caster.concentrating = True
        caster.concentration_spell = "moonbeam"
        caster.concentration_spell_level = 2
        self.app._find_spell_preset = lambda spell_slug="", spell_id="": {
            "slug": "ensnaring-strike",
            "id": "ensnaring-strike",
            "name": "Ensnaring Strike",
            "concentration": True,
            "level": 1,
            "duration": "Concentration, up to 1 minute",
        }

        msg = {
            "type": "cast_spell",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 7,
            "spell_slug": "ensnaring-strike",
            "spell_id": "ensnaring-strike",
            "action_type": "bonus",
            "payload": {"action_type": "bonus"},
        }

        self.app._lan_apply_action(msg)

        self.assertTrue(caster.concentrating)
        self.assertEqual(caster.concentration_spell, "ensnaring-strike")
        self.assertEqual(caster.concentration_spell_level, 1)
        self.assertEqual(caster.concentration_target, [1])
        ensnaring_stacks = [st for st in list(getattr(caster, "condition_stacks", []) or []) if st.ctype == "ensnaring_strike"]
        self.assertEqual(len(ensnaring_stacks), 1)
        self.assertEqual(int(ensnaring_stacks[0].remaining_turns or 0), 10)

    def test_concentration_save_uses_war_caster_advantage(self):
        caster = self.app.combatants[1]
        caster.saving_throws = {"con": 0}
        self.app._profile_for_player_name = lambda _name: {"features": ["War Caster"]}
        self.app._start_concentration(caster, "ensnaring-strike", spell_level=1, targets=[1])

        seq = iter([3, 17])
        orig_randint = tracker_mod.random.randint
        tracker_mod.random.randint = lambda a, b: next(seq)
        try:
            self.app._queue_concentration_save(caster, "damage")
        finally:
            tracker_mod.random.randint = orig_randint

        self.assertTrue(caster.concentrating)


    def test_shield_of_faith_concentration_end_clears_registered_modifier(self):
        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.app._start_concentration(caster, "shield-of-faith", spell_level=1, targets=[target.cid])
        self.app._register_target_spell_effect(
            caster.cid,
            target.cid,
            "shield-of-faith",
            concentration_bound=True,
            clear_group=f"shield_of_faith_{caster.cid}_{target.cid}",
            primitives={"modifiers": {"ac_bonus": 2}},
        )

        self.assertEqual(self.app._combatant_ac_modifier(target), 2)
        self.app._end_concentration(caster)
        self.assertEqual(self.app._combatant_ac_modifier(target), 0)



    def test_map_effect_template_metadata_is_created_for_migrated_spells(self):
        caster = self.app.combatants[1]
        spells = [
            ("entangle", True, "start", "cube", 20),
            ("fog-cloud", False, None, "sphere", 20),
            ("darkness", False, None, "sphere", 15),
            ("silence", False, None, "sphere", 20),
            ("zone-of-truth", True, "start_or_enter", "sphere", 15),
            ("spike-growth", True, "enter", "sphere", 20),
        ]

        for idx, (slug, over_time, trigger_mode, shape, size_ft) in enumerate(spells, start=1):
            with self.subTest(spell=slug):
                self.app._lan_aoes = {}
                self.app._lan_next_aoe_id = 1
                caster.concentrating = False
                caster.concentration_spell = ""
                caster.concentration_aoe_ids = []
                self.app._find_spell_preset = lambda spell_slug="", spell_id="", _slug=slug, _ot=over_time, _tm=trigger_mode: {
                    "slug": _slug,
                    "id": _slug,
                    "name": _slug.replace("-", " ").title(),
                    "concentration": _slug != "zone-of-truth",
                    "level": 2,
                    "mechanics": {
                        "automation": "partial",
                        "aoe_behavior": {
                            "map_effect": True,
                            "persistent_default": True,
                            "over_time_default": _ot,
                            "trigger_mode": _tm,
                        },
                    },
                }
                payload = {"shape": shape, "name": slug, "cx": float(idx + 1), "cy": 2.0, "concentration": slug != "zone-of-truth"}
                if shape in ("sphere", "circle"):
                    payload["radius_ft"] = float(size_ft)
                else:
                    payload["side_ft"] = float(size_ft)

                self.app._lan_apply_action(
                    {
                        "type": "cast_aoe",
                        "cid": 1,
                        "_claimed_cid": 1,
                        "_ws_id": 7,
                        "spell_slug": slug,
                        "spell_id": slug,
                        "admin_token": "admin",
                        "payload": payload,
                    }
                )

                self.assertTrue(self.app._lan_aoes)
                aid = next(iter(self.app._lan_aoes.keys()))
                effect = self.app._lan_aoes[aid]
                self.assertTrue(effect.get("map_effect"))
                self.assertEqual(effect.get("effect_id"), aid)
                self.assertEqual(effect.get("aoe_id"), aid)
                self.assertTrue(effect.get("persistent"))
                template = effect.get("template")
                self.assertIsInstance(template, dict)
                self.assertEqual(template.get("shape"), shape)
                self.assertEqual(((template.get("triggers") or {}).get("timing")), trigger_mode)

    def test_end_concentration_clears_concentration_bound_map_effects_via_shared_helper(self):
        caster = self.app.combatants[1]
        self.app._start_concentration(caster, "entangle", spell_level=1, aoe_ids=[11])
        self.app._register_map_spell_effect(
            11,
            {
                "kind": "cube",
                "name": "Entangle",
                "owner_cid": caster.cid,
                "concentration_bound": True,
                "map_effect": True,
                "persistent": True,
            },
        )

        self.assertIn(11, self.app._lan_aoes)
        self.app._end_concentration(caster)
        self.assertNotIn(11, self.app._lan_aoes)

    def test_zone_of_truth_and_spike_growth_triggers_flow_through_shared_map_trigger_helper(self):
        calls = []

        def _capture_trigger(aid, aoe, *, target_cids, turn_key=None):
            calls.append((aid, list(target_cids), aoe.get("spell_slug")))
            return True

        self.app._lan_apply_aoe_trigger_to_targets = _capture_trigger
        self.app._lan_aoes = {
            21: {
                "kind": "sphere",
                "cx": 5.0,
                "cy": 5.0,
                "radius_sq": 4.0,
                "over_time": True,
                "trigger_on_start_or_enter": "start_or_enter",
                "spell_slug": "zone-of-truth",
                "map_effect": True,
            },
            22: {
                "kind": "sphere",
                "cx": 8.0,
                "cy": 5.0,
                "radius_sq": 4.0,
                "over_time": True,
                "trigger_on_start_or_enter": "enter",
                "spell_slug": "spike-growth",
                "map_effect": True,
            },
        }

        self.app._lan_positions[2] = (5, 5)
        self.app._apply_map_spell_trigger(21, self.app._lan_aoes[21], target_cids=[2])
        self.app._lan_handle_aoe_enter_triggers_for_moved_unit(2, (2, 5), (8, 5))

        slugs = {entry[2] for entry in calls}
        self.assertIn("zone-of-truth", slugs)
        self.assertIn("spike-growth", slugs)


    def test_gust_of_wind_map_trigger_pushes_along_line_via_shared_movement_helper(self):
        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.app._lan_positions[caster.cid] = (5, 5)
        self.app._lan_positions[target.cid] = (7, 5)
        target.saving_throws = {"str": 0}
        target.ability_mods = {"str": 0}

        self.app._lan_auto_resolve_cast_aoe = tracker_mod.InitiativeTracker._lan_auto_resolve_cast_aoe.__get__(
            self.app,
            tracker_mod.InitiativeTracker,
        )
        self.app._find_spell_preset = lambda **_kwargs: {
            "slug": "gust-of-wind",
            "id": "gust-of-wind",
            "name": "Gust of Wind",
            "automation": "full",
            "tags": ["aoe", "automation_full"],
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "strength", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [{"effect": "movement", "kind": "push", "distance_ft": 15, "origin": "aoe_direction"}],
                            "success": [],
                        },
                    }
                ]
            },
        }

        aoe = {
            "kind": "line",
            "cx": 5.0,
            "cy": 5.0,
            "ax": 5.0,
            "ay": 4.0,
            "angle_deg": 90.0,
            "length_sq": 12.0,
            "width_sq": 2.0,
            "save_type": "str",
            "dc": 13,
            "spell_slug": "gust-of-wind",
            "spell_id": "gust-of-wind",
            "owner_cid": caster.cid,
            "slot_level": 2,
            "over_time": True,
            "trigger_on_start_or_enter": "enter_or_end",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            applied = self.app._lan_apply_aoe_trigger_to_targets(33, aoe, target_cids=[target.cid])

        self.assertTrue(applied)
        self.assertEqual(self.app._lan_positions.get(target.cid), (10, 5))

if __name__ == "__main__":
    unittest.main()
