import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so
import svgwrite

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
