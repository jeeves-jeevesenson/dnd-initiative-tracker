import threading
import unittest
from unittest import mock

import dnd_initative_tracker as tracker_mod


class AideDDMonsterImageTests(unittest.TestCase):
    def _tracker(self):
        tracker = object.__new__(tracker_mod.InitiativeTracker)
        tracker._monster_image_cache = {}
        tracker._monster_image_cache_ttl_s = 60
        tracker._monster_image_negative_ttl_s = 30
        tracker._monster_image_lock = threading.Lock()
        return tracker

    def test_extract_prefers_og_image_meta(self):
        tracker = self._tracker()
        html = """
        <html><head>
        <meta property='og:image' content='https://www.aidedd.org/monster/img/beholder.jpg'>
        </head><body>
        <div class='picture'><img src='img/ape.jpg'></div>
        </body></html>
        """

        self.assertEqual(
            tracker._extract_aidedd_image_url(html),
            "https://www.aidedd.org/monster/img/beholder.jpg",
        )

    def test_extract_from_picture_div_markup(self):
        tracker = self._tracker()
        samples = [
            "aarakocra.jpg",
            "ape.jpg",
            "gold-dragon-ancient.jpg",
        ]
        for filename in samples:
            with self.subTest(filename=filename):
                html = f"""
                <div class=\"stats\">...</div>
                <div class='picture'>
                    <img
                      alt='Monster art'
                      src='img/{filename}'
                      class='img-fluid'
                    >
                </div>
                """
                self.assertEqual(tracker._extract_aidedd_image_url(html), f"img/{filename}")

    def test_normalize_relative_img_url(self):
        tracker = self._tracker()
        self.assertEqual(
            tracker._normalize_aidedd_image_url("img/ape.jpg", "https://www.aidedd.org/monster/ape"),
            "https://www.aidedd.org/monster/img/ape.jpg",
        )

    def test_resolve_fetches_and_normalizes_picture_img(self):
        tracker = self._tracker()
        html = b"""
        <html><body>
        <div class='picture'><img src='img/ape.jpg' alt='ape'></div>
        </body></html>
        """

        response = mock.MagicMock()
        response.read.return_value = html
        response.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value = response
        response.__exit__.return_value = None

        with mock.patch("urllib.request.urlopen", return_value=response):
            result = tracker._resolve_aidedd_monster_image_url("ape")

        self.assertEqual(result, "https://www.aidedd.org/monster/img/ape.jpg")


if __name__ == "__main__":
    unittest.main()
