import unittest

import dnd_initative_tracker as tracker_mod


class DmTurnAlertTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app.combatants = {}

    def _set_claims(self, claimed_cids):
        payload = {str(cid): f"client-{cid}" for cid in claimed_cids}
        self.app._lan = type("LanStub", (), {"_claims_payload": lambda _self: dict(payload)})()

    def test_claimed_pc_to_unclaimed_npc_alerts(self):
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "is_pc": True})(),
            2: type("C", (), {"cid": 2, "is_pc": False})(),
        }
        self._set_claims({1})

        self.assertTrue(self.app._should_show_dm_up_alert(1, 2))

    def test_unclaimed_npc_to_unclaimed_npc_does_not_alert(self):
        self.app.combatants = {
            3: type("C", (), {"cid": 3, "is_pc": False})(),
            4: type("C", (), {"cid": 4, "is_pc": False})(),
        }
        self._set_claims(set())

        self.assertFalse(self.app._should_show_dm_up_alert(3, 4))

    def test_claimed_pc_to_claimed_pc_does_not_alert(self):
        self.app.combatants = {
            5: type("C", (), {"cid": 5, "is_pc": True})(),
            6: type("C", (), {"cid": 6, "is_pc": True})(),
        }
        self._set_claims({5, 6})

        self.assertFalse(self.app._should_show_dm_up_alert(5, 6))

    def test_unclaimed_pc_to_unclaimed_npc_does_not_alert(self):
        self.app.combatants = {
            7: type("C", (), {"cid": 7, "is_pc": True})(),
            8: type("C", (), {"cid": 8, "is_pc": False})(),
        }
        self._set_claims(set())

        self.assertFalse(self.app._should_show_dm_up_alert(7, 8))


if __name__ == "__main__":
    unittest.main()
