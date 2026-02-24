import unittest
from unittest.mock import patch

import dnd_initative_tracker as tracker_mod


class _InlineThread:
    def __init__(self, target=None, daemon=None):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target()


class StartupUpdateBehaviorTests(unittest.TestCase):
    def _make_app(self):
        app = object.__new__(tracker_mod.InitiativeTracker)
        app.combatants = {}
        app._session_has_saved = False
        app._oplog = lambda *_args, **_kwargs: None
        app.after = lambda _delay, func: func()
        return app

    def test_startup_up_to_date_is_silent(self):
        app = self._make_app()

        with patch("dnd_initative_tracker.threading.Thread", side_effect=lambda target, daemon: _InlineThread(target=target, daemon=daemon)), \
             patch("dnd_initative_tracker.update_checker.check_for_updates", return_value=(False, "up to date", None)), \
             patch("dnd_initative_tracker.messagebox.showinfo") as showinfo, \
             patch.object(app, "_offer_update_and_run_if_confirmed") as offer_update:
            app._check_for_updates_on_startup()

        showinfo.assert_not_called()
        offer_update.assert_not_called()

    def test_update_accept_with_unsaved_state_offers_quick_save(self):
        app = self._make_app()
        app.combatants = {1: object()}

        with patch("dnd_initative_tracker.messagebox.askyesno", side_effect=[True, True]) as askyesno, \
             patch.object(app, "_quick_save_session") as quick_save, \
             patch.object(app, "_launch_update_workflow") as launch_update:
            app._offer_update_and_run_if_confirmed("update found")

        self.assertEqual(askyesno.call_count, 2)
        self.assertEqual(askyesno.call_args_list[1].args[1], "quick save? yes no")
        quick_save.assert_called_once()
        launch_update.assert_called_once_with("update found")


if __name__ == "__main__":
    unittest.main()
