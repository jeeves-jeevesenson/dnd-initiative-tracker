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
    return c


class BeguilingMagicTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.pool_values = {
            "throat goat": {
                "beguiling_magic": 1,
                "bardic_inspiration": 3,
            }
        }
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
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._lan_force_state_broadcast = lambda: None
        self.app._remove_condition_type = tracker_mod.InitiativeTracker._remove_condition_type.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._has_condition = tracker_mod.InitiativeTracker._has_condition.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._register_combatant_turn_hook = tracker_mod.InitiativeTracker._register_combatant_turn_hook.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._run_combatant_turn_hooks = tracker_mod.InitiativeTracker._run_combatant_turn_hooks.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._condition_is_immune_for_target = lambda target, condition: False
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, {1: (4, 4), 2: (8, 4)})
        self.app._lan_current_position = lambda cid: {1: (4, 4), 2: (8, 4)}.get(int(cid))
        self.app._map_window = None
        self.app._next_stack_id = 1
        self.app.current_cid = 1
        self.app.in_combat = True
        self.app.combatants = {
            1: _make_combatant(1, "Throat Goat", ally=True, is_pc=True),
            2: _make_combatant(2, "Bandit"),
        }
        self.app.combatants[2].saving_throws = {"wis": 1}
        self.app.combatants[2].ability_mods = {"wis": 1}

        def _consume_pool(player_name, pool_id, cost):
            key = str(player_name or "").strip().lower()
            pool_key = str(pool_id or "").strip().lower()
            current = int(self.pool_values.get(key, {}).get(pool_key, 0))
            if current < int(cost):
                return False, "That resource pool be exhausted, matey."
            self.pool_values[key][pool_key] = current - int(cost)
            return True, ""

        self.app._consume_resource_pool_for_cast = _consume_pool
        self.app._set_player_resource_pool_current = lambda player, pool_id, value: (True, "")
        self.app._normalize_player_resource_pools = lambda _profile: [
            {"id": "beguiling_magic", "current": self.pool_values["throat goat"]["beguiling_magic"], "max": 1},
            {"id": "bardic_inspiration", "current": self.pool_values["throat goat"]["bardic_inspiration"], "max": 5},
        ]
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_beguiling_magic_use_consumes_pool_and_rolls_wis_save(self):
        caster = self.app.combatants[1]
        caster._beguiling_magic_window_until = tracker_mod.time.monotonic() + 20
        msg = {
            "type": "beguiling_magic_use",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 5,
            "target_cid": 2,
            "condition": "charmed",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=5):
            self.app._lan_apply_action(msg)

        self.assertEqual(self.pool_values["throat goat"]["beguiling_magic"], 0)
        self.assertTrue(any("WIS save DC 17" in entry[1] for entry in self.logs))
        self.assertLessEqual(float(getattr(caster, "_beguiling_magic_window_until", 1)), 0.0)

    def test_beguiling_magic_failed_save_applies_condition_and_registers_hook(self):
        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        caster._beguiling_magic_window_until = tracker_mod.time.monotonic() + 20
        msg = {
            "type": "beguiling_magic_use",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 6,
            "target_cid": 2,
            "condition": "frightened",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        frightened = [st for st in list(getattr(target, "condition_stacks", []) or []) if getattr(st, "ctype", "") == "frightened"]
        self.assertEqual(len(frightened), 1)
        self.assertEqual(frightened[0].remaining_turns, 6)
        hooks = list(getattr(target, "_feature_turn_hooks", []) or [])
        self.assertTrue(any(str(h.get("type")) == "save_ends_condition" and str(h.get("condition")) == "frightened" for h in hooks))

    def test_save_ends_condition_hook_removes_condition_on_success(self):
        target = self.app.combatants[2]
        target.condition_stacks = [tracker_mod.base.ConditionStack(sid=1, ctype="charmed", remaining_turns=6)]
        target._feature_turn_hooks = [
            {
                "type": "save_ends_condition",
                "when": "end_turn",
                "condition": "charmed",
                "ability": "wisdom",
                "dc": 14,
                "source": "Beguiling Magic",
            }
        ]

        with mock.patch("dnd_initative_tracker.random.randint", return_value=19):
            self.app._run_combatant_turn_hooks(target, "end_turn")

        self.assertFalse(any(getattr(st, "ctype", "") == "charmed" for st in list(getattr(target, "condition_stacks", []) or [])))
        self.assertEqual(list(getattr(target, "_feature_turn_hooks", []) or []), [])


if __name__ == "__main__":
    unittest.main()
