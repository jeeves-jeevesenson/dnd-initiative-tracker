import unittest

from character_autofill import (
    highest_class_save_proficiencies,
    hit_dice_from_classes,
    proficiency_bonus_for_level,
    slugify_filename,
    total_level,
)


class CharacterAutofillTests(unittest.TestCase):
    def test_proficiency_bonus_progression(self):
        self.assertEqual(proficiency_bonus_for_level(1), 2)
        self.assertEqual(proficiency_bonus_for_level(4), 2)
        self.assertEqual(proficiency_bonus_for_level(5), 3)
        self.assertEqual(proficiency_bonus_for_level(9), 4)
        self.assertEqual(proficiency_bonus_for_level(13), 5)
        self.assertEqual(proficiency_bonus_for_level(17), 6)

    def test_hit_dice_for_multiclass(self):
        dice = hit_dice_from_classes([
            {"name": "Wizard", "level": 1},
            {"name": "Barbarian", "level": 1},
            {"name": "Fighter", "level": 2},
        ])
        self.assertEqual(dice, [
            {"die": "d12", "total": 1, "current": 1},
            {"die": "d10", "total": 2, "current": 2},
            {"die": "d6", "total": 1, "current": 1},
        ])

    def test_saving_throw_highest_class_and_tiebreak(self):
        saves = highest_class_save_proficiencies([
            {"name": "Rogue", "level": 3},
            {"name": "Fighter", "level": 3},
        ])
        self.assertEqual(saves, ["dex", "int"])

    def test_total_level_uses_classes_first(self):
        self.assertEqual(total_level([{"name": "Wizard", "level": 2}, {"name": "Cleric", "level": 3}], 1), 5)
        self.assertEqual(total_level([], 4), 4)

    def test_slugify_filename(self):
        self.assertEqual(slugify_filename("John Twilight"), "john_twilight")
        self.assertEqual(slugify_filename("Mara O'Neil"), "mara_o_neil")


if __name__ == "__main__":
    unittest.main()
