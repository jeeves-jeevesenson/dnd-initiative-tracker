import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class SummonHarness:
    def __init__(self):
        self.combatants = {}
        self._summon_groups = {}
        self._summon_group_meta = {}
        self._next_cid = 1

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
        )
        self.combatants[cid] = c
        return cid

    # Bind target methods from InitiativeTracker
    _resolve_summon_choice = staticmethod(tracker_mod.InitiativeTracker._resolve_summon_choice)
    _normalize_summon_controller_mode = staticmethod(tracker_mod.InitiativeTracker._normalize_summon_controller_mode)
    _apply_summon_initiative = tracker_mod.InitiativeTracker._apply_summon_initiative
    _spawn_summons_from_cast = tracker_mod.InitiativeTracker._spawn_summons_from_cast
    _sorted_combatants = tracker_mod.InitiativeTracker._sorted_combatants


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

    def test_rolled_initiative_assigns_distinct_values_and_sorts(self):
        h = self._build_harness()
        s1 = h._create_combatant("S1", 10, 30, 1, 0, True)
        s2 = h._create_combatant("S2", 10, 30, 1, 0, True)
        s3 = h._create_combatant("S3", 10, 30, 1, 0, True)

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[18, 9, 14]):
            h._apply_summon_initiative(100, [s1, s2, s3], {"initiative": {"mode": "rolled_per_creature"}})

        initiatives = [h.combatants[s1].initiative, h.combatants[s2].initiative, h.combatants[s3].initiative]
        self.assertEqual(initiatives, [18, 9, 14])
        self.assertEqual(len(set(initiatives)), 3)

        order = [c.cid for c in h._sorted_combatants()]
        # caster stays first at 15, then summons by rolled values 18,14,9 are globally sorted among all combatants
        self.assertEqual(order[:4], [s1, 100, s3, s2])


if __name__ == "__main__":
    unittest.main()
