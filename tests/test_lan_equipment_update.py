import unittest

import dnd_initative_tracker as tracker_mod


class LanEquipmentUpdateTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._is_admin_token_valid = lambda token: False
        self.app._summon_can_be_controlled_by = lambda claimed, target: False
        self.app._lan_force_state_broadcast = lambda: None
        self.app.in_combat = True
        self.app.current_cid = 1
        self.app.combatants = {
            1: type("C", (), {"cid": 1, "name": "Fred", "ac": 13})(),
        }
        self.app._lan = type(
            "LanStub",
            (),
            {
                "toast": lambda *_args, **_kwargs: None,
                "_append_lan_log": lambda *_args, **_kwargs: None,
                "_loop": None,
            },
        )()

    def test_equipment_update_adds_shield_ac_once(self):
        self.app._lan_apply_action({"type": "equipment_update", "cid": 1, "_claimed_cid": 1, "shield_equipped": True})
        self.assertEqual(self.app.combatants[1].ac, 15)

        self.app._lan_apply_action({"type": "equipment_update", "cid": 1, "_claimed_cid": 1, "shield_equipped": True})
        self.assertEqual(self.app.combatants[1].ac, 15)

    def test_equipment_update_removes_shield_ac(self):
        self.app._lan_apply_action({"type": "equipment_update", "cid": 1, "_claimed_cid": 1, "shield_equipped": True})
        self.app._lan_apply_action({"type": "equipment_update", "cid": 1, "_claimed_cid": 1, "shield_equipped": False})
        self.assertEqual(self.app.combatants[1].ac, 13)


if __name__ == "__main__":
    unittest.main()
