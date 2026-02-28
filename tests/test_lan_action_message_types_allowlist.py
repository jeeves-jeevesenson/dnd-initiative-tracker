import unittest

import dnd_initative_tracker as tracker_mod


class LanActionMessageTypesAllowlistTests(unittest.TestCase):
    def test_lan_controller_action_types_include_bard_and_glamour_actions(self):
        required_types = {
            "beguiling_magic_use",
            "beguiling_magic_restore",
            "command_resolve",
            "bardic_inspiration_grant",
            "bardic_inspiration_use",
            "mantle_of_inspiration",
            "reaction_prefs_update",
            "reaction_response",
        }
        action_types = set(tracker_mod.LanController._ACTION_MESSAGE_TYPES)
        self.assertTrue(required_types.issubset(action_types))
        self.assertIn("command_resolve", action_types)


if __name__ == "__main__":
    unittest.main()
