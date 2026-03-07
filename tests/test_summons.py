import unittest
from unittest import mock
from pathlib import Path

import yaml

import dnd_initative_tracker as tracker_mod


class SummonHarness:
    def __init__(self):
        self.combatants = {}
        self._summon_groups = {}
        self._summon_group_meta = {}
        self._next_cid = 1
        self._lan_positions = {}
        self._oplog = lambda *args, **kwargs: None
        self._rebuild_table = lambda *args, **kwargs: None
        self._lan_force_state_broadcast = lambda *args, **kwargs: None
        self._monster_specs = []
        self._load_monsters_index = lambda: None
        self._turn_snapshots = {}
        self._lan_aoes = {}

    def _unique_name(self, name):
        return str(name)

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
        actions=None,
        bonus_actions=None,
        **_kwargs,
    ):
        cid = self._next_cid
        self._next_cid += 1
        c = tracker_mod.base.Combatant(
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
            actions=list(actions or []),
            bonus_actions=list(bonus_actions or []),
        )
        self.combatants[cid] = c
        return cid


    def _normalize_token_color(self, color):
        return tracker_mod.InitiativeTracker._normalize_token_color(self, color)

    def _profile_for_player_name(self, _name):
        return {}

    def _resolve_player_ac(self, _normalized, defenses):
        return int((defenses or {}).get("ac") or 10)

    # Bind target methods from InitiativeTracker
    _resolve_summon_choice = staticmethod(tracker_mod.InitiativeTracker._resolve_summon_choice)
    _normalize_summon_controller_mode = staticmethod(tracker_mod.InitiativeTracker._normalize_summon_controller_mode)
    _resolve_summon_count_config = staticmethod(tracker_mod.InitiativeTracker._resolve_summon_count_config)
    _resolve_spell_summon_request = tracker_mod.InitiativeTracker._resolve_spell_summon_request
    _build_summon_scaling_context = tracker_mod.InitiativeTracker._build_summon_scaling_context
    _normalize_monster_slug_value = tracker_mod.InitiativeTracker._normalize_monster_slug_value
    _normalize_spellcasting_ability = tracker_mod.InitiativeTracker._normalize_spellcasting_ability
    _compute_spell_save_dc = tracker_mod.InitiativeTracker._compute_spell_save_dc
    _proficiency_bonus_for_level = staticmethod(tracker_mod.InitiativeTracker._proficiency_bonus_for_level)
    _is_spellcasting_enabled = staticmethod(tracker_mod.InitiativeTracker._is_spellcasting_enabled)
    _apply_summon_initiative = tracker_mod.InitiativeTracker._apply_summon_initiative
    _evaluate_dynamic_formula = tracker_mod.InitiativeTracker._evaluate_dynamic_formula
    _apply_monster_variant = tracker_mod.InitiativeTracker._apply_monster_variant
    _apply_startup_summon_overrides = tracker_mod.InitiativeTracker._apply_startup_summon_overrides
    _spawn_mount = tracker_mod.InitiativeTracker._spawn_mount
    _spawn_summons_from_cast = tracker_mod.InitiativeTracker._spawn_summons_from_cast
    _spawn_startup_summons_for_pc = tracker_mod.InitiativeTracker._spawn_startup_summons_for_pc
    _summon_actions_from_spec = tracker_mod.InitiativeTracker._summon_actions_from_spec
    _normalize_action_entries = staticmethod(tracker_mod.InitiativeTracker._normalize_action_entries)
    _normalize_startup_summon_entries = tracker_mod.InitiativeTracker._normalize_startup_summon_entries
    _monster_int_from_value = tracker_mod.InitiativeTracker._monster_int_from_value
    _sorted_combatants = tracker_mod.InitiativeTracker._sorted_combatants
    _remove_combatants_with_lan_cleanup = tracker_mod.InitiativeTracker._remove_combatants_with_lan_cleanup
    _monster_slug_from_spec = tracker_mod.InitiativeTracker._monster_slug_from_spec
    _resolve_summon_lifecycle = tracker_mod.InitiativeTracker._resolve_summon_lifecycle
    _dismiss_spell_summon_groups_for_caster = tracker_mod.InitiativeTracker._dismiss_spell_summon_groups_for_caster
    _dismiss_summon_group = tracker_mod.InitiativeTracker._dismiss_summon_group
    _dismiss_persistent_summon_group = tracker_mod.InitiativeTracker._dismiss_persistent_summon_group
    _reappear_persistent_summon_group = tracker_mod.InitiativeTracker._reappear_persistent_summon_group
    _find_persistent_spell_group_for_caster = tracker_mod.InitiativeTracker._find_persistent_spell_group_for_caster
    _validate_relocation_destination = tracker_mod.InitiativeTracker._validate_relocation_destination
    _spell_destination_distance_ft = tracker_mod.InitiativeTracker._spell_destination_distance_ft

    def _lan_feet_per_square(self):
        return 5.0

    def _lan_live_map_data(self):
        return (20, 20, set(), {}, dict(self._lan_positions))


