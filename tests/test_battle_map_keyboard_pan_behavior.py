from types import SimpleNamespace
from unittest.mock import patch

from helper_script import BattleMapWindow


def _make_window() -> BattleMapWindow:
    win = BattleMapWindow.__new__(BattleMapWindow)
    win._pan_key_to_dir = {
        "w": (0, -1),
        "a": (-1, 0),
        "s": (0, 1),
        "d": (1, 0),
        "Up": (0, -1),
        "Down": (0, 1),
        "Left": (-1, 0),
        "Right": (1, 0),
    }
    win._pan_held_dirs = set()
    win._pan_pressed_at = {}
    win._pan_velocity_x = 0.0
    win._pan_velocity_y = 0.0
    win._pan_last_time = None
    win._pan_after_id = None
    win._pan_hold_threshold_s = 0.15
    win.cell = 32.0
    win._moves = []
    win._after_calls = 0

    def _move(dx, dy):
        win._moves.append((dx, dy))

    win._move_canvas_by_pixels = _move
    win.after_cancel = lambda _id: None

    def _after(_ms, _cb):
        win._after_calls += 1
        return "after-id"

    win.after = _after
    return win


def test_short_tap_clears_velocity_on_release():
    win = _make_window()
    event = SimpleNamespace(keysym="d", state=0, widget=None)

    with patch("helper_script.time.monotonic", side_effect=[10.0, 10.0, 10.05]):
        win._on_pan_key_press(event)
        win._pan_velocity_x = 99.0
        win._pan_velocity_y = -14.0
        win._on_pan_key_release(event)

    assert win._pan_velocity_x == 0.0
    assert win._pan_velocity_y == 0.0
    assert win._pan_held_dirs == set()
    assert win._pan_pressed_at == {}


def test_hold_release_decelerates_without_sign_reversal():
    win = _make_window()
    win._pan_velocity_x = 120.0
    win._pan_velocity_y = 0.0
    win._pan_last_time = 1.0

    with patch("helper_script.time.monotonic", side_effect=[1.016, 1.032, 1.048, 1.064, 1.080]):
        samples = []
        for _ in range(5):
            win._keyboard_pan_tick()
            samples.append(win._pan_velocity_x)

    assert all(v >= 0.0 for v in samples)
    assert all(samples[i + 1] <= samples[i] for i in range(len(samples) - 1))
