from pathlib import Path
from types import SimpleNamespace

import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnd_initative_tracker as tracker_mod


def _make_app():
    app = object.__new__(tracker_mod.InitiativeTracker)
    app.combatants = {}
    app.round_num = 1
    app._log = lambda *_args, **_kwargs: None
    app._turn_timing_active = True
    app._turn_timing_current_cid = None
    app._turn_timing_start_ts = None
    app._turn_timing_last_round = 1
    app._turn_timing_round_totals = {}
    app._turn_timing_pc_order = []
    return app


def test_startup_archives_time_log_and_excludes_from_generic_archive(tmp_path: Path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    time_log = logs_dir / "time.log"
    time_log.write_text("Round 9:\nDM Time: 4:12\n", encoding="utf-8")
    other_log = logs_dir / "operations.log"
    other_log.write_text("ops", encoding="utf-8")

    with patch("dnd_initative_tracker._app_data_dir", return_value=tmp_path):
        tracker_mod._archive_startup_time_log()
        tracker_mod._archive_startup_logs()

    archived = list((logs_dir / "time").glob("*_archived*.log"))
    assert len(archived) == 1
    assert archived[0].read_text(encoding="utf-8") == "Round 9:\nDM Time: 4:12\n"

    assert time_log.exists()
    assert time_log.read_text(encoding="utf-8") == ""

    old_logs = list((logs_dir / "old logs").glob("**/operations.log"))
    assert len(old_logs) == 1
    assert not list((logs_dir / "old logs").glob("**/time.log"))


def test_round_flush_formats_dm_and_pc_buckets(tmp_path: Path):
    app = _make_app()
    app.combatants = {
        1: SimpleNamespace(cid=1, name="Dorian Vandergraff", is_pc=True),
        2: SimpleNamespace(cid=2, name="Goblin 1", is_pc=False),
        3: SimpleNamespace(cid=3, name="John Twilight", is_pc=True),
    }

    with patch("dnd_initative_tracker._ensure_logs_dir", return_value=tmp_path), \
         patch("dnd_initative_tracker.time.perf_counter", side_effect=[0.0, 10.0, 10.0, 25.0, 25.0, 40.0, 40.0]):
        app.round_num = 1
        app._log_turn_start(1)
        app._log_turn_end(1)
        app._log_turn_start(2)
        app._log_turn_end(2)
        app._log_turn_start(3)
        app._log_turn_end(3)

        app.round_num = 2
        app._log_turn_start(1)

    text = (tmp_path / "time.log").read_text(encoding="utf-8")
    assert text == (
        "Round 1:\n"
        "DM Time: 0:15\n"
        "Dorian Vandergraff: 0:10\n"
        "John Twilight: 0:15\n"
        "\n"
    )
