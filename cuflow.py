from collections import defaultdict

import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so
import math

import gerber
import hershey

def inches(x):  return x * 25.4
def mil(x):     return inches(x / 1000)
def micron(x):  return x / 1000

class Layer:
    def __init__(self, desc):
        self.polys = []
        self.desc = desc

    def circle(self, x, y, r, color = None):
        self.add(sg.Point(x, y).buffer(r))

    def add(self, o):
        # .buffer(0) to work around shapely bugs
        self.polys.append(o.buffer(0))

    def save(self, f):
        surface = so.unary_union(self.polys)
        g = gerber.Gerber(f, self.desc)
        def renderpoly(g, po):
            if type(po) == sg.MultiPolygon:
                [renderpoly(g, p) for p in po]
                return
            # Subdivide a poly if it has holes
            if len(po.interiors) == 0:
                g.poly(po.exterior.coords)
            else:
                x0 = min([x for (x, y) in po.exterior.coords])
                x1 = max([x for (x, y) in po.exterior.coords])
                y0 = min([y for (x, y) in po.exterior.coords])
                y1 = max([y for (x, y) in po.exterior.coords])
                xm = (x0 + x1) / 2
                renderpoly(g, po.intersection(sg.box(x0, y0, xm, y1)))
                renderpoly(g, po.intersection(sg.box(xm, y0, x1, y1)))

        if isinstance(surface, sg.Polygon):
            renderpoly(g, surface)
        else:
            [renderpoly(g, po) for po in surface]
        g.finish()

class Turtle:
    def w(self, s, layer = 'GTL'):
        tokens = s.split()
        cmds1 = {
            'i' : self.inside,
            'o' : self.outside,
            '-' : lambda: self.wvia('GL2'),
            '+' : lambda: self.wvia('GL3'),
        }
        cmds2 = {
            'f' : self.forward,
            'l' : self.left,
            'r' : self.right
        }

        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t in cmds1:
                cmds1[t]()
                i += 1
            else:
                cmds2[t](float(tokens[i + 1]))
                i += 2
        # self.wire(layer)

    def inside(self): pass
    def outside(self): pass

class Draw(Turtle):
    def __init__(self, board, xy, dir = 0):
        self.board = board
        self.xy = xy
        self.dir = dir
        self.stack = []
        self.newpath()

    def newpath(self):
        self.path = [self.xy]

    def push(self):
        self.stack.append((self.xy, self.dir))

    def pop(self):
        (self.xy, self.dir) = self.stack.pop(-1)

    def copy(self):
        r = Draw(self.board, self.xy, self.dir)
        r.h = self.h
        return r

    def forward(self, d):
        (x, y) = self.xy
        a = (self.dir / 360) * (2 * math.pi)
        (xd, yd) = (d * math.sin(a), d * math.cos(a))
        self.xy = (x + xd, y + yd)
        self.path.append(self.xy)

    def left(self, d):
        self.dir = (self.dir - d) % 360

    def right(self, d):
        self.dir = (self.dir + d) % 360

    def approach(self, d, other):
        assert ((self.dir - other.dir) % 360) in (90, 270)
        # Go forward to be exactly d away from infinite line 'other'
        (x0, y0) = self.xy
        (x1, y1) = other.xy
        o2 = other.copy()
        o2.forward(1)
        (x2, y2) = o2.xy
        # print((x0, y0), (x1, y1), (x2, y2))

        self.forward(abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) - d)

    def seek(self, other):
        # Return position of other in our frame as (x, y) so that
        #     forward(y)
        #     right(90)
        #     forward(x)
        # moves to the other

        (dx, dy) = (other.xy[0] - self.xy[0], other.xy[1] - self.xy[1])
        a = (self.dir / 360) * (2 * math.pi)
        s = math.sin(a)
        c = math.cos(a)
        ox = dx * c - dy * s
        oy = dy * c + dx * s
        return (ox, oy)

    def is_behind(self, other):
        assert abs(self.dir - other.dir) < 0.0001
        (_, y) = self.seek(other)
        return y > 0

    def distance(self, other):
        return math.sqrt((other.xy[0] - self.xy[0]) ** 2 + (other.xy[1] - self.xy[1]) ** 2)

    def rect(self, w, h):
        self.push()
        self.forward(h / 2)
        self.right(90)
        self.forward(w / 2)

        self.newpath()
        self.right(90)
        self.forward(h)
        self.right(90)
        self.forward(w)
        self.right(90)
        self.forward(h)
        self.right(90)
        self.forward(w)
        self.pop()
        self.h = h  # used by inside, outside for pad escape

    def inside(self):
        self.right(180)
        self.forward(self.h / 2)

    def outside(self):
        self.forward(self.h / 2)

    def square(self, w):
        self.rect(w, w)

    def pad(self):
        g = sg.Polygon(self.path)
        for n in ('GTL', 'GTS', 'GTP'):
            self.board.layers[n].add(g)

    def silko(self):
        g = sg.LinearRing(self.path).buffer(self.board.silk / 2)
        self.board.layers['GTO'].add(g)

    def via(self, connect = None):
        g = sg.Point(self.xy).buffer(self.board.via / 2)
        for n in {'GTL', 'GL2', 'GL3', 'GBL'} - {connect}:
            self.board.layers[n].add(g)
        self.newpath()

    def wire(self, layer = 'GTL'):
        if len(self.path) > 1:
            g = sg.LineString(self.path).buffer(self.board.trace / 2)
            self.board.layers[layer].add(g)
            self.newpath()

    def wvia(self, l):
        # enough wire then a via
        b = self.board
        self.forward(b.via_space + b.via / 2)
        self.wire()
        self.via(l)

