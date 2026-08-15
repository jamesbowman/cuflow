"""Load filled SVG artwork as Shapely polygon geometry."""

import math

import shapely.geometry as sg
import shapely.ops as so
from svgelements import Close, Color, Line, Move, Path, Shape, SVG


def _xy(point):
    return (float(point.x), float(point.y))


def _point_segment_distance(point, start, end):
    px, py = point
    x0, y0 = start
    x1, y1 = end
    dx = x1 - x0
    dy = y1 - y0
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0,
        ((px - x0) * dx + (py - y0) * dy) / length_squared))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def _flatten_segment(segment, tolerance, max_depth=18):
    """Return points after the segment start, within the given tolerance."""
    result = []

    def visit(t0, start, t1, end, depth):
        dt = t1 - t0
        samples = [
            _xy(segment.point(t0 + dt * 0.25)),
            _xy(segment.point(t0 + dt * 0.50)),
            _xy(segment.point(t0 + dt * 0.75)),
        ]
        error = max(
            _point_segment_distance(point, start, end)
            for point in samples)
        if error <= tolerance or depth == max_depth:
            result.append(end)
            return

        midpoint = samples[1]
        middle_t = t0 + dt * 0.5
        visit(t0, start, middle_t, midpoint, depth + 1)
        visit(middle_t, midpoint, t1, end, depth + 1)

    visit(0.0, _xy(segment.point(0.0)),
          1.0, _xy(segment.point(1.0)), 0)
    return result


def _flatten_subpath(subpath, tolerance):
    points = []
    for segment in subpath:
        if isinstance(segment, Move):
            if segment.end is not None:
                points.append(_xy(segment.end))
        elif segment.end is not None:
            if not points and segment.start is not None:
                points.append(_xy(segment.start))
            if isinstance(segment, (Line, Close)):
                points.append(_xy(segment.end))
            else:
                points.extend(_flatten_segment(segment, tolerance))

    # SVG fill closes open subpaths implicitly.
    if points and points[-1] != points[0]:
        points.append(points[0])

    deduplicated = []
    for point in points:
        if not deduplicated or point != deduplicated[-1]:
            deduplicated.append(point)
    if deduplicated and deduplicated[-1] != deduplicated[0]:
        deduplicated.append(deduplicated[0])
    return deduplicated


def _winding_number(rings, point):
    px, py = point
    winding = 0
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            side = (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0)
            if y0 <= py < y1 and side > 0:
                winding += 1
            elif y1 <= py < y0 and side < 0:
                winding -= 1
    return winding


def _crossing_count(rings, point):
    px, py = point
    crossings = 0
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            if (y0 > py) != (y1 > py):
                crossing_x = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
                if crossing_x > px:
                    crossings += 1
    return crossings


def _filled_path(path, fill_rule, tolerance):
    rings = [
        ring for ring in (
            _flatten_subpath(subpath, tolerance)
            for subpath in path.as_subpaths())
        if len(ring) >= 4
    ]
    if not rings:
        return sg.MultiPolygon()

    boundaries = so.unary_union([sg.LineString(ring) for ring in rings])
    faces = []
    for face in so.polygonize(boundaries):
        point = face.representative_point().coords[0]
        if fill_rule == "evenodd":
            filled = _crossing_count(rings, point) % 2 == 1
        else:
            filled = _winding_number(rings, point) != 0
        if filled:
            faces.append(face)
    return so.unary_union(faces) if faces else sg.MultiPolygon()


def _opacity(values, name):
    value = values.get(name, 1.0)
    if isinstance(value, str) and value.endswith("%"):
        return float(value[:-1]) / 100.0
    return float(value)


def _visible_fill(element, wanted_rgb):
    fill = getattr(element, "fill", None)
    if fill is None or fill.value is None or fill.alpha == 0:
        return False
    values = element.values
    if values.get("visibility") in ("hidden", "collapse"):
        return False
    if (_opacity(values, "opacity") == 0 or
            _opacity(values, "fill-opacity") == 0):
        return False
    return wanted_rgb is None or fill.rgb == wanted_rgb


def _as_multipolygon(geometry):
    if geometry.is_empty:
        return sg.MultiPolygon()
    if isinstance(geometry, sg.Polygon):
        return sg.MultiPolygon([geometry])
    if isinstance(geometry, sg.MultiPolygon):
        return geometry

    polygons = []
    for part in geometry.geoms:
        if isinstance(part, sg.Polygon):
            polygons.append(part)
        elif isinstance(part, (sg.MultiPolygon, sg.GeometryCollection)):
            polygons.extend(_as_multipolygon(part).geoms)
    return sg.MultiPolygon(polygons)


def load_svg(source, fill=None, tolerance=0.25, ppi=96.0):
    """Return the filled regions in an SVG as a Shapely MultiPolygon.

    ``fill`` optionally selects one SVG fill color, such as ``"#f6d410"``.
    Colors are matched by RGB value; transparent and zero-opacity shapes are
    always skipped. ``tolerance`` is the maximum curve-flattening error in SVG
    user units.

    SVG and group transforms are applied. Filled paths and basic SVG shapes are
    supported; strokes, clipping paths, masks, filters, images, and live text
    are not rendered. Coordinates retain SVG's downwards-positive Y axis.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")

    wanted_rgb = None
    if fill is not None:
        wanted = Color(fill)
        if wanted.value is None:
            raise ValueError("fill must be a visible SVG color")
        wanted_rgb = wanted.rgb

    svg = SVG.parse(source, reify=True, ppi=ppi)
    geometries = []
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        if not _visible_fill(element, wanted_rgb):
            continue
        fill_rule = element.values.get("fill-rule", "nonzero").lower()
        geometries.append(_filled_path(
            Path(element), fill_rule, tolerance))

    if not geometries:
        return sg.MultiPolygon()
    return _as_multipolygon(so.unary_union(geometries))


# The short name is convenient when importing the module as ``svg_loader``.
load = load_svg
