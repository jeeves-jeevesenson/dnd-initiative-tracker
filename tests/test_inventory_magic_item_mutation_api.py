import threading
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest
import yaml

pytest.importorskip("httpx")
from fastapi.testclient import TestClient

import dnd_initative_tracker as tracker_mod


class _MutationAppStub:
    def __init__(self, tracker):
        self._tracker = tracker

    def _oplog(self, *_args, **_kwargs):
        return None

    def _lan_snapshot(self):
        return {"grid": None, "obstacles": [], "units": [], "active_cid": None, "round_num": 0}

    def _lan_pcs(self):
        return []

    def after(self, *_args, **_kwargs):
        return None

    def _character_schema_config(self):
        return tracker_mod._CHARACTER_SCHEMA_CONFIG or {}

    def _character_schema_readme_map(self):
        return tracker_mod._CHARACTER_SCHEMA_README_MAP or {}

    def _list_character_filenames(self):
        return ["hero.yaml"]

    def _get_character_payload(self, _name):
        return {"filename": "hero.yaml", "character": {}}

    def _create_character_payload(self, _payload):
        return {"filename": "hero.yaml", "character": {}}

    def _update_character_payload(self, _name, _payload):
        return {"filename": "hero.yaml", "character": {}}

    def _overwrite_character_payload(self, _name, _payload):
        return {"filename": "hero.yaml", "character": {}}

    def _upload_character_yaml_payload(self, _payload):
        return {"filename": "hero.yaml", "character": {}}

    def _mutate_owned_magic_item_state(self, name, instance_id, operation):
        return self._tracker._mutate_owned_magic_item_state(name, instance_id, operation)


class InventoryMagicItemMutationApiTests(unittest.TestCase):
    def _build_tracker(self, temp_player_path: Path):
        tracker = object.__new__(tracker_mod.InitiativeTracker)
        tracker._player_yaml_lock = threading.RLock()
        tracker._player_yaml_cache_by_path = {}
        tracker._player_yaml_meta_by_path = {}
        tracker._player_yaml_data_by_name = {}
        tracker._player_yaml_name_map = {}
        tracker._schedule_player_yaml_refresh = lambda: None
        tracker._normalize_player_profile = lambda raw, _name: raw
        tracker._load_player_yaml_cache = lambda: None
        tracker._find_player_profile_path = lambda _name: temp_player_path
        tracker._magic_items_registry_payload = lambda: {
            "wand_of_fireballs": {
                "id": "wand_of_fireballs",
                "name": "Wand of Fireballs",
                "requires_attunement": True,
            },
            "tyrs_circlet": {
                "id": "tyrs_circlet",
                "name": "Tyr's Circlet",
                "requires_attunement": True,
            },
            "ring_of_desert_sands": {
                "id": "ring_of_desert_sands",
                "name": "Ring of Desert Sands",
                "requires_attunement": False,
            },
        }
        tracker._oplog = lambda *_args, **_kwargs: None
        return tracker

    def _build_client(self, tracker):
        lan = object.__new__(tracker_mod.LanController)
        lan._tracker = _MutationAppStub(tracker)
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
        with mock.patch("threading.Thread.start", return_value=None):
            lan.start(quiet=True)
        return TestClient(lan._fastapi_app)

    def test_equip_unequip_and_attune_unattune_routes_mutate_yaml(self):
        with TemporaryDirectory() as tmpdir:
            player_path = Path(tmpdir) / "hero.yaml"
            payload = {
                "name": "Hero",
                "inventory": {
                    "items": [
                        {
                            "id": "wand_of_fireballs",
                            "instance_id": "wand_of_fireballs__001",
                            "equipped": False,
                            "attuned": False,
                            "state": {"pools": [{"id": "wand_pool", "current": 0, "max": 1}]},
                        }
                    ]
                },
            }
            player_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            tracker = self._build_tracker(player_path)
            client = self._build_client(tracker)

            equip = client.post("/api/characters/Hero/inventory/items/wand_of_fireballs__001/equip")
            self.assertEqual(equip.status_code, 200)
            self.assertTrue(equip.json().get("equipped"))

            attune = client.post("/api/characters/Hero/inventory/items/wand_of_fireballs__001/attune")
            self.assertEqual(attune.status_code, 200)
            self.assertTrue(attune.json().get("attuned"))

            unattune = client.post("/api/characters/Hero/inventory/items/wand_of_fireballs__001/unattune")
            self.assertEqual(unattune.status_code, 200)
            self.assertFalse(unattune.json().get("attuned"))

            unequip = client.post("/api/characters/Hero/inventory/items/wand_of_fireballs__001/unequip")
            self.assertEqual(unequip.status_code, 200)
            self.assertFalse(unequip.json().get("equipped"))

            saved = yaml.safe_load(player_path.read_text(encoding="utf-8"))
            item = saved["inventory"]["items"][0]
            self.assertFalse(item.get("equipped"))
            self.assertFalse(item.get("attuned"))
            self.assertEqual(item.get("state", {}).get("pools", [])[0].get("id"), "wand_pool")

    def test_attune_requires_attunement_and_cap_and_unknown_instance_guardrails(self):
        with TemporaryDirectory() as tmpdir:
            player_path = Path(tmpdir) / "hero.yaml"
            payload = {
                "name": "Hero",
                "inventory": {
                    "items": [
                        {"id": "wand_of_fireballs", "instance_id": "wand_1", "equipped": True, "attuned": True},
                        {"id": "tyrs_circlet", "instance_id": "circlet_1", "equipped": True, "attuned": True},
                        {"id": "tyrs_circlet", "instance_id": "circlet_2", "equipped": True, "attuned": True},
                        {"id": "tyrs_circlet", "instance_id": "circlet_3", "equipped": True, "attuned": False},
                        {"id": "rope", "instance_id": "rope_1", "equipped": False, "attuned": False},
                        {"id": "ring_of_desert_sands", "instance_id": "ring_1", "equipped": True, "attuned": False},
                    ]
                },
            }
            player_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            tracker = self._build_tracker(player_path)
            client = self._build_client(tracker)

            cap = client.post("/api/characters/Hero/inventory/items/circlet_3/attune")
            self.assertEqual(cap.status_code, 400)

            not_magic = client.post("/api/characters/Hero/inventory/items/rope_1/equip")
            self.assertEqual(not_magic.status_code, 400)

            no_attune_needed = client.post("/api/characters/Hero/inventory/items/ring_1/attune")
            self.assertEqual(no_attune_needed.status_code, 400)

            missing = client.post("/api/characters/Hero/inventory/items/missing/equip")
            self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
