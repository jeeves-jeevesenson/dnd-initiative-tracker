import threading
import unittest
from types import SimpleNamespace

import dnd_initative_tracker as tracker_mod


class PlanningChatNameResolutionTests(unittest.TestCase):
    def _build_controller(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = SimpleNamespace(combatants={})
        lan._clients_lock = threading.RLock()
        lan._cid_to_host = {}
        lan._cached_pcs = []
        return lan

    def test_returns_assigned_character_name_for_host(self):
        lan = self._build_controller()
        lan.app.combatants[5] = SimpleNamespace(cid=5, name="Mira")
        lan._cached_pcs.append({"cid": 5, "name": "Mira"})
        lan._cid_to_host = {5: {"10.0.0.22"}}

        self.assertEqual(lan._assigned_character_name_for_host("10.0.0.22"), "Mira")

    def test_ignores_cid_style_name_and_returns_none(self):
        lan = self._build_controller()
        lan.app.combatants[12] = SimpleNamespace(cid=12, name="cid:12")
        lan._cached_pcs.append({"cid": 12, "name": "cid:12"})
        lan._cid_to_host = {12: {"10.0.0.33"}}

        self.assertIsNone(lan._assigned_character_name_for_host("10.0.0.33"))


if __name__ == "__main__":
    unittest.main()
