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
    c.ability_mods = {"cha": 3}
    c.temp_hp = 0
    return c


class MantleOfInspirationTests(unittest.TestCase):
    def setUp(self):
        self.toasts = []
        self.logs = []
        self.pool_values = {"throat goat": {"bardic_inspiration": 2}}
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: {1: "Throat Goat", 2: "Mike Hawk", 3: "Yaz"}.get(int(cid), "")
        self.app._profile_for_player_name = lambda _name: {"leveling": {"classes": [{"name": "bard", "level": 8}]}}
        self.app._load_player_yaml_cache = lambda force_refresh=False: None
        self.app._player_yaml_data_by_name = {}
        self.app._use_bonus_action = lambda caster: True
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, {1: (4, 4), 2: (7, 4), 3: (8, 4)})
        self.app._lan_current_position = lambda cid: {1: (4, 4), 2: (7, 4), 3: (8, 4)}.get(int(cid))
        self.app._map_window = None
        self.app._next_stack_id = 1
        self.app.in_combat = True
        self.app.current_cid = 1
        self.app._lan_force_state_broadcast = lambda: None
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._ability_score_modifier = tracker_mod.InitiativeTracker._ability_score_modifier.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._combatant_ability_modifier = tracker_mod.InitiativeTracker._combatant_ability_modifier.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._bardic_inspiration_die_sides = tracker_mod.InitiativeTracker._bardic_inspiration_die_sides.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app._mantle_of_inspiration_max_targets = tracker_mod.InitiativeTracker._mantle_of_inspiration_max_targets.__get__(self.app, tracker_mod.InitiativeTracker)
        self.app.combatants = {
            1: _make_combatant(1, "Throat Goat", ally=True, is_pc=True),
            2: _make_combatant(2, "Mike Hawk", ally=True, is_pc=True),
            3: _make_combatant(3, "Yaz", ally=True, is_pc=True),
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

    def test_mantle_of_inspiration_applies_temp_hp_and_spends_bi(self):
        msg = {
            "type": "mantle_of_inspiration",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 8,
            "target_cids": [2, 3],
            "die_override": 4,
        }
        self.app._lan_apply_action(msg)
        self.assertEqual(self.pool_values["throat goat"]["bardic_inspiration"], 1)
        self.assertEqual(int(getattr(self.app.combatants[2], "temp_hp", 0)), 8)
        self.assertEqual(int(getattr(self.app.combatants[3], "temp_hp", 0)), 8)
        self.assertTrue(any("Mantle of Inspiration" in entry[1] for entry in self.logs))

    def test_mantle_of_inspiration_enforces_target_cap(self):
        self.app.combatants[1].ability_mods["cha"] = 1
        msg = {
            "type": "mantle_of_inspiration",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 9,
            "target_cids": [2, 3],
            "die_override": 4,
        }
        self.app._lan_apply_action(msg)
        self.assertEqual(self.pool_values["throat goat"]["bardic_inspiration"], 2)
        self.assertEqual(int(getattr(self.app.combatants[2], "temp_hp", 0)), 0)
        self.assertTrue(any("Too many targets" in message for _, message in self.toasts))

    def test_mantle_uses_max_temp_hp_semantics(self):
        self.app.combatants[2].temp_hp = 10
        msg = {
            "type": "mantle_of_inspiration",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 10,
            "target_cids": [2],
        }
        with mock.patch("dnd_initative_tracker.random.randint", return_value=4):
            self.app._lan_apply_action(msg)
        self.assertEqual(int(getattr(self.app.combatants[2], "temp_hp", 0)), 10)

    def test_mantle_of_inspiration_allows_self_target(self):
        msg = {
            "type": "mantle_of_inspiration",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 13,
            "target_cids": [1],
            "die_override": 4,
        }
        self.app._lan_apply_action(msg)
        self.assertEqual(self.pool_values["throat goat"]["bardic_inspiration"], 1)
        self.assertEqual(int(getattr(self.app.combatants[1], "temp_hp", 0)), 8)


if __name__ == "__main__":
    unittest.main()
