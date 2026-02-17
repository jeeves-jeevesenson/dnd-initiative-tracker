import pytest

pytest.importorskip("httpx")
pytest.importorskip("pypdf")

import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from pypdf import PdfWriter

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


class LanRulesHelpPdfTests(unittest.TestCase):
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
        lan._rules_toc_cache_key = None
        lan._rules_toc_cache_payload = None
        return lan

    def _build_test_client(self):
        lan = self._build_lan_controller()
        with mock.patch("threading.Thread.start", return_value=None):
            lan.start(quiet=True)
        return TestClient(lan._fastapi_app)

    def test_no_rules_pdf_returns_404_and_empty_toc(self):
        with mock.patch.dict("os.environ", {"INITTRACKER_RULES_PDF": "/tmp/does-not-exist.pdf"}, clear=False):
            client = self._build_test_client()
            pdf_response = client.get("/rules.pdf")
            toc_response = client.get("/api/rules/toc")

        self.assertEqual(pdf_response.status_code, 404)
        self.assertEqual(toc_response.status_code, 200)
        payload = toc_response.json()
        self.assertEqual(payload.get("toc"), [])
        self.assertFalse(payload.get("available"))

    def test_rules_pdf_and_toc_when_pdf_is_present(self, tmp_path: Path):
        pdf_path = tmp_path / "Rules.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.add_blank_page(width=300, height=300)
        writer.add_outline_item("Fighter", 0)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with mock.patch.dict("os.environ", {"INITTRACKER_RULES_PDF": str(pdf_path)}, clear=False):
            client = self._build_test_client()
            pdf_response = client.get("/rules.pdf")
            toc_response = client.get("/api/rules/toc")

        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("application/pdf", pdf_response.headers.get("content-type", ""))
        self.assertEqual(toc_response.status_code, 200)
        toc_payload = toc_response.json()
        self.assertTrue(toc_payload.get("available"))
        toc = toc_payload.get("toc") or []
        self.assertTrue(toc)
        self.assertEqual(toc[0].get("title"), "Fighter")
        self.assertEqual(toc[0].get("page"), 1)

    def test_rules_pdf_supports_byte_range_requests(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "Rules.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            with pdf_path.open("wb") as handle:
                writer.write(handle)

            file_size = pdf_path.stat().st_size
            with mock.patch.dict("os.environ", {"INITTRACKER_RULES_PDF": str(pdf_path)}, clear=False):
                client = self._build_test_client()
                range_response = client.get("/rules.pdf", headers={"Range": "bytes=0-1023"})
                full_response = client.get("/rules.pdf")

        self.assertEqual(range_response.status_code, 206)
        self.assertEqual(range_response.headers.get("content-range"), f"bytes 0-{file_size - 1}/{file_size}")
        self.assertEqual(range_response.headers.get("accept-ranges"), "bytes")
        self.assertEqual(int(range_response.headers.get("content-length", "0")), file_size)
        self.assertEqual(len(range_response.content), file_size)
        self.assertEqual(full_response.status_code, 200)
        self.assertIn("application/pdf", full_response.headers.get("content-type", ""))

    def test_spell_pages_endpoint_parses_markdown_mapping(self, tmp_path: Path):
        spells_dir = tmp_path / "Spells"
        spells_dir.mkdir(parents=True, exist_ok=True)
        (spells_dir / "spells_by_page.md").write_text(
            "\n".join(
                [
                    "## p.273",
                    "**Spells**",
                    "- Fireball",
                    "- Alarm [R]",
                    "",
                    "## p.274",
                    "**Spells**",
                    "- Flame Strike",
                    "",
                    "**Related statblocks**",
                    "- Giant Insect Statblock",
                ]
            ),
            encoding="utf-8",
        )

        tracker_mod._load_spell_source_page_map.cache_clear()
        with mock.patch.object(tracker_mod, "_app_base_dir", return_value=tmp_path):
            client = self._build_test_client()
            response = client.get("/api/rules/spell-pages")
        tracker_mod._load_spell_source_page_map.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        pages = payload.get("pages") or {}
        self.assertEqual(pages.get("fireball"), 273)
        self.assertEqual(pages.get("alarm"), 273)
        self.assertEqual(pages.get("flame strike"), 274)
        self.assertNotIn("giant insect statblock", pages)


if __name__ == "__main__":
    unittest.main()
