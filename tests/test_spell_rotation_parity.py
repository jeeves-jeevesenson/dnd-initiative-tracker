import unittest
from pathlib import Path


class SpellRotationParityTests(unittest.TestCase):
    def test_lan_rotate_mode_supports_wall_and_square(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn(
            'kind !== "line" && kind !== "cone" && kind !== "cube" && kind !== "wall" && kind !== "square"',
            html,
        )

    def test_server_aoe_move_applies_angle_for_wall_and_square(self):
        py = Path("dnd_initative_tracker.py").read_text(encoding="utf-8")
        self.assertIn('if kind in ("line", "cone", "cube", "wall", "square"):', py)
        self.assertIn("facing_synced = self._sync_owner_facing_from_rotatable_aoe(d, angle_deg)", py)

    def test_server_set_facing_syncs_owned_rotatable_aoes(self):
        py = Path("dnd_initative_tracker.py").read_text(encoding="utf-8")
        self.assertIn("self._sync_owned_rotatable_aoes_with_facing(int(cid), getattr(c, \"facing_deg\", 0))", py)

    def test_dm_map_drag_rotation_supports_wall_and_square(self):
        py = Path("helper_script.py").read_text(encoding="utf-8")
        self.assertIn(
            'if kind in ("line", "cone", "cube", "wall", "square") and shift_held:',
            py,
        )

    def test_lan_rotate_handle_is_shift_gated(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn("if (!shiftMoveMode && !isCurrentlyRotating) return null;", html)

    def test_lan_rotate_handle_uses_active_controlled_character(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('const rotationCid = normalizeCid(activeControlledUnitCid(), "rotateHandle.controlledCid");', html)

    def test_dm_map_rotation_persists_to_combatant_facing(self):
        py = Path("helper_script.py").read_text(encoding="utf-8")
        self.assertIn('setattr(c, "facing_deg", facing)', py)
        self.assertIn('broadcast_fn = getattr(self.app, "_lan_force_state_broadcast", None)', py)

    def test_cast_aoe_defaults_rotatable_angle_to_caster_facing(self):
        py = Path("dnd_initative_tracker.py").read_text(encoding="utf-8")
        self.assertIn('caster_facing_deg = (', py)
        self.assertIn('aoe["angle_deg"] = float(angle_deg) if angle_deg is not None else float(caster_facing_deg)', py)

    def test_lan_cast_uses_claimed_unit_facing_for_default_angle(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('const casterFacingDeg = normalizeFacingDeg(getClaimedUnit()?.facing_deg);', html)
        self.assertIn('const angleDeg = angleDegInput !== null ? angleDegInput : casterFacingDeg;', html)


if __name__ == "__main__":
    unittest.main()
