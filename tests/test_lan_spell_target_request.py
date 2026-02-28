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


    def test_save_spell_log_uses_pass_fail_without_roll_details(self):
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
        self.assertTrue(any("succeeds their save" in entry for entry in save_logs))
        self.assertTrue(all("DC" not in entry for entry in save_logs))
        self.assertTrue(all("+" not in entry for entry in save_logs))

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
        self.assertTrue(any("fails their save against Hold Person" in message for _, message in self.logs))

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

if __name__ == "__main__":
    unittest.main()
