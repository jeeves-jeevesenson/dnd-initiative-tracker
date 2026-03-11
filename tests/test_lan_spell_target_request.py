import unittest
from unittest import mock
from pathlib import Path

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
        self.app._reaction_prefs_by_cid = {}
        self.app._lan_aoes = {}
        self.app.start_cid = None
        self.app.current_cid = 1
        self.app._map_window = None
        self.app._lan_grid_cols = 20
        self.app._lan_grid_rows = 20
        self.app._lan_obstacles = set()
        self.app._lan_rough_terrain = {}
        self.app._lan_positions = {1: (4, 4), 2: (6, 4), 3: (8, 4)}
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
            "damage_dice": "1d12",
            "damage_type": "necrotic",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=15):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 0)
        self.assertFalse(result.get("hit"))
        self.assertTrue(result.get("save_result", {}).get("passed"))
        self.assertEqual(self.app.combatants[2].hp, 20)


    def test_save_spell_log_includes_ability_total_and_dc(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 24,
            "target_cid": 2,
            "spell_name": "Toll the Dead",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 13,
            "roll_save": True,
            "damage_dice": "1d12",
            "damage_type": "necrotic",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=15):
            self.app._lan_apply_action(msg)

        save_logs = [entry for _cid, entry in self.logs if "save against Toll the Dead" in entry]
        self.assertTrue(save_logs)
        self.assertTrue(any("succeeds" in entry for entry in save_logs))
        self.assertTrue(any("WIS" in entry for entry in save_logs))
        self.assertTrue(any("vs DC 13" in entry for entry in save_logs))

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
            "damage_dice": "1d12",
            "damage_type": "necrotic",
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
        self.assertIn((11, "Fire Bolt hits: 9 damage (9 fire)."), self.toasts)


    def test_spell_target_request_toast_includes_beam_label_for_multi_projectile(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 2,
            "spell_name": "Eldritch Blast",
            "spell_mode": "attack",
            "hit": True,
            "damage_entries": [{"amount": 7, "type": "force"}],
            "shot_index": 2,
            "shot_total": 3,
        }

        self.app._lan_apply_action(msg)

        self.assertIn((31, "Beam 2/3: Eldritch Blast hits: 7 damage (7 force)."), self.toasts)

    def test_format_single_target_spell_outcome_save_toast_includes_damage_and_adjustment_notes(self):
        detail = self.app._format_single_target_spell_outcome(
            {
                "spell_name": "Sacred Flame",
                "target_name": "Goblin",
                "spell_mode": "save",
                "save_result": {"ability": "dex", "dc": 14, "total": 8, "passed": False},
                "damage_entries": [{"amount": 3, "type": "radiant"}],
                "damage_total": 3,
                "damage_adjustment_notes": [{"type": "radiant", "original": 6, "applied": 3, "reasons": ["resistance"]}],
            }
        )

        self.assertEqual(
            detail["toast"],
            "Sacred Flame: Goblin failed DEX save (8 vs DC 14), takes 3 damage (3 radiant) [radiant 6→3 (resistance)].",
        )

    def test_format_single_target_spell_outcome_effect_fallback_is_explicit(self):
        detail = self.app._format_single_target_spell_outcome(
            {
                "spell_name": "Haste",
                "target_name": "Borin",
                "spell_mode": "effect",
                "hit": True,
            }
        )

        self.assertEqual(detail["log"], "Haste applied to Borin.")
        self.assertEqual(detail["toast"], "Haste applied to Borin.")

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

    def test_spell_target_request_invalid_manual_damage_falls_back_to_auto_roll(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 17,
            "target_cid": 2,
            "spell_name": "Ray of Frost",
            "spell_mode": "attack",
            "hit": True,
            "damage_entries": [{"amount": "10f", "type": "cold"}],
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

    def test_spell_target_request_scales_cantrip_damage_dice_from_character_level(self):
        self.app._profile_for_player_name = lambda _name: {"leveling": {"level": 5}}
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "shocking-grasp",
            "id": "shocking-grasp",
            "name": "Shocking Grasp",
            "scaling": {
                "kind": "character_level",
                "thresholds": {
                    "5": {"add": "1d8"},
                    "11": {"add": "1d8"},
                    "17": {"add": "1d8"},
                },
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 30,
            "target_cid": 2,
            "spell_name": "Shocking Grasp",
            "spell_slug": "shocking-grasp",
            "spell_mode": "attack",
            "hit": True,
            "critical": False,
            "damage_entries": [],
            "damage_dice": "1d8",
            "damage_type": "lightning",
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[3, 4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_entries"), [{"amount": 7, "type": "lightning"}])
        self.assertEqual(result.get("damage_total"), 7)
        self.assertEqual(self.app.combatants[2].hp, 13)


    def test_spell_target_request_allows_claim_swap_with_prompt_attacker_override_on_attack(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "prompt_attacker_cid": 1,
            "_claimed_cid": 3,
            "_ws_id": 31,
            "target_cid": 2,
            "spell_name": "Eldritch Blast",
            "spell_slug": "eldritch-blast",
            "spell_mode": "attack",
            "hit": True,
            "damage_entries": [{"amount": 7, "type": "force"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("attacker_cid"), 1)
        self.assertEqual(self.app.combatants[2].hp, 13)

    def test_spell_target_request_uses_preset_dice_when_damage_dice_blank(self):
        self.app._profile_for_player_name = lambda _name: {"leveling": {"level": 5}}
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "shocking-grasp",
            "id": "shocking-grasp",
            "name": "Shocking Grasp",
            "dice": "1d8",
            "damage_types": ["lightning"],
            "scaling": {
                "kind": "character_level",
                "thresholds": {
                    "5": {"add": "1d8"},
                    "11": {"add": "1d8"},
                    "17": {"add": "1d8"},
                },
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 33,
            "target_cid": 2,
            "spell_name": "Shocking Grasp",
            "spell_slug": "shocking-grasp",
            "spell_mode": "attack",
            "hit": True,
            "critical": False,
            "damage_entries": [],
            "damage_dice": "",
            "damage_type": "",
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[3, 4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_entries"), [{"amount": 7, "type": "lightning"}])
        self.assertEqual(result.get("damage_total"), 7)
        self.assertEqual(self.app.combatants[2].hp, 13)

    def test_spell_target_request_scales_cantrip_damage_dice_for_critical(self):
        self.app._profile_for_player_name = lambda _name: {"leveling": {"level": 17}}
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "shocking-grasp",
            "id": "shocking-grasp",
            "name": "Shocking Grasp",
            "scaling": {
                "kind": "character_level",
                "thresholds": {
                    "5": {"add": "1d8"},
                    "11": {"add": "1d8"},
                    "17": {"add": "1d8"},
                },
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 2,
            "spell_name": "Shocking Grasp",
            "spell_slug": "shocking-grasp",
            "spell_mode": "attack",
            "hit": True,
            "critical": True,
            "damage_entries": [],
            "damage_dice": "1d8",
            "damage_type": "lightning",
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_entries"), [{"amount": 32, "type": "lightning"}])
        self.assertEqual(result.get("damage_total"), 32)

    def test_spell_target_request_scales_cantrip_damage_when_thresholds_use_totals(self):
        self.app._profile_for_player_name = lambda _name: {"leveling": {"level": 11}}
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "acid-splash",
            "id": "acid-splash",
            "name": "Acid Splash",
            "scaling": {
                "kind": "character_level",
                "thresholds": {
                    "5": {"add": "2d6"},
                    "11": {"add": "3d6"},
                    "17": {"add": "4d6"},
                },
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 32,
            "target_cid": 2,
            "spell_name": "Acid Splash",
            "spell_slug": "acid-splash",
            "spell_mode": "attack",
            "hit": True,
            "critical": False,
            "damage_entries": [],
            "damage_dice": "1d6",
            "damage_type": "acid",
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 2, 2]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_entries"), [{"amount": 6, "type": "acid"}])
        self.assertEqual(result.get("damage_total"), 6)

    def test_polymorph_save_fail_requires_form_selection(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "polymorph",
            "id": "polymorph",
            "name": "Polymorph",
        }
        self.app._wild_shape_beast_cache = [
            {"id": "wolf", "name": "Wolf", "hp": 11, "challenge_rating": 0.25}
        ]
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 20,
            "target_cid": 2,
            "spell_name": "Polymorph",
            "spell_slug": "polymorph",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 16,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertTrue(result.get("needs_polymorph_form"))
        self.assertEqual(result.get("beast_forms"), self.app._wild_shape_beast_cache)

    def test_polymorph_save_fail_applies_selected_form_temp_hp(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "polymorph",
            "id": "polymorph",
            "name": "Polymorph",
        }
        self.app._wild_shape_beast_cache = [
            {"id": "wolf", "name": "Wolf", "hp": 11, "challenge_rating": 0.25}
        ]
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 21,
            "target_cid": 2,
            "spell_name": "Polymorph",
            "spell_slug": "polymorph",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 16,
            "roll_save": True,
            "polymorph_form_id": "wolf",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertEqual(result.get("polymorph_form", {}).get("id"), "wolf")
        self.assertEqual(self.app.combatants[2].temp_hp, 11)
        self.assertEqual(getattr(self.app.combatants[2], "wild_shape_form_name", ""), "Wolf")
        self.assertEqual(self.app.combatants[2].name, "Wolf")
        self.assertFalse(bool(getattr(self.app.combatants[2], "is_spellcaster", False)))


    def test_polymorph_replaces_stats_and_reverts_when_temp_hp_depleted(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "polymorph",
            "id": "polymorph",
            "name": "Polymorph",
        }
        self.app._wild_shape_beast_cache = [
            {
                "id": "wolf",
                "name": "Wolf",
                "hp": 11,
                "challenge_rating": 0.25,
                "speed": {"walk": 40, "swim": 0, "fly": 0, "climb": 0},
                "abilities": {"str": 12, "dex": 15, "con": 12, "int": 3, "wis": 12, "cha": 6},
                "saving_throws": {"dex": 4, "wis": 2},
                "actions": [
                    {
                        "name": "Bite",
                        "description": "Melee Attack Roll: +4, reach 5 ft. Hit: 7 (2d4 + 2) piercing damage.",
                    }
                ],
            }
        ]
        target = self.app.combatants[2]
        target.name = "Black Bear 1"
        target.is_spellcaster = True
        target.str = 18
        target.dex = 10
        target.con = 16
        target.int = 7
        target.wis = 8
        target.cha = 9
        target.speed = 30
        target.saving_throws = {"wis": 1}
        target.ability_mods = {"str": 4, "dex": 0, "con": 3, "int": -2, "wis": -1, "cha": -1}
        target.monster_slug = "black-bear"

        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 2,
            "spell_name": "Polymorph",
            "spell_slug": "polymorph",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 16,
            "roll_save": True,
            "polymorph_form_id": "wolf",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        self.assertEqual(target.name, "Wolf")
        self.assertEqual(target.speed, 40)
        self.assertEqual(target.str, 12)
        self.assertEqual(target.int, 3)
        self.assertEqual(target.ability_mods.get("int"), -4)
        self.assertEqual(target.saving_throws.get("dex"), 4)
        self.assertEqual(target.monster_slug, "wolf")

        self.app._apply_damage_to_target_with_temp_hp(target, 11)

        self.assertEqual(target.name, "Black Bear 1")
        self.assertEqual(target.speed, 30)
        self.assertEqual(target.str, 18)
        self.assertEqual(target.int, 7)
        self.assertEqual(target.saving_throws.get("wis"), 1)
        self.assertEqual(target.monster_slug, "black-bear")




    def test_polymorph_reverts_when_temp_hp_is_manually_set_to_zero(self):
        target = self.app.combatants[2]
        target.name = "Black Bear 1"
        target.temp_hp = 11
        target.polymorph_source_cid = 1
        target.wild_shape_form_name = "Wolf"
        target.wild_shape_form_id = "wolf"
        target.polymorph_base = {
            "name": "Black Bear 1",
            "speed": 30,
            "swim_speed": 0,
            "fly_speed": 0,
            "climb_speed": 0,
            "burrow_speed": 0,
            "movement_mode": "Normal",
            "str": 18,
            "dex": 10,
            "con": 16,
            "int": 7,
            "wis": 8,
            "cha": 9,
            "is_spellcaster": True,
            "ability_mods": {"str": 4},
            "saving_throws": {"wis": 1},
            "actions": [],
            "monster_slug": "black-bear",
        }

        self.app._set_temp_hp(2, 0)

        self.assertEqual(target.name, "Black Bear 1")
        self.assertEqual(target.temp_hp, 0)
        self.assertEqual(getattr(target, "wild_shape_form_name", ""), "")
        self.assertIsNone(getattr(target, "polymorph_source_cid", None))

    def test_polymorph_defaults_to_save_mode_and_wisdom(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "polymorph",
            "id": "polymorph",
            "name": "Polymorph",
            "tags": ["save"],
            "duration": "Concentration, up to 1 hour",
            "level": 4,
            "import": {"raw": {"description": "The target must succeed on a Wisdom saving throw."}},
        }
        self.app._wild_shape_beast_cache = [
            {"id": "wolf", "name": "Wolf", "hp": 11, "challenge_rating": 0.25}
        ]
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 22,
            "target_cid": 2,
            "spell_name": "Polymorph",
            "spell_slug": "polymorph",
            "spell_mode": "attack",
            "save_dc": 16,
            "polymorph_form_id": "wolf",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertEqual(result.get("spell_mode"), "save")
        self.assertFalse(result.get("save_result", {}).get("passed"))
        self.assertEqual(result.get("save_result", {}).get("ability"), "wis")
        self.assertEqual(result.get("polymorph_duration_turns"), 600)
        self.assertEqual(getattr(self.app.combatants[1], "concentration_spell", ""), "polymorph")



    def test_spell_target_request_rejects_summon_spell_payload(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "find-steed",
            "id": "find-steed",
            "name": "Find Steed",
            "summon": {"choices": [{"monster_slug": "otherworldly-steed"}]},
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 51,
            "target_cid": 1,
            "spell_name": "Find Steed",
            "spell_slug": "find-steed",
            "spell_mode": "attack",
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("ok"))
        self.assertIn("summon placement", result.get("reason", "").lower())
        self.assertIn((51, "That summon spell must be cast via summon placement, matey."), self.toasts)
        self.assertFalse(any("resolves Find Steed" in entry for _, entry in self.logs))

    def test_spell_target_request_rejects_relocation_destination_for_non_relocation_spell(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "haste",
            "id": "haste",
            "name": "Haste",
            "mechanics": {"sequence": []},
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 52,
            "target_cid": 1,
            "spell_name": "Haste",
            "spell_slug": "haste",
            "spell_mode": "attack",
            "destination_col": 8,
            "destination_row": 9,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("ok"))
        self.assertIn("relocation destination", result.get("reason", "").lower())
        self.assertIn((52, "That spell can't accept a relocation destination."), self.toasts)

    def test_save_tagged_spell_coerces_attack_payload_to_save(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "hold-person",
            "id": "hold-person",
            "name": "Hold Person",
            "tags": ["save"],
            "import": {"raw": {"description": "A humanoid must make a Wisdom saving throw."}},
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 23,
            "target_cid": 2,
            "spell_name": "Hold Person",
            "spell_slug": "hold-person",
            "spell_mode": "attack",
            "save_dc": 16,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertEqual(result.get("spell_mode"), "save")
        self.assertEqual(result.get("save_result", {}).get("ability"), "wis")
        self.assertFalse(result.get("save_result", {}).get("passed"))

    def test_save_tagged_spell_coercion_uses_caster_spell_dc_when_missing(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "hold-person",
            "id": "hold-person",
            "name": "Hold Person",
            "tags": ["save"],
            "import": {"raw": {"description": "The target must succeed on a Wisdom saving throw."}},
        }
        self.app._pc_name_for = lambda cid: "Aelar"
        self.app._profile_for_player_name = lambda name: {
            "spellcasting": {"save_dc_formula": "8 + prof + wis_mod", "casting_ability": "wis"},
            "abilities": {"wis": 18},
            "leveling": {"level": 5},
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 26,
            "target_cid": 2,
            "spell_name": "Hold Person",
            "spell_slug": "hold-person",
            "spell_mode": "attack",
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertEqual(result.get("spell_mode"), "save")
        self.assertEqual(result.get("save_result", {}).get("dc"), 15)
        self.assertFalse(result.get("save_result", {}).get("passed"))
        self.assertFalse(any("misses" in message.lower() for _, message in self.logs))
        self.assertTrue(any("fails their WIS save against Hold Person" in message for _, message in self.logs))

    def test_polymorph_temp_hp_depletion_reverts_form_via_legacy_damage_helper(self):
        target = self.app.combatants[2]
        target.hp = 20
        target.temp_hp = 5
        target.wild_shape_form_id = "wolf"
        target.wild_shape_form_name = "Wolf"
        target.polymorph_source_cid = 1
        target.polymorph_remaining_turns = 10

        state = self.app._apply_damage_to_combatant(target, 7)

        self.assertEqual(state.get("temp_absorbed"), 5)
        self.assertEqual(target.hp, 18)
        self.assertEqual(target.temp_hp, 0)
        self.assertEqual(getattr(target, "wild_shape_form_name", ""), "")
        self.assertIsNone(getattr(target, "polymorph_source_cid", None))

    def test_polymorph_temp_hp_depletion_reverts_form(self):
        target = self.app.combatants[2]
        target.hp = 20
        target.temp_hp = 5
        target.wild_shape_form_id = "wolf"
        target.wild_shape_form_name = "Wolf"
        target.polymorph_source_cid = 1
        target.polymorph_remaining_turns = 10

        state = self.app._apply_damage_to_target_with_temp_hp(target, 7)

        self.assertEqual(state.get("temp_absorbed"), 5)
        self.assertEqual(target.hp, 18)
        self.assertEqual(target.temp_hp, 0)
        self.assertEqual(getattr(target, "wild_shape_form_name", ""), "")
        self.assertIsNone(getattr(target, "polymorph_source_cid", None))

    def test_damage_consumes_temp_hp_before_main_hp_when_fully_absorbed(self):
        target = self.app.combatants[2]
        target.hp = 10
        target.temp_hp = 6

        state = self.app._apply_damage_to_target_with_temp_hp(target, 6)

        self.assertEqual(state.get("temp_absorbed"), 6)
        self.assertEqual(state.get("hp_damage"), 0)
        self.assertEqual(target.hp, 10)
        self.assertEqual(target.temp_hp, 0)

    def test_damage_overflow_spills_from_temp_hp_into_main_hp(self):
        target = self.app.combatants[2]
        target.hp = 10
        target.temp_hp = 10

        state = self.app._apply_damage_to_target_with_temp_hp(target, 15)

        self.assertEqual(state.get("temp_absorbed"), 10)
        self.assertEqual(state.get("hp_damage"), 5)
        self.assertEqual(target.hp, 5)
        self.assertEqual(target.temp_hp, 0)
    def test_haste_spell_target_request_applies_buffs_and_concentration(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "haste",
            "id": "haste",
            "name": "Haste",
            "level": 3,
            "concentration": True,
            "mechanics": {
                "ui": {"spell_targeting": {"duration_turns": 10, "ac_bonus": 2}},
                "sequence": [{"check": {"kind": "auto_hit"}, "outcomes": {"hit": [{"effect": "condition", "condition": "hasted", "duration_turns": 0, "ongoing": {"concentration_bound": True, "clear_group": "haste_{source_cid}_{target_cid}", "adapter": "haste", "modifiers": {"ac_bonus": 2, "speed_multiplier": 2, "save_advantage_by_ability": ["dex"]}, "turn_state": {"extra_action_profile": "haste_limited"}}}]}}],
            },
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
        self.assertEqual(target.ac, 16)
        self.assertEqual(self.app._combatant_ac_modifier(target), 2)
        self.assertEqual(getattr(target, "haste_remaining_turns", 0), 10)
        self.assertTrue(
            any(
                str(entry.get("spell_key") or "") == "haste"
                for entry in list(getattr(target, "ongoing_spell_effects", []) or [])
                if isinstance(entry, dict)
            )
        )
        skip, _, _ = self.app._process_start_of_turn(target)
        self.assertFalse(skip)
        self.assertEqual(target.action_remaining, 2)
        self.assertEqual(target.move_total, 60)
        self.assertEqual(self.app._combatant_extra_action_profile(target), "haste_limited")
        self.assertEqual(self.app._combatant_action_restrictions(target), set())
        self.app._end_turn_cleanup(target.cid)
        self.assertEqual(getattr(target, "haste_remaining_turns", 0), 9)

    def test_haste_breaking_concentration_applies_lethargy(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "haste",
            "id": "haste",
            "name": "Haste",
            "level": 3,
            "concentration": True,
            "mechanics": {
                "ui": {"spell_targeting": {"duration_turns": 10, "ac_bonus": 2}},
                "sequence": [{"check": {"kind": "auto_hit"}, "outcomes": {"hit": [{"effect": "condition", "condition": "hasted", "duration_turns": 0, "ongoing": {"concentration_bound": True, "clear_group": "haste_{source_cid}_{target_cid}", "adapter": "haste", "modifiers": {"ac_bonus": 2, "speed_multiplier": 2, "save_advantage_by_ability": ["dex"]}, "turn_state": {"extra_action_profile": "haste_limited"}}}]}}],
            },
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
        self.assertEqual(list(getattr(target, "ongoing_spell_effects", []) or []), [])
        self.assertEqual(target.ac, 16)
        self.assertEqual(getattr(target, "haste_lethargy_turns_remaining", 0), 1)
        self.assertEqual(self.app._effective_speed(target), 0)
        incapacitated = [st for st in target.condition_stacks if getattr(st, "ctype", "") == "incapacitated"]
        self.assertEqual(len(incapacitated), 1)
        self.assertEqual(incapacitated[0].remaining_turns, 1)


    def test_greater_invisibility_registers_ongoing_effect_and_clears_on_concentration_end(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "greater-invisibility",
            "id": "greater-invisibility",
            "name": "Greater Invisibility",
            "level": 4,
            "concentration": True,
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "effect"},
                        "outcomes": {
                            "hit": [
                                {
                                    "effect": "condition",
                                    "condition": "invisible",
                                    "duration_turns": 0,
                                    "ongoing": {
                                        "concentration_bound": True,
                                        "clear_group": "greater_invisibility_{source_cid}_{target_cid}",
                                        "condition_clear": ["invisible"],
                                    },
                                }
                            ]
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 3,
            "spell_name": "Greater Invisibility",
            "spell_slug": "greater-invisibility",
            "spell_mode": "effect",
            "hit": True,
        }

        self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        target = self.app.combatants[3]
        self.assertTrue(any(getattr(st, "ctype", "") == "invisible" for st in target.condition_stacks))
        self.assertTrue(
            any(
                str(entry.get("spell_key") or "") == "greater-invisibility"
                for entry in list(getattr(target, "ongoing_spell_effects", []) or [])
                if isinstance(entry, dict)
            )
        )

        self.app._end_concentration(caster)

        self.assertFalse(any(getattr(st, "ctype", "") == "invisible" for st in target.condition_stacks))
        self.assertEqual(list(getattr(target, "ongoing_spell_effects", []) or []), [])

    def test_spell_target_request_save_fail_without_damage_intent_has_no_prompt(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 17,
            "target_cid": 2,
            "spell_name": "Hold Person",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 16,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("save_result", {}).get("passed"))
        self.assertFalse(result.get("needs_damage_prompt", False))
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 0)

    def test_spell_target_request_effect_mode_logs_without_hp_change(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "bless",
            "id": "bless",
            "name": "Bless",
            "level": 1,
            "concentration": True,
        }
        start_hp = self.app.combatants[3].hp
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 18,
            "target_cid": 3,
            "spell_name": "Bless",
            "spell_slug": "bless",
            "spell_mode": "effect",
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("spell_mode"), "effect")
        self.assertEqual(self.app.combatants[3].hp, start_hp)
        self.assertTrue(any("targets Borin with Bless" in message for _, message in self.logs))
        self.assertFalse(any("hits" in message.lower() or "misses" in message.lower() for _, message in self.logs))

    def test_spell_target_request_applies_movement_from_hit_outcome(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "thorn-whip",
            "id": "thorn-whip",
            "name": "Thorn Whip",
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "spell_attack", "attack_type": "melee"},
                        "outcomes": {
                            "hit": [
                                {"effect": "movement", "kind": "pull", "distance_ft": 10, "origin": "caster"}
                            ],
                            "miss": [],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 19,
            "target_cid": 2,
            "spell_name": "Thorn Whip",
            "spell_slug": "thorn-whip",
            "spell_mode": "attack",
            "hit": True,
        }

        with mock.patch.object(self.app, "_lan_apply_forced_movement", return_value=True) as movement_mock:
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("spell_mode"), "attack")
        movement_mock.assert_called_once_with(1, 2, "pull", 10.0, source_cell=None, direction_step=None)


    def test_spell_target_request_thorn_whip_movement_flows_through_generic_single_target_resolver(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "thorn-whip",
            "id": "thorn-whip",
            "name": "Thorn Whip",
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "spell_attack", "attack_type": "melee"},
                        "outcomes": {
                            "hit": [{"effect": "movement", "kind": "pull", "distance_ft": 10, "origin": "caster"}],
                            "miss": [],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 41,
            "target_cid": 2,
            "spell_name": "Thorn Whip",
            "spell_slug": "thorn-whip",
            "spell_mode": "attack",
            "hit": True,
        }

        real = tracker_mod.InitiativeTracker._resolve_single_target_spell.__get__(self.app, tracker_mod.InitiativeTracker)
        with mock.patch.object(self.app, "_resolve_single_target_spell", wraps=real) as resolver_mock:
            with mock.patch.object(self.app, "_lan_apply_forced_movement", return_value=True) as movement_mock:
                self.app._lan_apply_action(msg)

        resolver_mock.assert_called_once()
        movement_mock.assert_called_once()
        self.assertTrue(msg.get("_spell_target_result", {}).get("ok"))

    def test_phantasmal_killer_failed_save_applies_damage_and_end_turn_rider(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "phantasmal-killer",
            "id": "phantasmal-killer",
            "name": "Phantasmal Killer",
            "level": 4,
            "concentration": True,
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "wisdom", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [{"effect": "damage", "damage_type": "psychic", "dice": "4d10"}],
                            "success": [{"effect": "damage", "damage_type": "psychic", "dice": "4d10", "multiplier": 0.5}],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 25,
            "target_cid": 2,
            "spell_name": "Phantasmal Killer",
            "spell_slug": "phantasmal-killer",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 17,
            "roll_save": True,
            "slot_level": 4,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 4, 4, 4, 4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 16)
        self.assertTrue(any(getattr(st, "ctype", "") == "frightened" for st in self.app.combatants[2].condition_stacks))
        self.assertTrue(getattr(self.app.combatants[1], "concentrating", False))
        self.assertEqual(getattr(self.app.combatants[1], "concentration_spell", ""), "phantasmal-killer")
        riders = list(getattr(self.app.combatants[2], "end_turn_save_riders", []) or [])
        self.assertTrue(any(str(r.get("on_fail_damage_dice")) == "4d10" for r in riders if isinstance(r, dict)))

    def test_phantasmal_killer_successful_save_deals_half_damage(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "phantasmal-killer",
            "id": "phantasmal-killer",
            "name": "Phantasmal Killer",
            "level": 4,
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "wisdom", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [{"effect": "damage", "damage_type": "psychic", "dice": "4d10"}],
                            "success": [{"effect": "damage", "damage_type": "psychic", "dice": "4d10", "multiplier": 0.5}],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 26,
            "target_cid": 2,
            "spell_name": "Phantasmal Killer",
            "spell_slug": "phantasmal-killer",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 13,
            "roll_save": True,
            "slot_level": 4,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[12, 4, 4, 4, 4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("save_result", {}).get("passed"))
        self.assertEqual(result.get("damage_total"), 8)
        self.assertEqual(self.app.combatants[2].hp, 12)

    def test_tashas_hideous_laughter_failed_save_applies_conditions_and_riders(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "tasha-s-hideous-laughter",
            "id": "tasha-s-hideous-laughter",
            "name": "Tasha's Hideous Laughter",
            "level": 1,
            "concentration": True,
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "wisdom", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [
                                {"effect": "condition", "condition": "prone", "duration_turns": 0},
                                {"effect": "condition", "condition": "incapacitated", "duration_turns": 0, "ongoing": {"concentration_bound": True, "clear_group": "tashas_hideous_laughter_{source_cid}_{target_cid}", "condition_apply": ["prone", "incapacitated"], "condition_clear": ["incapacitated"], "repeat_save_end_turn": {"save_ability": "wis", "save_dc": "spell_save_dc", "condition": "incapacitated"}, "repeat_save_on_damage": {"save_ability": "wis", "save_dc": "spell_save_dc", "condition": "incapacitated", "advantage": True}}},
                            ],
                            "success": [],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 28,
            "target_cid": 2,
            "spell_name": "Tasha's Hideous Laughter",
            "spell_slug": "tasha-s-hideous-laughter",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 15,
            "roll_save": True,
            "slot_level": 1,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            self.app._lan_apply_action(msg)

        target = self.app.combatants[2]
        caster = self.app.combatants[1]
        self.assertTrue(any(getattr(st, "ctype", "") == "prone" for st in target.condition_stacks))
        self.assertTrue(any(getattr(st, "ctype", "") == "incapacitated" for st in target.condition_stacks))
        self.assertTrue(getattr(caster, "concentrating", False))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "tasha-s-hideous-laughter")
        self.assertIn(2, list(getattr(caster, "concentration_target", []) or []))
        group = self.app._tashas_hideous_laughter_group(caster.cid, target.cid)
        self.assertTrue(
            any(
                str(r.get("clear_group") or "").strip().lower() == group
                for r in list(getattr(target, "end_turn_save_riders", []) or [])
                if isinstance(r, dict)
            )
        )
        self.assertTrue(
            any(
                str(r.get("clear_group") or "").strip().lower() == group and bool(r.get("advantage"))
                for r in list(getattr(target, "on_damage_save_riders", []) or [])
                if isinstance(r, dict)
            )
        )
        self.assertTrue(
            any(
                str(entry.get("spell_key") or "") == "tasha-s-hideous-laughter"
                for entry in list(getattr(target, "ongoing_spell_effects", []) or [])
                if isinstance(entry, dict)
            )
        )

    def test_tashas_hideous_laughter_damage_save_ends_incapacitated_but_not_prone(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "tasha-s-hideous-laughter",
            "id": "tasha-s-hideous-laughter",
            "name": "Tasha's Hideous Laughter",
            "level": 1,
            "concentration": True,
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "wisdom", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [
                                {"effect": "condition", "condition": "prone", "duration_turns": 0},
                                {"effect": "condition", "condition": "incapacitated", "duration_turns": 0, "ongoing": {"concentration_bound": True, "clear_group": "tashas_hideous_laughter_{source_cid}_{target_cid}", "condition_apply": ["prone", "incapacitated"], "condition_clear": ["incapacitated"], "repeat_save_end_turn": {"save_ability": "wis", "save_dc": "spell_save_dc", "condition": "incapacitated"}, "repeat_save_on_damage": {"save_ability": "wis", "save_dc": "spell_save_dc", "condition": "incapacitated", "advantage": True}}},
                            ],
                            "success": [],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 29,
            "target_cid": 2,
            "spell_name": "Tasha's Hideous Laughter",
            "spell_slug": "tasha-s-hideous-laughter",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 15,
            "roll_save": True,
            "slot_level": 1,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            self.app._lan_apply_action(msg)

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 17]):
            self.app._apply_damage_to_target_with_temp_hp(self.app.combatants[2], 1)

        target = self.app.combatants[2]
        self.assertTrue(any(getattr(st, "ctype", "") == "prone" for st in target.condition_stacks))
        self.assertFalse(any(getattr(st, "ctype", "") == "incapacitated" for st in target.condition_stacks))
        self.assertEqual(list(getattr(target, "on_damage_save_riders", []) or []), [])
        self.assertEqual(list(getattr(target, "end_turn_save_riders", []) or []), [])
        self.assertEqual(list(getattr(target, "ongoing_spell_effects", []) or []), [])

    def test_hold_person_failed_save_applies_paralyzed_and_end_turn_save_rider(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "hold-person",
            "id": "hold-person",
            "name": "Hold Person",
            "level": 2,
            "concentration": True,
            "mechanics": {
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "wisdom", "dc": "spell_save_dc"},
                        "outcomes": {
                            "fail": [
                                {"effect": "condition", "condition": "paralyzed", "duration_turns": 0, "ongoing": {"concentration_bound": True, "clear_group": "hold_person_{source_cid}_{target_cid}", "condition_clear": ["paralyzed"], "repeat_save_end_turn": {"save_ability": "wis", "save_dc": "spell_save_dc", "condition": "paralyzed"}}},
                            ],
                            "success": [],
                        },
                    }
                ]
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 30,
            "target_cid": 2,
            "spell_name": "Hold Person",
            "spell_slug": "hold-person",
            "spell_mode": "save",
            "save_type": "wis",
            "save_dc": 15,
            "roll_save": True,
            "slot_level": 2,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=3):
            self.app._lan_apply_action(msg)

        target = self.app.combatants[2]
        caster = self.app.combatants[1]
        self.assertTrue(any(getattr(st, "ctype", "") == "paralyzed" for st in target.condition_stacks))
        self.assertTrue(getattr(caster, "concentrating", False))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "hold-person")
        self.assertIn(2, list(getattr(caster, "concentration_target", []) or []))
        self.assertTrue(
            any(
                str(r.get("clear_group") or "").strip().lower() == "hold_person_1_2"
                and str(r.get("condition") or "").strip().lower() == "paralyzed"
                and int(r.get("save_dc") or 0) == 15
                for r in list(getattr(target, "end_turn_save_riders", []) or [])
                if isinstance(r, dict)
            )
        )
        self.assertTrue(
            any(
                str(entry.get("spell_key") or "") == "hold-person"
                for entry in list(getattr(target, "ongoing_spell_effects", []) or [])
                if isinstance(entry, dict)
            )
        )

    def test_hold_person_end_turn_save_success_removes_paralyzed_after_skip(self):
        target = self.app.combatants[2]
        target.saving_throws = {"wis": 1}
        target.ability_mods = {"wis": 1}
        target.condition_stacks = [tracker_mod.base.ConditionStack(sid=1, ctype="paralyzed", remaining_turns=None)]
        target.end_turn_save_riders = [
            {
                "clear_group": "hold_person_1_2",
                "save_ability": "wis",
                "save_dc": 15,
                "condition": "paralyzed",
                "source": "Hold Person",
            }
        ]

        with mock.patch("dnd_initative_tracker.random.randint", return_value=14):
            skip, _msg, _dec = self.app._process_start_of_turn(target)
            self.assertTrue(skip)
            self.assertTrue(any(getattr(st, "ctype", "") == "paralyzed" for st in target.condition_stacks))
            self.app._end_turn_cleanup(2)

        self.assertFalse(any(getattr(st, "ctype", "") == "paralyzed" for st in target.condition_stacks))
        self.assertEqual(list(getattr(target, "end_turn_save_riders", []) or []), [])
        self.assertEqual(list(getattr(target, "ongoing_spell_effects", []) or []), [])

    def test_hold_person_concentration_end_clears_paralyzed_and_rider(self):
        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.app._start_concentration(caster, "hold-person", spell_level=2, targets=[2])
        self.app._register_target_spell_effect(
            1,
            2,
            "hold-person",
            spell_level=2,
            concentration_bound=True,
            clear_group="hold_person_1_2",
            primitives={
                "condition_apply": ["paralyzed"],
                "condition_clear": ["paralyzed"],
                "end_turn_save_riders": [
                    {
                        "clear_group": "hold_person_1_2",
                        "save_ability": "wis",
                        "save_dc": 15,
                        "condition": "paralyzed",
                        "source": "Hold Person",
                    }
                ],
            },
        )

        self.app._end_concentration(caster)

        self.assertFalse(any(getattr(st, "ctype", "") == "paralyzed" for st in target.condition_stacks))
        self.assertEqual(list(getattr(target, "end_turn_save_riders", []) or []), [])

    def test_heat_metal_applies_start_turn_damage_rider_and_concentration(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "heat-metal",
            "id": "heat-metal",
            "name": "Heat Metal",
            "level": 2,
            "concentration": True,
            "mechanics": {
                "scaling": {"kind": "slot_level", "base_slot": 2, "add_per_slot_above": "1d8"},
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "constitution", "dc": "spell_save_dc"},
                        "outcomes": {"fail": [], "success": []},
                    }
                ],
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 30,
            "target_cid": 2,
            "spell_name": "Heat Metal",
            "spell_slug": "heat-metal",
            "spell_mode": "save",
            "save_type": "con",
            "save_dc": 15,
            "roll_save": True,
            "slot_level": 2,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 4, 5]):
            self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("hit"))
        self.assertEqual(result.get("damage_total"), 9)
        self.assertTrue(getattr(caster, "concentrating", False))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "heat-metal")
        self.assertIn(2, list(getattr(caster, "concentration_target", []) or []))
        riders = list(getattr(target, "start_turn_damage_riders", []) or [])
        self.assertEqual(len(riders), 1)
        rider = riders[0]
        self.assertEqual(str(rider.get("dice") or ""), "2d8")
        self.assertEqual(str(rider.get("save_ability") or ""), "con")
        self.assertEqual(int(rider.get("save_dc") or 0), 15)

    def test_heat_metal_start_turn_successful_save_ends_concentration(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "heat-metal",
            "id": "heat-metal",
            "name": "Heat Metal",
            "level": 2,
            "concentration": True,
            "mechanics": {
                "scaling": {"kind": "slot_level", "base_slot": 2, "add_per_slot_above": "1d8"},
                "sequence": [
                    {
                        "check": {"kind": "saving_throw", "ability": "constitution", "dc": "spell_save_dc"},
                        "outcomes": {"fail": [], "success": []},
                    }
                ],
            },
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 2,
            "spell_name": "Heat Metal",
            "spell_slug": "heat-metal",
            "spell_mode": "save",
            "save_type": "con",
            "save_dc": 15,
            "roll_save": True,
            "slot_level": 2,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 4, 5]):
            self.app._lan_apply_action(msg)

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[3, 4, 18]):
            _skip, turn_msg, _dec = self.app._process_start_of_turn(self.app.combatants[2])

        caster = self.app.combatants[1]
        target = self.app.combatants[2]
        self.assertIn("CON save DC 15", turn_msg)
        self.assertFalse(getattr(caster, "concentrating", False))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "")
        self.assertEqual(list(getattr(target, "start_turn_damage_riders", []) or []), [])

    def test_healing_spell_requests_manual_healing_when_not_provided(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "healing-word",
            "id": "healing-word",
            "name": "Healing Word",
            "mechanics": {
                "sequence": [
                    {
                        "outcomes": {
                            "hit": [{"effect": "healing", "dice": "2d4"}],
                            "miss": [],
                        }
                    }
                ]
            },
        }
        self.app.combatants[3].hp = 10
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 27,
            "target_cid": 3,
            "spell_name": "Healing Word",
            "spell_slug": "healing-word",
            "spell_mode": "effect",
            "prompt_for_healing": True,
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("needs_healing_prompt"))
        self.assertEqual(self.app.combatants[3].hp, 10)

    def test_healing_spell_applies_healing_without_exceeding_max_hp(self):
        self.app._find_spell_preset = lambda *_args, **_kwargs: {
            "slug": "healing-word",
            "id": "healing-word",
            "name": "Healing Word",
            "mechanics": {
                "sequence": [
                    {
                        "outcomes": {
                            "hit": [{"effect": "healing", "dice": "2d4"}],
                            "miss": [],
                        }
                    }
                ]
            },
        }
        self.app.combatants[3].hp = 19
        self.app.combatants[3].max_hp = 22
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 28,
            "target_cid": 3,
            "spell_name": "Healing Word",
            "spell_slug": "healing-word",
            "spell_mode": "effect",
            "healing_entries": [{"amount": 8, "type": "healing"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("healing_total"), 8)
        self.assertEqual(result.get("healing_applied"), 3)
        self.assertEqual(self.app.combatants[3].hp, 22)


    def _load_spell_preset(self, slug: str):
        with open(f"Spells/{slug}.yaml", "r", encoding="utf-8") as fh:
            return tracker_mod.yaml.safe_load(fh)

    def test_yaml_healing_word_resolves_through_generic_engine(self):
        preset = self._load_spell_preset("healing-word")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        self.app._profile_for_player_name = lambda _name: {
            "spellcasting": {"casting_ability": "wis"},
            "abilities": {"wis": 18},
        }
        self.app.combatants[3].hp = 10
        self.app.combatants[3].max_hp = 22
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 41,
            "target_cid": 3,
            "spell_name": "Healing Word",
            "spell_slug": "healing-word",
            "spell_mode": "effect",
            "slot_level": 2,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[4, 3, 4, 3]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("healing_total"), 18)
        self.assertEqual(self.app.combatants[3].hp, 22)

    def test_yaml_cure_wounds_includes_spellcasting_modifier(self):
        preset = self._load_spell_preset("cure-wounds")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        self.app._profile_for_player_name = lambda _name: {
            "spellcasting": {"casting_ability": "wis"},
            "abilities": {"wis": 16},
        }
        self.app.combatants[3].hp = 4
        self.app.combatants[3].max_hp = 30
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 90,
            "target_cid": 3,
            "spell_name": "Cure Wounds",
            "spell_slug": "cure-wounds",
            "spell_mode": "effect",
            "slot_level": 1,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("healing_total"), 12)
        self.assertEqual(self.app.combatants[3].hp, 16)

    def test_yaml_shocking_grasp_cantrip_scaling_resolves_damage(self):
        preset = self._load_spell_preset("shocking-grasp")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        self.app._profile_for_player_name = lambda _name: {"leveling": {"level": 11}}
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 42,
            "target_cid": 2,
            "spell_name": "Shocking Grasp",
            "spell_slug": "shocking-grasp",
            "spell_mode": "attack",
            "hit": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[5, 4, 3]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("damage_total"), 12)
        self.assertEqual(self.app.combatants[2].hp, 8)

    def test_yaml_vicious_mockery_save_fail_deals_damage(self):
        preset = self._load_spell_preset("vicious-mockery")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 43,
            "target_cid": 2,
            "spell_name": "Vicious Mockery",
            "spell_slug": "vicious-mockery",
            "spell_mode": "save",
            "save_dc": 16,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[2, 4]):
            self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("save_result", {}).get("passed"))
        self.assertEqual(result.get("damage_total"), 4)

    def test_yaml_charm_person_save_fail_applies_condition(self):
        preset = self._load_spell_preset("charm-person")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 44,
            "target_cid": 2,
            "spell_name": "Charm Person",
            "spell_slug": "charm-person",
            "spell_mode": "save",
            "save_dc": 16,
            "roll_save": True,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        stacks = list(getattr(self.app.combatants[2], "condition_stacks", []) or [])
        self.assertTrue(any(str(getattr(st, "ctype", "")).lower() == "charmed" for st in stacks))

    def test_yaml_save_condition_concentration_bookkeeping(self):
        preset = self._load_spell_preset("charm-person")
        preset["concentration"] = True
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 45,
            "target_cid": 2,
            "spell_name": "Charm Person",
            "spell_slug": "charm-person",
            "spell_mode": "save",
            "save_dc": 16,
            "roll_save": True,
            "slot_level": 1,
        }

        with mock.patch("dnd_initative_tracker.random.randint", return_value=2):
            self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        self.assertTrue(getattr(caster, "concentrating", False))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "charm-person")
        self.assertIn(2, list(getattr(caster, "concentration_target", []) or []))
    def test_star_advantage_spell_attack_miss_spends_charge(self):
        self.app.combatants[1].pending_star_advantage_charge = {"name": "Star Advantage"}
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 29,
            "target_cid": 2,
            "spell_name": "Fire Bolt",
            "spell_mode": "attack",
            "hit": False,
        }

        self.app._lan_apply_action(msg)

        self.assertIsNone(getattr(self.app.combatants[1], "pending_star_advantage_charge", None))
        self.assertTrue(any("expends Star Advantage on a miss" in message for _, message in self.logs))


    def test_shield_of_faith_modifier_applies_and_clears_with_concentration(self):
        target = self.app.combatants[3]
        entry = self.app._register_target_spell_effect(
            1,
            3,
            "shield-of-faith",
            concentration_bound=True,
            clear_group="shield_of_faith_1_3",
            primitives={"modifiers": {"ac_bonus": 2}},
        )
        self.assertEqual(self.app._combatant_ac_modifier(target), 2)
        self.assertTrue(any(e.get("effect_id") == entry.get("effect_id") for e in target.ongoing_spell_effects))

        self.app.combatants[1].concentrating = True
        self.app.combatants[1].concentration_spell = "shield-of-faith"
        self.app.combatants[1].concentration_target = [3]
        self.app._end_concentration(self.app.combatants[1])

        self.assertEqual(self.app._combatant_ac_modifier(target), 0)
        self.assertEqual(list(getattr(target, "ongoing_spell_effects", []) or []), [])

    def test_longstrider_speed_bonus_affects_mode_speed_and_cleanup(self):
        target = self.app.combatants[3]
        self.app._register_target_spell_effect(
            1,
            3,
            "longstrider",
            concentration_bound=False,
            clear_group="longstrider_1_3",
            primitives={"modifiers": {"speed_bonus": 10}},
        )
        self.assertEqual(int(self.app._mode_speed(target)), 40)

        self.app._clear_target_spell_effects_for_spell(1, 3, "longstrider", reason="ended")
        self.assertEqual(int(self.app._mode_speed(target)), 30)

    def test_blur_forces_attack_disadvantage_against_target(self):
        target = self.app.combatants[3]
        self.app._register_target_spell_effect(
            1,
            3,
            "blur",
            concentration_bound=True,
            clear_group="blur_1_3",
            primitives={"modifiers": {"attackers_have_disadvantage_against_target": True}},
        )
        mode = self.app._attack_roll_mode_against_target(self.app.combatants[2], target)
        self.assertEqual(mode, "disadvantage")

        self.app._clear_target_spell_effects_for_spell(1, 3, "blur", reason="ended")
        mode_after = self.app._attack_roll_mode_against_target(self.app.combatants[2], target)
        self.assertEqual(mode_after, "normal")

    def test_protection_from_energy_grants_typed_resistance_and_cleanup(self):
        target = self.app.combatants[3]
        self.app._register_target_spell_effect(
            1,
            3,
            "protection-from-energy",
            concentration_bound=True,
            clear_group="pfe_1_3",
            primitives={"modifiers": {"damage_resistance_types": ["fire"]}},
        )
        adj = self.app._adjust_damage_entries_for_target(target, [{"amount": 9, "type": "fire"}])
        self.assertEqual(adj.get("entries"), [{"amount": 4, "type": "fire"}])

        self.app._clear_target_spell_effects_for_spell(1, 3, "protection-from-energy", reason="ended")
        adj2 = self.app._adjust_damage_entries_for_target(target, [{"amount": 9, "type": "fire"}])
        self.assertEqual(adj2.get("entries"), [{"amount": 9, "type": "fire"}])

    def test_protection_from_evil_and_good_supported_subset_uses_attack_disadvantage_only(self):
        target = self.app.combatants[3]
        self.app._register_target_spell_effect(
            1,
            3,
            "protection-from-evil-and-good",
            concentration_bound=True,
            clear_group="pfeg_1_3",
            primitives={"modifiers": {"attackers_have_disadvantage_against_target": True}},
        )
        self.assertEqual(
            self.app._attack_roll_mode_against_target(self.app.combatants[2], target),
            "disadvantage",
        )

    def test_save_roll_mode_modifiers_support_advantage_and_disadvantage(self):
        target = self.app.combatants[2]
        self.app._register_target_spell_effect(
            1,
            2,
            "save-test",
            clear_group="save_test_1_2",
            primitives={"modifiers": {"save_advantage_by_ability": ["dex"]}},
        )
        self.assertEqual(self.app._combatant_save_roll_mode(target, "dex"), "advantage")
        self.app._register_target_spell_effect(
            1,
            2,
            "save-test-dis",
            clear_group="save_test_dis_1_2",
            primitives={"modifiers": {"save_disadvantage_by_ability": ["dex"]}},
        )
        self.assertEqual(self.app._combatant_save_roll_mode(target, "dex"), "normal")


    def test_yaml_shield_of_faith_applies_ac_modifier_and_cleans_up_on_concentration_end(self):
        preset = self._load_spell_preset("shield-of-faith")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 46,
            "target_cid": 3,
            "spell_name": "Shield of Faith",
            "spell_slug": "shield-of-faith",
            "spell_mode": "effect",
            "slot_level": 1,
        }

        self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        target = self.app.combatants[3]
        self.assertTrue(getattr(caster, "concentrating", False))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "shield-of-faith")
        self.assertEqual(self.app._combatant_ac_modifier(target), 2)

        self.app._end_concentration(caster)
        self.assertEqual(self.app._combatant_ac_modifier(target), 0)

    def test_yaml_greater_invisibility_applies_and_clears_invisible_condition(self):
        preset = self._load_spell_preset("greater-invisibility")
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 47,
            "target_cid": 3,
            "spell_name": "Greater Invisibility",
            "spell_slug": "greater-invisibility",
            "spell_mode": "effect",
            "slot_level": 4,
        }

        self.app._lan_apply_action(msg)

        caster = self.app.combatants[1]
        target = self.app.combatants[3]
        self.assertTrue(self.app._has_condition(target, "invisible"))
        self.assertEqual(getattr(caster, "concentration_spell", ""), "greater-invisibility")

        self.app._end_concentration(caster)
        self.assertFalse(self.app._has_condition(target, "invisible"))



    def test_lesser_restoration_uses_shared_cleanup_for_supported_conditions(self):
        target = self.app.combatants[2]
        target.condition_stacks = [
            tracker_mod.base.ConditionStack(sid=101, ctype="poisoned", remaining_turns=None),
            tracker_mod.base.ConditionStack(sid=102, ctype="blinded", remaining_turns=None),
        ]
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 30,
            "target_cid": 2,
            "spell_name": "Lesser Restoration",
            "spell_slug": "lesser-restoration",
            "spell_mode": "effect",
        }
        preset = {
            "id": "lesser-restoration",
            "slug": "lesser-restoration",
            "name": "Lesser Restoration",
            "mechanics": {"sequence": [{"outcomes": {"hit": []}}]},
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result") or {}
        self.assertTrue(result.get("ok"))
        self.assertEqual((result.get("cleanup") or {}).get("conditions"), 1)
        remaining = [str(getattr(st, "ctype", "") or "").strip().lower() for st in list(getattr(target, "condition_stacks", []) or [])]
        self.assertEqual(remaining, ["blinded"])

    def test_lesser_restoration_falls_back_to_single_supported_ongoing_effect_cleanup(self):
        target = self.app.combatants[2]
        self.app._register_target_spell_effect(
            1,
            2,
            "ray-of-sickness",
            spell_level=1,
            clear_group="ray_of_sickness_1_2",
            effect_tags=["poison"],
            primitives={},
        )
        self.app._register_target_spell_effect(
            1,
            2,
            "contagion",
            spell_level=5,
            clear_group="contagion_1_2",
            effect_tags=["disease"],
            primitives={},
        )
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 130,
            "target_cid": 2,
            "spell_name": "Lesser Restoration",
            "spell_slug": "lesser-restoration",
            "spell_mode": "effect",
        }
        preset = {
            "id": "lesser-restoration",
            "slug": "lesser-restoration",
            "name": "Lesser Restoration",
            "mechanics": {"sequence": [{"outcomes": {"hit": []}}]},
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result") or {}
        self.assertEqual((result.get("cleanup") or {}).get("target_effects"), 1)
        remaining_effects = [str((entry or {}).get("spell_key") or "") for entry in list(getattr(target, "ongoing_spell_effects", []) or [])]
        self.assertEqual(remaining_effects, ["contagion"])

    def test_remove_curse_clears_curse_tagged_ongoing_effects(self):
        target = self.app.combatants[2]
        self.app._register_target_spell_effect(
            1,
            2,
            "hex",
            spell_level=1,
            effect_tags=["curse"],
            clear_group="hex_1_2",
            primitives={"condition_apply": ["cursed"]},
        )
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "target_cid": 2,
            "spell_name": "Remove Curse",
            "spell_slug": "remove-curse",
            "spell_mode": "effect",
        }
        preset = {
            "id": "remove-curse",
            "slug": "remove-curse",
            "name": "Remove Curse",
            "mechanics": {"sequence": [{"outcomes": {"hit": []}}]},
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result") or {}
        self.assertEqual((result.get("cleanup") or {}).get("target_effects"), 1)
        self.assertEqual(list(getattr(target, "ongoing_spell_effects", []) or []), [])
        self.assertIn((31, "Remove Curse removed 2 effects from Goblin (1 condition, 1 effect)."), self.toasts)
        self.assertTrue(any(entry == "Remove Curse removed 2 effects from Goblin (1 condition, 1 effect)." for _, entry in self.logs))

    def test_hex_registers_mark_on_target(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 210,
            "target_cid": 2,
            "spell_name": "Hex",
            "spell_slug": "hex",
            "spell_mode": "effect",
            "slot_level": 1,
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: {"id": "hex", "slug": "hex", "name": "Hex", "level": 1, "concentration": True}

        self.app._lan_apply_action(msg)

        marks = self.app._collect_marks_for_attacker(self.app.combatants[1], "hex")
        self.assertEqual(len(marks), 1)
        self.assertEqual(int(marks[0].get("target_cid") or 0), 2)
        self.assertIn((210, "Hex applied to Goblin."), self.toasts)
        self.assertTrue(any(entry == "Hex applied to Goblin." for _, entry in self.logs))
        self.assertFalse(any("Spell resolved." in entry for _, entry in self.toasts))

    def test_hunters_mark_reassign_requires_prior_target_down(self):
        self.app._register_target_mark(
            1,
            2,
            "hunter-s-mark",
            spell_level=1,
            concentration_bound=True,
            clear_group="hunter-s-mark_1_2",
            reassign={"allow_reassign": True, "requires_prior_target_down": True},
            attack_augments={"extra_damage_dice": [{"dice": "1d6", "damage_type": "force"}]},
        )
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 211,
            "target_cid": 3,
            "spell_name": "Hunter's Mark",
            "spell_slug": "hunter-s-mark",
            "spell_mode": "effect",
            "slot_level": 1,
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: {"id": "hunter-s-mark", "slug": "hunter-s-mark", "name": "Hunter's Mark", "level": 1, "concentration": True}

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result") or {}
        self.assertFalse(result.get("ok"))
        marks = self.app._collect_marks_for_attacker(self.app.combatants[1], "hunter-s-mark")
        self.assertEqual(len(marks), 1)
        self.assertEqual(int(marks[0].get("target_cid") or 0), 2)

    def test_hunters_mark_reassign_allows_when_prior_target_down(self):
        self.app.combatants[2].hp = 0
        self.app._register_target_mark(
            1,
            2,
            "hunter-s-mark",
            spell_level=1,
            concentration_bound=True,
            clear_group="hunter-s-mark_1_2",
            reassign={"allow_reassign": True, "requires_prior_target_down": True},
            attack_augments={"extra_damage_dice": [{"dice": "1d6", "damage_type": "force"}]},
        )
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 212,
            "target_cid": 3,
            "spell_name": "Hunter's Mark",
            "spell_slug": "hunter-s-mark",
            "spell_mode": "effect",
            "slot_level": 1,
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: {"id": "hunter-s-mark", "slug": "hunter-s-mark", "name": "Hunter's Mark", "level": 1, "concentration": True}

        self.app._lan_apply_action(msg)

        marks = self.app._collect_marks_for_attacker(self.app.combatants[1], "hunter-s-mark")
        self.assertEqual(len(marks), 1)
        self.assertEqual(int(marks[0].get("target_cid") or 0), 3)

    def test_bestow_curse_extra_damage_mode_registers_mark_on_failed_save(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 213,
            "target_cid": 2,
            "spell_name": "Bestow Curse",
            "spell_slug": "bestow-curse",
            "spell_mode": "effect",
            "slot_level": 3,
            "curse_mode": "extra-damage",
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: {"id": "bestow-curse", "slug": "bestow-curse", "name": "Bestow Curse", "level": 3, "concentration": True}

        with mock.patch("dnd_initative_tracker.random.randint", return_value=1):
            self.app._lan_apply_action(msg)

        marks = self.app._collect_marks_for_attacker(self.app.combatants[1], "bestow-curse")
        self.assertEqual(len(marks), 1)
        self.assertEqual(int(marks[0].get("target_cid") or 0), 2)
        self.assertIn((213, "Bestow Curse: Goblin failed WIS save (3 vs DC 0) Bestow Curse applied to Goblin."), self.toasts)
        self.assertTrue(
            any(
                entry == "Goblin fails their WIS save against Bestow Curse (3 vs DC 0); Bestow Curse applied to Goblin."
                for _, entry in self.logs
            )
        )

    def test_dispel_magic_clears_target_and_map_effects_by_slot_level(self):
        target = self.app.combatants[2]
        self.app.combatants[2].concentration_aoe_ids = [77, 78]
        self.app._register_target_spell_effect(1, 2, "slow", spell_level=3, clear_group="slow_1_2", primitives={"condition_apply": ["slowed"]})
        self.app._register_target_spell_effect(1, 2, "hold-person", spell_level=4, clear_group="hold_1_2", primitives={"condition_apply": ["paralyzed"]})
        self.app._register_map_spell_effect(
            77,
            {
                "name": "Spirit Guardians",
                "owner_cid": 2,
                "spell_slug": "spirit-guardians",
                "slot_level": 3,
                "concentration_bound": True,
            },
        )
        self.app._register_map_spell_effect(
            78,
            {
                "name": "Wall of Fire",
                "owner_cid": 2,
                "spell_slug": "wall-of-fire",
                "slot_level": 4,
                "concentration_bound": True,
            },
        )
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 32,
            "target_cid": 2,
            "spell_name": "Dispel Magic",
            "spell_slug": "dispel-magic",
            "spell_mode": "effect",
            "slot_level": 3,
        }
        preset = {
            "id": "dispel-magic",
            "slug": "dispel-magic",
            "name": "Dispel Magic",
            "level": 3,
            "mechanics": {"sequence": [{"outcomes": {"hit": []}}]},
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result") or {}
        cleanup = result.get("cleanup") or {}
        self.assertEqual(cleanup.get("target_effects"), 1)
        self.assertEqual(cleanup.get("map_effects"), 1)
        remaining_spells = [str((entry or {}).get("spell_key") or "") for entry in list(getattr(target, "ongoing_spell_effects", []) or [])]
        self.assertEqual(remaining_spells, ["hold-person"])
        self.assertNotIn(77, self.app._lan_aoes)
        self.assertIn(78, self.app._lan_aoes)
        self.assertEqual(self.app.combatants[2].concentration_aoe_ids, [78])
        self.assertIn((32, "Dispel Magic removed 2 effects from Goblin (1 effect, 1 map effect)."), self.toasts)
        self.assertTrue(
            any(entry == "Dispel Magic removed 2 effects from Goblin (1 effect, 1 map effect)." for _, entry in self.logs)
        )

    def test_lan_manual_spell_prompt_copy_no_longer_uses_generic_resolve_text(self):
        asset_path = Path(__file__).resolve().parents[1] / "assets" / "web" / "lan" / "index.html"
        text = asset_path.read_text(encoding="utf-8")

        self.assertNotIn("Resolve ${pendingSpellTargeting.spellName} on ${pendingAttackResolve.targetName}.", text)
        self.assertIn("Choose hit or miss, then enter damage if it hits.", text)
        self.assertIn("hits ${pendingAttackResolve.targetName}. Enter damage for ${pendingSpellTargeting.spellName}.", text)

    def test_misty_step_requires_destination_then_relocates_via_shared_path(self):
        preset = {
            "slug": "misty-step",
            "id": "misty-step",
            "name": "Misty Step",
            "range": "Self",
            "mechanics": {
                "targeting": {"range": {"kind": "self", "distance_ft": 30}},
                "sequence": [
                    {
                        "check": {"kind": "effect"},
                        "outcomes": {
                            "hit": [
                                {
                                    "effect": "relocation",
                                    "origin_mode": "target",
                                    "range_ft": 30,
                                    "requires_unoccupied": True,
                                }
                            ]
                        },
                    }
                ],
            },
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset

        first = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "spell_name": "Misty Step",
            "spell_slug": "misty-step",
            "spell_mode": "effect",
        }
        self.app._lan_apply_action(first)
        first_result = first.get("_spell_target_result") or {}
        self.assertTrue(first_result.get("needs_relocation_destination"))

        second = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 31,
            "spell_name": "Misty Step",
            "spell_slug": "misty-step",
            "spell_mode": "effect",
            "destination_col": 9,
            "destination_row": 4,
        }
        self.app._lan_apply_action(second)
        second_result = second.get("_spell_target_result") or {}
        self.assertTrue(second_result.get("ok"))
        self.assertEqual(self.app._lan_positions.get(1), (9, 4))

    def test_misty_step_rejects_occupied_destination(self):
        preset = {
            "slug": "misty-step",
            "id": "misty-step",
            "name": "Misty Step",
            "range": "Self",
            "mechanics": {
                "targeting": {"range": {"kind": "self", "distance_ft": 30}},
                "sequence": [
                    {
                        "check": {"kind": "effect"},
                        "outcomes": {
                            "hit": [
                                {
                                    "effect": "relocation",
                                    "origin_mode": "target",
                                    "range_ft": 30,
                                    "requires_unoccupied": True,
                                }
                            ]
                        },
                    }
                ],
            },
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 32,
            "spell_name": "Misty Step",
            "spell_slug": "misty-step",
            "spell_mode": "effect",
            "destination_col": 6,
            "destination_row": 4,
        }
        self.app._lan_apply_action(msg)
        result = msg.get("_spell_target_result") or {}
        self.assertFalse(result.get("ok"))
        self.assertEqual(self.app._lan_positions.get(1), (4, 4))

    def test_misty_step_rejects_out_of_range_destination(self):
        preset = {
            "slug": "misty-step",
            "id": "misty-step",
            "name": "Misty Step",
            "range": "Self",
            "mechanics": {
                "targeting": {"range": {"kind": "self", "distance_ft": 30}},
                "sequence": [
                    {
                        "check": {"kind": "effect"},
                        "outcomes": {
                            "hit": [
                                {
                                    "effect": "relocation",
                                    "origin_mode": "target",
                                    "range_ft": 30,
                                    "requires_unoccupied": True,
                                }
                            ]
                        },
                    }
                ],
            },
        }
        self.app._find_spell_preset = lambda *_args, **_kwargs: preset
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 1,
            "_ws_id": 33,
            "spell_name": "Misty Step",
            "spell_slug": "misty-step",
            "spell_mode": "effect",
            "destination_col": 15,
            "destination_row": 4,
        }
        self.app._lan_apply_action(msg)
        result = msg.get("_spell_target_result") or {}
        self.assertFalse(result.get("ok"))
        self.assertEqual(self.app._lan_positions.get(1), (4, 4))


    def test_spell_target_request_allows_prompt_attacker_override_for_active_persistent_aoe(self):
        self.app._lan_aoes = {
            99: {
                "kind": "sphere",
                "cx": 6.0,
                "cy": 4.0,
                "radius_sq": 1.0,
                "owner_cid": 1,
                "over_time": True,
                "persistent": True,
                "spell_slug": "wall-of-fire",
                "spell_id": "wall-of-fire",
            }
        }
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "prompt_attacker_cid": 1,
            "_claimed_cid": 3,
            "_ws_id": 34,
            "target_cid": 2,
            "spell_name": "Wall of Fire",
            "spell_slug": "wall-of-fire",
            "spell_id": "wall-of-fire",
            "spell_mode": "attack",
            "hit": True,
            "damage_entries": [{"amount": 7, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        result = msg.get("_spell_target_result") or {}
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("attacker_cid"), 1)
        self.assertEqual(self.app.combatants[2].hp, 13)

    def test_spell_target_request_rejects_claim_swap_without_prompt_override(self):
        msg = {
            "type": "spell_target_request",
            "cid": 1,
            "_claimed_cid": 3,
            "_ws_id": 35,
            "target_cid": 2,
            "spell_name": "Wall of Fire",
            "spell_slug": "wall-of-fire",
            "spell_mode": "effect",
            "hit": True,
            "damage_entries": [{"amount": 7, "type": "fire"}],
        }

        self.app._lan_apply_action(msg)

        self.assertNotIn("_spell_target_result", msg)
        self.assertEqual(self.app.combatants[2].hp, 20)
        self.assertIn((35, "Arrr, that token ain’t yers."), self.toasts)


if __name__ == "__main__":
    unittest.main()
