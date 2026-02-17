import unittest

import dnd_initative_tracker as tracker_mod


class EchoKnightLanTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.toasts = []
        self.broadcasts = 0
        self.rebuilds = 0
        self.bonus_uses = 0
        self.next_cid = 2
        self.spec = tracker_mod.MonsterSpec(
            filename="johns-echo.yaml",
            name="Johns Echo",
            mtype="construct",
            cr=None,
            hp=1,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=0,
            init_mod=0,
            saving_throws={},
            ability_mods={},
            raw_data={},
        )
        john = tracker_mod.base.Combatant(
            cid=1,
            name="John Twilight",
            hp=50,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="Normal",
            move_remaining=30,
            initiative=12,
            dex=1,
            ally=True,
            is_pc=True,
        )
        john.bonus_action_remaining = 1
        john.spell_cast_remaining = 1
        self.app.combatants = {1: john}
        self.app.current_cid = 1
        self.app.in_combat = True
        self.app._lan_positions = {1: (5, 5)}
        self.app._summon_groups = {}
        self.app._summon_group_meta = {}
        self.app._map_window = None
        self.app._oplog = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._find_monster_spec_by_slug = lambda slug: self.spec if str(slug).strip().lower() == "johns-echo" else None
        self.app._unique_name = lambda name: str(name)
        self.app._lan_current_position = lambda cid: self.app._lan_positions.get(int(cid))
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, dict(self.app._lan_positions))
        self.app._rebuild_table = lambda scroll_to_current=False: self._mark_rebuild()
        self.app._lan_force_state_broadcast = lambda: self._mark_broadcast()
        self.app._lan = type(
            "Lan",
            (),
            {
                "toast": lambda _self, ws_id, text: self.toasts.append((ws_id, text)),
                "_append_lan_log": lambda *args, **kwargs: None,
            },
        )()
        self.app._create_combatant = self._create_combatant
        self.app._use_bonus_action = self._use_bonus_action
        self.app._apply_summon_initiative = tracker_mod.InitiativeTracker._apply_summon_initiative.__get__(
            self.app, tracker_mod.InitiativeTracker
        )
        self.app._normalize_token_color = tracker_mod.InitiativeTracker._normalize_token_color.__get__(
            self.app, tracker_mod.InitiativeTracker
        )
    def _mark_rebuild(self):
        self.rebuilds += 1

    def _mark_broadcast(self):
        self.broadcasts += 1

    def _create_combatant(
        self,
        name,
        hp,
        speed,
        initiative,
        dex,
        ally,
        swim_speed=0,
        fly_speed=0,
        burrow_speed=0,
        climb_speed=0,
        movement_mode="Normal",
        is_pc=False,
        is_spellcaster=None,
        saving_throws=None,
        ability_mods=None,
        monster_spec=None,
    ):
        cid = self.next_cid
        self.next_cid += 1
        unit = tracker_mod.base.Combatant(
            cid=cid,
            name=name,
            hp=hp,
            speed=speed,
            swim_speed=swim_speed,
            fly_speed=fly_speed,
            burrow_speed=burrow_speed,
            climb_speed=climb_speed,
            movement_mode=movement_mode,
            move_remaining=speed,
            initiative=initiative,
            dex=dex,
            ally=ally,
            is_pc=is_pc,
            is_spellcaster=bool(is_spellcaster),
            saving_throws=dict(saving_throws or {}),
            ability_mods=dict(ability_mods or {}),
            monster_spec=monster_spec,
        )
        unit.bonus_action_remaining = 0
        self.app.combatants[cid] = unit
        return cid

    def _use_bonus_action(self, unit):
        remaining = int(getattr(unit, "bonus_action_remaining", 0) or 0)
        if remaining <= 0:
            return False
        unit.bonus_action_remaining = remaining - 1
        self.bonus_uses += 1
        return True

    def _apply(self, msg):
        base = {"cid": 1, "_claimed_cid": 1, "_ws_id": 9}
        base.update(msg)
        self.app._lan_apply_action(base)

    def _echo_units(self):
        return [
            unit
            for unit in self.app.combatants.values()
            if getattr(unit, "summon_group_id", "") == "echo:1"
        ]

    def test_echo_summon_spawns_once_and_repositions(self):
        self._apply({"type": "echo_summon", "to": {"col": 7, "row": 5}})
        echo_units = self._echo_units()
        self.assertEqual(len(echo_units), 1)
        echo = echo_units[0]
        self.assertEqual(getattr(echo, "token_color", None), "#7ec8ff")
        self.assertEqual(getattr(echo, "initiative", None), self.app.combatants[1].initiative)
        self.assertTrue(getattr(echo, "summon_shared_turn", False))
        self.assertEqual(self.app._lan_positions.get(echo.cid), (7, 5))

        self.app.combatants[1].bonus_action_remaining = 1
        self._apply({"type": "echo_summon", "to": {"col": 6, "row": 6}})
        echo_units = self._echo_units()
        self.assertEqual(len(echo_units), 1)
        self.assertEqual(self.app._lan_positions.get(echo.cid), (6, 6))

    def test_echo_summon_consumes_bonus_action_but_not_spell_resource(self):
        self.app.combatants[1].bonus_action_remaining = 1
        self.app.combatants[1].spell_cast_remaining = 1

        self._apply({"type": "echo_summon", "to": {"col": 6, "row": 5}})

        self.assertEqual(self.app.combatants[1].bonus_action_remaining, 0)
        self.assertEqual(self.app.combatants[1].spell_cast_remaining, 1)
        self.assertEqual(self.bonus_uses, 1)

    def test_echo_summon_rejects_out_of_range(self):
        self._apply({"type": "echo_summon", "to": {"col": 9, "row": 9}})
        self.assertEqual(len(self._echo_units()), 0)
        self.assertTrue(any("out of echo range" in text for _ws_id, text in self.toasts))

    def test_echo_summon_accepts_payload_to_coordinates(self):
        self.app.combatants[1].bonus_action_remaining = 1
        self._apply({"type": "echo_summon", "payload": {"to": {"col": 6, "row": 5}}})
        self.assertEqual(len(self._echo_units()), 1)
        self.assertEqual(self.app.combatants[1].bonus_action_remaining, 0)

    def test_echo_swap_requires_echo_and_range_then_swaps_positions(self):
        self._apply({"type": "echo_swap"})
        self.assertTrue(any("Summon Johns Echo first" in text for _ws_id, text in self.toasts))

        self.toasts.clear()
        self.app.combatants[1].bonus_action_remaining = 1
        self._apply({"type": "echo_summon", "to": {"col": 7, "row": 5}})
        echo = self._echo_units()[0]
        self.app.combatants[1].bonus_action_remaining = 1
        self.app.combatants[1].spell_cast_remaining = 1
        self._apply({"type": "echo_swap"})
        self.assertEqual(self.app._lan_positions.get(1), (7, 5))
        self.assertEqual(self.app._lan_positions.get(echo.cid), (5, 5))
        self.assertEqual(self.app.combatants[1].bonus_action_remaining, 0)
        self.assertEqual(self.app.combatants[1].spell_cast_remaining, 1)

        self.app._lan_positions[1] = (0, 0)
        self.app._lan_positions[echo.cid] = (5, 5)
        self.app.combatants[1].bonus_action_remaining = 1
        self.toasts.clear()
        self._apply({"type": "echo_swap"})
        self.assertTrue(any("too far to swap" in text for _ws_id, text in self.toasts))


class EchoKnightRoutingTests(unittest.TestCase):
    def test_lan_controller_action_types_include_echo_actions(self):
        self.assertIn("echo_summon", tracker_mod.LanController._ACTION_MESSAGE_TYPES)
        self.assertIn("echo_swap", tracker_mod.LanController._ACTION_MESSAGE_TYPES)
        self.assertIn("set_facing", tracker_mod.LanController._ACTION_MESSAGE_TYPES)


if __name__ == "__main__":
    unittest.main()
