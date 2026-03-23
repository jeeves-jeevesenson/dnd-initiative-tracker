import pytest

pytest.importorskip("httpx")

import threading
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import dnd_initative_tracker as tracker_mod


class _AppStub:
    combatants = {}

    def _oplog(self, *_args, **_kwargs):
        return None

    def _lan_snapshot(self):
        return {"grid": None, "obstacles": [], "units": [], "active_cid": None, "round_num": 0}

    def _lan_pcs(self):
        return []

    def after(self, *_args, **_kwargs):
        return None

    def _load_shop_catalog_normalized(self):
        return []


class ShopCatalogApiTests(unittest.TestCase):
    def _build_lan_controller(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = _AppStub()
        lan.cfg = types.SimpleNamespace(host="127.0.0.1", port=0, vapid_public_key=None, allowlist=[], denylist=[], admin_password=None)
        lan._server_thread = None
        lan._fastapi_app = None
        lan._polling = False
        lan._cached_snapshot = {}
        lan._cached_pcs = []
        lan._clients_lock = threading.RLock()
        lan._actions = None
        lan._best_lan_url = lambda: "http://127.0.0.1:0"
        lan._tick = lambda: None
        lan._append_lan_log = lambda *_args, **_kwargs: None
        lan._init_admin_auth = lambda: None
        lan._admin_password_hash = None
        lan._admin_token_ttl_seconds = 900
        lan._save_push_subscription = lambda *_args, **_kwargs: True
        lan._admin_password_matches = lambda *_args, **_kwargs: False
        lan._issue_admin_token = lambda: "token"
        return lan

    def _build_test_client(self):
        lan = self._build_lan_controller()
        with mock.patch("threading.Thread.start", return_value=None):
            lan.start(quiet=True)
        return TestClient(lan._fastapi_app), lan

    def test_shop_catalog_defaults_to_enabled_entries_with_stable_sort(self):
        client, lan = self._build_test_client()
        with mock.patch.object(
            lan.app,
            "_load_shop_catalog_normalized",
            return_value=[
                {
                    "item_id": "healing_potion",
                    "item_bucket": "consumable",
                    "name": "Healing Potion",
                    "type": "consumable",
                    "shop_category": "consumables",
                    "enabled": False,
                    "price": {"gp": 50},
                    "definition_path": "Items/Consumables/healing_potion.yaml",
                },
                {
                    "item_id": "dagger",
                    "item_bucket": "weapon",
                    "name": "Dagger",
                    "type": "weapon",
                    "shop_category": "weapons",
                    "enabled": True,
                    "price": {"gp": 2},
                    "definition_path": "Items/Weapons/dagger.yaml",
                },
                {
                    "item_id": "apple",
                    "item_bucket": "consumable",
                    "name": "Apple",
                    "type": "consumable",
                    "shop_category": "consumables",
                    "enabled": True,
                    "price": {"cp": 5},
                    "definition_path": "Items/Consumables/apple.yaml",
                },
            ],
        ):
            response = client.get("/api/shop/catalog")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        entries = payload.get("entries")
        self.assertIsInstance(entries, list)
        self.assertEqual(2, len(entries))
        self.assertEqual(["apple", "dagger"], [row.get("item_id") for row in entries])
        for row in entries:
            for field in (
                "item_id",
                "item_bucket",
                "name",
                "type",
                "shop_category",
                "enabled",
                "price",
                "definition_path",
            ):
                self.assertIn(field, row)
            self.assertTrue(row.get("enabled"))

    def test_shop_catalog_include_disabled_true_returns_all_entries(self):
        client, lan = self._build_test_client()
        normalized = [
            {
                "item_id": "ring_mail",
                "item_bucket": "armor",
                "name": "Ring Mail",
                "type": "armor",
                "shop_category": "armor",
                "enabled": True,
                "price": {"gp": 30},
                "definition_path": "Items/Armor/ring_mail.yaml",
            },
            {
                "item_id": "healing_potion",
                "item_bucket": "consumable",
                "name": "Healing Potion",
                "type": "consumable",
                "shop_category": "consumables",
                "enabled": False,
                "price": {"gp": 50},
                "definition_path": "Items/Consumables/healing_potion.yaml",
            },
        ]
        with mock.patch.object(lan.app, "_load_shop_catalog_normalized", return_value=normalized):
            response = client.get("/api/shop/catalog?include_disabled=true")

        self.assertEqual(response.status_code, 200)
        entries = response.json().get("entries") or []
        self.assertEqual(2, len(entries))
        self.assertEqual({"ring_mail", "healing_potion"}, {row.get("item_id") for row in entries})

    def test_shop_catalog_loader_failure_returns_http_500_with_detail(self):
        client, lan = self._build_test_client()
        with mock.patch.object(lan.app, "_load_shop_catalog_normalized", side_effect=ValueError("catalog broken")):
            response = client.get("/api/shop/catalog")

        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to load shop catalog", response.json().get("detail", ""))
        self.assertIn("catalog broken", response.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