class River(Turtle):
    def __init__(self, board, tt):
        self.tt = tt
        self.board = board
        self.c = self.board.c

    def r(self):
        return self.c * (len(self.tt) - 1)

    def forward(self, d):
        [t.forward(d) for t in self.tt]

    def rpivot(self, a):
        # rotate all points clockwise by angle a
        s = math.sin(a)
        c = math.cos(a)
        (x0, y0) = self.tt[0].xy
        for (i, t) in enumerate(self.tt):
            r = self.c * i
            x = t.xy[0] - x0
            y = t.xy[1] - y0
            nx = x * c - y * s
            ny = y * c + x * s
            t.xy = (x0 + nx, y0 + ny)
            t.path.append(t.xy)

    def lpivot(self, a):
        # rotate all points counter-clockwise by angle a
        s = math.sin(a)
        c = math.cos(a)
        tt = self.tt[::-1]
        (x0, y0) = tt[0].xy
        for (i, t) in enumerate(tt):
            r = self.c * i
            x = t.xy[0] - x0
            y = t.xy[1] - y0
            nx = x * c - y * s
            ny = y * c + x * s
            t.xy = (x0 + nx, y0 + ny)
            t.path.append(t.xy)

    def right(self, a):
        fd = (self.tt[0].dir + a) % 360
        n = int(a + 1)
        ra = 2 * math.pi * a / 360
        for i in range(n):
            self.rpivot(-ra / n)
        for t in self.tt:
            t.dir = fd

    def left(self, a):
        fd = (self.tt[0].dir - a) % 360
        n = int(a + 1)
        ra = 2 * math.pi * a / 360
        for i in range(n):
            self.lpivot(ra / n)
        for t in self.tt:
            t.dir = fd

    def shimmy(self, d):
        if d == 0:
            return
        r = self.r()
        if abs(d) > r:
            a = 90
            f = abs(d) - r
        else:
            a = 180 * math.acos(1 - abs(d) / r) / math.pi
            f = 0
        if d > 0:
            self.left(a)
            self.forward(f)
            self.right(a)
        else:
            self.right(a)
            self.forward(f)
            self.left(a)

    def join(self, other, ratio = 0.0):
        assert 0 <= ratio <= 1
        st = self.tt[-1]
        ot = other.tt[0]

        (x0, y0) = ot.xy
        (x1, y1) = st.xy
        s2 = st.copy()
        s2.forward(1)
        (x2, y2) = s2.xy

        d = ((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
        if d < 0:
            d += self.c
        else:
            d -= self.c
        self.shimmy(ratio * -d)
        other.shimmy((1 - ratio) * d)

        if st.is_behind(ot):
            extend(ot, self.tt)
        else:
            extend(st, other.tt)
        return River(self.board, self.tt + other.tt)

    def meet(self, other):
        tu = ((other.tt[0].dir + 180) - self.tt[0].dir) % 360
        if tu < 180:
            self.right(tu)
        else:
            self.left(tu)
        (x, _) = self.tt[0].seek(other.tt[-1])
        self.shimmy(-x)
        d = self.tt[0].distance(other.tt[-1])
        self.forward(d)
        self.wire()

    def wire(self):
        [t.wire() for t in self.tt]

class Board:
    def __init__(self, size,
               trace,
               space,
               via_hole,
               via,
               via_space,
               silk):
        self.size = size
        self.trace = trace
        self.space = space
        self.via_hole = via_hole
        self.via = via
        self.via_space = via_space
        self.silk = silk
        self.parts = defaultdict(list)

        self.c = trace + space # track spacing, used everywhere

        layers = [
            # ('GML', 'Mechanical'),

            ('GTP', 'Top Paste'),
            ('GTO', 'Top Silkscreen'),
            ('GTS', 'Top Solder Mask'),
            ('GTL', 'Top Copper'),
            ('GL2', 'Inner Layer 2'),
            ('GL3', 'Inner Layer 3'),
            ('GBL', 'Bottom Copper'),
            ('GBO', 'Bottom Silkscreen'),
            ('GBS', 'Bottom Solder Mask'),
            ('GBP', 'Bottom Paste'),
        ]
        self.layers = {id : Layer(desc) for (id, desc) in layers}

    def annotate(self, x, y, s):
        self.layers['GTO'].add(hershey.text(x, y, s))

    def DC(self, xy, d = 0):
        return Draw(self, xy, d)

    def save(self, basename):
        with open(basename + ".GML", "wt") as f:
            g = gerber.Gerber(f, "Mechanical")
            g.rect(0, 0, *self.size)
            g.finish()

        for (id, l) in self.layers.items():
            with open(basename + "." + id, "wt") as f:
                l.save(f)

    def enriver(self, ibank, a):
        if a > 0:
            bank = ibank[::-1]
        else:
            bank = ibank
        bank[0].right(a)
        for i,t in enumerate(bank[1:], 1):
            gap = (self.trace + self.space) * i
            t.left(a)
            t.approach(gap, bank[0])
            t.right(2 * a)
        extend(bank[-1], bank)
        return River(self, ibank)

    def assign(self, part):
        pl = self.parts[part.family]
        pl.append(part)
        return part.family + str(len(pl))

def extend(dst, traces):
    # extend parallel traces so that they are all level with dst
    # assert dst in traces, "One trace must be the target"
    assert len({t.dir for t in traces}) == 1, "All traces must be parallel"

    finish_line = dst.copy()
    finish_line.left(90)
    for t in traces:
        t.approach(0, finish_line)
        t.wire()

class Part:
    def __init__(self, dc, val = None):
        self.id = dc.board.assign(self)
        self.val = val
        self.pads  = []
        self.place(dc)

    def label(self, dc):
        (x, y) = dc.xy
        dc.board.annotate(x, y, self.id)

    def chamfered(self, dc, w, h):
        # Outline in top silk, chamfer indicates top-left
        # ID next to chamfer

        nt = 0.4
        dc.push()
        dc.forward(h / 2)
        dc.left(90)
        dc.forward(w / 2 - nt)
        dc.right(180)
        dc.newpath()
        for e in (w - nt, h, w, h - nt):
            dc.forward(e)
            dc.right(90)
        dc.silko()
        dc.pop()

        dc.push()
        dc.forward(h / 2 + 0.5)
        dc.left(90)
        dc.forward(w / 2 + 0.5)
        (x, y) = dc.xy
        dc.board.layers['GTO'].add(hershey.ctext(x, y, self.id))
        dc.pop()

    def pad(self, dc):
        dc.pad()
        self.pads.append(dc.copy())

class C0402(Part):
    family = "C"
    def place(self, dc):
        # Pads on either side
        for d in (-90, 90):
            dc.push()
            dc.left(d)
            dc.forward(1.30 / 2)
            dc.rect(0.7, 0.9)
            self.pad(dc)
            dc.pop()

        # Silk outline of the package
        dc.rect(1.0, 0.5)
        dc.silko()

        dc.push()
        dc.right(90)
        dc.forward(2)
        self.label(dc)
        dc.pop()

        # Connections to GND and VCC
        for d,l in ((-90, 'GL2'), (90, 'GL3')):
            dc.push()
            dc.left(d)
            dc.forward(1.1)

            dc.newpath()
            dc.forward(dc.board.via_space + dc.board.via / 2)
            dc.wire()

            dc.via(l)
            dc.pop()

# Taken from:
# https://www.analog.com/media/en/package-pcb-resources/package/pkg_pdf/ltc-legacy-qfn/QFN_64_05-08-1705.pdf

class QFN64(Part):
    family = "U"
    def place(self, dc):
        # Ground pad
        g = 7.15 / 3
        for i in (-g, 0, g):
            for j in (-g, 0, g):
                dc.push()
                dc.forward(i)
                dc.left(90)
                dc.forward(j)
                dc.square(g - 0.5)
                self.pad(dc)
                dc.via('GL2')
                dc.pop()
        self.pads = self.pads[:1]

        # Silk outline of the package
        self.chamfered(dc, 9, 9)
        # self.chamfered(dc, 7.15, 7.15)

        for i in range(4):
            dc.left(90)
            dc.push()
            dc.forward(8.10 / 2)
            dc.forward(0.70 / 2)
            dc.right(90)
            dc.forward(7.50 / 2)
            dc.left(90)
            for i in range(16):
                dc.rect(0.25, 0.70)
                self.pad(dc)
                dc.left(90)
                dc.forward(0.50)
                dc.right(90)
            dc.pop()

# IPC-SM-782A section 9.1: SOIC

class SOIC(Part):
    family = "U"
    def place(self, dc):

        self.chamfered(dc, self.A, self.B)
        for _ in range(2):
            dc.push()
            dc.forward(self.D / 2)
            dc.left(90)
            dc.forward(self.C / 2)
            dc.left(90)
            for i in range(self.N // 2):
                dc.right(90)
                dc.rect(0.60, 2.20)
                self.pad(dc)
                dc.left(90)
                dc.forward(1.27)
            dc.pop()
            dc.right(180)

class SOIC8(SOIC):
    N = 8

    A = 4.0
    B = 5.0
    C = 5.20
    D = 3.81
    G = 3.0
    Z = 7.4

