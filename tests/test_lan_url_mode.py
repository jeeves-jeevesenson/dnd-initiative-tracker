import types
import unittest

import dnd_initative_tracker as tracker_mod


class LanUrlModeTests(unittest.TestCase):
    def _build_lan(self):
        lan = object.__new__(tracker_mod.LanController)
        lan.cfg = types.SimpleNamespace(host="0.0.0.0", port=8787)
        lan.url_settings = tracker_mod.LanUrlSettings()
        lan._resolve_local_ip = lambda: "192.168.1.10"
        return lan

    def test_http_mode_prefers_http_and_injects_http_base_url(self):
        lan = self._build_lan()
        lan.url_settings.url_mode = "http"

        self.assertEqual(lan.preferred_url(), "http://192.168.1.10:8787/")
        self.assertEqual(lan.html_injected_base_url(), "http://192.168.1.10:8787/")

    def test_https_mode_prefers_configured_https(self):
        lan = self._build_lan()
        lan.url_settings.url_mode = "https"
        lan.url_settings.public_https_url = " https://dnd.3045.network "

        self.assertEqual(lan.preferred_url(), "https://dnd.3045.network/")
        self.assertEqual(lan.html_injected_base_url(), "https://dnd.3045.network/")

    def test_both_mode_uses_undefined_injected_base_url_and_publishes_both(self):
        lan = self._build_lan()
        lan.url_settings.url_mode = "both"
        lan.url_settings.public_https_url = "https://dnd.3045.network/"

        urls = lan.published_urls()

        self.assertEqual(urls.get("http"), "http://192.168.1.10:8787/")
        self.assertEqual(urls.get("https"), "https://dnd.3045.network/")
        self.assertIsNone(lan.html_injected_base_url())


if __name__ == "__main__":
    unittest.main()
