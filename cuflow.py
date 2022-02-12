from collections import defaultdict
import re
import math
import csv

from PIL import Image
import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so
import math

import gerber
from excellon import excellon
import hershey

def inches(x):  return x * 25.4
def mil(x):     return inches(x / 1000)
def micron(x):  return x / 1000

def DEGREES(r): return 180 * r / math.pi

def pretty_parts(nms):
    f = nms[0][0]
    nn = [int(nm[1:]) for nm in nms]
    ni = []
    while nn:
        seq = [i for (i,j) in zip(nn, range(nn[0], 9999)) if (i == j)]
        if len(seq) > 2:
            ni.append("{0}{1}-{2}".format(f, nn[0], nn[len(seq) - 1]))
            nn = nn[len(seq):]
        else:
            ni.append("{0}{1}".format(f, nn[0]))
            nn = nn[1:]
    return ",".join(ni)

class Layer:
    def __init__(self, desc):
        self.polys = []
        self.desc = desc
        self.connected = []
        self.p = None

    def add(self, o, nm = None):
        self.polys.append((nm, o.simplify(0.001, preserve_topology=False)))
        self.p = None

    def preview(self):
        if self.p is None:
            self.p = so.unary_union([p for (_, p) in self.polys])
        return self.p

    def paint(self, bg, include, r):
        # Return the intersection of bg with the current polylist
        # touching the included, avoiding the others by distance r
        ingrp = so.unary_union([bg] + [o for (nm, o) in self.polys if nm == include])
        exgrp = so.unary_union([o for (nm, o) in self.polys if nm != include])
        self.powered = so.unary_union(ingrp).difference(exgrp.buffer(r))
        return exgrp.union(self.powered)

    def fill(self, bg, include, d):
        self.polys = [('filled', self.paint(bg, include, d))]
        
    def save(self, f):
        surface = self.preview()
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
                eps = 0.005
                # eps = 0.000
                renderpoly(g, po.intersection(sg.box(x0, y0, xm + eps, y1)))
                renderpoly(g, po.intersection(sg.box(xm - eps, y0, x1, y1)))

        if isinstance(surface, sg.Polygon):
            renderpoly(g, surface)
        else:
            [renderpoly(g, po) for po in surface]
        g.finish()

    def povray(self, f, prefix = "polygon {", mask = None, invert = False):
        surface = self.preview()
        if invert:
            surface = mask.difference(surface)
        elif mask is not None:
            surface = surface.intersection(mask)
        def renderpoly(po):
            if type(po) == sg.MultiPolygon:
                [renderpoly(p) for p in po]
                return
            allc = [po.exterior.coords] + [c.coords for c in po.interiors]
            total = sum([len(c) for c in allc])
            f.write(prefix)
            f.write("\n%d\n" % total)
            for c in allc:
                f.write(" ".join(["<%f,%f>" % (x, y) for (x,y) in c]) + "\n")
            f.write("}\n")

        if isinstance(surface, sg.Polygon):
            renderpoly(surface)
        else:
            [renderpoly(po) for po in surface]

class OutlineLayer:
    def __init__(self, desc):
        self.lines = []
        self.desc = desc

    def add(self, o):
        self.lines.append(o)

    def union(self, o):
        po = sg.Polygon(self.lines[0]).union(o.buffer(0))
        self.lines = [po.exterior]

    def remove(self, o):
        po = sg.Polygon(self.lines[0]).difference(o.buffer(0))
        self.lines = [po.exterior]

    def save(self, f):
        g = gerber.Gerber(f, self.desc)
        for ls in self.lines:
            g.linestring(ls.coords)
        g.finish()

