import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import pcb_preflight


def excellon(*hits):
    lines = ["M48", "METRIC", "T1C0.300", "%", "T1"]
    lines += [f"X{x}Y{y}" for (x, y) in hits]
    return "\n".join(lines + ["M30"]) + "\n"


class DrillFileTests(unittest.TestCase):
    def drill_check(self, hits, **profile):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "board.TXT").write_text(excellon(*hits))
            audit = pcb_preflight.Audit()
            with patch.object(pcb_preflight, "ROOT", root):
                pcb_preflight.audit_manufacturing_files(audit, {
                    "board": "board",
                    "gerber_layers": {},
                    "drill_file": "board.TXT",
                    "airwire_file": "board.GTD",
                    **profile,
                })
        [check] = [c for c in audit.checks if c.name == "Drill file"]
        return check

    def test_a_board_needs_drills_by_default(self):
        self.assertFalse(self.drill_check([]).passed)
        self.assertTrue(self.drill_check([(10000, 20000)]).passed)

    def test_profile_can_declare_an_all_smd_board(self):
        check = self.drill_check(
            [], expected_drill_hits=0,
            expected_drill_hits_reason="all SMD")
        self.assertTrue(check.passed)
        self.assertIn("expected 0: all SMD", check.detail)

    def test_declared_count_must_match_exactly(self):
        check = self.drill_check([(10000, 20000)], expected_drill_hits=0)
        self.assertFalse(check.passed)


if __name__ == "__main__":
    unittest.main()
