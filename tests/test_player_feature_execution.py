import unittest
from pathlib import Path
from unittest import mock

import yaml

import dnd_initative_tracker as tracker_mod


class PlayerFeatureExecutionTests(unittest.TestCase):
    def _new_app(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._items_registry_payload = lambda: {"weapons": {}}
        return app

    def test_grants_actions_and_reactions_compile_into_resources(self):
        app = self._new_app()
        normalized = app._normalize_player_profile(
            {
                "name": "Tester",
                "resources": {"actions": [], "bonus_actions": [], "reactions": []},
                "features": [
                    {
                        "id": "feature_a",
                        "name": "Feature A",
                        "selection": "sample",
                        "grants": {
                            "actions": [
                                {
                                    "id": "feature_action",
                                    "name": "Feature Action",
                                    "activation": "bonus_action",
                                    "consumes": {"pool": "points", "cost": 1},
                                    "effect": "recover_spell_slot",
                                    "slot_level": 1,
                                }
                            ],
                            "reactions": [{"id": "feature_reaction", "name": "Feature Reaction"}],
                            "modifiers": [{"id": "mod_1", "trigger": "example"}],
                            "damage_riders": [{"id": "rider_1", "trigger": "weapon_attack_hit"}],
                        },
                    }
                ],
            },
            "tester",
        )
        resources = normalized.get("resources") or {}
        bonus_names = {str(entry.get("name") or "") for entry in (resources.get("bonus_actions") or []) if isinstance(entry, dict)}
        reaction_names = {str(entry.get("name") or "") for entry in (resources.get("reactions") or []) if isinstance(entry, dict)}
        self.assertIn("Feature Action", bonus_names)
        self.assertIn("Feature Reaction", reaction_names)
        compiled_bonus = next(
            entry
            for entry in (resources.get("bonus_actions") or [])
            if isinstance(entry, dict) and str(entry.get("name") or "") == "Feature Action"
        )
        self.assertEqual((compiled_bonus.get("uses") or {}).get("pool"), "points")
        effects = normalized.get("feature_effects") or {}
        self.assertTrue(any(str(entry.get("id") or "") == "mod_1" for entry in (effects.get("modifiers") or [])))
        self.assertTrue(any(str(entry.get("id") or "") == "rider_1" for entry in (effects.get("damage_riders") or [])))


    def test_grants_actions_support_type_and_uses_fields(self):
        app = self._new_app()
        normalized = app._normalize_player_profile(
            {
                "name": "Tester",
                "resources": {"actions": [], "bonus_actions": [], "reactions": []},
                "features": [
                    {
                        "id": "feature_type_uses",
                        "name": "Feature Type Uses",
                        "grants": {
                            "actions": [
                                {
                                    "id": "feature_bonus_action",
                                    "name": "Feature Bonus Action",
                                    "type": "bonus_action",
                                    "uses": {"pool": "points", "cost": 1},
                                }
                            ]
                        },
                    }
                ],
            },
            "tester",
        )
        resources = normalized.get("resources") or {}
        compiled_bonus = next(
            entry
            for entry in (resources.get("bonus_actions") or [])
            if isinstance(entry, dict) and str(entry.get("name") or "") == "Feature Bonus Action"
        )
        self.assertEqual((compiled_bonus.get("uses") or {}).get("pool"), "points")

    def test_attuned_magic_item_actions_compile_even_when_slots_overfilled(self):
        app = self._new_app()
        tyrs_circlet = yaml.safe_load(Path("Items/Magic_Items/tyrs_circlet.yaml").read_text(encoding="utf-8"))
        app._magic_items_registry_payload = lambda: {"tyrs_circlet": tyrs_circlet}
        normalized = app._normalize_player_profile(
            {
                "name": "Dorian",
                "resources": {"actions": [], "bonus_actions": [], "reactions": []},
                "magic_items": {
                    "attunement_slots": 3,
                    "equipped": ["item_a", "item_b", "item_c", "tyrs_circlet"],
                    "attuned": ["item_a", "item_b", "item_c", "tyrs_circlet"],
                },
            },
            "dorian",
        )
        resources = normalized.get("resources") or {}
        compiled_bonus = next(
            entry
            for entry in (resources.get("bonus_actions") or [])
            if isinstance(entry, dict) and str(entry.get("name") or "") == "Activate Blessed by Tyr"
        )
        self.assertEqual((compiled_bonus.get("uses") or {}).get("pool"), "tyrs_circlet_blessing")

    def test_recover_spell_slots_handler_respects_budget_and_caps(self):
        app = self._new_app()
        saved = {}
        app._save_player_spell_slots = lambda name, payload: saved.setdefault("slots", payload)
        profile = {
            "name": "Eldramar",
            "leveling": {"classes": [{"name": "Wizard", "level": 10}], "level": 10},
            "spellcasting": {
                "spell_slots": {
                    "1": {"max": 4, "current": 4},
                    "2": {"max": 3, "current": 2},
                    "3": {"max": 3, "current": 1},
                    "4": {"max": 3, "current": 3},
                    "5": {"max": 2, "current": 2},
                }
            },
        }
        ok, err, recovered = app._recover_spell_slots(
            "Eldramar",
            profile,
            {"max_combined_level_formula": "ceil(wizard_level / 2)", "max_slot_level": 5},
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(sum(recovered), 5)
        self.assertEqual((saved["slots"]["3"] or {}).get("current"), 2)
        self.assertEqual((saved["slots"]["2"] or {}).get("current"), 3)

    def test_once_per_turn_limiter_blocks_second_use_same_turn(self):
        app = self._new_app()
        app.round_num = 2
        app.turn_num = 3
        self.assertTrue(app._once_per_turn_limiter_allows(7, "sneak_attack"))
        app._once_per_turn_limiter_mark(7, "sneak_attack")
        self.assertFalse(app._once_per_turn_limiter_allows(7, "sneak_attack"))
        app.turn_num = 4
        self.assertTrue(app._once_per_turn_limiter_allows(7, "sneak_attack"))

    def test_rage_lifecycle_ends_on_turn_boundary_without_maintenance(self):
        app = self._new_app()
        logs = []
        toasts = []
        app._log = lambda message, cid=None: logs.append((cid, message))
        app._is_admin_token_valid = lambda token: False
        app._summon_can_be_controlled_by = lambda claimed, target: False
        app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        app._mount_action_is_restricted = lambda c, action_name: False
        app._consume_resource_pool_for_cast = lambda caster_name, pool_id, cost: (True, "")
        app._rebuild_table = lambda scroll_to_current=True: None
        app._lan = type(
            "LanStub",
            (),
            {"toast": lambda _self, ws_id, message: toasts.append((ws_id, message)), "_append_lan_log": lambda *args, **kwargs: None, "_loop": None},
        )()
        app.combatants = {
            5: type(
                "C",
                (),
                {
                    "cid": 5,
                    "name": "Malagrou",
                    "bonus_action_remaining": 1,
                    "action_remaining": 1,
                    "reaction_remaining": 1,
                    "condition_stacks": [],
                    "bonus_actions": [{"name": "Rage", "type": "bonus_action"}],
                    "actions": [],
                    "reactions": [],
                    "end_turn_damage_riders": [],
                },
            )()
        }
        app.round_num = 1
        app.turn_num = 1
        app.current_cid = 5
        app.in_combat = True
        app.start_cid = None
        app._lan_apply_action({"type": "perform_action", "cid": 5, "_claimed_cid": 5, "_ws_id": 9, "spend": "bonus", "action": "Rage"})
        combatant = app.combatants[5]
        self.assertTrue(getattr(combatant, "rage_active", False))
        self.assertTrue(any(getattr(st, "ctype", "") == "rage" for st in combatant.condition_stacks))
        with mock.patch.object(tracker_mod.base.InitiativeTracker, "_end_turn_cleanup", lambda *args, **kwargs: None):
            app._end_turn_cleanup(5)
        self.assertFalse(getattr(combatant, "rage_active", False))
        self.assertFalse(any(getattr(st, "ctype", "") == "rage" for st in combatant.condition_stacks))
        self.assertTrue(any("Rage ends" in msg for _cid, msg in logs))

    def test_real_johnny_yaml_compiles_feature_actions_and_effects(self):
        app = self._new_app()
        data = yaml.safe_load(
            Path("players/johnny_morris.yaml").read_text(encoding="utf-8")
        )
        normalized = app._normalize_player_profile(data, "johnny_morris")
        resources = normalized.get("resources") or {}
        action_names = {str(entry.get("name") or "") for entry in (resources.get("actions") or []) if isinstance(entry, dict)}
        self.assertIn("Wild Companion", action_names)
        self.assertIn("Natural Recovery (Recover Spell Slots)", action_names)
        pools = {str(entry.get("id") or "") for entry in (resources.get("pools") or []) if isinstance(entry, dict)}
        self.assertIn("wand_of_fireballs_fireball_cast", pools)
        cantrips = (((normalized.get("spellcasting") or {}).get("cantrips") or {}).get("known") or [])
        self.assertIn("fire-bolt", cantrips)
        pool_spells = app._player_pool_granted_spells(normalized)
        self.assertTrue(any(str(entry.get("spell") or "") == "fireball" and str((entry.get("consumes_pool") or {}).get("id") or "") == "wand_of_fireballs_fireball_cast" for entry in pool_spells))
        effects = normalized.get("feature_effects") or {}
        rider_ids = {str(entry.get("id") or "") for entry in (effects.get("damage_riders") or []) if isinstance(entry, dict)}
        self.assertIn("elemental_fury_primal_strike", rider_ids)


if __name__ == "__main__":
    unittest.main()
