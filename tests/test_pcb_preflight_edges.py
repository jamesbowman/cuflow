import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shapely.geometry as sg

from tools import pcb_preflight


def gerber(*polygons):
    lines = ["%MOMM*%", "%FSLAX34Y34*%", "%LPD*%"]
    for polygon in polygons:
        lines.append("G36*")
        for i, (x, y) in enumerate(polygon.exterior.coords):
            lines.append(
                f"X{round(x * 10000):07d}Y{round(y * 10000):07d}"
                f"D{2 if i == 0 else 1:02d}*")
        lines.append("G37*")
    return "\n".join(lines) + "\nM02*\n"


class CopperEdgeTests(unittest.TestCase):
    def check_copper(self, copper, outline=None, slots=(), overrides=None):
        if outline is None:
            outline = sg.box(0, 0, 10, 10)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "board.GML").write_text(gerber(outline, *slots))
            (root / "board.GTL").write_text(gerber(*copper))
            (root / "board.GBL").write_text(gerber(*copper))
            audit = pcb_preflight.Audit()
            with patch.object(pcb_preflight, "ROOT", root):
                pcb_preflight.audit_copper_edges(audit, {
                    "board": "board",
                    **({"copper_edge_clearance_mm": {"GTL": 0.4}}
                       if overrides is None else overrides),
                })
            return audit

    def test_missing_setting_checks_both_layers_at_routed_default(self):
        audit = self.check_copper([sg.box(.2, .2, 9.8, 9.8)], overrides={})
        self.assertTrue(audit.passed)
        self.assertEqual(len(audit.checks), 2)
        self.assertTrue(all("needs 0.200 mm" in c.detail for c in audit.checks))
        audit = self.check_copper([sg.box(.19, 2, 1, 3)], overrides={})
        self.assertEqual([c.passed for c in audit.checks], [False, False])

    def test_partial_override_keeps_other_layer_enabled(self):
        audit = self.check_copper([sg.box(.3, .3, 9.7, 9.7)])
        self.assertEqual([c.passed for c in audit.checks], [False, True])

    def test_exact_clearance_passes(self):
        self.assertTrue(self.check_copper([sg.box(.4, .4, 9.6, 9.6)]).passed)

    def test_isolated_artwork_too_close_fails(self):
        audit = self.check_copper([
            sg.box(2, 2, 8, 8), sg.box(.3, 4, .35, 4.1)])
        self.assertFalse(audit.passed)
        self.assertIn("0.3000 mm", audit.checks[0].detail)

    def test_entirely_external_copper_fails(self):
        audit = self.check_copper([sg.box(11, 4, 12, 5)])
        self.assertFalse(audit.passed)
        self.assertIn("outside board", audit.checks[0].detail)

    def test_actual_perimeter_not_bounding_box(self):
        # A chamfered corner cuts through this otherwise safely inset pad.
        outline = sg.Polygon([(0, 2), (2, 0), (10, 0), (10, 10), (0, 10)])
        self.assertFalse(self.check_copper(
            [sg.box(.5, .5, 1, 1)], outline).passed)

    def test_internal_plated_slot_not_treated_as_outer_edge(self):
        self.assertTrue(self.check_copper(
            [sg.box(3.9, 3.9, 6.1, 6.1)],
            slots=[sg.box(4, 4, 6, 6)]).passed)

    def test_missing_outline_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = pcb_preflight.Audit()
            with patch.object(pcb_preflight, "ROOT", Path(directory)):
                pcb_preflight.audit_copper_edges(audit, {
                    "board": "missing",
                    "copper_edge_clearance_mm": {"GBL": 0.4},
                })
            self.assertFalse(audit.passed)
