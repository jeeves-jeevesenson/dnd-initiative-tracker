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

    def test_directional_self_range_mode_activates_for_self_range_line(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('function isDirectionalSelfRangeAoePlacement(preset, shape)', html)
        self.assertIn('function isSelfRangeAoePreset(preset)', html)
        self.assertIn('const directionalSelfRange = isDirectionalSelfRangeAoePlacement(preset, shape);', html)
        self.assertIn('mode: directionalSelfRange ? "directional_self_range" : null,', html)

    def test_directional_self_range_skips_range_prompt(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('let placementRangeFt = directionalSelfRange ? null : parseSpellTargetRangeFeet(preset);', html)
        self.assertIn('if (!directionalSelfRange && !Number.isFinite(placementRangeFt)){', html)

    def test_directional_self_range_applies_anchor_and_heading(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('function applyDirectionalSelfRangePlacement()', html)
        self.assertIn('function directionalPlacementAnchor(casterPos, cursorPos, headingDeg)', html)
        self.assertIn('payload.ax = anchor.ax;', html)
        self.assertIn('payload.ay = anchor.ay;', html)
        self.assertIn('payload.cx = anchor.ax + anchor.vx * halfLen;', html)

    def test_directional_self_range_cast_sends_anchor_fields(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('if (isDirectionalSelfRangePlacementActive()){', html)
        self.assertIn('msg.payload.ax = Number(placementPayload.ax);', html)
        self.assertIn('msg.payload.ay = Number(placementPayload.ay);', html)

    def test_server_accepts_directional_anchor_for_line_cone(self):
        py = Path("dnd_initative_tracker.py").read_text(encoding="utf-8")
        self.assertIn('if payload_ax is not None and payload_ay is not None and shape in ("line", "wall", "cone"):', py)
        self.assertIn('max_anchor_offset = 0.6001', py)

    def test_cube_square_placement_uses_zero_default_angle(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('payload.angle_deg = angleDegInput !== null ? angleDegInput : 0;', html)

    def test_cube_square_placement_wheel_rotation_is_present(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('function isPlacementSquareOrCube()', html)
        self.assertIn('isPlacementSquareOrCube()', html)
        self.assertIn('pendingAoePlacement.payload.angle_deg = normalizeFacingDeg(base + step);', html)

    def test_server_facing_sync_gates_on_fixed_to_caster(self):
        py = Path("dnd_initative_tracker.py").read_text(encoding="utf-8")
        self.assertIn("if aoe.get(\"fixed_to_caster\") is not True:", py)
        self.assertIn("continue", py)

    def test_lan_facing_sync_gates_on_fixed_to_caster(self):
        html = Path("assets/web/lan/index.html").read_text(encoding="utf-8")
        self.assertIn('|| aoe.fixed_to_caster !== true', html)


if __name__ == "__main__":
    unittest.main()
