import pytest

pytest.importorskip("httpx")

import threading
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import dnd_initative_tracker as tracker_mod


class _AppStub:
    def _oplog(self, *_args, **_kwargs):
        return None

    def _lan_snapshot(self):
        return {"grid": None, "obstacles": [], "units": [], "active_cid": None, "round_num": 0}

    def _lan_pcs(self):
        return []

    def after(self, *_args, **_kwargs):
        return None

    def _list_character_filenames(self):
        return ["hero.yaml"]

    def _upload_character_yaml_payload(self, payload):
        return {"filename": payload.get("filename", "hero.yaml"), "character": {}}

    def _character_schema_config(self):
        return tracker_mod._CHARACTER_SCHEMA_CONFIG or {}

    def _character_schema_readme_map(self):
        return tracker_mod._CHARACTER_SCHEMA_README_MAP or {}


class EditCharacterRoutesTests(unittest.TestCase):
    def _build_lan_controller(self):
        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = _AppStub()
        lan.cfg = types.SimpleNamespace(host="127.0.0.1", port=0, vapid_public_key=None)
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
        return TestClient(lan._fastapi_app)

    def test_edit_character_page_contains_expected_shell_and_asset_paths(self):
        client = self._build_test_client()

        response = client.get("/edit_character")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="character-form"', response.text)
        self.assertIn('id="character-select"', response.text)
        self.assertIn('id="upload-yaml-input"', response.text)
        self.assertIn('/assets/web/edit_character/app.js', response.text)

    def test_edit_character_assets_are_served(self):
        client = self._build_test_client()

        js_response = client.get("/assets/web/edit_character/app.js")
        css_response = client.get("/assets/web/edit_character/styles.css")

        self.assertEqual(js_response.status_code, 200)
        self.assertEqual(css_response.status_code, 200)

    def test_config_redirects_to_edit_character(self):
        client = self._build_test_client()

        response = client.get("/config", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/edit_character"))

    def test_upload_character_yaml_route_accepts_payload(self):
        client = self._build_test_client()

        response = client.post("/api/characters/upload", json={"filename": "hero.yaml", "yaml_text": "name: Hero"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("filename"), "hero.yaml")

    def test_character_schema_includes_weapon_presets(self):
        client = self._build_test_client()

        response = client.get("/api/characters/schema")

        self.assertEqual(response.status_code, 200)
        sections = response.json().get("schema", {}).get("sections", [])
        attacks = next((section for section in sections if section.get("id") == "attacks"), {})
        fields = {field.get("key"): field for field in attacks.get("fields", [])}
        weapons = fields.get("weapons", {})
        self.assertEqual(weapons.get("type"), "array")
        weapon_fields = {
            field.get("key")
            for field in weapons.get("items", {}).get("fields", [])
        }
        self.assertTrue({"id", "name", "proficient", "to_hit", "one_handed", "two_handed", "effect"} <= weapon_fields)


if __name__ == "__main__":
    unittest.main()
