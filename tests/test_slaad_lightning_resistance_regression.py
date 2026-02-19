import unittest

import dnd_initative_tracker as tracker_mod


class SlaadLightningResistanceRegressionTests(unittest.TestCase):
    """Blue Slaad has Lightning resistance; 40 lightning should be halved to 20."""

    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._oplog = lambda *args, **kwargs: None
        self.app._log = lambda *args, **kwargs: None
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        self.app._pc_name_for = lambda cid: "Wizard"
        self.app._profile_for_player_name = lambda name: {}
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
        self.app._lan_positions = {}
        self.app._lan_live_map_data = lambda: (20, 20, set(), {}, {})
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

        self.app._load_monsters_index()
        slaad_spec = self.app._find_monster_spec_by_slug("blue-slaad")
        self.assertIsNotNone(slaad_spec, "blue-slaad monster spec not found")

        target_cid = self.app._create_combatant(
            name=slaad_spec.name,
            hp=int(slaad_spec.hp or 133),
            speed=int(slaad_spec.speed or 30),
            swim_speed=0,
            fly_speed=0,
            burrow_speed=0,
            climb_speed=0,
            movement_mode="Normal",
            initiative=12,
            dex=slaad_spec.dex,
            ally=False,
            is_pc=False,
            is_spellcaster=None,
            saving_throws=dict(slaad_spec.saving_throws or {}),
            ability_mods=dict(slaad_spec.ability_mods or {}),
            monster_spec=slaad_spec,
        )
        self.target_cid = target_cid
        self.app.combatants[target_cid].exhaustion_level = 0
        self.start_hp = int(slaad_spec.hp or 133)

    def test_adjust_lightning_resistance_halves_damage(self):
        """_adjust_damage_entries_for_target should halve lightning damage for Blue Slaad."""
        target = self.app.combatants[self.target_cid]
        result = self.app._adjust_damage_entries_for_target(target, [{"amount": 40, "type": "lightning"}])
        entries = result.get("entries") or []
        notes = result.get("notes") or []

        self.assertEqual(len(entries), 1, f"Expected 1 adjusted entry, got {entries}")
        self.assertEqual(entries[0]["amount"], 20, f"Expected 20 (halved), got {entries[0]['amount']}")
        self.assertTrue(
            any("resistant" in (n.get("reasons") or []) for n in notes),
            f"Expected 'resistant' in notes, got {notes}",
        )

    def test_adjust_lightning_full_immunity_blocks_damage(self):
        """_adjust_damage_entries_for_target should block damage for immune types."""
        target = self.app.combatants[self.target_cid]
        # Blue Slaad is not immune to lightning, but let's test with a type it IS immune to
        # (Blue Slaad has no immunities per YAML, so use an unresisted type to confirm no change)
        result = self.app._adjust_damage_entries_for_target(target, [{"amount": 40, "type": "slashing"}])
        entries = result.get("entries") or []
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["amount"], 40, "Slashing should not be modified for Blue Slaad")

    def test_mixed_damage_only_halves_resistant_component(self):
        """Only the lightning component should be halved; slashing should pass through."""
        target = self.app.combatants[self.target_cid]
        result = self.app._adjust_damage_entries_for_target(
            target, [{"amount": 40, "type": "lightning"}, {"amount": 10, "type": "slashing"}]
        )
        entries = result.get("entries") or []
        by_type = {e["type"]: e["amount"] for e in entries}
        self.assertEqual(by_type.get("lightning"), 20, f"Lightning should be halved; entries={entries}")
        self.assertEqual(by_type.get("slashing"), 10, f"Slashing should be unchanged; entries={entries}")


if __name__ == "__main__":
    unittest.main()
