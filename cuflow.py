from collections import defaultdict
import re
import math

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

    def add(self, o):
        self.polys.append(o.simplify(0.001, preserve_topology=False))

    def preview(self):
        return so.unary_union(self.polys)

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

class OutlineLayer:
    def __init__(self, desc):
        self.lines = []
        self.desc = desc

    def add(self, o):
        self.lines.append(o)

    def save(self, f):
        g = gerber.Gerber(f, self.desc)
        for ls in self.lines:
            g.linestring(ls.coords)
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
        return self

    def left(self, d):
        self.dir = (self.dir - d) % 360
        return self

    def right(self, d):
        self.dir = (self.dir + d) % 360
        return self

    def approach(self, d, other):
        assert ((self.dir - other.dir) % 360) in (90, 270)
        # Go forward to be exactly d away from infinite line 'other'
        (x0, y0) = self.xy
        (x1, y1) = other.xy
        o2 = other.copy()
        o2.forward(1)
        (x2, y2) = o2.xy

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

    def contact(self):
        g = sg.Polygon(self.path)
        for n in ('GTL', 'GTS', 'GBL', 'GBS'):
            self.board.layers[n].add(g)

    def silk(self):
        g = sg.LineString(self.path).buffer(self.board.silk / 2)
        self.board.layers['GTO'].add(g)

    def silko(self):
        g = sg.LinearRing(self.path).buffer(self.board.silk / 2)
        self.board.layers['GTO'].add(g)

    def via(self, connect = None):
        g = sg.Point(self.xy).buffer(self.board.via / 2)
        for n in {'GTL', 'GL2', 'GL3', 'GBL'} - {connect}:
            self.board.layers[n].add(g)
        self.newpath()

    def preview(self):
        return sg.LineString(self.path)

    def wire(self, layer = 'GTL', width = None):
        if width is None:
            width = self.board.trace
        if len(self.path) > 1:
            g = sg.LineString(self.path).buffer(width / 2)
            self.board.layers[layer].add(g)
            self.newpath()

    def wvia(self, l):
        # enough wire then a via
        b = self.board
        self.forward(b.via_space + b.via / 2)
        self.wire()
        self.via(l)

    def platedslot(self, buf):
        g1 = sg.LineString(self.path).buffer(buf)
        g2 = sg.LinearRing(g1.exterior.coords)
        self.board.layers['GML'].add(g2)

        g3 = g1.buffer(.3).difference(g1.buffer(-0.05))
        self.board.layers['GTL'].add(g3)
        self.board.layers['GBL'].add(g3)

class River(Turtle):
    def __init__(self, board, tt):
        self.tt = tt
        self.board = board
        self.c = self.board.c

    def r(self):
        return self.c * (len(self.tt) - 1)

    def forward(self, d):
        [t.forward(d) for t in self.tt]
        return self

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
        return self

    def left(self, a):
        fd = (self.tt[0].dir - a) % 360
        n = int(a + 1)
        ra = 2 * math.pi * a / 360
        for i in range(n):
            self.lpivot(ra / n)
        for t in self.tt:
            t.dir = fd
        return self

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
            ('GTP', 'Top Paste'),
            ('GTO', 'Top Silkscreen'),
            ('GTS', 'Top Solder Mask'),
            ('GTL', 'Top Copper'),
            ('GL2', 'Inner Layer 2'),
            ('GL3', 'Inner Layer 3'),
            ('GBL', 'Bottom Copper'),
            ('GBS', 'Bottom Solder Mask'),
            ('GBO', 'Bottom Silkscreen'),
            ('GBP', 'Bottom Paste'),
        ]
        self.layers = {id : Layer(desc) for (id, desc) in layers}
        self.layers['GML'] = OutlineLayer('Mechanical')

        self.layers['GML'].add(sg.LinearRing([
            (0, 0),
            (self.size[0], 0),
            (self.size[0], self.size[1]),
            (0, self.size[1])]))

    def annotate(self, x, y, s):
        self.layers['GTO'].add(hershey.text(x, y, s))

    def DC(self, xy, d = 0):
        return Draw(self, xy, d)

    def save(self, basename):
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

    def enriver90(self, ibank, a):
        if a < 0:
            bank = ibank[::-1]
        else:
            bank = ibank
        bank[0].right(a)
        for i,t in enumerate(bank[1:], 1):
            gap = (self.trace + self.space) * i
            t.forward(gap)
            t.right(a)
        extend(bank[0], bank)
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
        self.board = dc.board
        self.place(dc)

    def label(self, dc):
        (x, y) = dc.xy
        dc.board.annotate(x, y, self.id)

    def minilabel(self, dc, s):
        dc.push()
        dc.rect(.7, .7)
        dc.silko()
        dc.w("r 180 f 1.5")
        (x, y) = dc.xy
        dc.board.layers['GTO'].add(hershey.ctext(x, y, s))
        dc.pop()

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

    def rpad(self, dc, w, h):
        dc.right(90)
        dc.rect(w, h)
        self.pad(dc)
        dc.left(90)

    def roundpad(self, dc, d):
        (dc.w, dc.h) = (d, d)
        g = sg.Point(dc.xy).buffer(d / 2)
        for n in ('GTL', 'GTS', 'GTP'):
            dc.board.layers[n].add(g)
        self.pads.append(dc.copy())

    def train(self, dc, n, op, step):
        for i in range(n):
            op()
            dc.forward(step)

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
            dc.left(180)
            self.train(dc, 16, lambda: self.rpad(dc, 0.25, 0.70), 0.50)
            dc.pop()

