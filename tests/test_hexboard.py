import unittest

import shapely.geometry as sg

from hex import Hex, axial_direction_vectors
from hexboard import HexBoard


class HexRouteNetWidthTests(unittest.TestCase):
    def board(self):
        board = HexBoard(
            (12, 12),
            trace=0.1,
            space=0.2,
            via_hole=0.3,
            via=0.6,
            via_space=0.1,
            silk=0.1,
        )
        board.hex_setup()
        return board

    def terminals(self, board):
        result = []
        for index, xy in enumerate(((2, 2), (10, 2), (6, 10))):
            terminal = board.DC(
                Hex.from_xy_fine(*xy).to_plane()).setlayer("GTL")
            terminal.part = f"J{index + 1}"
            terminal.setname("1")
            result.append(terminal)
        return tuple(result)

    def test_default_width_preserves_single_cell_occupancy(self):
        board = self.board()
        before = board.blocked["GTL"].copy()

        routes = board.hex_route_net(self.terminals(board))

        occupied = {
            tuple(cell)
            for route in routes
            for cell in route
        }
        newly_blocked = {
            tuple(cell)
            for cell in board.route_hexes
            if not before[cell.q, cell.r]
            and board.blocked["GTL"][cell.q, cell.r]
        }
        self.assertEqual(newly_blocked, occupied)
        self.assertEqual(board.route_widths, [board.trace] * 3)

    def test_wide_route_reserves_a_clearance_corridor(self):
        board = self.board()
        width = 0.8

        routes = board.hex_route_net(self.terminals(board), width=width)

        self.assertEqual(board.route_widths, [width] * 3)
        directions = [Hex(*direction) for direction in axial_direction_vectors]
        interior = next(
            cell
            for route in routes
            for cell in route[1:-1]
            if all(tuple(cell + direction) in board.valid_cells
                   for direction in directions)
        )
        self.assertTrue(all(
            board.blocked["GTL"][
                (interior + direction).q,
                (interior + direction).r,
            ]
            for direction in directions
        ))

        board.wire_routes()
        self.assertEqual(len(board.layers["GTL"].polys), 3)
        self.assertTrue(all(
            polygon.area > 0
            for _, polygon in board.layers["GTL"].polys
        ))

    def test_width_must_be_positive(self):
        board = self.board()

        with self.assertRaisesRegex(AssertionError, "positive"):
            board.hex_route_net(self.terminals(board), width=0)

    def test_explicit_width_expands_fixed_copper_clearance(self):
        board = HexBoard(
            (12, 12),
            trace=0.1,
            space=0.2,
            via_hole=0.3,
            via=0.6,
            via_space=0.1,
            silk=0.1,
        )
        board.layers["GTL"].add(sg.Point((6, 6)).buffer(0.1))
        board.hex_setup()

        wide_blocked = board.layer_blocks("GTL", width=0.8)

        self.assertGreater(
            int(wide_blocked.sum()),
            int(board.blocked["GTL"].sum()),
        )


if __name__ == "__main__":
    unittest.main()
