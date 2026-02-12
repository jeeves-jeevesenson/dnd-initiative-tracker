import unittest

import dnd_initative_tracker as tracker_mod


class LanClaimableTests(unittest.TestCase):
    def test_claimable_uses_is_pc(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Alice (Wolf)", "is_pc": True})(),
            2: type("C", (), {"cid": 2, "name": "Goblin", "is_pc": False})(),
        }
        app._name_role_memory = {}
        pcs = app._lan_claimable()
        self.assertEqual(pcs, [{"cid": 1, "name": "Alice (Wolf)"}])


if __name__ == "__main__":
    unittest.main()