BT815pins = [
    'GND',
    'R0',
    '+1V2',
    'E.SCK',
    'E.MISO',
    'E.MOSI',
    'E.CS',
    '',
    '',
    '3V3',
    '',
    'E.INT',
    'E.PD',
    '',
    'M_SCK',
    'M_CS',
    'M_MOSI',
    '3V3',
    'M_MISO',
    'M_IO2',
    'M_IO3',
    '',
    '',
    'GND',
    '3V3',
    '+1V2',
    'AUDIO',
    '3V3',
    '3V3',
    '',
    '',
    '',
    '',
    'GND',
    '',
    'DE',
    'VSYNC',
    'HSYNC',
    'DISP',
    'PCLK',
    'B7',
    'B6',
    'B5',
    'B4',
    'B3',
    'B2',
    'B1',
    'B0',
    'GND',
    'G7',
    'G6',
    'G5',
    'G4',
    'G3',
    'G2',
    'G1',
    'G0',
    '+1V2',
    'R7',
    'R6',
    'R5',
    'R4',
    'R3',
    'R2',
    'R1',
]

class BT815(QFN64):
    def escape(self):
        brd = self.board

        dc = self.pads[23]
        dc.right(180)
        dc.forward(2)
        dc.wire()

        dc = self.pads[33]
        dc.right(180)
        dc.forward(.65)
        dc.right(45)
        dc.forward(1)
        dc.wire()

        dc = self.pads[48]
        dc.right(180)
        dc.forward(.65)
        dc.left(45)
        dc.forward(1)
        dc.wire()

        def backside(dc, d):
            dc.newpath()
            dc.push()
            dc.right(180)
            dc.forward(0.35 + .2)
            dc.right(90)
            dc.forward(d * 0.5)
            dc.right(90)
            dc.forward(0.35 + .2)
            dc.wire()
            dc.pop()

        def via(dc, l):
            dc.push()
            dc.forward(.35)
            dc.forward(brd.via_space + brd.via / 2)
            dc.wire()
            dc.via(l)
            dc.pop()
        # VCC
        backside(self.pads[24], 3)
        backside(self.pads[24], 4)

        for i in (9, 17, 27):
            dc = self.pads[i]
            via(dc, 'GL3')

        for i,sig in enumerate(BT815pins):
            if sig == "+1V2":
                via(self.pads[i], 'GBL')

        power = {'3V3', 'GND', '', '+1V2'}
        spim = {'M_SCK', 'M_CS', 'M_MOSI', 'M_MISO', 'M_IO2', 'M_IO3'}

        ext = [i for i,sig in enumerate(BT815pins) if sig not in (power | spim)]
        spi = [i for i,sig in enumerate(BT815pins) if sig in spim]
        for i in ext:
            self.pads[i].forward(1)
            self.pads[i].wire()
        [self.pads[i].outside() for i in spi]

        def bank(n, pool):
            return [self.pads[i] for i in pool if (i - 1) // 16 == n]
        rv0 = brd.enriver90(bank(0, ext), 90)
        rv1 = brd.enriver(bank(1, ext), -45)
        rv2 = brd.enriver(bank(2, ext), -45)
        rv3 = brd.enriver(bank(3, ext), 45)
        rv0.forward(.2)
        rv0.right(45)
        rv0.forward(1)
        rv0.wire()

        rv1.w("f .2 l 45 f 2.5 l 45 f 3 l 45 f .53 r 45 f 3")
        rv1.wire()

        rv2 = rv1.join(rv2, 1)

        rv2.forward(0.6)

        rv23 = rv2.join(rv3, 1.0)
        rv23.wire()
        rv230 = rv23.join(rv0)
        # rv230.w("f 1 r 31 f 1")
        rv230.wire()

        rv4 = brd.enriver(bank(0, spi), -45)
        rv4.w("f 0.7 l 90 f 2.3 l 45 f 1 r 45")
        rv5 = brd.enriver(bank(1, spi), -45)
        rv5.forward(1)
        rvspi = rv4.join(rv5)

        rvspi.wire()
        return (rvspi, rv230)

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
            self.train(dc, self.N // 2, lambda: self.rpad(dc, 0.60, 2.20), 1.27)
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

class W25Q16J(SOIC8):
    def escape(self):
        nms = "CS MISO IO2 GND MOSI SCK IO3 VCC".split()
        sigs = {nm: p for (nm, p) in zip(nms, self.pads)}
        
        sigs['SCK' ].w("f 1.1 f .1")
        sigs['CS'  ].w("i f 1.5 r 90 f 1.27 f 1.27 f .63 l 90 f .1")
        sigs['MISO'].w("i f 1.0 r 90 f 1.27 f 1.27 f .63 l 90 f .1")
        sigs['MOSI'].w("o f .1")
        sigs['IO2' ].w("i f 0.5 r 90 f 2.20 l 90 f .1")
        sigs['IO3' ].w("i f 0.5 r 90 f 1.27 f .63 l 90 f 5.5 l 90 f 5.65 l 90 f .1")
        sigs['GND' ].w("o -")
        sigs['VCC' ].w("o +")

        proper = (
            sigs['IO3' ],
            sigs['IO2' ],
            sigs['MISO'],
            sigs['MOSI'],
            sigs['CS'  ],
            sigs['SCK' ],
        )
        extend(sigs['SCK'], proper)
        rv = self.board.enriver(proper, 45)
        return rv

class HDMI(Part):
    family = "J"
    source = {'LCSC': 'C138388'}
    def place(self, dc):
        self.chamfered(dc, 15, 11.1)

        def mounting(dc, l):
            dc.push()
            dc.newpath()
            dc.forward(l / 2)
            dc.right(180)
            dc.forward(l)
            dc.platedslot(.5)
            dc.pop()

        # mounting(dc, 2)
        dc.push()
        dc.right(90)
        dc.forward(4.5)
        dc.left(90)
        dc.forward(5.35)
        dc.left(90)
        self.train(dc, 19, lambda: self.rpad(dc, 0.30, 2.60), 0.50)
        dc.pop()

        dc.right(90)
        dc.forward(14.5 / 2)
        dc.left(90)
        dc.forward(5.35 + 1.3 - 2.06)
        dc.right(180)

        def holepair():
            dc.push()
            mounting(dc, 2.8 - 1)
            dc.forward(5.96)
            mounting(dc, 2.2 - 1)
            dc.pop()
        holepair()
        dc.right(90)
        dc.forward(14.5)
        dc.left(90)
        holepair()
        dc.forward(5.96 + 3.6)
        dc.left(90)

        dc.newpath()
        dc.forward(14.5)
        dc.silk()

class SOT223(Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 6.30, 3.30)
        dc.push()
        dc.forward(6.2 / 2)
        dc.rect(3.6, 2.2)
        self.pad(dc)
        dc.pop()

        dc.left(90)
        dc.forward(4.60 / 2)
        dc.left(90)
        dc.forward(6.2 / 2)
        dc.left(90)
        self.train(dc, 3, lambda: self.rpad(dc, 1.20, 2.20), 2.30)

    def escape(self):
        self.pads[2].w("i f 4")
        self.pads[2].wire(width = 0.8)
        self.pads[1].w("i - f .2 -")
        self.pads[1].wire(width = 0.8)

class FTG256(Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 17, 17)
        dc.left(90)
        dc.forward(7.5)
        dc.right(90)
        dc.forward(7.5)
        dc.right(90)
        for j in range(16):
            dc.push()
            for i in range(16):
                dc.left(90)
                self.roundpad(dc, 0.4)
                dc.right(90)
                dc.forward(1)
            dc.pop()
            dc.right(90)
            dc.forward(1)
            dc.left(90)

        return

class XC6LX9(FTG256):
    def collect(self, pp):
        p0 = pp[0]
        return [p for (_,p) in sorted([(p.seek(p0)[0], p) for p in pp])]

    def escape(self):
        north = self.pads[0].dir
        done = [False for _ in self.pads]

        FGname = "ABCDEFGHJKLMNPRT"
        padname = {FGname[i] + str(1 + j): self.pads[16 * i + j] for i in range(16) for j in range(16)}
        self.signals = {}
        for l in open("6slx9ftg256pkg.txt", "rt"):
            (pad, _, _, signal) = l.split()
            self.signals[pad] = signal

        powernames = (
            'GND', 'VCCO_0', 'VCCO_1', 'VCCO_2', 'VCCO_3', 'VCCAUX', 'VCCINT',
            'IO_L1P_CCLK_2',
            'IO_L3P_D0_DIN_MISO_MISO1_2',
            'IO_L3N_MOSI_CSI_B_MISO0_2',
            'IO_L65N_CSO_B_2',
            'TCK',
            'TDI',
            'TMS',
            'TDO',
            'PROGRAM_B_2',
            'SUSPEND',
            'IO_L1N_M0_CMPMISO_2',  # M0 to VCC
            'IO_L13P_M1_2',         # M1 to GND
        )
        def isio(s):
            return s.startswith("IO_") and s not in powernames

        ios = {s for (pn, s) in self.signals.items() if isio(s)}
        unconnected = {'CMPCS_B_2', 'DONE_2'}
        assert (set(self.signals.values()) - ios - set(powernames)) == unconnected

        byname = {s : padname[pn] for (pn, s) in self.signals.items()}

        specials = [
            ( 'IO_L1P_CCLK_2', 'SCK'),
            ( 'IO_L3P_D0_DIN_MISO_MISO1_2', 'MISO'),
            ( 'IO_L3N_MOSI_CSI_B_MISO0_2', 'MOSI'),
            ( 'IO_L65N_CSO_B_2', 'CS'),
            ( 'TCK', 'TCK'),
            ( 'TDI', 'TDI'),
            ( 'TMS', 'TMS'),
            ( 'TDO', 'TDO')]
        for (nm, lbl) in specials:
            self.minilabel(byname[nm], lbl)

        for pn,s in self.signals.items():
            if s in powernames:
                p = padname[pn]
                p.right(45)
                p.forward(math.sqrt(2) / 2)
                p.wire()
                p.via({
                    'GND' : 'GL2',
                    'IO_L13P_M1_2' : 'GL2',
                    'SUSPEND' : 'GL2',

                    'IO_L1N_M0_CMPMISO_2' : 'GL3',
                    'PROGRAM_B_2' : 'GL3',

                    'VCCINT' : 'GBL',
                }.get(s, 'GL3'))

        d1 = math.sqrt(2 * (.383 ** 2))
        d2 = math.sqrt(2 * ((1 - .383) ** 2))

        s1 = "f 0.500"
        s2 = "l 45  f {0} r 45 f 1.117".format(d1)
        s3 = "l 45  f {0} r 45 f 1.883".format(d2)

        plan = (
            (0, ".1$",  "l 90 " + s1),
            (0, ".2$",  "l 90 " + s2),
            (0, ".3$",  "l 90 " + s3),
            (1, "T",    "r 180 " + s1),
            (1, "R",    "r 180 " + s2),
            (1, "P",    "r 180 " + s3),
            (2, ".16$", "r 90 " + s1),
            (2, ".15$", "r 90 " + s2),
            (2, ".14$", "r 90 " + s3),
            (3, "A",    s1),
            (3, "B",    s2),
            (3, "C",    s3),
        )
        keepout = self.pads[0].board.layers['GL2'].preview().union(
                  self.pads[0].board.layers['GL3'].preview())
        outer = {i:[] for i in range(4)}
        for pn,sig in self.signals.items():
            if isio(sig):
                for grp,pat,act in plan:
                    if re.match(pat, pn):
                        p = padname[pn]
                        p.push()
                        p.w(act)
                        if p.preview().intersects(keepout):
                            p.pop()
                        else:
                            p.wire()
                            outer[grp].append(p)
                            break

        board = self.pads[0].board
        rv0 = board.enriver90(self.collect(outer[0]), -90)
        rv1 = board.enriver90(self.collect(outer[1]), -90)
        rem = 36 - len(rv1.tt)
        rv2 = board.enriver90(self.collect(outer[2])[:rem], 90)
        rv3 = board.enriver90(self.collect(outer[3]), 90)

        rv1.right(45)
        rv1.wire()
        rv2.left(45)
        rv2.wire()

        rv12 = rv1.join(rv2)
        return rv12
        # rv0.wire()

class Castellation(Part):
    family = "J"
    def place(self, dc):
        dc.w("l 90 f 0.4 r 90")
        def cp():
            dc.right(90)
            dc.rect(1, 1)
            dc.contact()
            dc.left(90)
        self.train(dc, self.val, cp, 2.0)
