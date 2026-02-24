import unittest
from pathlib import Path


class ReservedMapPanningKeysTests(unittest.TestCase):
    def test_main_window_no_wasd_or_arrow_binds(self):
        src = Path("helper_script.py").read_text(encoding="utf-8")
        disallowed = [
            'self.bind("<KeyPress-w>"',
            'self.bind("<KeyPress-a>"',
            'self.bind("<KeyPress-s>"',
            'self.bind("<KeyPress-d>"',
            'self.bind("<KeyPress-Up>"',
            'self.bind("<KeyPress-Down>"',
            'self.bind("<KeyPress-Left>"',
            'self.bind("<KeyPress-Right>"',
        ]
        for token in disallowed:
            self.assertNotIn(token, src)

    def test_lan_hotkeys_do_not_default_to_reserved_keys_and_have_filtering(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        reserved = ["W", "A", "S", "D", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]
        for key in reserved:
            self.assertNotIn(f'localStorage.setItem("inittracker_hotkey_toggleAttackOverlay", "{key}");', html)
        self.assertIn("const RESERVED_PAN_BASE_KEYS = new Set", html)
        self.assertIn("function hotkeyContainsReservedPanKey", html)
        self.assertIn('config.conflictEl.textContent = reserved ? "Reserved"', html)


if __name__ == "__main__":
    unittest.main()
