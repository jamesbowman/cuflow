import os
import sys
import math
import pickle
import cairo
import sys
import shapely.geometry as sg

sys.path.append("..")

import hex

empty = sg.GeometryCollection()

def polygon(ctx, pts):
    ctx.move_to(*pts[0])
    for x, y in pts[1:]:
        ctx.line_to(x, y)
    ctx.close_path()

SCALE = 100     # pixels per mm

def make_internal():
    F = math.sin(math.pi / 3)
    d = 0.3 / F
    d = 0.4

    W = int(SCALE * d)
    H = int(SCALE * d)

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    ctx.translate(W/2.0, H/2.0)
    ctx.scale(SCALE, -SCALE)

    xys = []
    for i in range(4):
        th = i * (2 * math.pi) / 6
        x = (d / 2) * math.sin(th)
        y = (d / 2) * math.cos(th)
        xys.append((x, y))

    ctx.move_to(*xys[0])
    for p in xys[1:]:
        ctx.line_to(*p)
    # ctx.close_path()

    ctx.set_source_rgb(.4, .4, .3)
    ctx.set_line_width(0.01)
    ctx.stroke()

    surf.write_to_png(f"_blank.png")
    
def make_part(fn):
    basename = fn[3:-7]
    print(f"{basename=}")
    part = pickle.load(open(fn, "rb"))

    geom = empty
    for k in part.keys():
        if k.startswith("G"):
            geom = geom.union(part[k])

    (minx, miny, maxx, maxy) = geom.bounds
    d = 2 * max([abs(o) for o in (minx, miny, maxx, maxy)])
    w = 2 * d        # in mm
    h = 2 * d

    W = int(SCALE * w)
    H = int(SCALE * h)

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    ctx.translate(W/2.0, H/2.0)
    ctx.scale(SCALE, -SCALE)

    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)  # holes punched out

    for (rgba, n) in [
        ((0.62, 0.62, 0.00, 0.8), "GTL"),
        ((1.00, 1.00, 1.00, 0.8), "GTO"),
        ]:
        ctx.set_source_rgba(*rgba)
        l = part[n]
        for po in l.geoms:
            polygon(ctx, list(po.exterior.coords))
            for lr in po.interiors:
                polygon(ctx, list(lr.coords))
            ctx.fill()

    surf.write_to_png(f"{basename}.png")

for fn in sys.argv[1:]:
    if fn == "internal":
        make_internal()
    else:
        make_part(fn)
