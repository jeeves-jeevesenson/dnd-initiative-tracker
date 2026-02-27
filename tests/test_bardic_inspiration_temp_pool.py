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
    c.bonus_action_remaining = 1
    c.condition_stacks = []
    return c


class BardicInspirationTempPoolTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.pool_values = {"throat goat": {"bardic_inspiration": 2}}
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: {1: "Throat Goat", 2: "Mike Hawk"}.get(int(cid), "")
        self.app._profile_for_player_name = lambda _name: {"leveling": {"classes": [{"name": "bard", "level": 8}]}}
        self.app._load_player_yaml_cache = lambda force_refresh=False: None
        self.app._player_yaml_data_by_name = {
            "Throat Goat": {"resources": {"pools": [{"id": "bardic_inspiration", "current": 2, "max": 5}]}},
            "Mike Hawk": {"resources": {"pools": []}},
        }
        self.app._normalize_player_resource_pools = lambda data: [{"id": "bardic_inspiration", "label": "Bardic Inspiration", "current": 2, "max": 5}]
        self.app._augment_resource_pools_with_temporary_conditions = tracker_mod.InitiativeTracker._augment_resource_pools_with_temporary_conditions.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._combatant_for_player_name = tracker_mod.InitiativeTracker._combatant_for_player_name.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._inspired_state_for = tracker_mod.InitiativeTracker._inspired_state_for.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._player_resource_pools_payload = tracker_mod.InitiativeTracker._player_resource_pools_payload.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._bardic_inspiration_die_sides = tracker_mod.InitiativeTracker._bardic_inspiration_die_sides.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._remove_condition_type = tracker_mod.InitiativeTracker._remove_condition_type.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._use_bonus_action = lambda caster: True
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, {1: (4, 4), 2: (7, 4)})
        self.app._lan_current_position = lambda cid: {1: (4, 4), 2: (7, 4)}.get(int(cid))
        self.app._map_window = None
        self.app._next_stack_id = 1
        self.app.in_combat = True
        self.app.current_cid = 1
        self.app._lan_force_state_broadcast = lambda: None
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app.combatants = {
            1: _make_combatant(1, "Throat Goat", ally=True, is_pc=True),
            2: _make_combatant(2, "Mike Hawk", ally=True, is_pc=True),
        }

        def _consume_pool(player_name, pool_id, cost):
            key = str(player_name or "").strip().lower()
            pkey = str(pool_id or "").strip().lower()
            current = int(self.pool_values.get(key, {}).get(pkey, 0))
            if current < int(cost):
                return False, "That resource pool be exhausted, matey."
            self.pool_values[key][pkey] = current - int(cost)
            return True, ""

        self.app._consume_resource_pool_for_cast = _consume_pool
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: self.toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

    def test_bardic_inspiration_grant_applies_inspired_and_metadata(self):
        msg = {
            "type": "bardic_inspiration_grant",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 6,
            "target_cid": 2,
        }
        self.app._lan_apply_action(msg)
        target = self.app.combatants[2]
        self.assertTrue(any(getattr(st, "ctype", "") == "inspired" for st in target.condition_stacks))
        inspired = getattr(target, "_inspired_state", None)
        self.assertIsInstance(inspired, dict)
        self.assertEqual(int(inspired.get("die_sides", 0)), 8)
        self.assertEqual(self.pool_values["throat goat"]["bardic_inspiration"], 1)

    def test_resource_pool_payload_includes_temp_bardic_dice_pool(self):
        target = self.app.combatants[2]
        target.condition_stacks = [tracker_mod.base.ConditionStack(sid=1, ctype="inspired", remaining_turns=None)]
        target._inspired_state = {
            "source_cid": 1,
            "die_sides": 8,
            "granted_at": tracker_mod.time.monotonic(),
            "expires_at": tracker_mod.time.monotonic() + 120,
            "label": "Bardic Inspiration",
        }
        pools = self.app._player_resource_pools_payload()
        mike_pools = pools.get("Mike Hawk") or []
        self.assertTrue(any(str(entry.get("id", "")).startswith("temp_bardic_dice_") for entry in mike_pools))

    def test_bardic_inspiration_use_spends_and_clears_condition(self):
        target = self.app.combatants[2]
        target.condition_stacks = [tracker_mod.base.ConditionStack(sid=1, ctype="inspired", remaining_turns=None)]
        target._inspired_state = {
            "source_cid": 1,
            "die_sides": 8,
            "granted_at": tracker_mod.time.monotonic(),
            "expires_at": tracker_mod.time.monotonic() + 120,
            "label": "Bardic Inspiration",
        }
        msg = {
            "type": "bardic_inspiration_use",
            "cid": 2,
            "_claimed_cid": 2,
            "_ws_id": 7,
        }
        with mock.patch("dnd_initative_tracker.random.randint", return_value=5):
            self.app._lan_apply_action(msg)
        self.assertFalse(any(getattr(st, "ctype", "") == "inspired" for st in target.condition_stacks))
        self.assertIsNone(getattr(target, "_inspired_state", None))
        self.assertTrue(any("rolled 5" in entry[1] for entry in self.logs))

    def test_bardic_inspiration_grant_rejects_out_of_range_without_spending_pool(self):
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, {1: (0, 0), 2: (20, 20)})
        self.app._lan_current_position = lambda cid: {1: (0, 0), 2: (20, 20)}.get(int(cid))
        msg = {
            "type": "bardic_inspiration_grant",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 11,
            "target_cid": 2,
        }
        self.app._lan_apply_action(msg)
        self.assertEqual(self.pool_values["throat goat"]["bardic_inspiration"], 2)
        target = self.app.combatants[2]
        self.assertFalse(any(getattr(st, "ctype", "") == "inspired" for st in target.condition_stacks))
        self.assertIsNone(getattr(target, "_inspired_state", None))
        self.assertTrue(any("out of Bardic Inspiration range" in message for _, message in self.toasts))

    def test_bardic_inspiration_grant_allows_self_target(self):
        msg = {
            "type": "bardic_inspiration_grant",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 12,
            "target_cid": 1,
        }
        self.app._lan_apply_action(msg)
        target = self.app.combatants[1]
        self.assertTrue(any(getattr(st, "ctype", "") == "inspired" for st in target.condition_stacks))
        inspired = getattr(target, "_inspired_state", None)
        self.assertIsInstance(inspired, dict)
        self.assertEqual(int(inspired.get("source_cid", 0)), 1)
        self.assertEqual(self.pool_values["throat goat"]["bardic_inspiration"], 1)


if __name__ == "__main__":
    unittest.main()
