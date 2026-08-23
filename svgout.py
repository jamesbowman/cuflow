import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so
import svgwrite


def _polygons(geometry):
    if geometry.is_empty:
        return
    if isinstance(geometry, sg.Polygon):
        yield geometry
    elif isinstance(geometry, (sg.MultiPolygon, sg.GeometryCollection)):
        for part in geometry.geoms:
            yield from _polygons(part)


def _ring_path(ring):
    coordinates = list(ring.coords)
    if coordinates and coordinates[0] == coordinates[-1]:
        coordinates.pop()
    if not coordinates:
        return ""
    points = [f"{x:.6f},{y:.6f}" for x, y in coordinates]
    return "M " + " L ".join(points) + " Z"


class SVGAnnotations:
    """SVG-native artwork kept separate from manufacturing layers."""

    def __init__(self):
        self.elements = []

    def rectangle(self, center, size, *, fill):
        self.elements.append({
            "kind": "rectangle",
            "center": center,
            "size": size,
            "fill": fill,
        })

    def text(self, xy, value, font_size, *, anchor="start",
             font_family="sans-serif", font_weight="normal", fill="black"):
        self.elements.append({
            "kind": "text",
            "xy": xy,
            "value": value,
            "font_size": font_size,
            "anchor": anchor,
            "font_family": font_family,
            "font_weight": font_weight,
            "fill": fill,
        })


def _add_geometry(drawing, group, geometry, fill):
    for polygon in _polygons(geometry):
        rings = [polygon.exterior, *polygon.interiors]
        path_data = " ".join(filter(None, map(_ring_path, rings)))
        group.add(drawing.path(
            d=path_data,
            fill=fill,
            fill_rule="evenodd",
            stroke="none",
        ))


def write_art(board, filename, silkscreen_fill="#add8e6"):
    """Write the top silkscreen plus SVG-native annotations."""
    width, height = board.size
    artwork = board.layers["GTO"].preview()

    # CuFlow coordinates have their origin at the board's bottom-left. SVG's
    # Y axis points down, so flip about the board's horizontal centreline.
    artwork = sa.scale(artwork, 1, -1, origin=(0, 0))
    artwork = sa.translate(artwork, yoff=height)

    drawing = svgwrite.Drawing(
        filename,
        size=(f"{width:g}mm", f"{height:g}mm"),
        viewBox=f"0 0 {width:g} {height:g}",
    )
    drawing.attribs["shape-rendering"] = "geometricPrecision"

    silkscreen = drawing.g(id="silkscreen")
    _add_geometry(drawing, silkscreen, artwork, silkscreen_fill)
    drawing.add(silkscreen)

    annotations = drawing.g(id="art")
    for element in board.svg_layers["art"].elements:
        if element["kind"] == "rectangle":
            x, y = element["center"]
            rectangle_width, rectangle_height = element["size"]
            annotations.add(drawing.rect(
                insert=(x - rectangle_width / 2,
                        height - y - rectangle_height / 2),
                size=(rectangle_width, rectangle_height),
                fill=element["fill"],
            ))
        elif element["kind"] == "text":
            x, y = element["xy"]
            annotations.add(drawing.text(
                element["value"],
                insert=(x, height - y),
                fill=element["fill"],
                font_family=element["font_family"],
                font_weight=element["font_weight"],
                font_size=element["font_size"],
                text_anchor=element["anchor"],
                dominant_baseline="middle",
            ))
    drawing.add(annotations)
    drawing.save(pretty=True)


def write(board, filename, style = 'laser'):
    gml = board.layers['GML'].lines
    block = sg.Polygon(gml[-1], gml[:-1])
    block = block.buffer(1).buffer(-1)
    for d,xys in board.holes.items():
        if d > 0.3:
            hlist = so.unary_union([sg.Point(xy).buffer(d / 2) for xy in xys])
            block = block.difference(hlist)

    block = sa.scale(block, 1, -1, origin = (0,0))  # flip Y for svg
    (x0, y0, x1, y1) = block.bounds
    block = sa.translate(block, -x0, -y0)
    x1 -= x0
    y1 -= y0

    if style == 'laser':
        args = {'stroke':'red', 'fill_opacity':0.0, 'stroke_width':.1}
    else:
        args = {'stroke':'gray', 'fill_opacity':0.0, 'stroke_width':.1}

    dwg = svgwrite.Drawing(filename, size=('%fmm' % x1, '%fmm' % y1), viewBox=('0 0 %f %f' % (x1, y1)))
    li = [block.exterior] + list(block.interiors)
    for l in li:
        dwg.add(dwg.polyline(l.coords, **args))

    def renderpoly(po, args):
        if type(po) == sg.MultiPolygon:
            [renderpoly(p, args) for p in po.geoms]
            return
        # Subdivide a poly if it has holes
        if len(po.interiors) == 0:
            dwg.add(dwg.polygon(po.exterior.coords, **args))
        else:
            x0 = min([x for (x, y) in po.exterior.coords])
            x1 = max([x for (x, y) in po.exterior.coords])
            y0 = min([y for (x, y) in po.exterior.coords])
            y1 = max([y for (x, y) in po.exterior.coords])
            xm = (x0 + x1) / 2
            eps = 0.00
            renderpoly(po.intersection(sg.box(x0, y0, xm + eps, y1)), args)
            renderpoly(po.intersection(sg.box(xm - eps, y0, x1, y1)), args)

    if 0:
        args = {'stroke':'blue', 'fill_opacity':0.0, 'stroke_width':.1}
        for po in gto.geoms:
            li = [po.exterior] + list(po.interiors)
            for l in li:
                dwg.add(dwg.polyline(l.coords, **args))

    def layer(nm, args1, args2):
        gto = board.layers[nm].preview()
        gto = sa.scale(gto, 1, -1, origin = (0, 0))  # flip Y for svg
        gto = sa.translate(gto, -x0, -y0)

        if 1:
            if isinstance(gto, sg.Polygon):
                renderpoly(gto, args1)
            else:
                [renderpoly(po, args1) for po in gto.geoms]

        for po in gto.geoms:
            li = [po.exterior] + list(po.interiors)
            for l in li:
                dwg.add(dwg.polyline(l.coords, **args2))

    if style == 'laser':
        args = {'stroke':'blue', 'fill_opacity':0.0, 'stroke_width':.1}
    else:
        args = {'stroke':'black', 'fill_opacity':0.0, 'stroke_width':0}
    layer('GTO',
        {'fill':'black', 'fill_opacity':1.0, 'stroke_width':0},
        args)

    if style == 'lands':
        layer('GTL',
            {'fill':'black', 'fill_opacity':1.0, 'stroke_width':0},
            {'stroke':'grey', 'fill_opacity':0.0, 'stroke_width':.1})

    dwg.save()
