import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


def _make_combatant(cid: int, name: str, *, ac: int, hp: int, speed: int = 30, ally: bool = False, is_pc: bool = False):
    c = tracker_mod.base.Combatant(
        cid=cid,
        name=name,
        hp=hp,
        speed=speed,
        swim_speed=0,
        fly_speed=0,
        burrow_speed=0,
        climb_speed=0,
        movement_mode="normal",
        move_remaining=speed,
        initiative=10,
        ally=ally,
        is_pc=is_pc,
    )
    c.move_total = speed
    c.ac = ac
    c.max_hp = hp
    return c


class LanSpellTargetRequestTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Aelar"
        self.app._profile_for_player_name = lambda name: {}
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app._next_stack_id = 1
        self.app._concentration_save_state = {}
        self.app._lan_aoes = {}
        self.app.start_cid = None
        self.app.current_cid = 1
        self.app._map_window = None
        self.app.combatants = {
            1: _make_combatant(1, "Aelar", ac=16, hp=25, ally=True, is_pc=True),
            2: _make_combatant(2, "Goblin", ac=15, hp=20),
            3: _make_combatant(3, "Borin", ac=16, hp=22, ally=True, is_pc=True),
        }
        self.app.combatants[2].saving_throws = {"wis": 2}
        self.app.combatants[2].ability_mods = {"wis": 1}
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._remove_combatants_with_lan_cleanup = lambda cids: [self.app.combatants.pop(int(cid), None) for cid in cids]
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._find_spell_preset = lambda *_args, **_kwargs: None
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_spell_target_request_save_passes_without_damage(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 9,
            "target_cid": 2,
            "spell_name": "Toll the Dead",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 13,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=15):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 0)
        self.assertFalse(result.get("hit"))
        self.assertTrue(result.get("save_result", {}).get("passed"))
        self.assertEqual(self.app.combatants[2].hp, 20)

    def test_spell_target_request_save_fail_requests_damage_prompt(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 10,
            "target_cid": 2,
            "spell_name": "Toll the Dead",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 16,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=4):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("needs_damage_prompt"))
        self.assertFalse(result.get("save_result", {}).get("passed"))
        self.assertEqual(self.app.combatants[2].hp, 20)

    def test_spell_target_request_applies_manual_damage(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 11,
            "target_cid": 2,
            "spell_name": "Fire Bolt",
            "spell_mode": "attack",
            "hit": True,
            "damage_entries": [{"amount": 9, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 9)
        self.assertEqual(self.app.combatants[2].hp, 11)
        self.assertIn((11, "Spell hits."), self.toasts)


    def test_spell_target_request_records_manual_critical_hit(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 12,
            "target_cid": 2,
            "spell_name": "Fire Bolt",
            "spell_mode": "attack",
            "hit": True,
            "critical": True,
            "damage_entries": [{"amount": 9, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("critical"))
        self.assertTrue(any("(CRIT)" in message for _, message in self.logs))


    def test_spell_target_request_auto_crit_uses_max_damage_from_damage_dice(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 15,
            "target_cid": 2,
            "spell_name": "Fire Bolt",
            "spell_mode": "attack",
            "hit": True,
            "critical": True,
            "damage_entries": [],
            "damage_dice": "1d10",
            "damage_type": "fire",
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("critical"))
        self.assertEqual(result.get("damage_entries"), [{"amount": 10, "type": "fire"}])
        self.assertEqual(result.get("damage_total"), 10)
        self.assertEqual(self.app.combatants[2].hp, 10)

    def test_spell_target_request_auto_roll_damage_dice_when_blank(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 16,
            "target_cid": 2,
            "spell_name": "Ray of Frost",
            "spell_mode": "attack",
            "hit": True,
            "critical": False,
            "damage_entries": [],
            "damage_dice": "2d6+1",
            "damage_type": "cold",
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 5]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_entries"), [{"amount": 8, "type": "cold"}])
        self.assertEqual(result.get("damage_total"), 8)
        self.assertEqual(self.app.combatants[2].hp, 12)
    def test_haste_spell_target_request_applies_buffs_and_concentration(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "haste",
            "id": "haste",
            "name": "Haste",
            "level": 3,
            "mechanics": {"ui": {"spell_targeting": {"duration_turns": 10, "ac_bonus": 2}}},
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 13,
            "target_cid": 3,
            "spell_name": "Haste",
            "spell_slug": "haste",
            "spell_mode": "auto_hit",
            "hit": True,
        }

        self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        target = self.app.combatants[3]
        self.assertTrue(caster.concentrating)
        self.assertEqual(caster.concentration_spell, "haste")
        self.assertEqual(target.ac, 18)
        self.assertEqual(getattr(target, "haste_remaining_turns", 0), 10)
        skip, _, _ = self.app._process_start_of_turn(target)
        self.assertFalse(skip)
        self.assertEqual(target.action_remaining, 2)
        self.assertEqual(target.move_total, 60)
        self.app._end_turn_cleanup(target.cid)
        self.assertEqual(getattr(target, "haste_remaining_turns", 0), 9)

    def test_haste_breaking_concentration_applies_lethargy(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "haste",
            "id": "haste",
            "name": "Haste",
            "level": 3,
            "mechanics": {"ui": {"spell_targeting": {"duration_turns": 10, "ac_bonus": 2}}},
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 14,
            "target_cid": 3,
            "spell_name": "Haste",
            "spell_slug": "haste",
            "spell_mode": "auto_hit",
            "hit": True,
        }

        self.app._lan_apply_action(msg)
        self.app._end_concentration(self.app.combatants[1])

        target = self.app.combatants[3]
        self.assertEqual(getattr(target, "haste_remaining_turns", 0), 0)
        self.assertEqual(target.ac, 16)
        self.assertEqual(getattr(target, "haste_lethargy_turns_remaining", 0), 1)
        self.assertEqual(self.app._effective_speed(target), 0)
        incapacitated = [st for st in target.condition_stacks if getattr(st, "ctype", "") == "incapacitated"]
        self.assertEqual(len(incapacitated), 1)
        self.assertEqual(incapacitated[0].remaining_turns, 1)


if __name__ == "__main__":
    unittest.main()
