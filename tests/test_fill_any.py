import unittest

import shapely.geometry as sg

import cuflow as cu


class FillAnyClearanceTests(unittest.TestCase):
    def board(self, space):
        board = cu.Board(
            (10, 10),
            trace=0.127,
            space=space,
            via_hole=0.3,
            via=0.6,
            via_space=0.2,
            silk=0.1,
        )
        board.outline()
        return board

    def test_pour_keeps_full_space_from_other_copper(self):
        # Round copper is stored as a 16-segment polygon and the pour's
        # keep-away is another buffer of it, so the keep-away's chords cut
        # inside the true distance; Layer.add then simplifies by 1 um. The
        # chord error grows with the clearance, so check a wide one too.
        for space in (0.2, 2.0):
            with self.subTest(space=space):
                board = self.board(space)
                layer = board.layers["GTL"]
                for i, xy in enumerate([(3, 3), (6.1, 4.7), (4.4, 7.3)]):
                    layer.add(sg.Point(xy).buffer(0.8), f"N{i}")
                board.fill_any("GTL", "VCC")
                pours = [o for (nm, o) in layer.polys if nm == ["VCC"]]
                others = [o for (nm, o) in layer.polys if nm != ["VCC"]]
                self.assertEqual(len(pours), 1)
                self.assertFalse(pours[0].is_empty)
                gap = min(pours[0].distance(o) for o in others)
                self.assertGreaterEqual(gap, space)


if __name__ == "__main__":
    unittest.main()
