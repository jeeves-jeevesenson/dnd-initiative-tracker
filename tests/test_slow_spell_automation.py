import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


def _make_combatant(cid: int, name: str, *, ally: bool = False, is_pc: bool = False):
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
    c.max_hp = 30
    c.action_remaining = 1
    c.bonus_action_remaining = 1
    c.attack_resource_remaining = 1
    c.spell_cast_remaining = 1
    c.condition_stacks = []
    c.end_turn_save_riders = []
    c.saving_throws = {"wis": 0, "dex": 1}
    c.ability_mods = {"wis": 0, "dex": 1}
    return c


class SlowAutomationTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.toasts = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._lan_force_state_broadcast = lambda: None
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._next_stack_id = 1
        self.app.current_cid = 1
        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.combatants = {
            1: _make_combatant(1, "Mage", ally=True, is_pc=True),
            2: _make_combatant(2, "Bandit"),
        }
        self.app._find_spell_preset = lambda slug, sid: {
            "slug": "slow",
            "id": "slow",
            "name": "Slow",
            "level": 3,
            "mechanics": {
                "sequence": [{"check": {"kind": "saving_throw", "ability": "wis", "dc": "spell_save_dc"}, "outcomes": {"fail": []}}]
            },
        }
        self.app._infer_spell_targeting_mode = lambda preset: "save"
        self.app._infer_spell_save_ability = lambda preset: "wis"
        self.app._condition_is_immune_for_target = lambda target, condition: False
        self.app._compute_spell_save_dc = lambda profile: 15
        self.app._pc_name_for = lambda cid: "Mage"
        self.app._profile_for_player_name = lambda name: {"spellcasting": {}}
        self.app._start_concentration = tracker_mod.InitiativeTracker._start_concentration.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._end_concentration = tracker_mod.InitiativeTracker._end_concentration.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._remove_condition_type = tracker_mod.InitiativeTracker._remove_condition_type.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._has_condition = tracker_mod.InitiativeTracker._has_condition.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_slow_applies_condition_concentration_and_end_turn_rider(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 11,
            "target_cid": 2,
            "spell_name": "Slow",
            "spell_slug": "slow",
            "spell_id": "slow",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 15,
            "roll_save": True,
        }
        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.assertTrue(any(getattr(st, "ctype", "") == "slow_spell" for st in target.condition_stacks))
        self.assertTrue(any(str(r.get("clear_group", "")).startswith("slow_1_2") for r in target.end_turn_save_riders))
        self.assertTrue(bool(getattr(caster, "concentrating", False)))
        self.assertEqual(str(getattr(caster, "concentration_spell", "")).lower(), "slow")

    def test_slow_helpers_apply_dex_disadvantage_and_ac_penalty(self):
        target = self.app.combatants[2]
        target.condition_stacks = [tracker_mod.base.ConditionStack(sid=9, ctype="slow_spell", remaining_turns=None)]
        self.assertTrue(self.app._slow_spell_save_disadvantage(target, "dex"))
        self.assertFalse(self.app._slow_spell_save_disadvantage(target, "wis"))
        self.assertEqual(self.app._slow_spell_ac_penalty(target), 2)


if __name__ == "__main__":
    unittest.main()
