import json
import unittest
from types import SimpleNamespace

import cuflow as cu


class NetlistManifestTests(unittest.TestCase):
    def board(self):
        return cu.Board(
            (10, 10),
            trace=0.1,
            space=0.1,
            via_hole=0.3,
            via=0.4,
            via_space=0.1,
            silk=0.1,
        )

    def add_part(self, board, designator, pads):
        part = SimpleNamespace(id=designator, pads=[])
        for pad_name, xy in pads:
            pad = board.DC(xy).setname(pad_name)
            pad.part = designator
            part.pads.append(pad)
        board.parts[designator[0]].append(part)
        return part

    def test_writes_independent_logical_nets_and_global_power(self):
        board = self.board()
        u1 = self.add_part(board, "U1", (
            ("GPIO12", (1, 1)),
            ("GPIO13", (2, 1)),
            ("GND", (3, 1)),
        ))
        j3 = self.add_part(board, "J3", (
            ("DTR", (1, 2)),
            ("RTS", (2, 2)),
            ("GND", (3, 2)),
        ))

        with self.subTest("manifest"):
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as directory:
                basename = directory + "/board"
                document = board.save_netlist(basename, (
                    (u1.pads[0], j3.pads[0]),
                    (u1.pads[1], j3.pads[1]),
                ))
                with open(basename + ".net.json") as source:
                    saved = json.load(source)

        self.assertEqual(saved, document)
        self.assertEqual(document["format"], "cuflow-netlist-1")
        self.assertEqual(len(document["nets"]), 3)

        terminal_sets = {
            frozenset(
                (terminal["designator"], terminal["pad"])
                for terminal in net["terminals"]
            ): net["name"]
            for net in document["nets"]
        }
        self.assertEqual(terminal_sets[frozenset((
            ("U1", "GPIO12"), ("J3", "DTR")))], None)
        self.assertEqual(terminal_sets[frozenset((
            ("U1", "GPIO13"), ("J3", "RTS")))], None)
        self.assertEqual(terminal_sets[frozenset((
            ("U1", "GND"), ("J3", "GND")))], "GND")


if __name__ == "__main__":
    unittest.main()
