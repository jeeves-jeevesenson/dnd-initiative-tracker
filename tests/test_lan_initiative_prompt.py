import threading
import unittest
from unittest.mock import patch

import dnd_initative_tracker as tracker_mod


class RollLanInitiativeTests(unittest.TestCase):
    def _build_app(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app.combatants = {}
        app._name_role_memory = {}
        return app

    def test_roll_lan_initiative_prompts_only_claimed_player_characters(self):
        app = self._build_app()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Fred", "is_pc": True})(),
            2: type("C", (), {"cid": 2, "name": "Goblin", "is_pc": False})(),
            3: type("C", (), {"cid": 3, "name": "Dorian", "is_pc": True})(),
        }

        sent = []
        lan = type("LanStub", (), {})()
        lan._clients_lock = threading.RLock()
        lan._cid_to_ws = {3: {42}, 2: {99}}
        lan._view_only_clients = set()
        lan.is_running = lambda: True
        lan.send_initiative_prompt = lambda ws_id, cid, name: sent.append((ws_id, cid, name))
        app._lan = lan

        with patch("dnd_initative_tracker.messagebox.showinfo") as showinfo:
            app._roll_lan_initiative_for_claimed_pcs()

        self.assertEqual(sent, [(42, 3, "Dorian")])
        showinfo.assert_called_once()
        self.assertIn("Prompted 1 player character(s): Dorian", showinfo.call_args.args[1])

    def test_roll_lan_initiative_shows_notice_when_no_claimed_players(self):
        app = self._build_app()
        app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Fred", "is_pc": True})(),
        }

        lan = type("LanStub", (), {})()
        lan._clients_lock = threading.RLock()
        lan._cid_to_ws = {}
        lan._view_only_clients = set()
        lan.is_running = lambda: True
        lan.send_initiative_prompt = lambda ws_id, cid, name: None
        app._lan = lan

        with patch("dnd_initative_tracker.messagebox.showinfo") as showinfo:
            app._roll_lan_initiative_for_claimed_pcs()

        showinfo.assert_called_once()
        self.assertIn("No claimed player characters", showinfo.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
