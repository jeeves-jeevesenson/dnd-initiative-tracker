import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


def _make_combatant(cid: int, name: str, *, hp: int = 20, ally: bool = False, is_pc: bool = False):
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
    c.action_remaining = 1
    c.bonus_action_remaining = 1
    c.attack_resource_remaining = 1
    c.spell_cast_remaining = 1
    c.condition_stacks = []
    return c


class CommandSpellTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Throat Goat"
        self.app._profile_for_player_name = lambda _name: {
            "spellcasting": {"save_dc_formula": "8 + prof + casting_mod", "casting_ability": "cha"},
            "abilities": {"cha": 20},
            "leveling": {"level": 10},
        }
        self.app._compute_spell_save_dc = lambda _profile: 17
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._lan_force_state_broadcast = lambda: None
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, {1: (4, 4), 2: (7, 4), 3: (9, 4)})
        self.app._lan_current_position = lambda cid: {1: (4, 4), 2: (7, 4), 3: (9, 4)}.get(int(cid))
        self.app._map_window = None
        self.app._next_stack_id = 1
        self.app.current_cid = 1
        self.app.in_combat = True
        self.app.combatants = {
            1: _make_combatant(1, "Throat Goat", ally=True, is_pc=True),
            2: _make_combatant(2, "Bandit"),
            3: _make_combatant(3, "Cultist"),
        }
        self.app.combatants[2].saving_throws = {"wis": 1}
        self.app.combatants[2].ability_mods = {"wis": 1}
        self.app.combatants[3].saving_throws = {"wis": 0}
        self.app.combatants[3].ability_mods = {"wis": 0}
        self.app._condition_is_immune_for_target = lambda target, condition: False
        self.app._run_combatant_turn_hooks = tracker_mod.InitiativeTracker._run_combatant_turn_hooks.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._register_combatant_turn_hook = tracker_mod.InitiativeTracker._register_combatant_turn_hook.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._has_condition = tracker_mod.InitiativeTracker._has_condition.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._remove_condition_type = tracker_mod.InitiativeTracker._remove_condition_type.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_command_resolve_applies_condition_and_hook_on_failed_save(self):
        msg = {
            "type": "command_resolve",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 9,
            "target_cids": [2],
            "command_option": "halt",
            "slot_level": 1,
            "spell_slug": "command",
        }
        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            self.app._lan_apply_action(msg)

        target = self.app.combatants[2]
        self.assertTrue(any(getattr(st, "ctype", "") == "command_halt" for st in target.condition_stacks))
        hooks = list(getattr(target, "_feature_turn_hooks", []) or [])
        self.assertTrue(any(str(h.get("type")) == "command_effect" and str(h.get("condition")) == "command_halt" for h in hooks))

    def test_command_resolve_enforces_upcast_target_limit(self):
        msg = {
            "type": "command_resolve",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 10,
            "target_cids": [2, 3],
            "command_option": "flee",
            "slot_level": 1,
            "spell_slug": "command",
        }
        self.app._lan_apply_action(msg)
        self.assertTrue(any("allows only 1 target" in text for _, text in self.toasts))

    def test_command_effect_hook_grovel_prones_and_ends_turn(self):
        target = self.app.combatants[2]
        target.condition_stacks = [tracker_mod.base.ConditionStack(sid=1, ctype="command_grovel", remaining_turns=1)]
        target._feature_turn_hooks = [
            {
                "type": "command_effect",
                "when": "start_turn",
                "condition": "command_grovel",
                "command": "grovel",
                "source": "Command",
                "source_name": "Throat Goat",
                "source_cid": 1,
            }
        ]
        self.app._run_combatant_turn_hooks(target, "start_turn")
        self.assertTrue(any(getattr(st, "ctype", "") == "prone" for st in target.condition_stacks))
        self.assertFalse(any(getattr(st, "ctype", "") == "command_grovel" for st in target.condition_stacks))
        self.assertEqual(list(getattr(target, "_feature_turn_hooks", []) or []), [])
        self.assertEqual(int(target.action_remaining), 0)
        self.assertEqual(int(target.bonus_action_remaining), 0)
        self.assertEqual(int(target.move_remaining), 0)

    def test_command_resolve_not_blocked_by_turn_gate(self):
        self.app.current_cid = 2
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: False
        msg = {
            "type": "command_resolve",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 9,
            "target_cids": [2],
            "command_option": "halt",
            "slot_level": 1,
            "spell_slug": "command",
        }
        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            self.app._lan_apply_action(msg)

        target = self.app.combatants[2]
        self.assertTrue(any(getattr(st, "ctype", "") == "command_halt" for st in target.condition_stacks))
        self.assertNotIn((9, "Not yer turn yet, matey."), self.toasts)


if __name__ == "__main__":
    unittest.main()
