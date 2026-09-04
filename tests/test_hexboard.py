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

    def test_hex_clearance_does_not_shrink_cell_occupancy_radius(self):
        board = HexBoard(
            (12, 12),
            trace=0.1,
            space=0.2,
            via_hole=0.3,
            via=0.4,
            via_space=0.1,
            silk=0.1,
        )
        board.hex_clearance = 0.01

        board.hex_setup()

        self.assertEqual(board.route_radius, board.hr)

    def test_routes_four_terminal_net(self):
        board = HexBoard(
            (12, 12),
            trace=0.1,
            space=0.2,
            via_hole=0.3,
            via=0.6,
            via_space=0.1,
            silk=0.1,
        )
        terminals = list(self.terminals(board))
        terminal = board.DC(
            Hex.from_xy_fine(6, 6).to_plane()).setlayer("GTL")
        terminal.part = "J4"
        terminal.setname("1")
        terminals.append(terminal)
        for terminal in terminals:
            board.layers["GTL"].add(
                sg.Point(terminal.xy).buffer(0.2), terminal.name)
        board.drill(terminals[0].xy, 0.3)
        board.hex_setup()

        routes = board.hex_route_net(terminals, width=0.4)

        self.assertEqual(len(routes), 4)
        self.assertEqual(board.route_widths, [0.4] * 4)
        self.assertEqual(len(board.nets), 3)

    def test_pad_endpoint_uses_seeds_and_exempts_pad_periphery(self):
        board = HexBoard(
            (12, 12),
            trace=0.1,
            space=0.2,
            via_hole=0.3,
            via=0.6,
            via_space=0.1,
            silk=0.1,
        )
        pad_center = Hex.from_xy_fine(6, 6).to_plane()
        pad = board.DC(pad_center).setlayer("GTL")
        pad.part = "Y1"
        pad.setname("CLK")
        pad.boundary = sg.box(
            pad_center[0] - 0.65, pad_center[1] - 0.6,
            pad_center[0] + 0.65, pad_center[1] + 0.6,
        )
        board.layers["GTL"].add(pad.boundary, pad.name)

        obstacle_cell = Hex.from_xy_fine(2, 2)
        board.layers["GTL"].add(
            sg.Point(obstacle_cell.to_plane()).buffer(0.1), "obstacle")
        source_cell = Hex.from_xy_fine(10, 6)
        source = board.DC(source_cell.to_plane()).setlayer("GTL")
        source.part = "U1"
        source.setname("XIN")
        board.hex_setup()

        endpoint = board.pad_endpoint(pad)
        seeds = board.pad_hex_cells(endpoint)
        pad_exempt = board._blocked_for_width(
            "GTL", board.trace,
            exempt_geometries=(pad.boundary,),
        )
        peripheral = {
            tuple(cell)
            for cell in board.route_hexes
            if board.blocked["GTL"][cell.q, cell.r]
            and not pad_exempt[cell.q, cell.r]
            and tuple(cell) not in seeds
        }

        self.assertGreater(len(seeds), 1)
        self.assertTrue(peripheral)
        self.assertTrue(
            pad_exempt[obstacle_cell.q, obstacle_cell.r],
            "exempting the endpoint pad must not clear another obstacle",
        )
        for q, r in seeds:
            disk = sg.Point(Hex(q, r).to_plane()).buffer(board.trace / 2)
            self.assertGreaterEqual(
                disk.intersection(pad.boundary).area / disk.area,
                0.5 - 1e-12,
            )

        route = board.hex_route(source, endpoint)

        self.assertIn(tuple(route[0]), seeds)
        self.assertEqual(tuple(route[-1]), tuple(source_cell))
        self.assertEqual(
            board.nets,
            [(("U1", "XIN"), ("Y1", "CLK"))],
        )

    def test_multi_terminal_route_accepts_pad_endpoints(self):
        board = self.board()

        def pad_at(cell, part):
            center = cell.to_plane()
            draw = board.DC(center).setlayer("GTL")
            draw.part = part
            draw.setname("1")
            draw.boundary = sg.box(
                center[0] - 0.65, center[1] - 0.6,
                center[0] + 0.65, center[1] + 0.6,
            )
            board.layers["GTL"].add(draw.boundary, draw.name)
            return draw

        first = pad_at(Hex.from_xy_fine(2, 2), "C1")
        second = pad_at(Hex.from_xy_fine(10, 2), "C2")
        plain_cell = Hex.from_xy_fine(6, 10)
        plain = board.DC(plain_cell.to_plane()).setlayer("GTL")
        plain.part = "U1"
        plain.setname("VOUT")
        board.hex_setup()

        first_endpoint = board.pad_endpoint(first)
        second_endpoint = board.pad_endpoint(second)
        first_seeds = board.pad_hex_cells(first_endpoint)
        second_seeds = board.pad_hex_cells(second_endpoint)
        routes = board.hex_route_net(
            (first_endpoint, plain, second_endpoint))

        self.assertEqual(len(routes), 3)
        self.assertIn(tuple(routes[0][-1]), first_seeds)
        self.assertEqual(tuple(routes[1][-1]), tuple(plain_cell))
        self.assertIn(tuple(routes[2][-1]), second_seeds)
        self.assertEqual(
            board.nets,
            [(("C1", "1"), ("U1", "VOUT")),
             (("C1", "1"), ("C2", "1"))],
        )


if __name__ == "__main__":
    unittest.main()