class Turtle:
    def __repr__(self):
        return "<at (%.3f, %.3f) facing %.3f>" % (self.xy + (self.dir, ))
    def w(self, s, layer = 'GTL'):
        tokens = s.split()
        cmds1 = {
            'i' : self.inside,
            'o' : self.outside,
            '-' : lambda: self.wvia('GL2'),
            '+' : lambda: self.wvia('GL3'),
            '.' : lambda: self.wvia('GBL'),
            '/' : self.through,
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
        return self

    def inside(self): pass
    def outside(self): pass
    def through(self): pass

class Draw(Turtle):
    def __init__(self, board, xy, dir = 0, name = None):
        self.board = board
        self.xy = xy
        self.dir = dir
        self.stack = []
        self.part = None
        self.name = None
        self.newpath()
        self.width = board.trace
        self.h = None
        self.length = 0
        self.defaults()

    def defaults(self):
        self.layer = 'GTL'

    def setname(self, nm):
        self.name = nm
        return self

    def setwidth(self, w):
        self.width = w
        return self

    def setlayer(self, l):
        self.layer = l
        return self

    def newpath(self):
        self.path = [self.xy]
        return self

    def push(self):
        self.stack.append((self.xy, self.dir))
        return self

    def pop(self):
        (self.xy, self.dir) = self.stack.pop(-1)
        return self

    def copy(self):
        r = type(self)(self.board, self.xy, self.dir)
        r.h = self.h
        r.layer = self.layer
        r.name = self.name
        r.part = self.part
        r.width = self.width
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

    def goto(self, other):
        return self.goxy(*self.seek(other))

    def goxy(self, x, y):
        self.right(90)
        self.forward(x)
        self.left(90)
        self.forward(y)
        return self

    def is_behind(self, other):
        assert abs(self.dir - other.dir) < 0.0001, abs(self.dir - other.dir)
        (_, y) = self.seek(other)
        return y > 0

    def distance(self, other):
        return math.sqrt((other.xy[0] - self.xy[0]) ** 2 + (other.xy[1] - self.xy[1]) ** 2)

    def direction(self, other):
        x = other.xy[0] - self.xy[0]
        y = other.xy[1] - self.xy[1]
        return math.atan2(x, y)

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
        return self

    def mark(self):
        self.board.layers['GTO'].add(sg.Point(self.xy).buffer(.2))
        self.push()
        self.newpath()
        self.forward(.3)
        self.silk()
        self.pop()
        return self

    def n_agon(self, r, n):
        # an n-agon approximating a circle radius r
        ea = 360 / n
        self.push()
        half_angle = math.pi / n
        half_edge = r * math.tan(half_angle)
        self.forward(r)
        self.right(90)

        self.newpath()
        for _ in range(n):
            self.forward(half_edge)
            self.right(ea)
            self.forward(half_edge)
        self.pop()

    def thermal(self, d):
        for i in range(4):
            self.forward(d)
            self.right(180)
            self.forward(d)
            self.right(90)
        return self

    def inside(self):
        self.right(180)
        self.forward(self.h / 2)
        return self

    def outside(self):
        self.forward(self.h / 2)
        return self

    def square(self, w):
        self.rect(w, w)

    def poly(self):
        return sg.Polygon(self.path)

    def pad(self):
        g = self.poly()
        if self.layer == 'GTL':
            ly = ('GTL', 'GTS', 'GTP')
        elif self.layer == 'GBL':
            ly = ['GBL', 'GBS']
        else:
            assert False, "Attempt to create pad in layer " + self.layer
        for n in ly:
            self.board.layers[n].add(g, self.name)

    def contact(self):
        g = sg.Polygon(self.path)
        for n in ('GTL', 'GTS', 'GBL', 'GBS'):
            self.board.layers[n].add(g, self.name)

    def silk(self):
        g = sg.LineString(self.path).buffer(self.board.silk / 2)
        self.board.layers['GTO'].add(g)
        return self

    def silko(self):
        g = sg.LinearRing(self.path).buffer(self.board.silk / 2)
        self.board.layers['GTO'].add(g)

    def outline(self):
        g = sg.LinearRing(self.path)
        self.board.layers['GML'].add(g)

    def drill(self, d):
        self.board.drill(self.xy, d)

    def via(self, connect = None):
        g = sg.Point(self.xy).buffer(self.board.via / 2)
        for n in ('GTL', 'GL2', 'GL3', 'GBL'):
            self.board.layers[n].add(g, connect)
        if connect is not None:
            self.board.layers[connect].connected.append(g)
        self.board.drill(self.xy, self.board.via_hole)
        self.newpath()
        return self

    def preview(self):
        return sg.LineString(self.path)

    def wire(self, layer = None, width = None):
        if layer is not None:
            self.layer = layer
        if width is not None:
            self.width = width
        if len(self.path) > 1:
            ls = sg.LineString(self.path)
            self.length += ls.length
            g = ls.buffer(self.width / 2)
            self.board.layers[self.layer].add(g, self.name)
            self.newpath()
        return self

    def wvia(self, l):
        # enough wire then a via
        b = self.board
        self.forward(b.via_space + b.via / 2)
        self.wire()
        self.via(l)

    def fan(self, l, dst):
        for a in (-45, 0, 45):
            self.copy().right(a).forward(l).wire(width = 0.8).via(dst)

    def platedslot(self, buf):
        brd = self.board

        g1 = sg.LineString(self.path).buffer(buf)

        g2 = sg.LinearRing(g1.exterior.coords)
        brd.layers['GML'].add(g2)

        g3 = g1.buffer(.3)
        brd.layers['GTS'].add(g3)

        g4 = g3.difference(g1.buffer(-0.05))
        for l in ('GTL', 'GL2', 'GL3', 'GBL'):
            brd.layers[l].add(g4)

        strut_x = sa.scale(g4.envelope, yfact = 0.15)
        strut_y = sa.scale(g4.envelope, xfact = 0.15)
        struts = strut_x.union(strut_y)
        brd.layers['GTP'].add(g4.difference(struts))

    def meet(self, other):
        self.path.append(other.xy)
        return self.wire()

    def text(self, s):
        (x, y) = self.xy
        self.board.layers['GTO'].add(hershey.ctext(x, y, s))
        return self

    def ltext(self, s):
        (x, y) = self.xy
        self.board.layers['GTO'].add(hershey.ltext(x, y, s))

    def through(self):
        self.wire()
        dst = {'GTL': 'GBL', 'GBL': 'GTL'}[self.layer]
        self.via().setlayer(dst)
        return self

class Drawf(Draw):
    def defaults(self):
        self.layer = 'GBL'

    def left(self, a):
        return Draw.right(self, a)
    def right(self, a):
        return Draw.left(self, a)
    def goxy(self, x, y):
        return Draw.goxy(-x , y)

class River(Turtle):
    def __init__(self, board, tt):
        self.tt = tt
        self.board = board
        self.c = self.board.c

    def __repr__(self):
        return "<River %d at %r>" % (len(self.tt), self.tt[0])

    def __len__(self):
        return len(self.tt)

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
            x = t.xy[0] - x0
            y = t.xy[1] - y0
            nx = x * c - y * s
            ny = y * c + x * s
            t.xy = (x0 + nx, y0 + ny)
            t.path.append(t.xy)

    def right(self, a):
        if a < 0:
            return self.left(-a)
        fd = (self.tt[0].dir + a) % 360
        n = int(a + 1)
        ra = 2 * math.pi * a / 360
        for i in range(n):
            self.rpivot(-ra / n)
        for t in self.tt:
            t.dir = fd
        return self

    def left(self, a):
        if a < 0:
            return self.right(-a)
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
        return self

    def spread(self, d):
        c = self.board.trace + self.board.space
        n = len(self.tt) - 1
        for i,t in enumerate(self.tt[::-1]):
            i_ = n - i
            t.forward(c * i).left(90).forward(i_ * d).right(90).forward(c * i_)
        return self

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
        self.board.nets += [((a.part, a.name), (b.part, b.name)) for (a, b) in zip(self.tt, other.tt[::-1])]
        """
        for (a, b) in zip(self.tt, other.tt[::-1]):
            print(a.name, b.name, a.length + b.length)
        """

    def meet0(self, other):
        d = self.tt[0].distance(other.tt[0])
        c = self.board.trace + self.board.space
        r = c * (len(self.tt) - 1)
        l = math.sqrt(d ** 2 - r ** 2)
        dir_d = self.tt[0].direction(other.tt[0])
        a = math.acos(l / d)
        self.right(180 * (dir_d + a) / math.pi)
        self.forward(l)
        self.wire()

    def meet2(self, other):
        src = self.tt[0]
        dst = other.tt[-1]
        d = src.distance(dst)
        dir_d = DEGREES(src.direction(dst))

        self.right(dir_d)
        self.forward(d)
        self.wire()

        other.left(90 - dir_d).wire()
        self.board.nets += [((a.part, a.name), (b.part, b.name)) for (a, b) in zip(self.tt, other.tt[::-1])]

    def split(self, n):
        a = River(self.board, self.tt[:n])
        b = River(self.board, self.tt[n:])
        return (a, b)

    def wire(self, layer = None, width = None):
        [t.wire(layer, width) for t in self.tt]
        return self

    def through(self):
        # print(self.tt[0].distance(self.tt[-1]))
        h = self.board.via + self.board.via_space
        th = math.acos(self.c / h)
        d = self.board.via / 2 + self.board.via_space
        a = h * math.sin(th)
        th_d = math.degrees(th)
        dst = {'GTL': 'GBL', 'GBL': 'GTL'}[self.tt[0].layer]

        self.forward(d)
        for i,t in enumerate(self.tt):
            t.forward(i * a).right(th_d).forward(d).wire()
            t.via().setlayer(dst)
            t.forward(d).left(th_d).forward((len(self.tt) - 1 - i) * a)
        self.forward(d)
        self.wire()
        return self

    def shuffle(self, other, mp):
        # print(self.tt[0].distance(self.tt[-1]))
        h = (self.board.via + self.board.via_space) # / math.sqrt(2)
        th = math.acos(self.c / h)
        d = self.board.via / 2 + self.board.via_space
        a = h * math.sin(th)
        th_d = math.degrees(th)
        dst = {'GTL': 'GBL', 'GBL': 'GTL'}[self.tt[0].layer]

        # print('         mp', mp)
        # print('   original', [t.name for t in self.tt])
        # print('      other', [t.name for t in other.tt])
        self.forward(d)
        othernames = {p.name:i for i,p in enumerate(other.tt)}
        newt = [None for _ in self.tt]
        for i,t in enumerate(self.tt):
            t.forward(i * a).right(th_d)
            t.forward(d)
            fa = othernames[mp[t.name]]
            newt[fa] = t
            t.forward(h * fa)
            t.wire()
            t.through()
            t.left(90)
        extend2(self.tt)
        # print('       newt', [t.name for t in newt])
        self.tt = newt[::-1]
        self.forward(d)
        for i,t in enumerate(self.tt):
            t.left(th_d).forward((len(self.tt) - 1 - i) * a)
        self.wire()
        return self

    def widen(self, c):
        y = math.sqrt((c ** 2) - (self.c ** 2))
        print(c, self.c, y)
        th = math.acos(self.c / c)
        th_d = math.degrees(th)
        print('th', th_d)

        for i,t in enumerate(self.tt):
            t.forward(i * y).wire().right(th_d).wire()
        print('dist', self.tt[0].distance(self.tt[1]))

        self.c = c
        self.left(th_d)
        self.wire()
        return self

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
        self.holes = defaultdict(list)
        self.keepouts = []

        self.c = trace + space # track spacing, used everywhere

        self.counters = defaultdict(lambda: 0)
        self.nets = []

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

    def boundary(self, r = 0):
        x0,y0 = (-r, -r)
        x1,y1 = self.size
        x1 += r
        y1 += r
        return sg.LinearRing([
            (x0, y0),
            (x1, y0),
            (x1, y1),
            (x0, y1)])

    def outline(self):
        self.layers['GML'].add(self.boundary())

    def oversize(self, r):
        self.layers['GML'].add(self.boundary(r))
        sr = self.silk / 2
        g = self.boundary(1.1 * sr).buffer(sr)
        self.layers['GTO'].add(g.buffer(0))

    def hole(self, xy, inner, outer = None):
        self.drill(xy, inner)
        if outer is not None:
            g = sg.LinearRing(sg.Point(xy).buffer(outer / 2).exterior).buffer(self.silk / 2)
            self.layers['GTO'].add(g)
            # self.layers['GTP'].add(sg.Point(xy).buffer(.2))
        self.keepouts.append(sg.Point(xy).buffer(inner / 2 + 0.5))

    def drill(self, xy, diam):
        self.holes[diam].append(xy)

    def annotate(self, x, y, s):
        self.layers['GTO'].add(hershey.ctext(x, y, s))

    def DC(self, xy, d = 0):
        return Draw(self, xy, d)

    def DCf(self, xy, d = 0):
        return Drawf(self, xy, d)

    def fill(self):
        ko = so.unary_union(self.keepouts)
        g = sg.box(0, 0, self.size[0], self.size[1]).buffer(-0.2).difference(ko)
        self.layers['GL2'].fill(g, 'GL2', self.via_space)
        self.layers['GL3'].fill(g, 'GL3', self.via_space)

    def fill_any(self, layer, include):
        if isinstance(include, str):
            include = [include]
        ko = so.unary_union(self.keepouts)
        g = self.body().buffer(-0.2).difference(ko)
        la = self.layers[layer]

        d = max(self.space, self.via_space)
        print('include', include)
        print({nm for (nm, o) in la.polys})
        notouch = so.unary_union([o for (nm, o) in la.polys if nm not in include])
        self.layers[layer].add(
            g.difference(notouch.buffer(d)), include
        )

    def addnet(self, a, b):
        self.nets.append(((a.part, a.name), (b.part, b.name)))

    def body(self):
        # Return the board outline with holes and slots removed.
        # This is the shape of the resin subtrate.
        gml = self.layers['GML'].lines
        assert gml != [], "Missing board outline"
        mask = sg.Polygon(gml[-1], gml[:-1])
        for d,xys in self.holes.items():
            if d > 0.3:
                hlist = so.unary_union([sg.Point(xy).buffer(d / 2) for xy in xys])
                mask = mask.difference(hlist)
        return mask

    def substrate(self):
        substrate = Layer(None)
        gml = self.layers['GML'].lines
        mask = sg.Polygon(gml[-1], gml[:-1])
        for d,xys in self.holes.items():
            if d > 0.3:
                hlist = so.unary_union([sg.Point(xy).buffer(d / 2) for xy in xys])
                mask = mask.difference(hlist)
        substrate.add(mask)
        return substrate

    def drc(self):
        mask = self.substrate().preview()
        for l in ("GTL", "GBL"):
            lg = self.layers[l].preview()
            if not mask.contains(lg):
                print("Layer", l, "boundary error")
                # self.layers["GTO"].add(lg.difference(mask).buffer(.1))

    def save(self, basename):
        # self.drc()
        # self.check()
        for (id, l) in self.layers.items():
            with open(basename + "." + id, "wt") as f:
                l.save(f)
        with open(basename + ".TXT", "wt") as f:
            excellon(f, self.holes)

        substrate = self.substrate()
        mask = substrate.preview()
        with open(basename + ".sub.pov", "wt") as f:
            substrate.povray(f, "prism { linear_sweep linear_spline 0 1")
        with open(basename + ".gto.pov", "wt") as f:
            self.layers['GTO'].povray(f, mask = mask)
        with open(basename + ".gtl.pov", "wt") as f:
            self.layers['GTL'].povray(f, mask = mask)
        with open(basename + ".gts.pov", "wt") as f:
            self.layers['GTS'].povray(f, mask = mask, invert = True)

        self.bom(basename)
        self.pnp(basename)

    def pnp(self, fn):
        with open(fn + "-pnp.csv", "wt") as f:
            cs = csv.writer(f)
            cs.writerow(["Designator", "Center(X)", "Center(Y)", "Rotatation", "Layer", "Note"])
            def flt(x): return "{:.3f}".format(x)
            for f,pp in self.parts.items():
                for p in pp:
                    if p.inBOM:
                        c = p.center
                        (x, y) = c.xy
                        note = p.footprint + "-" + p.mfr + p.val
                        cs.writerow([p.id, flt(x), flt(y), str(int(c.dir)), "Top", note])

    def bom(self, fn):
        parts = defaultdict(list)
        rank = "UJKTRCMY"
        for f,pp in self.parts.items():
            for p in pp:
                if p.inBOM:
                    if len(p.source) > 0:
                        vendor = list(p.source.keys())[0]
                        vendor_c = p.source[vendor]
                    else:
                        (vendor, vendor_c) = ('', '')
                    attr = (rank.index(f), p.mfr + p.val, p.footprint, vendor, vendor_c)
                    parts[attr].append(p.id)

        with open(fn + "-bom.csv", "wt") as f:
            c = csv.writer(f)
            c.writerow(['parts', 'qty', 'device', 'package', 'vendor', 'code'])
            for attr in sorted(parts):
                (f, mfr, footprint, vendor, vendor_c) = attr
                pp = parts[attr]
                c.writerow([pretty_parts(pp),
                    str(len(pp)),
                    mfr,
                    footprint,
                    vendor,
                    vendor_c])

    def postscript(self, fn):
        ps = ["%!PS-Adobe-2.0"]
        ps.append("72 72 translate")
        ps.append(".05 setlinewidth")

        body = self.body()
        pts = 72 / inches(1)
        def addring(r, style = "stroke"):
            ps.append("newpath")
            a = "moveto"
            for (x, y) in r.coords:
                ps.append("%f %f %s" % (x * pts, y * pts, a))
                a = "lineto"
            ps.append(style)

        addring(body.exterior)
        [addring(p) for p in body.interiors]
        [addring(p.exterior) for (_,p) in self.layers['GTL'].polys]
        rings = [body.exterior] + [r for r in body.interiors]

        ps.append("showpage")

        with open(fn, "wt") as f:
            f.write("".join([l + "\n" for l in ps]))

    def river1(self, i):
        return River(self, [i])

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

    def enriverS(self, pi, a):
        rv = self.enriver(pi, a)
        rv.left(a).wire()
        return rv

    def enriverPair(self, z):
        c = (self.trace + self.space)
        y = 0.5 * (z[0].distance(z[1]) - c)
        h = math.sqrt(2 * (y ** 2))
        
        z[0].w("o f .2 l 45 f {0} r 45 f .1".format(h))
        z[1].w("o f .2 r 45 f {0} l 45 f .1".format(h))
        assert (abs(c - z[0].distance(z[1]))) < 1e-3
        return River(self, z)

    def assign(self, part):
        pl = self.parts[part.family]
        pl.append(part)
        return part.family + str(len(pl))

    def logo(self, cx, cy, im, scale = None):
        im = im.convert("L")
        if scale is not None:
            w = int(im.size[0] * scale)
            h = int(im.size[1] * scale)
            im = im.resize((w, h), Image.BICUBIC)
        im = im.point(lambda p: p > 127 and 255)
        (w, h) = im.size
        ar = im.load()
        g = []
        s = 0.04
        ov = 1
        for y in range(h):
            (y0, y1) = (y * s, (y + ov) * s)
            slice = im.crop((0, (h - 1 - y), w, (h - 1 - y) + 1)).tobytes()
            x = 0
            while 255 in slice:
                assert len(slice) == (w - x)
                if slice[0] == 0:
                    l = slice.index(255)
                else:
                    if 0 in slice:
                        l = slice.index(0)
                    else:
                        l = len(slice)
                    g.append(sg.box(x * s, y0, (x + l * ov) * s, y1))
                slice = slice[l:]
                x += l
        g = sa.translate(so.unary_union(g), cx - 0.5 * w * s, cy - 0.5 * h * s).buffer(.001)
        self.layers['GTO'].add(g)

    def check(self):
        def npoly(g):
            if isinstance(g, sg.Polygon):
                return 1
            else:
                return len(g)
        g = self.layers['GTL'].preview()
        def clearance(g):
            p0 = micron(0)
            p1 = micron(256)
            while (p1 - p0) > micron(0.25):
                p = (p0 + p1) / 2
                if npoly(g) == npoly(g.buffer(p)):
                    p0 = p
                else:
                    p1 = p
            return 2 * p0
        for l in ('GTL', 'GBL'):
            if self.layers[l].polys:
                clr = clearance(self.layers[l].preview())
                if clr < (self.space - micron(1.5)):
                    print("space violation on layer %s, actual %.3f expected %.3f mm" % (l, clr, self.space))

        def h2pt(d, xys):
            return so.unary_union([sg.Point(xy).buffer(d / 2) for xy in xys])
        ghole = so.unary_union([h2pt(d, xys) for (d, xys) in self.holes.items()])
        return
        hot_vcc = ghole.intersection(self.layers['GL3'].powered)
        hot_gnd = ghole.intersection(self.layers['GL2'].powered)

        show = [po for po in self.layers['GTL'].p if po.intersects(hot_vcc)]
                
        # self.layers['GTP'].p = so.unary_union(show)

    def toriver(self, tt, ratio = 0.5):
        if len(tt) == 1:
            return River(self, tt)
        p = len(tt) // 2
        if ratio == 0.5:
            (lratio, rratio) = (1.0, 0.0)
        else:
            (lratio, rratio) = (ratio, ratio)
        (ra, rb) = (self.toriver(tt[:p], lratio), self.toriver(tt[p:], rratio))

        # Length-1 joins make horizontal lines, so must advance by C
        if len(ra.tt) == 1 or len(rb.tt) == 1:
            d = self.c
        else:
            d = 0

        extend2(ra.tt + rb.tt)
        return ra.join(rb, ratio).forward(d)

def extend(dst, traces):
    # extend parallel traces so that they are all level with dst
    assert len({t.dir for t in traces}) == 1, "All traces must be parallel"

    finish_line = dst.copy()
    finish_line.left(90)
    for t in traces:
        t.approach(0, finish_line)

def extend2(traces):
    by_y = {p.seek(traces[0])[1]: p for p in traces}
    extend(by_y[min(by_y)], traces)
    
class Part:
    mfr = ''
    footprint = ''
    val = ''
    inBOM = True
    source = {}
    def __init__(self, dc, val = None, source = None):
        self.id = dc.board.assign(self)
        if val is not None:
            self.val = val
        self.pads  = []
        self.board = dc.board
        self.center = dc.copy()
        self.place(dc)
        if source is not None:
            self.source = source

    def text(self, dc, s):
        (x, y) = dc.xy
        dc.board.layers['GTO'].add(hershey.ctext(x, y, s))

    def label(self, dc):
        (x, y) = dc.xy
        dc.board.layers['GTO'].add(hershey.ctext(x, y, self.id))

    def minilabel(self, dc, s):
        dc.push()
        dc.rect(.7, .7)
        dc.silko()
        dc.w("r 180 f 1.5")
        (x, y) = dc.xy
        dc.board.layers['GTO'].add(hershey.ctext(x, y, s))
        dc.pop()
        dc.newpath()

    def notate(self, dc, s):
        (x, y) = dc.xy
        dc.board.layers['GTO'].add(hershey.text(x, y, s, scale = 0.1))

    def chamfered(self, dc, w, h, drawid = True, idoffset = (0, 0)):
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
        dc.right(90)
        dc.goxy(*idoffset)
        (x, y) = dc.xy
        if drawid:
            dc.board.layers['GTO'].add(hershey.ctext(x, y, self.id))
        dc.pop()

    def pad(self, dc):
        dc.pad()
        p = dc.copy()
        p.part = self.id
        self.pads.append(p)

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
        p = dc.copy()
        p.part = self.id
        self.pads.append(p)

    def train(self, dc, n, op, step):
        for i in range(n):
            op()
            dc.forward(step)

    def s(self, nm):
        if " " in nm:
            return [self.s(n) for n in nm.split()]
        return {p.name:p for p in self.pads}[nm]

class Discrete2(Part):
    def escape(self, l0, l1):
        # Connections to GND and VCC
        [p.outside() for p in self.pads]
        self.pads[0].wvia(l0)
        self.pads[1].wvia(l1)

class C0402(Discrete2):
    family = "C"
    footprint = "0402"
    def place(self, dc):
        # Pads on either side
        for d in (-90, 90):
            dc.push()
            dc.right(d)
            dc.forward(1.30 / 2)
            dc.rect(0.7, 0.9)
            self.pad(dc)
            dc.pop()

        # Silk outline of the package
        dc.rect(1.0, 0.5)
        dc.silko()

        dc.push()
        dc.right(90)
        dc.forward(2.65)
        self.label(dc)
        dc.pop()

    def escape_2layer(self):
        # escape for 2-layer board (VCC on GTL, GND on GBL)
        self.pads[0].setname("VCC").w("o f 0.5").wire()
        self.pads[1].w("o -")

class C0603(Discrete2):
    family = "C"
    footprint = "0603"
    def place(self, dc, source = None):
        # Pads on either side
        for d in (-90, 90):
            dc.push()
            dc.right(d)
            dc.forward(1.70 / 2)
            dc.rect(1.0, 1.1)
            self.pad(dc)
            dc.pop()

        # Silk outline of the package
        dc.rect(1.6, 0.8)
        dc.silko()

        dc.push()
        dc.right(90)
        dc.forward(2)
        self.label(dc)
        dc.pop()

class R0402(C0402):
    family = "R"

# Taken from:
# https://www.analog.com/media/en/package-pcb-resources/package/pkg_pdf/ltc-legacy-qfn/QFN_64_05-08-1705.pdf

class QFN64(Part):
    family = "U"
    footprint = "QFN64"
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
    'E_SCK',
    'E_MISO',
    'E_MOSI',
    'E_CS',
    'E_IO2',
    'E_IO3',
    '3V3',
    '',
    'E_INT',
    'E_PD',
    '',
    'M_SCK',
    'M_CS',
    'M_MOSI',
    '3V3',
    'M_MISO',
    'M_IO2',
    'M_IO3',
    'X1',       # X1: in
    '',         # X2: out
    'GND',
    '3V3',
    '+1V2',
    'AUDIO',
    '3V3',
    '3V3',
    'CTP_RST',
    'CTP_INT',
    'CTP_SCL',
    'CTP_SDA',
    'GND',
    '',
    'DE',
    'VSYNC',
    'HSYNC',
    '',
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
    source = {'BridgeTek': 'BT815Q'}
    mfr = 'BT815Q'
    def escape(self):
        brd = self.board

        assert len(BT815pins) == len(self.pads)
        for p,n in zip(self.pads, BT815pins):
            p.setname(n)

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
        ctp = ['CTP_RST', 'CTP_INT', 'CTP_SCL', 'CTP_SDA']

        sctp = [self.s(nm) for nm in ctp]
        for i,s in enumerate(sctp):
            s.w("o f 0.4").forward(0.5 * (i & 1)).wire()
            s.via().setlayer('GBL').w("f 0.7")
        extend2(sctp)
        rctp = brd.enriver90(sctp, -90)
        rctp.wire()

        ext = [i for i,sig in enumerate(BT815pins) if sig not in (power | spim | set(ctp))]
        spi = [i for i,sig in enumerate(BT815pins) if sig in spim]
        for i in ext:
            self.pads[i].forward(1)
            self.pads[i].wire()
        # self.s("AUDIO").forward(.5)
        [self.pads[i].outside() for i in spi]

        def bank(n, pool):
            return [self.pads[i] for i in pool if (i - 1) // 16 == n]
        rv0 = brd.enriver90(bank(0, ext), 90)
        rv1 = brd.enriver90(bank(1, ext), -90)
        rv2 = brd.enriver(bank(2, ext), -45)
        rv3 = brd.enriver(bank(3, ext), 45)
        rv0.w("f .2 r 45 f .3").wire()

        rv1.w("r 45 f 1.0 l 45 f 2.5 l 45 f 3 l 45 f 1.2 r 45")
        rv1.wire()

        rv2 = rv1.join(rv2, 1)

        rv2.forward(0.6)

        rv0.forward(1).shimmy(0.344)
        rv3.shimmy(0.344)
        rv23 = rv2.join(rv3, 1.0)
        rv230 = rv23.join(rv0)
        rv230.wire()

        rv4 = brd.enriver90(bank(0, spi), -90)
        rv4.w("f 1 l 45")
        rv5 = brd.enriver(bank(1, spi), -45)
        rvspi = rv4.join(rv5)

        GBL = self.board.layers['GBL']
        dc = self.center.copy()
        dc.rect(12, 12)
        GBL.add(GBL.paint(dc.poly(), 'GBL', self.board.via_space))
        dc.layer = 'GBL'

        return (rvspi, rv230, rctp)

# IPC-SM-782A section 9.1: SOIC

class SOIC(Part):
    family = "U"
    footprint = "SOIC-8"
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
    C = 5.90
    D = 3.81
    G = 3.0
    Z = 7.4

class TSSOP(Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 4.4, {14:5.0, 20:6.5}[self.N])
        P = self.N // 2
        e = 0.65
        for _ in range(2):
            dc.push()
            dc.forward(e * (P - 1) / 2)
            dc.left(90)
            dc.forward((4.16 + 1.78) / 2)
            dc.left(90)
            self.train(dc, P, lambda: self.rpad(dc, 0.42, 1.78), e)
            dc.pop()
            dc.right(180)

class TSSOP14(TSSOP):
    N = 14

class M74VHC125(TSSOP14):
    def escape(self):
        for p,s in zip(self.pads, "A0 B0 O0 A1 B1 O1 GND  O3 B3 A3 O2 B2 A2 VCC".split()):
            p.setname(s)
        self.s("VCC").w("o f 1")
        for p in self.pads:
            if p.name in ("GND", "A0", "A1", "A2", "A3"):
                p.w("o -")

        self.s("O0").w("i f 0.4 l 90 f 3")
        self.s("O1").w("i f 1.2 l 90 f 3")
        self.s("O3").w("i f 1.2 r 90 f 3")
        self.s("O2").w("i f 0.4 r 90 f 3")
        outs = self.s("O2 O3 O1 O0")
        extend2(outs)
        rout = self.board.enriver90(outs, 90)

        self.s("B0").w("o f 1.2 . l 90 f 2").wire(layer = "GBL")
        self.s("B1").w("o f 0.6 . l 90 f 2").wire(layer = "GBL")
        self.s("B3").w("o f 0.6 . r 90 f 2").wire(layer = "GBL")
        self.s("B2").w("o f 1.2 . r 90 f 2").wire(layer = "GBL")

        ins = self.s("B0 B1 B3 B2")
        extend2(ins)
        rin = self.board.enriver90(ins, -90)

        [p.wire() for p in self.pads]
        return (rin, rout)

class SOT764(Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 2.5, 4.5)
        # pad side is .240 x .950

        def p():
            dc.rect(.240, .950)
            self.pad(dc)

        for i in range(2):
            dc.push()
            dc.goxy(-0.250, (3.5 + 1.0) / 2)
            p()
            dc.pop()

            dc.push()
            dc.goxy(-(1.7 / 2 + 0.5), 3.5 / 2)
            dc.right(180)
            self.train(dc, 8, lambda: self.rpad(dc, 0.240, 0.950), 0.5)
            dc.pop()

            dc.push()
            dc.goxy(-0.250, -(3.5 + 1.0) / 2).right(180)
            p()
            dc.pop()
            dc.right(180)

class M74LVC245(SOT764):
    source = {'LCSC': 'C294612'}
    mfr = '74LVC245ABQ'
    def escape(self):
        names = [
            "DIR", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "GND",
            "B7", "B6", "B5", "B4", "B3", "B2", "B1", "B0", "OE", "VCC"]
        [p.setname(nm) for (p, nm) in zip(self.pads, names)]
        [p.outside() for p in self.pads]
        self.s("GND").w("o -")
        self.s("OE").w("l 90 f 0.4 -")
        self.s("VCC").w("o f 0.5").wire()
        self.s("DIR").setname("VCC").w("o f 0.5").wire()

        gin = [self.s(nm) for nm in ('A6', 'A5', 'A4', 'A3', 'A2', 'A1', 'A0')]
        [s.forward(0.2 + 0.8 * i).w("l 45 f .2 .").w("f .2").wire("GBL") for (i, s) in enumerate(gin)]
        extend2(gin)
        ins = self.board.enriver90(gin[::-1], -90).w("r 45").wire()

        # self.s("B7").w("l 90 f 1.56").wire()
        gout = [self.s(nm) for nm in ('B6', 'B5', 'B4', 'B3', 'B2', 'B1', 'B0')]
        [s.forward(0.2) for s in gout]
        outs = self.board.enriver90(gout, 90).wire()

        return (ins, outs)

    def escape2(self):
        names = [
            "DIR", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "GND",
            "B7", "B6", "B5", "B4", "B3", "B2", "B1", "B0", "OE", "VCC"]
        [p.setname(nm) for (p, nm) in zip(self.pads, names)]
        [p.outside() for p in self.pads]
        self.s("GND").w("o -")
        self.s("OE").w("l 90 f 0.4 -")
        self.s("VCC").w("o f 0.5").wire()

        gin = [self.s(nm) for nm in ('A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7')]
        extend2(gin)
        ins = self.board.enriver90(gin, 90)

        # self.s("B7").w("l 90 f 1.56").wire()
        self.s("B7").w("l 90 f 0.9").wire()
        gout = [self.s(nm) for nm in ('B7', 'B6', 'B5', 'B4', 'B3', 'B2', 'B1', 'B0')]
        # [s.forward(0.2) for s in gout]
        extend2(gout)

        outs = self.board.enriver90(gout, 90).wire()

        return (ins, self.s("DIR"), outs)

class W25Q64J(SOIC8):
    source = {'LCSC': 'C179171'}
    mfr = 'W25Q64JVSSIQ'
    def escape(self):
        nms = "CS MISO IO2 GND MOSI SCK IO3 VCC".split()
        sigs = {nm: p for (nm, p) in zip(nms, self.pads)}

        for (nm, p) in zip(nms, self.pads):
            p.setname(nm)
        
        sigs['SCK' ].w("r 90 f 0.3 l 90 f 1.1")
        sigs['CS'  ].w("i f 1.5 r 90 f 1.27 f 1.27 f .63 l 90 f .1")
        sigs['MISO'].w("i f 1.0 r 90 f 1.27 f 1.27 f .63 l 90 f .1")
        sigs['MOSI'].w("o f .1")
        sigs['IO2' ].w("i f 0.5 r 90 f 2.20 l 90 f .1")
        sigs['IO3' ].w("i f 0.5 r 90 f 1.27 f .63 l 90 f 6.5 l 90 f 5.65 l 90 f .1")
        sigs['GND' ].w("o -")
        sigs['VCC' ].w("f -.4 l 90 f 0.5 +")

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
        rv.wire()
        return rv

    def escape1(self):
        b = self.board

        nms = "CS MISO IO2 GND MOSI SCK IO3 VCC".split()
        sigs = {nm: p for (nm, p) in zip(nms, self.pads)}
        for (nm, p) in zip(nms, self.pads):
            p.setname(nm)

        sigs['GND' ].w("o -")
        sigs['VCC' ].w("o +")

        ls = ('CS', 'MISO', 'IO2')
        rs = ('MOSI', 'SCK', 'IO3')
        
        for s in ls:
            sigs[s].w("i l 90 f 0.63 r 90").wire()
        for s in rs:
            sigs[s].w("i").wire()
        dv = b.via_space + b.via / 2
        for s in ls + rs:
            sigs[s].forward(dv)
        width = 3.7 - 2 * dv

        ord = "MOSI SCK MISO IO2 IO3 CS".split()
        gap = width / (len(ord) - 1)
        for i,s in enumerate(ord):
            x = i * gap
            if s in ls:
                x = width - x
            sigs[s].forward(x).wire().via('GBL')
            sigs[s].wire()
            if s in ls:
                sigs[s].right(180)
            sigs[s].right(90).forward(dv).wire('GBL')

        grp = [sigs[n] for n in ord]
        extend(grp[-1], grp)
        return self.board.enriver90(grp, -90).right(45).wire()

class HDMI(Part):
    family = "J"
    mfr = 'HDMI-001'
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

    def escape(self):
        board = self.board
        gnd = (1, 4, 7, 10, 13, 16)
        for g,p in zip(gnd, ["TMDS2", "TMDS1", "TMDS0", "TMDS_CLK"]):
            self.pads[g].setname("GND")
            self.pads[g - 1].setname(p + "_P")
            self.pads[g + 1].setname(p + "_N")

        for g in gnd:
            self.pads[g].w("i -")
        def pair(g):
            p = self.pads
            return self.board.enriverPair((p[g - 1], p[g + 1]))
        return ([pair(g) for g in gnd[:4]], self.pads[18])

class SOT223(Part):
    family = "U"
    footprint = "SOT223"
    def place(self, dc):
        self.chamfered(dc, 6.30, 3.30)
        dc.push()
        dc.forward(6.2 / 2)
        dc.rect(3.6, 2.2)
        self.pad(dc)
        dc.pop()

        dc.push()
        dc.left(90)
        dc.forward(4.60 / 2)
        dc.left(90)
        dc.forward(6.2 / 2)
        dc.left(90)
        self.train(dc, 3, lambda: self.rpad(dc, 1.20, 2.20), 2.30)
        dc.pop()

    def escape(self):
        # Returns (input, output) pads
        self.pads[2].w("i f 4").wire(width = 0.8)
        self.pads[1].inside().fan(1.0, 'GL2')
        self.pads[1].wire(width = 0.8)
        return (self.pads[3], self.pads[0])

class FTG256(Part):
    family = "U"
    footprint = "FTG256"
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
    mfr = 'XC6SLX9-2FTG256C'
    source = {'WIN SOURCE': 'XC6SLX9-2FTG256C'}
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

        for (pn, s) in self.signals.items():
            padname[pn].setname(s)

        powernames = (
            'GND', 'VCCO_0', 'VCCO_1', 'VCCO_2', 'VCCO_3', 'VCCAUX', 'VCCINT',
            'IO_L1P_CCLK_2',
            'IO_L3P_D0_DIN_MISO_MISO1_2',
            'IO_L3N_MOSI_CSI_B_MISO0_2',
            'IO_L65N_CSO_B_2',
            'IO_L49P_D3_2',
            'IO_L63P_2',
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
        self.padnames = padname

        if 0:
            for pn,s in self.signals.items():
                p = padname[pn]
                if s.startswith("IO_"):
                    f = s.split("_")
                    self.notate(p, f[1] + "." + f[-1])
                else:
                    self.notate(p, pn + "." + s)

        specials = [
            ( 'IO_L1P_CCLK_2', 'SCK'),
            ( 'IO_L3P_D0_DIN_MISO_MISO1_2', 'MISO'),
            ( 'IO_L3N_MOSI_CSI_B_MISO0_2', 'MOSI'),
            ( 'IO_L65N_CSO_B_2', 'CS'),
            ( 'IO_L49P_D3_2', 'IO2'),
            ( 'IO_L63P_2', 'IO3'),
            ( 'TCK', 'TCK'),
            ( 'TDI', 'TDI'),
            ( 'TMS', 'TMS'),
            ( 'TDO', 'TDO')]
        if 0:
            for (nm, lbl) in specials:
                self.minilabel(byname[nm], lbl)
        if 0:
            self.minilabel(byname['IO_L32N_M3DQ15_3'], 'PCLK')
        if 0:
            for nm,p in byname.items():
                if "GCLK" in nm:
                    self.minilabel(p, "C")
        if 0:
            for pn,s in self.signals.items():
                p = padname[pn]
                self.notate(p, pn)

        for pn,s in self.signals.items():
            if s in powernames:
                p = padname[pn]
                if pn in ("R6", "R8"):
                    p.right(180 - 25.28)
                    p.forward(.553)
                else:
                    p.right(45)
                    p.forward(math.sqrt(2) / 2)
                p.wire()
                dst = {
                    'GND' : 'GL2',
                    'IO_L13P_M1_2' : 'GL2',
                    'SUSPEND' : 'GL2',

                    'IO_L1N_M0_CMPMISO_2' : 'GL3',
                    'PROGRAM_B_2' : 'GBL',

                    'VCCINT' : 'GBL',
                    'IO_L1P_CCLK_2' : 'GBL',
                    'IO_L3P_D0_DIN_MISO_MISO1_2' : 'GBL',
                    'IO_L3N_MOSI_CSI_B_MISO0_2' : 'GBL',
                    'IO_L65N_CSO_B_2' : 'GBL',
                    'IO_L49P_D3_2' : 'GBL',
                    'IO_L63P_2' : 'GBL',
                    'TCK' : 'GBL',
                    'TDI' : 'GBL',
                    'TMS' : 'GBL',
                    'TDO' : 'GBL'
                }.get(s, 'GL3')
                p.via(dst)

        GBL = self.board.layers['GBL']
        dc = self.center.copy()
        dc.w("f 0.5 l 90")
        dc.rect(3, 23)
        GBL.add(GBL.paint(dc.poly(), 'GBL', self.board.via_space))
        dc.layer = 'GBL'

        v12 = dc
        v12.outside().newpath()

        d1 = math.sqrt(2 * (.383 ** 2))
        d2 = math.sqrt(2 * ((1 - .383) ** 2))

        s1 = "f 0.500"
        s2 = "l 45  f {0} r 45 f 1.117".format(d1)
        s3 = "l 45  f {0} r 45 f 1.883".format(d2)
        s3s = "l 90  f .637 r 90  f {0} f 1.883".format(1 - .383)

        plan = (
            (0, ".1$",  "l 90 " + s1),
            (0, "R2",   "l 90 " + "r 45  f {0} l 45 f 1.117".format(d1)),
            (0, ".2$",  "l 90 " + s2),
            (0, "[JL]3$",  "l 90 " + "l 45 f {0} r 45 f 2.117".format(d1)),
            (0, "[KM]3$",  "l 90 " + "r 45 f {0} l 45 f 2.117".format(d1)),
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
                            outer[grp].append(p)
                            break

        board = self.pads[0].board
        oc = [self.collect(outer[i]) for i in range(4)]
        x = 3
        oc = oc[x:] + oc[:x]
        ep0 = oc[0][-16]
        rv0 = board.enriver90(oc[0][-15:], -90)
        rv1 = board.enriver90(oc[1], -90)
        rem = 38 - len(rv1.tt)
        rv2 = board.enriver90(oc[2][:rem], 90)
        p0 = board.enriverS(oc[3][:7], -45)
        p1 = board.enriverS(oc[3][-7:], 45)

        # cand = sorted([p.name[1] for p in oc[2][rem:]])
        # [print(c) for c in cand if c[-1] == '2']

        # BT815 bus
        # rv1.forward(0.29)
        a = 0
        rv1.left(a).right(a)
        rv1.right(45)
        rv1.wire()

        rv2.w("f 1.8 l 45 f 2")
        rv2.wire()

        rv12 = rv1.join(rv2)
        rv12.wire()

        # LVDS
        def makepair(n, p):
            n = byname[n]
            p = byname[p]
            # self.notate(n, n.name[3:7])
            # self.notate(p, p.name[3:7])
            return board.enriverPair((n, p))
        lvds = [
            makepair('IO_L23N_2', 'IO_L23P_2'),
            makepair('IO_L30N_GCLK0_USERCCLK_2', 'IO_L30P_GCLK1_D13_2'),
            makepair('IO_L32N_GCLK28_2', 'IO_L32P_GCLK29_2'),
            makepair('IO_L47N_2', 'IO_L47P_2')
        ]

        # Flash

        grp = []
        for s,d in [('IO_L3P_D0_DIN_MISO_MISO1_2', 1.4),
                    ('IO_L1P_CCLK_2', 2.2),
                    ('IO_L3N_MOSI_CSI_B_MISO0_2', 1),
                    ]:
            t = byname[s]
            t.w("l 45 f 0.500 l 90").forward(d).left(90).forward(.1).wire('GBL')
            grp.append(t)
        extend(grp[-1], grp)
        [t.forward(0.8).wire('GBL') for t in grp]
        frv0 = board.enriver90(grp, 90)
        frv0.w("f 0.5 l 90").wire()
        
# 'IO_L49P_D3_2'      # P5
# 'IO_L63P_2'         # P4
# 'IO_L65N_CSO_B_2'   # T3
        grp = [byname[s] for s in ("IO_L65N_CSO_B_2", "IO_L63P_2", "IO_L49P_D3_2")]
        grp[2].w("r 45 f 0.330 r 90 f 0.2").wire('GBL')
        for t in grp[:2]:
            t.w("r 45 f 0.500 r 90 f 0.2").wire('GBL')
        extend(grp[0], grp)
        [t.forward(0.3).wire('GBL') for t in grp]
        frv1 = board.enriver90(grp, -90)
        frv1.w("r 90").wire('GBL')

        frv = frv1.join(frv0, .75)
        frv.wire('GBL')
    
        program = byname['PROGRAM_B_2']
        program.w("l 90 f 7.5 l 45 f 7").wire('GBL')

        # JTAG
        jtag = [byname[s] for s in ('TCK', 'TDI', 'TMS', 'TDO')]
        [t.w("l 45 f 0.5").wire('GBL') for t in jtag]
        # [self.notate(t, t.name[1]) for t in jtag]
        byname['TDO'].w("f 0.5 l 45 f 0.707 r 45").wire()
        extend(jtag[2], jtag)
        jrv = board.enriver90(self.collect(jtag), -90).wire()

        return (rv12, lvds, p0, p1, ep0, rv0, frv, jrv, program, v12)

    def dump_ucf(self, basename):
        with open(basename + ".ucf", "wt") as ucf:
            nets = self.board.nets
            def netpair(d):
                if self.id in d:
                    mine = d[self.id]
                    nms = set(d.values()) 
                    if len(nms) > 1:
                        nms -= {mine}
                    (oth, ) = tuple(nms)
                    return (mine, oth)
            mynets = [r for r in [netpair(dict(n)) for n in nets] if r]
            padname = {s : p for (p, s) in self.signals.items()}
            for (m, o) in mynets:
                if o in ("TMS", "TCK", "TDO", "TDI"):
                    continue
                if "TMDS" in o:
                    io = "TMDS_33"
                else:
                    io = "LVTTL"
                ucf.write('NET "{0}" LOC="{1}" | IOSTANDARD="{2}";\n'.format(o, padname[m], io))

class Castellation(Part):
    family = "J"
    inBOM = False
    def place(self, dc):
        dc.w("l 90 f 0.4 r 90")
        def cp():
            dc.right(90)
            dc.rect(1.2, 1)
            p = dc.copy()
            p.part = self.id
            self.pads.append(p)
            dc.contact()
            dc.push()
            dc.forward(0.375)
            dc.board.hole(dc.xy, 0.7)
            dc.pop()
            dc.left(90)
        self.train(dc, self.val, cp, 2.0)

    def escape(self):
        c = self.board.c
        def label(p, s):
            dc = p.copy()
            dc.inside()
            (d, tf) = {90: (0.05, hershey.text), 180: (0.6, hershey.ctext)}[dc.dir]
            dc.forward(d)
            (x, y) = dc.xy
            dc.board.layers['GTO'].add(tf(x, y, s))

        cnt = self.board.counters

        def group(pi, a):
            if a < 0:
                pp = pi[::-1]
            else:
                pp = pi
            for i,p in enumerate(pp):
                label(p, p.name[1:])
            for i,p in enumerate(pp):
                p.w("l 90 f .450 l 90 f .450 r 45" + (" f .12 l 9" * 10) + " r 45")
                p.forward((1 + i) * c)
                p.left(a)
                p.wire()
            extend(pp[0], pp)
            rv = River(self.board, pi[::-1])
            rv.right(a)
            rv.wire()
            return rv
        gnd = len(self.pads) // 2
        dc = self.pads[gnd]
        label(dc, "GND")
        self.sidevia(dc, "-")

        for p in self.pads:
            if p != self.pads[gnd]:
                cnt['port'] += 1
                p.setname("P" + str(cnt['port']))

        a = group(self.pads[:gnd], -90)
        b = group(self.pads[gnd + 1:], 90)
        return (a, b)

    def sidevia(self, dc, dst):
        assert dst in "-+."
        dc.setwidth(0.6)
        for l in ('GTL', 'GBL'):
            dc.push()
            dc.setlayer(l)
            dc.push()
            dc.w("f -0.3 r 90 f 0.4 " + dst)
            dc.pop()
            dc.w("f -0.3 l 90 f 0.4 " + dst)
            dc.pop()

    def escape1(self):
        pp = self.pads[::-1]
        names = "PGM TDI TDO TCK TMS".split()
        [t.setname(n) for t,n in zip(pp, names)]

        for t in pp:
            dc = t.copy().w("i f 0.6")
            (x, y) = dc.xy
            dc.board.layers['GTO'].add(hershey.ctext(x, y, t.name))
            t.w("i f 1").wire('GBL')

        return (self.board.enriver(pp[1:], 45).left(45).wire(), pp[0])

    def escape2(self):
        pp = self.pads
        def label(t, s):
            dc = t.copy().w("i f 0.6")
            (x, y) = dc.xy
            dc.board.layers['GTO'].add(hershey.ctext(x, y, s))
        label(pp[0], "3.3")
        label(pp[1], "GND")
        label(pp[2], "5V")

        for l in ('GTL', 'GBL'):
            pp[0].push().setlayer(l).setwidth(0.6).w("f -0.3 r 90 f 0.5 + f 0.5 +").pop()
        self.sidevia(pp[1], "-")
        return pp[2]

    def escape3(self):
        pp = self.pads[::-1]
        names = "SDA SCL INT RST".split()
        [t.setname(n) for t,n in zip(pp, names)]

        for t in pp:
            dc = t.copy().w("i f 0.6")
            (x, y) = dc.xy
            dc.board.layers['GTO'].add(hershey.ctext(x, y, t.name))
            t.w("i f 1").wire('GBL')

        return self.board.enriver(pp, 45).left(45).wire()

class WiiPlug(Part):
    family = "J"
    inBOM = False
    def place(self, dc):
        dc.rect(21, 10)
        self.board.keepouts.append(dc.poly().buffer(0))

        def finger():
            dc.right(90)
            dc.rect(1.6, 7)
            g = dc.poly()
            self.board.layers[dc.layer].add(g, dc.name)
            mask = dc.layer.replace("L", "S")
            self.board.layers[mask].add(g, dc.name)
            p = dc.copy()
            self.pads.append(p)
            p.part = self.id
            dc.left(90)
        dc.push()
        dc.w("l 90 f 2 r 180")
        dc.push()
        dc.setlayer('GTL')
        self.train(dc, 2, finger, 4)
        dc.pop()
        dc.setlayer('GBL')
        self.train(dc, 3, finger, 2)
        dc.pop()

        dc.goxy(-9.5, 4.8)
        F15 = " l 90 f 3 r 90 f 15 r 90 f 3 l 90 "
        dc.newpath()
        dc.w("r 90 f 3.3 r 90 f 3.15 r 90 f 1 l 90 f 3.25 l 90 f 1 r 90 f 2 l 90 f 2.95 l 90 f 7.3 r 90 f 3.25")
        dc.w("f 3.25 r 90 f 7.3 l 90 f 2.95 l 90 f 2 r 90 f 1 l 90 f 3.25 l 90 f 1 r 90 f 3.15 r 90 f 3.3")
        dc.w("r 90" + F15 + "r 90 f 19 r 90" + F15)
        self.board.layers['GML'].union(dc.poly())

    def escape(self):
        self.pads[0].setname("SCL").w("o f 2 .").setlayer("GBL")
        self.pads[1].setname("GND").w("o f 1 l 45 f 4 r 45 -")
        self.pads[2].setname("VCC").w("o f 0.2 r 45 f 0.6 +").setlayer("GTL").w("f 1").wire()
        self.pads[3].setname("DET").w("o f 2").wire()
        self.pads[4].setname("SDA").w("o f 2").wire()
        g = [self.s(nm) for nm in ("SCL", "DET", "SDA")]
        extend2(g)
        return self.board.enriver90(g, -90).wire()

class SMD_3225_4P(Part):
    family = "Y"
    def place(self, dc):
        self.chamfered(dc, 2.8, 3.5, idoffset = (1.4, .2))

        for _ in range(2):
            dc.push()
            dc.goxy(-1.75 / 2, 2.20 / 2).right(180)
            self.train(dc, 2, lambda: self.rpad(dc, 1.2, 0.95), 2.20)
            dc.pop()
            dc.right(180)
        [p.setname(nm) for p,nm in zip(self.pads, ["", "GND", "CLK", "VDD"])]

class Osc_6MHz(SMD_3225_4P):
    source = {'LCSC': 'C387333'}
    mfr = 'S3D6.000000B20F30T'
    def escape(self):
        self.s("GND").w("i -")
        self.s("VDD").w("i +")
        return self.s("CLK")
