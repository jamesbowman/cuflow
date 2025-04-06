import numpy as np
import shapely.geometry as sg
from shapely.strtree import STRtree
from PIL import Image, ImageDraw, ImageFont

import cuflow as cu
from hex import Hex, axial_direction_vectors

twenty_rgb = [
(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180), (0, 0, 128), (128, 128, 128), (255, 255, 255), (0, 0, 0)
]

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
    
    def hex_setup(self):
        (hd, _) = (Hex(1, 0).to_plane())    # hd is the center-center distance
        self.hr = hd / 2                         # hr is the hex radius

        self.gr = ByteGrid(*self.size)
        self.blocked = {layer: self.layer_blocks(layer) for layer in ('GTL', 'GBL')}
        self.routes = []

    def layer_blocks(self, nm):
        layer_poly = sg.MultiPolygon([p for (nm, p) in self.layers[nm].polys]).buffer(0)
        blocked = self.gr.zeros(np.uint8) | (self.gr.valid == 0)
        vv = list(self.gr.valids())
        hexes = [sg.Point(h.to_plane()).buffer(self.hr) for h in vv]
        s = STRtree(hexes)
        result = s.query_nearest(layer_poly)
        for i in result:
            h = vv[i]
            blocked[h.q, h.r] = 1
        return blocked

    def hex_route(self, a, b):
        layer = a.layer
        assert b.layer == a.layer
        a = Hex.from_xy(*a.xy)
        b = Hex.from_xy(*b.xy)

        wavefront = set([tuple(a)])
        dirs = [Hex(dq,dr) for (dq, dr) in axial_direction_vectors]

        valid = {(h.q, h.r) for h in self.gr.valids()}
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

        for (nm, p) in self.layers['GTL'].polys:
            pts = [xf(p) for p in p.exterior.coords]
            dr.polygon(pts, fill = (60, 60, 160))

        for h in self.gr.valids():
            if not self.blocked['GTL'][h.q, h.r]:
                dr.circle(xf(h.to_plane()), outline = (110, 110, 110), radius = hd * ppmm / 2)

        if 1:
            for color,(layer, r) in zip(twenty_rgb, self.routes):
                for e in r:
                    dr.circle(xf(e.to_plane()), fill = color, radius = hd * ppmm / 2)

        im.save("out.png")

    def wire_routes(self):
        for (layer, r) in self.routes:
            d = self.DC(r[0].to_plane()).setlayer(layer)
            for p in r[1:]:
                d.path.append(p.to_plane())
            d.wire()


def best_forward(p):
    hh = Hex.from_xy(*p.xy)
    return hh.best_forward(p)

def river_ongrid(rr):
    print(f"{rr=}")
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

