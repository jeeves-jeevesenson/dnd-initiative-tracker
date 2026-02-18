import importlib.util
import pathlib
import sys
import unittest


def _load_backfill_module():
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_monster_sections.py"
    spec = importlib.util.spec_from_file_location("backfill_monster_sections", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backfill = _load_backfill_module()


class MonsterBackfillPipelineTests(unittest.TestCase):
    def test_extract_sections_from_aidedd_html(self):
        raw_html = """
        <html><body>
          <h3>Traits</h3>
          <p><strong>Keen Smell.</strong> The wolf has Advantage on Wisdom (Perception) checks that rely on smell.</p>
          <h3>Actions</h3>
          <p><strong>Bite.</strong> Melee Attack Roll: +4, reach 5 ft. Hit: 7 (2d4 + 2) Piercing damage.</p>
          <h3>Legendary Actions</h3>
          <p><strong>Move.</strong> The wolf moves up to half its Speed.</p>
        </body></html>
        """

        sections = backfill.extract_sections_from_aidedd_html(raw_html)

        self.assertEqual(
            sections["traits"],
            [
                {
                    "name": "Keen Smell",
                    "desc": "The wolf has Advantage on Wisdom (Perception) checks that rely on smell.",
                }
            ],
        )
        self.assertEqual(
            sections["actions"],
            [{"name": "Bite", "desc": "Melee Attack Roll: +4, reach 5 ft. Hit: 7 (2d4 + 2) Piercing damage."}],
        )
        self.assertEqual(
            sections["legendary_actions"],
            [{"name": "Move", "desc": "The wolf moves up to half its Speed."}],
        )

    def test_extract_sections_from_5etools_monster(self):
        monster = {
            "trait": [{"name": "Pack Tactics", "entries": ["The wolf has Advantage when an ally is nearby."]}],
            "action": [
                {
                    "name": "Bite",
                    "entries": [
                        "Melee Attack Roll: +4, reach 5 ft.",
                        {"type": "entries", "entries": ["Hit: 7 (2d4 + 2) Piercing damage."]},
                    ],
                }
            ],
            "legendary": [{"name": "Move", "entries": ["The wolf moves up to half its Speed."]}],
        }

        sections = backfill.extract_sections_from_5etools_monster(monster)

        self.assertEqual(
            sections["traits"],
            [{"name": "Pack Tactics", "desc": "The wolf has Advantage when an ally is nearby."}],
        )
        self.assertEqual(
            sections["actions"],
            [{"name": "Bite", "desc": "Melee Attack Roll: +4, reach 5 ft. Hit: 7 (2d4 + 2) Piercing damage."}],
        )
        self.assertEqual(
            sections["legendary_actions"],
            [{"name": "Move", "desc": "The wolf moves up to half its Speed."}],
        )

    def test_apply_sections_uses_fallback_when_primary_missing(self):
        existing = {"name": "Wolf"}
        primary = {
            "traits": [{"name": "Keen Smell", "desc": "Primary"}],
            "actions": [],
            "legendary_actions": [],
        }
        fallback = {
            "traits": [{"name": "Keen Smell", "desc": "Fallback"}],
            "actions": [{"name": "Bite", "desc": "Fallback bite"}],
            "legendary_actions": [],
        }

        changed = backfill._apply_sections(existing, primary=primary, fallback=fallback)

        self.assertTrue(changed)
        self.assertEqual(existing["traits"], [{"name": "Keen Smell", "desc": "Primary"}])
        self.assertEqual(existing["actions"], [{"name": "Bite", "desc": "Fallback bite"}])
        self.assertEqual(existing["legendary_actions"], [])


if __name__ == "__main__":
    unittest.main()