class SummonSpawnTests(unittest.TestCase):
    def _build_harness(self):
        h = SummonHarness()
        caster = tracker_mod.base.Combatant(
            cid=100,
            name="Caster",
            hp=20,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="Normal",
            move_remaining=30,
            initiative=15,
            dex=2,
            ally=True,
            is_pc=True,
            is_spellcaster=True,
        )
        h.combatants[caster.cid] = caster
        return h

    def test_casting_summon_spawns_expected_count_variable_by_slot(self):
        h = self._build_harness()

        preset = {
            "slug": "create-undead",
            "id": "create-undead",
            "concentration": False,
            "summon": {
                "choices": [
                    {"name": "Ghoul", "monster_slug": "ghoul"},
                    {"name": "Ghast", "monster_slug": "ghast"},
                ],
                "count": {
                    "kind": "variable_by_slot",
                    "base": {"slot_level": 6, "quantity": 3, "creature_options": ["ghoul"]},
                    "slot_overrides": [
                        {"slot_level": 7, "quantity": 4, "creature_options": ["ghoul"]},
                    ],
                },
                "initiative": {"mode": "rolled_per_creature"},
            },
        }
        spec = tracker_mod.MonsterSpec(
            filename="ghoul.yaml",
            name="Ghoul",
            mtype="undead",
            cr=1,
            hp=22,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=2,
            init_mod=2,
            saving_throws={},
            ability_mods={},
            raw_data={},
        )

        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: spec

        spawned = h._spawn_summons_from_cast(
            caster_cid=100,
            spell_slug="create-undead",
            spell_id="",
            slot_level=7,
            summon_choice="ghoul",
        )

        self.assertEqual(len(spawned), 4)
        for cid in spawned:
            c = h.combatants[cid]
            self.assertEqual(getattr(c, "summoned_by_cid", None), 100)
            self.assertEqual(getattr(c, "summon_source_spell", None), "create-undead")
            self.assertTrue(getattr(c, "summon_group_id", ""))

    def test_shared_initiative_places_summons_immediately_after_caster(self):
        h = self._build_harness()
        enemy = tracker_mod.base.Combatant(
            cid=200,
            name="Enemy",
            hp=10,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="Normal",
            move_remaining=30,
            initiative=14,
            dex=1,
        )
        h.combatants[enemy.cid] = enemy

        a = h._create_combatant("Summon A", 10, 30, 1, 1, True)
        b = h._create_combatant("Summon B", 10, 30, 1, 1, True)

        h._apply_summon_initiative(100, [a, b], {"initiative": {"mode": "shared"}})

        order = [c.cid for c in h._sorted_combatants()]
        self.assertEqual(order[:4], [100, a, b, 200])

    def test_shared_initiative_keeps_summons_adjacent_on_tied_initiative(self):
        h = self._build_harness()
        tied_enemy = tracker_mod.base.Combatant(
            cid=201,
            name="Aaron",
            hp=10,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="Normal",
            move_remaining=30,
            initiative=15,
            dex=2,
        )
        h.combatants[tied_enemy.cid] = tied_enemy
        a = h._create_combatant("Summon A", 10, 30, 1, 1, True)
        h._apply_summon_initiative(100, [a], {"initiative": {"mode": "shared"}})

        order = [c.cid for c in h._sorted_combatants()]
        self.assertEqual(order[:3], [201, 100, a])

    def test_rolled_mode_still_forces_shared_initiative_and_anchor_order(self):
        h = self._build_harness()
        s1 = h._create_combatant("S1", 10, 30, 1, 0, True)
        s2 = h._create_combatant("S2", 10, 30, 1, 0, True)
        s3 = h._create_combatant("S3", 10, 30, 1, 0, True)

        h._apply_summon_initiative(100, [s1, s2, s3], {"initiative": {"mode": "rolled_per_creature"}})

        initiatives = [h.combatants[s1].initiative, h.combatants[s2].initiative, h.combatants[s3].initiative]
        self.assertEqual(initiatives, [15, 15, 15])
        self.assertTrue(all(getattr(h.combatants[cid], "summon_shared_turn", False) for cid in [s1, s2, s3]))

        order = [c.cid for c in h._sorted_combatants()]
        self.assertEqual(order[:4], [100, s1, s2, s3])


    def test_spawn_applies_side_color_and_positions(self):
        h = self._build_harness()
        preset = {
            "slug": "summon-construct",
            "id": "summon-construct",
            "concentration": True,
            "summon": {
                "side": "enemy",
                "color": "#3366ff",
                "choices": [{"name": "Construct Spirit", "monster_slug": "construct-spirit"}],
                "count": {"kind": "fixed", "min": 1, "max": 1},
                "initiative": {"mode": "shared"},
            },
        }
        spec = tracker_mod.MonsterSpec(
            filename="construct-spirit.yaml",
            name="Construct Spirit",
            mtype="construct",
            cr=1,
            hp=40,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=2,
            init_mod=2,
            saving_throws={},
            ability_mods={},
            raw_data={},
        )
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: spec

        spawned = h._spawn_summons_from_cast(
            caster_cid=100,
            spell_slug="summon-construct",
            spell_id="",
            slot_level=4,
            summon_choice="construct-spirit",
            summon_positions=[{"col": 4, "row": 5}],
        )

        self.assertEqual(len(spawned), 1)
        summoned = h.combatants[spawned[0]]
        self.assertFalse(getattr(summoned, "ally", True))
        self.assertEqual(getattr(summoned, "token_color", None), "#3366ff")
        self.assertEqual(h._lan_positions.get(spawned[0]), (4, 5))
        self.assertEqual(getattr(summoned, "summon_choice_slug", None), "construct-spirit")
        self.assertEqual(getattr(summoned, "summon_base_monster_slug", None), "construct-spirit")
        group_id = getattr(summoned, "summon_group_id", "")
        self.assertEqual(h._summon_group_meta.get(group_id, {}).get("summon_choice_slug"), "construct-spirit")

    def test_resolve_choice_does_not_fallback_when_invalid_choice_provided(self):
        summon_cfg = {
            "choices": [
                {"name": "Ghoul", "monster_slug": "ghoul"},
                {"name": "Ghast", "monster_slug": "ghast"},
            ],
            "count": {"kind": "fixed", "min": 1, "max": 1},
        }
        _choice, qty, slug = tracker_mod.InitiativeTracker._resolve_summon_choice(
            summon_cfg, "not-a-real-slug", 6
        )
        self.assertIsNone(slug)
        self.assertIsNone(qty)

    def test_summon_construct_defaults_to_construct_spirit_without_fallback(self):
        h = self._build_harness()
        preset = {
            "slug": "summon-construct",
            "id": "summon-construct",
            "concentration": True,
            "summon": {
                "choices": [{"name": "Construct Spirit", "monster_slug": "construct-spirit"}],
                "count": {"kind": "fixed", "min": 1, "max": 1},
                "initiative": {"mode": "shared"},
            },
        }
        recorded = []
        spec = tracker_mod.MonsterSpec(
            filename="construct-spirit.yaml",
            name="Construct Spirit",
            mtype="construct",
            cr=1,
            hp=40,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=2,
            init_mod=2,
            saving_throws={},
            ability_mods={},
            raw_data={},
        )

        def _finder(slug):
            recorded.append(slug)
            return spec if slug == "construct-spirit" else None

        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = _finder

        spawned = h._spawn_summons_from_cast(
            caster_cid=100,
            spell_slug="summon-construct",
            spell_id="",
            slot_level=4,
            summon_choice=None,
        )
        self.assertEqual(len(spawned), 1)
        self.assertIn("construct-spirit", recorded)

    def test_spell_summon_rejects_invalid_choice_without_fallback(self):
        h = self._build_harness()
        preset = {
            "slug": "summon-construct",
            "id": "summon-construct",
            "concentration": True,
            "summon": {
                "choices": [{"name": "Construct Spirit", "monster_slug": "construct-spirit"}],
                "count": {"kind": "fixed", "min": 1, "max": 1},
            },
        }
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: None

        spawned = h._spawn_summons_from_cast(
            caster_cid=100,
            spell_slug="summon-construct",
            spell_id="",
            slot_level=4,
            summon_choice="wolf",
        )
        self.assertEqual(spawned, [])

    def test_spawn_uses_monster_yaml_actions_and_attacks_for_controlled_summons(self):
        h = self._build_harness()
        preset = {
            "slug": "summon-construct",
            "id": "summon-construct",
            "concentration": True,
            "summon": {
                "choices": [{"name": "Construct Spirit", "monster_slug": "construct-spirit"}],
                "count": {"kind": "fixed", "min": 1, "max": 1},
                "initiative": {"mode": "shared"},
            },
        }
        spec = tracker_mod.MonsterSpec(
            filename="construct-spirit.yaml",
            name="Construct Spirit",
            mtype="construct",
            cr=1,
            hp=40,
            speed=30,
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            dex=2,
            init_mod=2,
            saving_throws={},
            ability_mods={},
            raw_data={
                "actions": [
                    {
                        "name": "Slam",
                        "description": "Melee Attack Roll: +8, reach 5 ft. Hit: 9 (1d8 + 5) force damage.",
                    }
                ],
                "attacks": [
                    {
                        "name": "Radiant Bolt",
                        "to_hit": 7,
                        "damage_formula": "2d6 + 4",
                        "damage_type": "radiant",
                    }
                ],
            },
        )
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: spec

        spawned = h._spawn_summons_from_cast(
            caster_cid=100,
            spell_slug="summon-construct",
            spell_id="",
            slot_level=4,
            summon_choice="construct-spirit",
        )
        self.assertEqual(len(spawned), 1)
        summon_actions = h.combatants[spawned[0]].actions
        self.assertGreaterEqual(len(summon_actions), 2)
        by_name = {str(entry.get("name")): entry for entry in summon_actions if isinstance(entry, dict)}
        self.assertIn("Slam", by_name)
        self.assertIn("Radiant Bolt", by_name)
        self.assertIsInstance(by_name["Slam"].get("attack_weapon"), dict)
        self.assertEqual(by_name["Slam"]["attack_weapon"].get("to_hit"), 8)
        self.assertEqual(by_name["Radiant Bolt"]["attack_weapon"].get("to_hit"), 7)

    def test_mount_spawn_evaluates_formula_and_variant(self):
        h = self._build_harness()
        preset = {
            "slug": "find-steed",
            "id": "find-steed",
            "concentration": False,
            "summon": {
                "mount": True,
                "color": "blue",
                "choices": [{"name": "Otherworldly Steed", "monster_slug": "otherworldly-steed"}],
                "count": {"kind": "fixed", "min": 1, "max": 1},
                "initiative": {"mode": "shared"},
                "control": {"controller_mode": "shared_turn"},
            },
        }
        spec = tracker_mod.MonsterSpec(
            filename="otherworldly-steed.yaml",
            name="Otherworldly Steed",
            mtype="celestial",
            cr=None,
            hp=5,
            speed=60,
            swim_speed=0,
            fly_speed=60,
            burrow_speed=0,
            climb_speed=0,
            dex=1,
            init_mod=1,
            saving_throws={},
            ability_mods={},
            raw_data={
                "hp": "5 + 10 * var.slot_level",
                "ac": "10 + var.slot_level",
                "variants": [
                    {"name": "Celestial", "damage_type": "Radiant", "bonus_action": {"name": "Healing Touch", "desc": "heal"}},
                    {"name": "Fey", "damage_type": "Psychic", "bonus_action": {"name": "Fey Step", "desc": "teleport"}},
                ],
            },
        )
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: spec

        spawned = h._spawn_summons_from_cast(
            caster_cid=100,
            spell_slug="find-steed",
            spell_id="",
            slot_level=4,
            summon_choice="otherworldly-steed",
            summon_variant="Fey",
        )
        self.assertEqual(len(spawned), 1)
        c = h.combatants[spawned[0]]
        self.assertTrue(getattr(c, "is_mount", False))
        self.assertEqual(c.hp, 45)
        self.assertEqual(getattr(c, "summon_variant", None), "Fey")
        self.assertEqual(getattr(c, "summon_choice_slug", None), "otherworldly-steed")
        self.assertEqual(getattr(c, "summon_base_monster_slug", None), "otherworldly-steed")
        self.assertEqual(getattr(c, "token_color", None), "#6aa9ff")

    def test_startup_summon_normalization_supports_alias_and_overrides(self):
        h = self._build_harness()
        parsed = h._normalize_startup_summon_entries("owl.yaml", "Eldramar")
        self.assertEqual(parsed, [{"monster": "owl.yaml", "count": 1, "overrides": {}}])

        parsed = h._normalize_startup_summon_entries(
            {"monster": "owl", "count": 2, "HP": 7, "ac": 14, "dex": 18, "name": "Familiar"},
            "Eldramar",
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["monster"], "owl")
        self.assertEqual(parsed[0]["count"], 2)
        self.assertEqual(parsed[0]["overrides"]["HP"], 7)
        self.assertEqual(parsed[0]["overrides"]["ac"], 14)
        self.assertEqual(parsed[0]["overrides"]["dex"], 18)
        self.assertEqual(parsed[0]["overrides"]["name"], "Familiar")

    def test_startup_summon_spawn_applies_overrides_and_metadata(self):
        h = self._build_harness()
        spec = tracker_mod.MonsterSpec(
            filename="owl.yaml",
            name="Owl",
            mtype="beast",
            cr=0,
            hp=1,
            speed=5,
            swim_speed=0,
            fly_speed=60,
            burrow_speed=0,
            climb_speed=0,
            dex=13,
            init_mod=1,
            saving_throws={},
            ability_mods={"dex": 1},
            raw_data={"name": "Owl", "ac": 11, "hp": 1, "abilities": {"Dex": 13}},
        )
        h._find_monster_spec_by_slug = lambda slug: spec if slug == "owl" else None

        spawned = h._spawn_startup_summons_for_pc(
            100,
            [
                {
                    "monster": "owl.yaml",
                    "count": 2,
                    "overrides": {
                        "HP": 7,
                        "AC": 15,
                        "dex": 18,
                        "name": "Scout Owl",
                        "token_color": "#112233",
                        "token_border_color": "#445566",
                    },
                }
            ],
        )

        self.assertEqual(len(spawned), 2)
        for cid in spawned:
            c = h.combatants[cid]
            self.assertEqual(c.hp, 7)
            self.assertEqual(getattr(c, "summoned_by_cid", None), 100)
            self.assertEqual(getattr(c, "summon_source_spell", None), "summon_on_start")
            self.assertTrue(getattr(c, "summon_group_id", ""))
            self.assertEqual(c.monster_spec.raw_data.get("ac"), 15)
            self.assertEqual(c.monster_spec.raw_data.get("abilities", {}).get("Dex"), 18)
            self.assertEqual(c.initiative, h.combatants[100].initiative)
            self.assertTrue(getattr(c, "summon_shared_turn", False))
            self.assertEqual(getattr(c, "summon_anchor_after_cid", None), 100)
            self.assertGreaterEqual(int(getattr(c, "summon_anchor_seq", 0) or 0), 1)
            self.assertEqual(getattr(c, "token_color", None), "#112233")
            self.assertEqual(getattr(c, "token_border_color", None), "#445566")

        group_id = getattr(h.combatants[spawned[0]], "summon_group_id", "")
        self.assertEqual(h._summon_groups.get(group_id), spawned)
        self.assertEqual(h._summon_group_meta.get(group_id, {}).get("caster_cid"), 100)
        self.assertEqual(h._summon_group_meta.get(group_id, {}).get("spell"), "summon_on_start")

    def test_create_pc_from_profile_triggers_startup_summons(self):
        h = SummonHarness()
        h._normalize_action_entries = lambda *_args, **_kwargs: []
        h._spawn_startup_summons_for_pc = mock.Mock(return_value=[])
        expected_entries = [{"monster": "owl.yaml", "count": 1, "overrides": {}}]
        h._normalize_player_profile = lambda _profile, _name: {
            "name": "Eldramar",
            "resources": {},
            "vitals": {"max_hp": 20, "current_hp": 20},
            "defenses": {"hp": 20},
            "identity": {},
            "spellcasting": {},
            "summon_on_start": expected_entries,
        }

        cid = tracker_mod.InitiativeTracker._create_pc_from_profile(h, "Eldramar", {})
        self.assertIsNotNone(cid)
        h._spawn_startup_summons_for_pc.assert_called_once_with(cid, expected_entries)


    def _find_familiar_preset(self):
        return {
            "slug": "find-familiar",
            "id": "find-familiar",
            "concentration": False,
            "summon": {
                "choices": [{"name": "Owl", "monster_slug": "owl"}],
                "choice_filters": [{"type": "monster_query", "criteria": {"type": "beast", "challenge_rating": 0}}],
                "type_override": {"options": ["Celestial", "Fey", "Fiend"]},
                "count": {"kind": "fixed", "min": 1, "max": 1},
                "lifecycle": {
                    "persist_until_dismissed": True,
                    "replace_existing_same_spell": True,
                    "dismissible": True,
                    "reappear_within_range_ft": 30,
                    "ends_on_zero_hp": True,
                },
            },
        }

    def test_find_familiar_uses_spell_owned_choices_and_filters_only(self):
        h = self._build_harness()
        h._monster_specs = [
            tracker_mod.MonsterSpec(filename="owl.yaml", name="Owl", mtype="beast", cr=0, hp=1, speed=5, swim_speed=0, fly_speed=60, burrow_speed=0, climb_speed=0, dex=13, init_mod=1, saving_throws={}, ability_mods={}, raw_data={}),
            tracker_mod.MonsterSpec(filename="wolf.yaml", name="Wolf", mtype="beast", cr=0.25, hp=11, speed=40, swim_speed=0, fly_speed=0, burrow_speed=0, climb_speed=0, dex=15, init_mod=2, saving_throws={}, ability_mods={}, raw_data={}),
        ]
        h._load_monsters_index = lambda: None
        resolved, err = h._resolve_spell_summon_request(
            preset=self._find_familiar_preset(),
            summon_cfg=self._find_familiar_preset()["summon"],
            caster=h.combatants[100],
            summon_choice="wolf",
            slot_level=1,
            summon_variant=None,
            summon_quantity=None,
        )
        self.assertIsNone(resolved)
        self.assertTrue(isinstance(err, str) and err)

    def test_find_familiar_recast_replaces_existing_familiar(self):
        h = self._build_harness()
        preset = self._find_familiar_preset()
        owl = tracker_mod.MonsterSpec(filename="owl.yaml", name="Owl", mtype="beast", cr=0, hp=1, speed=5, swim_speed=0, fly_speed=60, burrow_speed=0, climb_speed=0, dex=13, init_mod=1, saving_throws={}, ability_mods={}, raw_data={})
        raven = tracker_mod.MonsterSpec(filename="raven.yaml", name="Raven", mtype="beast", cr=0, hp=1, speed=10, swim_speed=0, fly_speed=50, burrow_speed=0, climb_speed=0, dex=14, init_mod=2, saving_throws={}, ability_mods={}, raw_data={})
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: owl if slug == "owl" else raven if slug == "raven" else None
        h._monster_specs = [owl, raven]

        first = h._spawn_summons_from_cast(100, "find-familiar", "", 1, "owl", summon_variant="Fey")
        self.assertEqual(len(first), 1)
        second = h._spawn_summons_from_cast(100, "find-familiar", "", 1, "raven", summon_variant="Fiend")
        self.assertEqual(len(second), 1)
        self.assertNotIn(first[0], h.combatants)
        self.assertIn(second[0], h.combatants)

    def test_find_familiar_dismiss_and_reappear_preserve_identity(self):
        h = self._build_harness()
        preset = self._find_familiar_preset()
        owl = tracker_mod.MonsterSpec(filename="owl.yaml", name="Owl", mtype="beast", cr=0, hp=1, speed=5, swim_speed=0, fly_speed=60, burrow_speed=0, climb_speed=0, dex=13, init_mod=1, saving_throws={}, ability_mods={}, raw_data={})
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: owl if slug == "owl" else None
        h._lan_positions[100] = (10, 10)

        spawned = h._spawn_summons_from_cast(100, "find-familiar", "", 1, "owl", summon_positions=[{"col": 11, "row": 10}])
        familiar_cid = spawned[0]
        group_id = getattr(h.combatants[familiar_cid], "summon_group_id")
        removed = h._dismiss_persistent_summon_group(group_id)
        self.assertEqual(removed, 1)
        self.assertNotIn(familiar_cid, h.combatants)
        restored = h._reappear_persistent_summon_group(group_id, 100, 12, 10)
        self.assertEqual(restored, 1)
        self.assertIn(familiar_cid, h.combatants)
        self.assertEqual(getattr(h.combatants[familiar_cid], "summon_source_spell", None), "find-familiar")

    def test_find_familiar_reappear_respects_range_and_type_override_preserved(self):
        h = self._build_harness()
        preset = self._find_familiar_preset()
        owl = tracker_mod.MonsterSpec(filename="owl.yaml", name="Owl", mtype="beast", cr=0, hp=1, speed=5, swim_speed=0, fly_speed=60, burrow_speed=0, climb_speed=0, dex=13, init_mod=1, saving_throws={}, ability_mods={}, raw_data={})
        h._find_spell_preset = lambda spell_slug, spell_id: preset
        h._find_monster_spec_by_slug = lambda slug: owl if slug == "owl" else None
        h._lan_positions[100] = (0, 0)

        spawned = h._spawn_summons_from_cast(100, "find-familiar", "", 1, "owl", summon_variant="Fiend")
        familiar = h.combatants[spawned[0]]
        self.assertEqual(getattr(familiar, "summon_type_override", None), "Fiend")
        group_id = getattr(familiar, "summon_group_id")
        h._dismiss_persistent_summon_group(group_id)
        too_far = h._reappear_persistent_summon_group(group_id, 100, 7, 0)
        self.assertEqual(too_far, 0)
        in_range = h._reappear_persistent_summon_group(group_id, 100, 6, 0)
        self.assertEqual(in_range, 1)

    def test_conjure_animals_uses_pack_aoe_automation(self):
        spell = yaml.safe_load(Path("Spells/conjure-animals.yaml").read_text(encoding="utf-8"))
        mechanics = spell.get("mechanics", {})
        self.assertNotIn("summon", mechanics)
        targeting = mechanics.get("targeting", {})
        self.assertEqual(targeting.get("area", {}).get("shape"), "square")
        self.assertEqual(targeting.get("area", {}).get("side_ft"), 30)
        sequence = mechanics.get("sequence", [])
        self.assertEqual(sequence[0].get("check", {}).get("ability"), "dexterity")
        self.assertEqual(sequence[0].get("outcomes", {}).get("fail", [])[0].get("dice"), "3d10")
        appearance_options = mechanics.get("ui", {}).get("appearance_options", [])
        self.assertEqual(appearance_options, ["Wolves", "Serpents", "Birds"])



if __name__ == "__main__":
    unittest.main()
