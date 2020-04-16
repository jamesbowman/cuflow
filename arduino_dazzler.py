import sys
from PIL import Image
import math
import cuflow as cu
import svgout
from dazzler import Dazzler
from collections import defaultdict

import xml.etree.ElementTree as ET
import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so

class LibraryPart(cu.Part):
    libraryfile = None
    partname = None
    def __init__(self, dc, val = None, source = {}):
        tree = ET.parse(self.libraryfile)
        root = tree.getroot()
        x_packages = root.find("drawing").find("library").find("packages")
        packages = {p.attrib["name"]:p for p in x_packages}
        self.pa = packages[self.partname]
        cu.Part.__init__(self, dc, val, source)

    def place(self, dc):
        ls = defaultdict(list)
        for c in self.pa:
            attr = c.attrib
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
                p.rect(dx, dy)
                p.setname(attr["name"])
                self.pad(p)
            elif c.tag == "pad":
                (x, y, diameter, drill) = [float(attr[t]) for t in "x y diameter drill".split()]
                nm = attr["name"]

                dc.push()
                dc.goxy(x, y)
                dc.board.hole(dc.xy, drill)
                n = {"circle" : 60, "octagon" : 8, "square" : 4}[attr.get("shape", "circle")]
                p = dc.copy()
                p.n_agon(diameter / 2, n)

                p.setname(nm)
                self.pads.append(p)
                p.contact()

                if nm not in ("RESERVED", ):
                    self.board.annotate(dc.xy[0], dc.xy[1], nm)
                dc.pop()
        if ls["20"]:
            g = so.linemerge(ls["20"])
            brd.layers['GML'].add(g)
        if ls["21"]:
            g = so.linemerge(ls["21"]).buffer(brd.silk / 2)
            brd.layers['GTO'].add(g)

class ArduinoR3(LibraryPart):
    libraryfile = "adafruit.lbr"
    partname = "ARDUINOR3"
    family = "J"
    def escape(self):
        spi = [self.s(n) for n in "D13 D11 D9 D8".split()]
        for t in spi:
            t.w("r 180 f 2").wire(layer = "GBL")
        spio = self.board.enriver90(spi, -90)
        [t.wire() for t in spi]
        for nm in ("GND", "GND1", "GND2"):
            self.s(nm).setname("GL2").w("f 1.2 r 180 f 1.2 r 90 " * 4).wire(layer = "GBL")
        return spio

class SD(LibraryPart):
    libraryfile = "x.lbrSD_TF_holder.lbr"
    partname = "MICROSD"
    family = "J"

__VERSION__ = "0.1.0"

if __name__ == "__main__":
    brd = cu.Board(
        (50, 42),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    Dazzler(brd.DC((68.58 - 43.59, 26.5)).right(180))
    sd = SD(brd.DC((53.6, 22)).right(0))
    sd.s("3").mark()
    (lvl_in, lvl_out) = cu.M74VHC125(brd.DC((58, 43)).right(180)).escape()

    shield = ArduinoR3(brd.DC((0, 0)))
    a_spio = shield.escape()

    a_spio.meet(lvl_in)

    # brd.fill_any("GTL", "VCC")
    # brd.fill_any("GBL", "GL2")

    cu.M74LVC245(brd.DC((25, 25)).right(90)).escape()

    brd.save("arduino_dazzler")
    svgout.write(brd, "arduino_dazzler.svg")
