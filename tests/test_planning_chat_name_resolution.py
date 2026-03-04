import threading
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import dnd_initative_tracker as tracker_mod


class PlanningChatNameResolutionTests(unittest.TestCase):
    def _build_controller(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = SimpleNamespace(combatants={})
        lan._clients_lock = threading.RLock()
        lan._cid_to_host = {}
        lan._cached_pcs = []
        lan._planning_chat_history = deque(maxlen=200)
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

    def test_planning_chat_avatar_key_uses_yaml_stem(self):
        lan = self._build_controller()
        lan.app._find_player_profile_path = lambda _name: Path("/tmp/players/john-twilight.yaml")

        self.assertEqual(lan._planning_chat_avatar_key_for_name("John Twilight"), "john-twilight")

    def test_planning_chat_avatar_key_empty_without_profile_path(self):
        lan = self._build_controller()
        lan.app._find_player_profile_path = lambda _name: None

        self.assertEqual(lan._planning_chat_avatar_key_for_name("Unknown"), "")

    def test_planning_chat_record_and_snapshot(self):
        lan = self._build_controller()
        lan._planning_chat_record(
            {
                "type": "planning_chat",
                "ts": "2026-03-04T00:00:00Z",
                "host": "10.0.0.12",
                "name": "Mira",
                "avatar_key": "mira",
                "text": "hello",
            }
        )

        snapshot = lan._planning_chat_history_snapshot()
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["text"], "hello")
        self.assertEqual(snapshot[0]["type"], "planning_chat")

    def test_planning_chat_record_enforces_history_limit(self):
        lan = self._build_controller()
        for idx in range(250):
            lan._planning_chat_record(
                {
                    "ts": f"2026-03-04T00:00:{idx:02d}Z",
                    "host": "10.0.0.44",
                    "name": "Mira",
                    "text": f"msg-{idx}",
                }
            )

        snapshot = lan._planning_chat_history_snapshot()
        self.assertEqual(len(snapshot), 200)
        self.assertEqual(snapshot[0]["text"], "msg-50")
        self.assertEqual(snapshot[-1]["text"], "msg-249")


if __name__ == "__main__":
    unittest.main()
