import unittest

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
        self.app._apply_haste_effect(caster, target, duration_turns=1, ac_bonus=2)

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


if __name__ == "__main__":
    unittest.main()
