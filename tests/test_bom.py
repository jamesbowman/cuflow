import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import cuflow as cu


class PrettyPartsTests(unittest.TestCase):
    def test_consecutive_runs_are_ranges(self):
        self.assertEqual(cu.pretty_parts(["R1", "R2", "R3", "R5"]), "R1-3,R5")

    def test_range_stops_at_first_gap(self):
        self.assertEqual(cu.pretty_parts(["R1", "R2", "R5", "R4"]), "R1,R2,R5,R4")

    def test_multi_letter_prefixes(self):
        self.assertEqual(cu.pretty_parts(["SW1", "SW2", "SW3"]), "SW1-3")
        self.assertEqual(cu.pretty_parts(["BT1"]), "BT1")

    def test_mixed_prefixes_are_compacted_separately(self):
        self.assertEqual(
            cu.pretty_parts(["TP1", "T1", "TP2", "TP3", "T2"]), "TP1-3,T1,T2"
        )


class BomTests(unittest.TestCase):
    def part(self, board, family, designator, mfr, code):
        part = SimpleNamespace(
            id=designator,
            inBOM=True,
            source={"LCSC": code},
            mfr=mfr,
            val="",
            footprint="SMD",
        )
        board.parts[family].append(part)

    def test_families_outside_rank_sort_after_it(self):
        board = cu.Board((10, 10), trace=0.1, space=0.1, via_hole=0.3,
                         via=0.4, via_space=0.1, silk=0.1)
        self.part(board, "SW", "SW1", "TS-1187A", "C318884")
        self.part(board, "SW", "SW2", "TS-1187A", "C318884")
        self.part(board, "BT", "BT1", "BH-18650", "C2988620")
        self.part(board, "R", "R1", "10k", "C25744")
        self.part(board, "U", "U1", "CN3158", "C559032")
        with TemporaryDirectory() as directory:
            records = board.bom(directory + "/board")["bom"]
        self.assertEqual(
            [(r["parts"], r["qty"]) for r in records],
            [("U1", "1"), ("R1", "1"), ("BT1", "1"), ("SW1,SW2", "2")],
        )


if __name__ == "__main__":
    unittest.main()
