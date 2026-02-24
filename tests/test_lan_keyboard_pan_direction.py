from pathlib import Path


def test_lan_pan_direction_mapping_signs_for_wasd_and_arrows():
    html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
    expected_entries = [
        'KeyW: {x: 0, y: -1}',
        'ArrowUp: {x: 0, y: -1}',
        'KeyS: {x: 0, y: 1}',
        'ArrowDown: {x: 0, y: 1}',
        'KeyA: {x: -1, y: 0}',
        'ArrowLeft: {x: -1, y: 0}',
        'KeyD: {x: 1, y: 0}',
        'ArrowRight: {x: 1, y: 0}',
    ]
    for entry in expected_entries:
        assert entry in html
    assert "const direction = PAN_DIRECTION_BY_CODE[code];" in html
    assert "function normalizedPanCodeFromKeyboardEvent(event)" in html
