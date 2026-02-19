import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class DragonLightningImmunityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._log = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Aelar"
        self.app._profile_for_player_name = lambda name: {
            "leveling": {"classes": [{"name": "Fighter", "level": 10, "attacks_per_action": 2}]},
            "attacks": {
                "weapon_to_hit": 5,
                "weapons": [{"id": "longsword", "name": "Longsword", "to_hit": 7}],
            },
        }
        self.app.in_combat = True
        self.app.round_num = 1
        self.app.turn_num = 1
        self.app.current_cid = 1
        self.app.start_cid = None
        self.app._next_id = 1
        self.app._next_stack_id = 1
        self.app._map_window = None
        self.app._monster_specs = []
        self.app._monsters_by_name = {}
        self.app._wild_shape_beast_cache = None
        self.app._wild_shape_available_cache = {}
        self.app._wild_shape_available_cache_source = None
        self.app.combatants = {}
        self.app._name_role_memory = {}
        self.app._lan_positions = {1: (5, 5), 2: (5, 4)}
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, dict(self.app._lan_positions))
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._remove_combatants_with_lan_cleanup = (
            lambda cids: [self.app.combatants.pop(int(cid), None) for cid in cids]
        )
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda *_args, **_kwargs: None,
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

        attacker_cid = self.app._create_combatant(
            name="Aelar",
            hp=30,
            speed=30,
            initiative=15,
            dex=14,
            ally=False,
            is_pc=True,
        )
        attacker = self.app.combatants[attacker_cid]
        attacker.action_remaining = 1
        attacker.reaction_remaining = 1
        attacker.attack_resource_remaining = 0
        attacker.exhaustion_level = 0

        self.app._load_monsters_index()
        dragon_spec = self.app._find_monster_spec_by_slug("adult-bronze-dragon")
        self.assertIsNotNone(dragon_spec)
        self.assertIsInstance(getattr(dragon_spec, "raw_data", None), dict)
        self.assertIn("damage_immunities", dragon_spec.raw_data)

        target_cid = self.app._create_combatant(
            name=dragon_spec.name,
            hp=int(dragon_spec.hp or 212),
            speed=int(dragon_spec.speed or 40),
            swim_speed=int(dragon_spec.swim_speed or 0),
            fly_speed=int(dragon_spec.fly_speed or 0),
            burrow_speed=int(dragon_spec.burrow_speed or 0),
            climb_speed=int(dragon_spec.climb_speed or 0),
            movement_mode="Normal",
            initiative=12,
            dex=dragon_spec.dex,
            ally=True,
            is_pc=False,
            is_spellcaster=None,
            saving_throws=dict(dragon_spec.saving_throws or {}),
            ability_mods=dict(dragon_spec.ability_mods or {}),
            monster_spec=dragon_spec,
        )
        target = self.app.combatants[target_cid]
        target.exhaustion_level = 0

    def _attack_msg(self, entries):
        return {
            "type": "attack_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 1,
            "target_cid": 2,
            "weapon_id": "longsword",
            "hit": True,
            "damage_entries": entries,
        }

    def test_attack_request_lightning_damage_is_zero_for_adult_bronze_dragon(self):
        msg = self._attack_msg([{"amount": 10, "type": "lightning"}])

        instrument = {}
        original_adjust = self.app._adjust_damage_entries_for_target
        original_defense = self.app._combatant_defense_sets

        def wrapped_defense(target_obj):
            result = original_defense(target_obj)
            spec = getattr(target_obj, "monster_spec", None)
            raw_data = getattr(spec, "raw_data", None) if spec is not None else None
            instrument["target_name"] = getattr(target_obj, "name", None)
            instrument["target_type"] = type(target_obj).__name__
            instrument["has_monster_spec"] = bool(spec is not None)
            instrument["raw_data_keys"] = sorted(raw_data.keys()) if isinstance(raw_data, dict) else []
            instrument["damage_immunities"] = sorted(result.get("damage_immunities") or [])
            return result

        def wrapped_adjust(target_obj, damage_entries):
            instrument["incoming_damage_entries"] = [dict(entry) for entry in damage_entries]
            return original_adjust(target_obj, damage_entries)

        with mock.patch.object(self.app, "_combatant_defense_sets", side_effect=wrapped_defense), mock.patch.object(
            self.app, "_adjust_damage_entries_for_target", side_effect=wrapped_adjust
        ):
            self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 0)
        self.assertEqual(result.get("damage_entries"), [])
        self.assertEqual(self.app.combatants[2].hp, 212)

        self.assertEqual(instrument.get("incoming_damage_entries"), [{"amount": 10, "type": "lightning"}])
        self.assertEqual(instrument.get("target_name"), "Adult Bronze Dragon")
        self.assertTrue(instrument.get("has_monster_spec"))
        self.assertIn("damage_immunities", instrument.get("raw_data_keys", []))
        self.assertIn("lightning", instrument.get("damage_immunities", []))

    def test_attack_request_mixed_damage_applies_only_non_immune_component(self):
        msg = self._attack_msg([{"amount": 10, "type": "slashing"}, {"amount": 10, "type": "lightning"}])

        self.app._lan_apply_action(msg)

        result = msg.get("_attack_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 10)
        self.assertEqual(result.get("damage_entries"), [{"amount": 10, "type": "slashing"}])
        self.assertEqual(self.app.combatants[2].hp, 202)


if __name__ == "__main__":
    unittest.main()
