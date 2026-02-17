import unittest

import dnd_initative_tracker as tracker_mod


class LanActionSurgePoolTests(unittest.TestCase):
    def test_action_surge_use_consumes_pool_and_grants_action(self):
        toasts = []
        logs = []
        consumed = []
        app = object.__new__(tracker_mod.InitiativeTracker)
        app._oplog = lambda *args, **kwargs: None
        app._is_admin_token_valid = lambda token: False
        app._summon_can_be_controlled_by = lambda claimed, target: False
        app._is_valid_summon_turn_for_controller = lambda controlling, target, current: True
        app._pc_name_for = lambda cid: "John Twilight"
        app._profile_for_player_name = lambda name: {"leveling": {"classes": [{"name": "Fighter", "level": 10}]}}
        app._fighter_level_from_profile = lambda profile: 10
        app._consume_resource_pool_for_cast = lambda player_name, pool_id, cost: (consumed.append((player_name, pool_id, cost)) or True, "")
        app._log = lambda message, cid=None: logs.append((cid, message))
        app._rebuild_table = lambda scroll_to_current=True: None
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
                    "name": "John Twilight",
                    "action_remaining": 0,
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
                "type": "action_surge_use",
                "cid": 1,
                "_claimed_cid": 1,
                "_ws_id": 42,
            }
        )

        self.assertEqual(app.combatants[1].action_remaining, 1)
        self.assertEqual(consumed, [("John Twilight", "action_surge", 1)])
        self.assertIn((42, "Action Surge used: +1 action."), toasts)
        self.assertTrue(any("uses Action Surge and gains 1 action" in message for _cid, message in logs))


if __name__ == "__main__":
    unittest.main()
