import sys
import math
import cuflow as cu
from collections import defaultdict

import xml.etree.ElementTree as ET
import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so

class LibraryPart(cu.Part):
    libraryfile = None
    partname = None
    use_silk = True
    use_pad_text = True
    def __init__(self, dc, val = None, source = None):
        tree = ET.parse(self.libraryfile)
        root = tree.getroot()
        x_packages = root.find("drawing").find("library").find("packages")
        packages = {p.attrib["name"]:p for p in x_packages}
        self.pa = packages[self.partname]
        cu.Part.__init__(self, dc, val, source)

    def place(self, dc):
        ls = defaultdict(list)
        attr = {}
        for c in self.pa:
            attr.update(c.attrib)
            if c.tag == "wire" and attr["layer"] in ("20", "21"):
                (x1, y1, x2, y2) = [float(attr[t]) for t in "x1 y1 x2 y2".split()]
                p0 = dc.copy().goxy(x1, y1)
                p1 = dc.copy().goxy(x2, y2)
                ls[attr["layer"]].append(sg.LineString([p0.xy, p1.xy]))
            elif c.tag == "hole":
                (x, y, drill) = [float(attr[t]) for t in "x y drill".split()]
                p = dc.copy().goxy(x, y)
                dc.board.hole(p.xy, drill)
            elif c.tag == "circle" and attr["layer"] == "51":
                (x, y, radius) = [float(attr[t]) for t in "x y radius".split()]
                p = dc.copy().goxy(x, y)
                dc.board.hole(p.xy, 2 * radius)
            elif c.tag == "smd":
                (x, y, dx, dy) = [float(attr[t]) for t in "x y dx dy".split()]
                p = dc.copy().goxy(x, y)
                if attr['rot'] in ("R90", "R270"):
                    (dx, dy) = (dy, dx)
                p.rect(dx, dy)
                p.setname(attr["name"])
                self.pad(p)
            elif c.tag == "pad":
                if 'diameter' not in attr:
                    attr['diameter'] = float(attr['drill']) * 1.5
                (x, y, diameter, drill) = [float(attr[t]) for t in "x y diameter drill".split()]
                nm = attr["name"]

                dc.push()
                dc.goxy(x, y)
                dc.board.hole(dc.xy, drill)
                shape = attr.get("shape", "circle")
                n = {"long" : 60, "circle" : 60, "octagon" : 8, "square" : 4}[shape]
                if shape == "square":
                    diameter /= 1.1
                attr["shape"] = "circle"
                p = dc.copy()
                p.n_agon(diameter / 2, n)

                p.setname(nm)
                p.part = self.id
                self.pads.append(p)
                p.contact()

                if 0 and self.use_pad_text and nm not in ("RESERVED", ):
                    self.board.annotate(dc.xy[0], dc.xy[1], nm)
                dc.pop()
        if ls["20"]:
            g = so.linemerge(ls["20"])
            brd.layers['GML'].add(g)
        if self.use_silk and ls["21"]:
            g = so.linemerge(ls["21"]).buffer(self.board.silk / 2)
            self.board.layers['GTO'].add(g)

