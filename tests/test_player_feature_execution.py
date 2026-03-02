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

    def test_magic_item_ability_override_and_defenses_apply_on_normalize(self):
        app = self._new_app()
        app._magic_items_registry_payload = lambda: {
            "gauntlets_of_lesser_hill_giant_strength": {
                "id": "gauntlets_of_lesser_hill_giant_strength",
                "requires_attunement": True,
                "grants": {"ability_overrides": {"str": 17}},
            },
            "grom": {
                "id": "grom",
                "requires_attunement": True,
                "grants": {
                    "defenses": {"damage_resistances": ["lightning"]},
                    "save_bonuses": {"con": 1},
                },
            },
        }
        normalized = app._normalize_player_profile(
            {
                "name": "стихия",
                "abilities": {"str": 10, "con": 16},
                "defenses": {"resistances": []},
                "magic_items": {
                    "attunement_slots": 3,
                    "equipped": ["gauntlets_of_lesser_hill_giant_strength", "grom"],
                    "attuned": ["gauntlets_of_lesser_hill_giant_strength", "grom"],
                },
            },
            "stikhiya",
        )
        self.assertEqual(int((normalized.get("abilities") or {}).get("str") or 0), 17)
        self.assertIn("lightning", (normalized.get("defenses") or {}).get("resistances") or [])
        self.assertEqual(int(((normalized.get("defenses") or {}).get("save_bonuses") or {}).get("con") or 0), 1)

    def test_magic_item_spell_save_dc_bonus_applies(self):
        app = self._new_app()
        app._magic_items_registry_payload = lambda: {
            "matteh": {
                "id": "matteh",
                "requires_attunement": True,
                "grants": {
                    "modifiers": [
                        {"id": "matteh_spell_save_dc_bonus", "target": "spell_save_dc", "effect": "spell_save_dc_bonus", "amount": 1}
                    ]
                },
            }
        }
        normalized = app._normalize_player_profile(
            {
                "name": "Johnny",
                "abilities": {"wis": 18},
                "proficiency": {"bonus": 4},
                "spellcasting": {"casting_ability": "wis", "save_dc_formula": "8 + prof + casting_mod"},
                "magic_items": {
                    "attunement_slots": 3,
                    "equipped": ["matteh"],
                    "attuned": ["matteh"],
                },
            },
            "johnny",
        )
        self.assertEqual(app._compute_spell_save_dc(normalized), 17)

    def test_requires_attunement_magic_item_does_not_apply_when_not_attuned(self):
        app = self._new_app()
        app._magic_items_registry_payload = lambda: {
            "gauntlets_of_strength": {
                "id": "gauntlets_of_strength",
                "requires_attunement": True,
                "grants": {"ability_overrides": {"str": 19}},
            }
        }
        normalized = app._normalize_player_profile(
            {
                "name": "Dorian",
                "abilities": {"str": 12},
                "magic_items": {
                    "equipped": ["gauntlets_of_strength"],
                    "attuned": [],
                },
            },
            "dorian",
        )
        self.assertEqual(int((normalized.get("abilities") or {}).get("str") or 0), 12)

    def test_nature_speaker_necklace_pool_spell_requires_equipped_and_attuned(self):
        app = self._new_app()
        necklace_path = Path("Items/Magic_Items/nature_speaker_necklace.yaml")
        self.assertTrue(necklace_path.exists(), "Expected magic item YAML missing: nature_speaker_necklace.yaml")
        necklace = yaml.safe_load(necklace_path.read_text(encoding="utf-8"))
        app._magic_items_registry_payload = lambda: {"nature_speaker_necklace": necklace}
        base_profile = {
            "name": "Johnny",
            "resources": {
                "pools": [
                    {
                        "id": "nature_speaker_necklace_speak_with_plants",
                        "label": "Nature Speaker Necklace (Speak with Plants)",
                        "current": 1,
                        "max_formula": "1",
                        "reset": "long_rest",
                    }
                ]
            },
        }
        equipped_attuned = {
            **base_profile,
            "magic_items": {"equipped": ["nature_speaker_necklace"], "attuned": ["nature_speaker_necklace"]},
        }
        spells = app._player_pool_granted_spells(equipped_attuned)
        self.assertTrue(any(str(entry.get("spell") or "") == "speak-with-plants" for entry in spells))

        equipped_not_attuned = {
            **base_profile,
            "magic_items": {"equipped": ["nature_speaker_necklace"], "attuned": []},
        }
        blocked_spells = app._player_pool_granted_spells(equipped_not_attuned)
        self.assertFalse(any(str(entry.get("spell") or "") == "speak-with-plants" for entry in blocked_spells))

    def test_big_ass_axe_plus_1_resolves_damage_and_magic_bonus_from_item_yaml(self):
        app = self._new_app()
        axe_path = Path("Items/Magic_Items/big_ass_axe_plus_1.yaml")
        self.assertTrue(axe_path.exists(), "Expected magic item YAML missing: big_ass_axe_plus_1.yaml")
        item_data = yaml.safe_load(axe_path.read_text(encoding="utf-8"))
        app._items_registry_payload = lambda: {"weapons": {"big_ass_axe_plus_1": item_data}}
        normalized = app._normalize_player_profile(
            {
                "name": "Malagrou",
                "abilities": {"str": 18},
                "attacks": {"weapons": [{"id": "big_ass_axe_plus_1"}]},
            },
            "malagrou",
        )
        weapons = ((normalized.get("attacks") or {}).get("weapons") or [])
        self.assertEqual(len(weapons), 1)
        weapon = weapons[0]
        self.assertEqual(str(weapon.get("name") or ""), "Big Ass Axe +1")
        self.assertEqual(int(weapon.get("magic_bonus") or 0), 1)
        self.assertEqual(str(((weapon.get("one_handed") or {}).get("damage_formula") or "")), "2d12 + 1 + str_mod")

    def test_magic_item_with_empty_grants_is_ignored_without_errors(self):
        app = self._new_app()
        app._magic_items_registry_payload = lambda: {
            "evil_eye": {"id": "evil_eye", "requires_attunement": True}
        }
        normalized = app._normalize_player_profile(
            {
                "name": "Vicnor",
                "features": [],
                "magic_items": {"equipped": ["evil_eye"], "attuned": ["evil_eye"]},
            },
            "vicnor",
        )
        self.assertEqual(normalized.get("features"), [])

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
