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


if __name__ == "__main__":
    unittest.main()
