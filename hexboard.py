import math

import numpy as np
import shapely
import shapely.geometry as sg
import shapely.ops as so
from collections import deque
from dataclasses import dataclass
from shapely.strtree import STRtree
from PIL import Image, ImageDraw, ImageFont

import cuflow as cu
import hex
from hex import Hex, axial_direction_vectors

twenty_rgb = [
(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180), (0, 0, 128), (128, 128, 128), (255, 255, 255), (0, 0, 0)
]


@dataclass(frozen=True)
class PadEndpoint:
    draw: cu.Draw


class ByteGrid:
    def __init__(self, w, h):
        (self.q0, self.r1) = Hex.from_xy(0, h)
        (self.q1, _      ) = Hex.from_xy(w, 0)
        self.valid = self.zeros(np.uint8)
        for r in range(self.r1):
            for q in range(self.q0, self.q1):
                (x,y) = Hex(q, r).to_plane()
                if (0 <= x < w) and (0 <= y < h):
                    self.valid[q, r] = 1

    def zeros(self, type):
        return np.zeros([self.q1 - self.q0, self.r1], type)

    def show(self):
        for r in range(self.r1):
            for q in range(self.q0, self.q1):
                val = self.valid[q,r]
                print(f"{val:2x} ", end = '')
            print()
    
    def valids(self):
        for r in range(self.r1):
            for q in range(self.q0, self.q1):
                if self.valid[q, r]:
                    yield Hex(q, r)

def shift_array(arr, shift_x, shift_y):
    shifted_arr = np.zeros_like(arr)
    rows, cols = arr.shape

    if shift_x >= 0:
        x_src_start = 0
        x_src_end = rows - shift_x
        x_dst_start = shift_x
        x_dst_end = rows
    else:
        x_src_start = -shift_x
        x_src_end = rows
        x_dst_start = 0
        x_dst_end = rows + shift_x

    if shift_y >= 0:
        y_src_start = 0
        y_src_end = cols - shift_y
        y_dst_start = shift_y
        y_dst_end = cols
    else:
        y_src_start = -shift_y
        y_src_end = cols
        y_dst_start = 0
        y_dst_end = cols + shift_y

    shifted_arr[x_dst_start:x_dst_end, y_dst_start:y_dst_end] = \
        arr[x_src_start:x_src_end, y_src_start:y_src_end]

    return shifted_arr


