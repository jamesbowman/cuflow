import unittest

import shapely.geometry as sg

from htmlout import _solder_paste_geometry


class _Layer:
    def __init__(self, geometry):
        self.geometry = geometry

    def preview(self):
        return self.geometry


class SolderPasteGeometryTests(unittest.TestCase):
    def test_paste_is_not_clipped_to_the_drilled_board_body(self):
        paste_over_hole = sg.Point((5, 5)).buffer(1)
        board = type("Board", (), {
            "layers": {
                "GTP": _Layer(paste_over_hole),
                "GBP": _Layer(sg.GeometryCollection()),
            },
        })()

        top, bottom = _solder_paste_geometry(board)

        self.assertTrue(top.equals(paste_over_hole))
        self.assertTrue(bottom.is_empty)


if __name__ == "__main__":
    unittest.main()
