import unittest

import dnd_initative_tracker as tracker_mod


class LanReactionActionTests(unittest.TestCase):
    def test_perform_action_reaction_spends_reaction_resource(self):
        toasts = []
        logs = []
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._is_admin_token_valid = lambda token: False
        app._summon_can_be_controlled_by = lambda claimed, target: False
        app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        app._pc_name_for = lambda cid: "Aelar"
        app._log = lambda message, cid=None: logs.append((cid, message))
        app._rebuild_table = lambda scroll_to_current=True: None
        app._mount_action_is_restricted = lambda c, action_name: False
        app.in_combat = True
        app.current_cid = 1
        app.round_num = 1
        app.turn_num = 1
        app.start_cid = None
        app.combatants = {
            1: type(
                "C",
                (),
                {
                    "cid": 1,
                    "name": "Aelar",
                    "reaction_remaining": 1,
                    "actions": [],
                    "bonus_actions": [],
                    "reactions": [{"name": "Opportunity Attack", "type": "reaction"}],
                },
            )()
        }
        app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda _self, ws_id, message: toasts.append((ws_id, message)),
                "_append_lan_log": lambda *args, **kwargs: None,
                "_loop": None,
            },
        )()

        app._lan_apply_action(
            {
                "type": "perform_action",
                "cid": 1,
                "_claimed_cid": 1,
                "_ws_id": 42,
                "spend": "reaction",
                "action": "Opportunity Attack",
            }
        )

        self.assertEqual(app.combatants[1].reaction_remaining, 0)
        self.assertIn((42, "Used Opportunity Attack."), toasts)
        self.assertTrue(any("used Opportunity Attack (reaction)" in message for _cid, message in logs))


if __name__ == "__main__":
    unittest.main()
