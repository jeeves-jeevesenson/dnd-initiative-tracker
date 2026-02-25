import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class DmMapAttackAutomationTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._queue_concentration_save = lambda *_args, **_kwargs: None
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._death_flavor_line = lambda attacker, amount, dtype, target: f"{attacker} downs {target} with {amount} {dtype}".strip()
        self.app._lan = None
        self.app.start_cid = None

    def test_monster_attack_options_parse_slaad_actions_and_multiattack_counts(self):
        attacker = type(
            "Combatant",
            (),
            {
                "monster_spec": type(
                    "Spec",
                    (),
                    {
                        "raw_data": {
                            "actions": [
                                {
                                    "name": "Multiattack",
                                    "desc": "The slaad makes three attacks: one with its bite and two with its claws or greatsword.",
                                },
                                {
                                    "name": "Bite (Slaad Form Only)",
                                    "desc": "{@atk mw} {@hit 9} to hit, reach 5 ft., one target. {@h}9 ({@damage 1d8 + 5}) piercing damage plus 7 ({@damage 2d6}) necrotic damage.",
                                },
                                {
                                    "name": "Claws (Slaad Form Only)",
                                    "desc": "{@atk mw} {@hit 9} to hit, reach 5 ft., one target. {@h}10 ({@damage 1d10 + 5}) slashing damage plus 7 ({@damage 2d6}) necrotic damage.",
                                },
                                {
                                    "name": "Greatsword",
                                    "desc": "{@atk mw} {@hit 9} to hit, reach 5 ft., one target. {@h}12 ({@damage 2d6 + 5}) slashing damage plus 7 ({@damage 2d6}) necrotic damage.",
                                },
                            ]
                        }
                    },
                )()
            },
        )()

        options, counts = self.app._monster_attack_options_for_map(attacker)

        by_name = {str(entry.get("name")): entry for entry in options}
        self.assertIn("Bite (Slaad Form Only)", by_name)
        self.assertIn("Claws (Slaad Form Only)", by_name)
        self.assertIn("Greatsword", by_name)
        self.assertEqual(by_name["Bite (Slaad Form Only)"]["to_hit"], 9)
        self.assertEqual(
            by_name["Bite (Slaad Form Only)"]["damage_entries"],
            [{"formula": "1d8 + 5", "type": "piercing"}, {"formula": "2d6", "type": "necrotic"}],
        )
        self.assertEqual(counts.get("__total__"), 3)
        self.assertEqual(counts.get("bite"), 1)
        self.assertEqual(counts.get("claws"), 2)
        self.assertEqual(counts.get("greatsword"), 2)

    def test_resolve_map_attack_rolls_to_hit_and_reports_manual_damage_rolls(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}

        attack_option = {
            "name": "Claws",
            "to_hit": 9,
            "damage_entries": [
                {"formula": "1d10 + 5", "type": "slashing"},
                {"formula": "2d6", "type": "necrotic"},
            ],
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[12, 4]):
            result = self.app._resolve_map_attack(1, 2, attack_option, attack_count=2)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("hits"), 1)
        self.assertEqual(result.get("misses"), 1)
        self.assertEqual(result.get("total_damage"), 0)
        self.assertEqual(self.app.combatants[2].hp, 30)
        self.assertEqual(
            result.get("damage_rolls"),
            [
                {"formula": "1d10 + 5", "type": "slashing", "count": 1},
                {"formula": "2d6", "type": "necrotic", "count": 1},
            ],
        )
        self.assertEqual(result.get("damage_types"), ["slashing", "necrotic"])
        self.assertTrue(any("roll damage manually" in message for _cid, message in self.logs))

    def test_apply_map_attack_manual_damage_updates_hp_and_logs_components(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}

        result = self.app._apply_map_attack_manual_damage(
            1,
            2,
            "Claws",
            [
                {"amount": 9, "type": "slashing"},
                {"amount": 5, "type": "necrotic"},
            ],
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 14)
        self.assertEqual(self.app.combatants[2].hp, 16)
        self.assertTrue(any("applies 14 damage" in message for _cid, message in self.logs))

    def test_apply_map_attack_manual_damage_accepts_simple_addition_expressions(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}

        parsed_entries = []
        amount_inputs = {"slashing": "2+3", "necrotic": "4+1"}
        for dtype, raw in amount_inputs.items():
            evaluated = self.app._evaluate_spell_formula(raw, {})
            amount = int(evaluated) if evaluated is not None else 0
            if amount > 0:
                parsed_entries.append({"amount": amount, "type": dtype})

        result = self.app._apply_map_attack_manual_damage(1, 2, "Claws", parsed_entries)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 10)
        self.assertEqual(self.app.combatants[2].hp, 20)

    def test_apply_map_attack_manual_damage_applies_resistance_and_immunity(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        target.monster_spec = type(
            "Spec",
            (),
            {"raw_data": {"damage_resistances": ["necrotic"], "damage_immunities": ["poison"]}},
        )()
        self.app.combatants = {1: attacker, 2: target}

        result = self.app._apply_map_attack_manual_damage(
            1,
            2,
            "Claws",
            [
                {"amount": 10, "type": "slashing"},
                {"amount": 10, "type": "necrotic"},
                {"amount": 10, "type": "poison"},
            ],
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 15)
        self.assertEqual(self.app.combatants[2].hp, 15)

    def test_resolve_map_attack_sequence_advantage_and_disadvantage_keep_correct_die(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 30, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        attack_option = {"name": "Claws", "key": "claws", "to_hit": 9, "damage_entries": [{"formula": "1d10 + 5", "type": "slashing"}]}

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[1, 20, 1, 20]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [
                    {"attack_option": attack_option, "attack_key": "claws", "count": 1, "roll_mode": "advantage"},
                    {"attack_option": attack_option, "attack_key": "claws", "count": 1, "roll_mode": "disadvantage"},
                ],
            )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("hits"), 1)
        self.assertEqual(result.get("crit_hits"), 1)
        self.assertEqual(result.get("misses"), 1)
        blocks = result.get("sequence_blocks") or []
        self.assertEqual(blocks[0].get("crit_hits"), 1)
        self.assertEqual(blocks[1].get("misses"), 1)
        self.assertTrue(any("advantage, kept 20" in message for _cid, message in self.logs))
        self.assertTrue(any("disadvantage, kept 1" in message for _cid, message in self.logs))

    def test_resolve_map_attack_sequence_keeps_block_order_and_aggregates_damage_templates(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        bite = {"name": "Bite", "key": "bite", "to_hit": 9, "damage_entries": [{"formula": "1d8 + 5", "type": "piercing"}]}
        claws = {"name": "Claws", "key": "claws", "to_hit": 9, "damage_entries": [{"formula": "1d10 + 5", "type": "slashing"}]}

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[10, 6, 1]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [
                    {"attack_option": bite, "attack_key": "bite", "count": 1, "roll_mode": "normal"},
                    {"attack_option": claws, "attack_key": "claws", "count": 2, "roll_mode": "normal"},
                ],
            )

        self.assertTrue(result.get("ok"))
        blocks = result.get("sequence_blocks") or []
        self.assertEqual([block.get("attack_name") for block in blocks], ["Bite", "Claws"])
        self.assertEqual(result.get("hits"), 2)
        self.assertEqual(result.get("misses"), 1)
        self.assertEqual(
            result.get("damage_rolls"),
            [
                {"formula": "1d8 + 5", "type": "piercing", "count": 1},
                {"formula": "1d10 + 5", "type": "slashing", "count": 1},
            ],
        )

    def test_resolve_map_attack_sequence_stops_when_target_removed_mid_sequence(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        attack_option = {"name": "Claws", "key": "claws", "to_hit": 9, "damage_entries": [{"formula": "1d10 + 5", "type": "slashing"}]}

        def pop_target_on_first_attack(message, cid=None):
            self.logs.append((cid, message))
            if "attack 1/1" in message and 2 in self.app.combatants:
                self.app.combatants.pop(2, None)

        self.app._log = pop_target_on_first_attack
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[10]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [
                    {"attack_option": attack_option, "attack_key": "claws", "count": 1, "roll_mode": "normal"},
                    {"attack_option": attack_option, "attack_key": "claws", "count": 2, "roll_mode": "normal"},
                ],
            )

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("target_removed"))
        self.assertEqual(len(result.get("sequence_blocks") or []), 1)


if __name__ == "__main__":
    unittest.main()
