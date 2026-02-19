import unittest
from pathlib import Path

import dnd_initative_tracker as tracker_mod


class MonsterStatBlockTests(unittest.TestCase):
    def _tracker(self):
        return object.__new__(tracker_mod.InitiativeTracker)

    def test_variant_and_slot_level_are_applied_to_payload(self):
        tracker = self._tracker()
        spec = tracker_mod.MonsterSpec(
            filename="otherworldly-steed.yaml",
            name="Otherworldly Steed",
            mtype="Celestial or Fey or Fiend",
            cr=None,
            hp=0,
            speed=60,
            swim_speed=0,
            fly_speed=60,
            burrow_speed=0,
            climb_speed=0,
            dex=12,
            init_mod=1,
            saving_throws={},
            ability_mods={},
            raw_data={
                "name": "Otherworldly Steed",
                "ac": "10 + var.slot_level",
                "hp": "5 + 10 * var.slot_level",
                "speed": {"Normal": "60 ft.", "Fly": "60 ft."},
                "abilities": {"Str": 18, "Dex": 12, "Con": 14, "Int": 6, "Wis": 12, "Cha": 8},
                "variants": [
                    {
                        "name": "Fey",
                        "damage_type": "Psychic",
                        "bonus_action": {"name": "Fey Step", "desc": "Teleport up to 30 feet."},
                    }
                ],
            },
        )

        mod = tracker._apply_monster_variant(spec, "Fey", 4)
        payload = tracker._monster_stat_block_payload(mod)

        self.assertEqual(payload["armor_class"], 14)
        self.assertEqual(payload["hit_points"], 45)
        self.assertEqual(payload["selected_variant"], "Fey")
        self.assertEqual(payload["selected_damage_type"], "Psychic")
        self.assertEqual(len(payload["bonus_actions"]), 1)

    def test_recharge_text_is_extracted(self):
        tracker = self._tracker()
        spec = tracker_mod.MonsterSpec(
            filename="young-red-dragon.yaml",
            name="Young Red Dragon",
            mtype="Dragon",
            cr=10,
            hp=178,
            speed=40,
            swim_speed=0,
            fly_speed=80,
            burrow_speed=0,
            climb_speed=40,
            dex=10,
            init_mod=0,
            saving_throws={},
            ability_mods={},
            raw_data={
                "actions": [
                    {"name": "Fire Breath (Recharge 5-6)", "desc": "Burn them all."},
                    {"name": "Bite", "desc": "Nom."},
                ]
            },
        )

        payload = tracker._monster_stat_block_payload(spec)
        self.assertEqual(payload["recharge"], ["Fire Breath (Recharge 5-6)"])

    def test_payload_uses_local_monster_image_when_present(self):
        tracker = self._tracker()
        image_dir = Path(tracker_mod.__file__).parent / "Monsters" / "Images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "unit-test-monster.jpg"

        try:
            image_path.write_bytes(b"\xff\xd8\xff\xd9")
            spec = tracker_mod.MonsterSpec(
                filename="unit-test-monster.yaml",
                name="Unit Test Monster",
                mtype="Beast",
                cr=1,
                hp=10,
                speed=30,
                swim_speed=0,
                fly_speed=0,
                burrow_speed=0,
                climb_speed=0,
                dex=10,
                init_mod=0,
                saving_throws={},
                ability_mods={},
                raw_data={},
            )

            payload = tracker._monster_stat_block_payload(spec)
            self.assertEqual(payload.get("image_url"), "/monsters/images/unit-test-monster.jpg")
            self.assertNotIn("image_proxy_url", payload)
        finally:
            try:
                image_path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
