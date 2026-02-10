import threading
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

import dnd_initative_tracker as tracker_mod


class _RequestStub:
    def __init__(self, host: str, headers=None, query_params=None):
        self.client = SimpleNamespace(host=host)
        self.headers = headers or {}
        self.query_params = query_params or {}


class _FakeTracker:
    def __init__(self):
        self.combatants = {}


class PlanningAuthTests(unittest.TestCase):
    def _build_controller(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = _FakeTracker()
        lan._clients_lock = threading.RLock()
        lan._cid_to_host = {}
        lan._cached_pcs = []
        lan._client_id_claims = {}
        lan._is_host_allowed = lambda host: host == "10.0.0.10"
        lan._is_admin_token_valid = lambda token: token == "valid-admin-token"
        return lan

    def _add_combatant(self, lan, cid: int, name: str):
        lan.app.combatants[cid] = SimpleNamespace(cid=cid, name=name)
        lan._cached_pcs.append({"cid": cid, "name": name})

    def test_assigned_host_claim_resolves_to_character_cid(self):
        lan = self._build_controller()
        self._add_combatant(lan, 7, "Aelar")
        lan._cid_to_host = {7: {"10.0.0.10"}}

        req = _RequestStub(host="10.0.0.10")
        auth = lan._resolve_planning_auth(req)

        self.assertFalse(auth["is_admin"])
        self.assertEqual(auth["player_cid"], 7)

    def test_planning_snapshot_requires_claim_for_non_admin(self):
        lan = self._build_controller()
        req = _RequestStub(host="10.0.0.10")

        with self.assertRaises(HTTPException) as exc_info:
            lan._resolve_planning_auth(req)

        self.assertEqual(exc_info.exception.status_code, 401)

    def test_admin_token_bypasses_claim_requirement(self):
        lan = self._build_controller()
        req = _RequestStub(
            host="10.0.0.10",
            headers={"authorization": "Bearer valid-admin-token"},
        )

        auth = lan._resolve_planning_auth(req)

        self.assertTrue(auth["is_admin"])
        self.assertIsNone(auth["player_cid"])

    def test_planning_endpoints_reject_unauthorized_hosts(self):
        lan = self._build_controller()
        req = _RequestStub(host="192.168.1.55")

        with self.assertRaises(HTTPException) as exc_info:
            lan._resolve_planning_auth(req)

        self.assertEqual(exc_info.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
