import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so
import svgwrite

def write(board, filename):
    gml = board.layers['GML'].lines
    block = sg.Polygon(gml[-1], gml[:-1])
    for d,xys in board.holes.items():
        if d > 0.3:
            hlist = so.unary_union([sg.Point(xy).buffer(d / 2) for xy in xys])
            block = block.difference(hlist)

    block = sa.scale(block, 1, -1)  # flip Y for svg
    (x0, y0, x1, y1) = block.bounds
    block = sa.translate(block, -x0, -y0)
    x1 -= x0
    y1 -= y0

    args = {'stroke':'red', 'fill_opacity':0.0, 'stroke_width':.1}

    dwg = svgwrite.Drawing(filename, size=('%fmm' % x1, '%fmm' % y1), viewBox=('0 0 %f %f' % (x1, y1)))
    li = [block.exterior] + list(block.interiors)
    for l in li:
        dwg.add(dwg.polyline(l.coords, **args))

    gto = board.layers['GTO'].preview()
    gto = sa.scale(gto, 1, -1)  # flip Y for svg
    gto = sa.translate(gto, -x0, -y0)

    args = {'fill':'black', 'fill_opacity':1.0, 'stroke_width':0}

    def renderpoly(po):
        if type(po) == sg.MultiPolygon:
            [renderpoly(p) for p in po]
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
            renderpoly(po.intersection(sg.box(x0, y0, xm + eps, y1)))
            renderpoly(po.intersection(sg.box(xm - eps, y0, x1, y1)))

    if 1:
        if isinstance(gto, sg.Polygon):
            renderpoly(gto)
        else:
            [renderpoly(po) for po in gto]

    args = {'stroke':'blue', 'fill_opacity':0.0, 'stroke_width':.1}
    for po in gto:
        li = [po.exterior] + list(po.interiors)
        for l in li:
            dwg.add(dwg.polyline(l.coords, **args))

    dwg.save()