class HexBoard(cu.Board):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.route_keepouts = {layer: [] for layer in ('GTL', 'GBL')}

    def add_hex_grid(self):
        width, height = self.size
        bounds = sg.box(0, 0, width, height)
        margin_x = 2 * hex.height
        margin_y = 2 * hex.size
        for h in hex.inrect(
                (-margin_x, -margin_y),
                (width + margin_x, height + margin_y)):
            clipped = sg.LineString(h.hexagon()).intersection(bounds)
            lines = clipped.geoms if hasattr(clipped, "geoms") else (clipped,)
            for line in lines:
                if isinstance(line, sg.LineString) and not line.is_empty:
                    self.layers["HEX"].add(line)
    
    def hex_setup(self):
        (hd, _) = (Hex(1, 0).to_plane())    # hd is the center-center distance
        self.hr = hd / 2                         # hr is the hex radius

        self.gr = ByteGrid(*self.size)
        self.route_hexes = tuple(self.gr.valids())
        self.valid_cells = frozenset(
            (h.q, h.r) for h in self.route_hexes)
        coordinates = np.asarray([h.to_plane() for h in self.route_hexes])
        self.route_radius = max(
            self.hr,
            self.trace / 2 + getattr(
                self, "hex_clearance", self.hr - self.trace / 2),
        )
        route_disks = shapely.buffer(
            shapely.points(coordinates), self.route_radius, quad_segs=16)
        self.route_tree = STRtree(route_disks)
        self.route_point_tree = STRtree(shapely.points(coordinates))
        self.blocked = {layer: self.layer_blocks(layer) for layer in ('GTL', 'GBL')}
        self.routes = []
        self.route_widths = []

    def layer_blocks(
            self, nm, width=None, exempt_points=(),
            exempt_geometries=()):
        explicit_width = width is not None
        width = self.trace if width is None else width
        endpoint_points = tuple(sg.Point(xy) for xy in exempt_points)
        exempt_geometry = so.unary_union(tuple(exempt_geometries))
        copper = [
            polygon
            for _, polygon in self.layers[nm].polys
            if not any(polygon.intersects(point) for point in endpoint_points)
        ]
        if not exempt_geometry.is_empty:
            copper = [polygon.difference(exempt_geometry) for polygon in copper]
        route_clearance = width / 2 + getattr(
            self, "hex_clearance", self.space)
        drill_expansion = max(0, route_clearance - self.route_radius)
        drill_keepouts = [
            sg.Point(xy).buffer(diameter / 2 + drill_expansion)
            for diameter, locations in self.holes.items()
            for xy in locations
            if not any(
                point.distance(sg.Point(xy)) <= diameter / 2 + 1e-6
                for point in endpoint_points
            )
        ]

        if not explicit_width:
            layer_poly = so.unary_union(
                copper + drill_keepouts + self.keepouts +
                self.route_keepouts[nm]).buffer(0)
            blocked = self.gr.zeros(np.uint8) | (self.gr.valid == 0)
            for i in self.route_tree.query(
                    layer_poly, predicate="intersects"):
                h = self.route_hexes[i]
                blocked[h.q, h.r] = 1
            return blocked

        geometry_expansion = max(0, route_clearance - self.route_radius)
        fixed_geometry = so.unary_union(
            copper + self.keepouts + self.route_keepouts[nm])
        if geometry_expansion:
            fixed_geometry = fixed_geometry.buffer(geometry_expansion)
        layer_poly = so.unary_union(
            [fixed_geometry] + drill_keepouts).buffer(0)
        blocked = self.gr.zeros(np.uint8) | (self.gr.valid == 0)
        for i in self.route_tree.query(layer_poly, predicate="intersects"):
            h = self.route_hexes[i]
            blocked[h.q, h.r] = 1
        return blocked

    @staticmethod
    def _route_geometry(route):
        points = [cell.to_plane() for cell in route]
        if len(points) == 1:
            return sg.Point(points[0])
        return sg.LineString(points)

    def _mark_blocked_geometry(self, blocked, geometry):
        for i in self.route_point_tree.query(
                geometry, predicate="intersects"):
            h = self.route_hexes[i]
            blocked[h.q, h.r] = 1

    def _blocked_for_width(
            self, layer, width, exempt_points=(), exempt_geometries=()):
        blocked = self.layer_blocks(
            layer, width, exempt_points, exempt_geometries)
        for ((route_layer, route), route_width) in zip(
                self.routes, self.route_widths):
            if route_layer != layer:
                continue
            clearance = (width + route_width) / 2 + getattr(
                self, "hex_clearance", self.space)
            corridor = self._route_geometry(route).buffer(clearance)
            self._mark_blocked_geometry(blocked, corridor)
        return blocked

    def pad_endpoint(self, draw):
        """Wrap a pad Draw for boundary-aware hex routing."""
        boundary = getattr(draw, "boundary", None)
        assert boundary is not None and not boundary.is_empty, (
            "pad_endpoint() needs a Draw with a non-empty boundary")
        return PadEndpoint(draw)

    def pad_hex_cells(self, endpoint, width=None):
        """Return cells whose wire-width center disk is >=50% in a pad."""
        draw = endpoint.draw if isinstance(endpoint, PadEndpoint) else endpoint
        boundary = getattr(draw, "boundary", None)
        assert boundary is not None and not boundary.is_empty, (
            "pad_hex_cells() needs a Draw with a non-empty boundary")
        route_width = self.trace if width is None else float(width)
        assert route_width > 0, "Route width must be positive"

        radius = route_width / 2
        search_area = boundary.buffer(radius)
        result = set()
        for index in self.route_point_tree.query(
                search_area, predicate="intersects"):
            cell = self.route_hexes[index]
            disk = sg.Point(cell.to_plane()).buffer(radius)
            coverage = disk.intersection(boundary).area / disk.area
            if coverage + 1e-12 >= 0.5:
                result.add(tuple(cell))
        assert result, (
            "No hex cell center disk is at least 50% covered by the pad")
        return frozenset(result)

    def _hex_route_pad_endpoints(self, a, b):
        """Lee-route between endpoints when at least one is a PadEndpoint."""
        source = a.draw if isinstance(a, PadEndpoint) else a
        target = b.draw if isinstance(b, PadEndpoint) else b
        layer = source.layer
        assert target.layer == layer

        source_cells = (
            self.pad_hex_cells(a)
            if isinstance(a, PadEndpoint)
            else frozenset((tuple(Hex.from_xy(*source.xy)),)))
        target_cells = (
            self.pad_hex_cells(b)
            if isinstance(b, PadEndpoint)
            else frozenset((tuple(Hex.from_xy(*target.xy)),)))
        exempt_geometries = tuple(
            endpoint.draw.boundary
            for endpoint in (a, b)
            if isinstance(endpoint, PadEndpoint)
        )
        blocked = self._blocked_for_width(
            layer, self.trace, exempt_geometries=exempt_geometries)

        def available(cells, endpoint):
            if not isinstance(endpoint, PadEndpoint):
                return cells
            return frozenset(
                cell for cell in cells
                if not blocked[cell[0], cell[1]])

        source_cells = available(source_cells, a)
        target_cells = available(target_cells, b)
        assert source_cells, "All source pad terminal cells are blocked"
        assert target_cells, "All target pad terminal cells are blocked"

        directions = [Hex(dq, dr) for dq, dr in axial_direction_vectors]
        previous = {cell: None for cell in source_cells}
        pending = deque(sorted(source_cells, key=lambda cell: (cell[1], cell[0])))
        destination = None
        while pending:
            cell = pending.popleft()
            if cell in target_cells:
                destination = cell
                break
            h = Hex(*cell)
            for direction in directions:
                neighbor = h + direction
                neighbor_cell = tuple(neighbor)
                if (neighbor_cell not in self.valid_cells or
                        neighbor_cell in previous or
                        (neighbor_cell not in target_cells and
                         blocked[neighbor.q, neighbor.r])):
                    continue
                previous[neighbor_cell] = cell
                pending.append(neighbor_cell)
        assert destination is not None, "Signal failed to route"

        route = [Hex(*destination)]
        cell = destination
        while previous[cell] is not None:
            cell = previous[cell]
            route.append(Hex(*cell))
        for cell in route:
            self.blocked[layer][cell.q, cell.r] = 1
        self.routes.append((layer, route))
        self.route_widths.append(self.trace)
        self.addnet(source, target)
        return route

    def hex_route(self, a, b):
        if isinstance(a, PadEndpoint) or isinstance(b, PadEndpoint):
            return self._hex_route_pad_endpoints(a, b)

        layer = a.layer
        assert b.layer == a.layer
        source = a
        target = b
        a = Hex.from_xy(*source.xy)
        b = Hex.from_xy(*target.xy)

        wavefront = set([tuple(a)])
        dirs = [Hex(dq,dr) for (dq, dr) in axial_direction_vectors]

        valid = self.valid_cells
        blocked = self.blocked[layer].copy()
        blocked[b.q, b.r] = 0
        distance = self.gr.zeros(np.uint8)

        i = 1
        while tuple(b) not in wavefront:
            wavefront2 = set()
            for p in wavefront:
                h = Hex(*p)
                for d in dirs:
                    n = h + d
                    if tuple(n) in valid and not blocked[n.q, n.r]:
                        wavefront2.add(tuple(n))
                        blocked[n.q, n.r] = 1
                        distance[n.q, n.r] = i
            assert wavefront2 != wavefront, f"Signal failed to route"
            wavefront = wavefront2
            # print(f"{i=} {wavefront=}")

            i += 1
        
        route = [b]
        p = b
        while distance[p.q, p.r] != 1:
            n = distance[p.q, p.r]
            assert n != 0
            for d in dirs:
                if distance[p.q + d.q, p.r + d.r] == (n - 1):
                    p = p + d
                    route.append(p)
                    self.blocked[layer][p.q, p.r] = 1
                    break
        route.append(a)
        self.routes.append((layer, route))
        self.route_widths.append(self.trace)
        self.addnet(source, target)

    def hex_route_net(self, terminals, width=None):
        """Route a multi-terminal net, optionally reserving a wide corridor.

        Omitting ``width`` retains the legacy one-cell routing behavior.
        An explicit width expands fixed-obstacle clearance, accounts for
        previously routed widths, renders the requested copper width, and
        reserves enough space for subsequent default-width routes.
        """
        terminals = tuple(terminals)
        assert len(terminals) >= 2, "hex_route_net() needs at least two terminals"

        route_width = self.trace if width is None else float(width)
        assert route_width > 0, "Route width must be positive"

        draws = tuple(
            terminal.draw if isinstance(terminal, PadEndpoint) else terminal
            for terminal in terminals)
        layer = draws[0].layer
        assert all(draw.layer == layer for draw in draws)

        endpoint_cells = [
            (self.pad_hex_cells(terminal, route_width)
             if isinstance(terminal, PadEndpoint)
             else frozenset((tuple(Hex.from_xy(*draw.xy)),)))
            for terminal, draw in zip(terminals, draws)
        ]
        exempt_geometries = tuple(
            terminal.draw.boundary
            for terminal in terminals
            if isinstance(terminal, PadEndpoint)
        )
        valid = self.valid_cells
        if width is None and not exempt_geometries:
            blocked = self.blocked[layer]
        else:
            blocked = self._blocked_for_width(
                layer, route_width,
                exempt_points=(draw.xy for draw in draws),
                exempt_geometries=exempt_geometries,
            )
        endpoint_cells = [
            (frozenset(
                cell for cell in cells
                if not blocked[cell[0], cell[1]])
             if isinstance(terminal, PadEndpoint) else cells)
            for terminal, cells in zip(terminals, endpoint_cells)
        ]
        assert all(endpoint_cells), "All pad terminal cells are blocked"
        terminal_cells = set().union(*endpoint_cells)
        directions = [Hex(dq, dr) for dq, dr in axial_direction_vectors]

        def wavefront(starts):
            ordered_starts = sorted(starts, key=lambda cell: (cell[1], cell[0]))
            distance = {cell: 0 for cell in ordered_starts}
            previous = {cell: None for cell in ordered_starts}
            pending = deque(ordered_starts)
            while pending:
                cell = pending.popleft()
                h = Hex(*cell)
                for direction in directions:
                    neighbor = h + direction
                    neighbor_cell = tuple(neighbor)
                    if neighbor_cell not in valid or neighbor_cell in distance:
                        continue
                    if (neighbor_cell not in terminal_cells and
                            blocked[neighbor.q, neighbor.r]):
                        continue
                    distance[neighbor_cell] = distance[cell] + 1
                    previous[neighbor_cell] = cell
                    pending.append(neighbor_cell)
            return distance, previous

        searches = [wavefront(cells) for cells in endpoint_cells]
        common = set(searches[0][0])
        for distance, _ in searches[1:]:
            common.intersection_update(distance)
        assert common, "Signal net failed to route"

        junction = min(common, key=lambda cell: (
            sum(distance[cell] for distance, _ in searches),
            max(distance[cell] for distance, _ in searches),
            cell[1],
            cell[0],
        ))

        routes = []
        occupied = set()
        for terminal_cells_for_endpoint, (_, previous) in zip(
                endpoint_cells, searches):
            cell = junction
            route = [Hex(*cell)]
            occupied.add(cell)
            while cell not in terminal_cells_for_endpoint:
                cell = previous[cell]
                route.append(Hex(*cell))
                occupied.add(cell)
            routes.append(route)

        if width is None:
            for q, r in occupied:
                self.blocked[layer][q, r] = 1
        else:
            clearance = (route_width + self.trace) / 2 + getattr(
                self, "hex_clearance", self.space)
            corridor = so.unary_union([
                self._route_geometry(route)
                for route in routes
            ]).buffer(clearance)
            self._mark_blocked_geometry(self.blocked[layer], corridor)
        self.routes.extend((layer, route) for route in routes)
        self.route_widths.extend(route_width for route in routes)
        for draw in draws[1:]:
            self.addnet(draws[0], draw)

        return routes

    def hex_render(self):
        (w, h) = self.size
        (hd, _) = (Hex(1, 0).to_plane())    # hd is the center-center distance
        hr = hd / 2                         # hr is the hex radius

        ppmm = 25   # pixels per mm
        im = Image.new("RGB", (int(w * ppmm), int(h * ppmm)), 'black')
        dr = ImageDraw.Draw(im)
        def xf(xy):
            (x, y) = xy
            return (x * ppmm, (self.size[1]  - y) * ppmm)

        def draw_geometry(geometry):
            if isinstance(geometry, sg.Polygon):
                dr.polygon(
                    [xf(point) for point in geometry.exterior.coords],
                    fill = (60, 60, 160))
                for interior in geometry.interiors:
                    dr.polygon(
                        [xf(point) for point in interior.coords],
                        fill = 'black')
            elif hasattr(geometry, "geoms"):
                for child in geometry.geoms:
                    draw_geometry(child)

        for _, polygon in self.layers['GTL'].polys:
            draw_geometry(polygon)

        for h in self.gr.valids():
            if not self.blocked['GTL'][h.q, h.r]:
                dr.circle(xf(h.to_plane()), outline = (110, 110, 110), radius = hd * ppmm / 2)

        if 1:
            for color,(layer, r) in zip(twenty_rgb, self.routes):
                for e in r:
                    dr.circle(xf(e.to_plane()), fill = color, radius = hd * ppmm / 2)

        im.save("out.png")

    def wire_routes(self):
        for ((layer, r), width) in zip(self.routes, self.route_widths):
            d = self.DC(r[0].to_plane()).setlayer(layer)
            for p in r[1:]:
                d.path.append(p.to_plane())
            if width == self.trace:
                d.wire()
            else:
                d.wire(width=width)


def best_forward(p):
    hh = Hex.from_xy(*p.xy)
    return hh.best_forward(p)

def river_ongrid(rr):
    assert rr.tt[0].dir in (30, 90, 150, 210, 270, 330)
    p = rr.tt[0]
    (dx, dy) = best_forward(p)

    rr.shimmy(-dx)
    for t in rr.tt:
        (dx, dy) = best_forward(t)
        assert dx < 0.010
        t.forward(dy).wire()
    return rr

def wire_ongrid(p):
    (dx, dy) = best_forward(p)
    if 0:
        (x, y) = p.xy
        p.path.append((x + dx, y + dy))
        p.wire()
    else:
        p.goyx(dx, dy).wire()
    p.dir = 30 + 60 * round((p.dir - 30) / 60)
    return p

def wire_ongrid2(p):
    """Join the selected forward hex center with one straight segment."""
    (dx, dy) = best_forward(p)
    (x, y) = p.xy
    a = math.radians(p.dir)
    s = math.sin(a)
    c = math.cos(a)
    p.xy = (
        x + dx * c + dy * s,
        y + dy * c - dx * s,
    )
    p.path.append(p.xy)
    p.wire()
    p.dir = 30 + 60 * round((p.dir - 30) / 60)
    return p
