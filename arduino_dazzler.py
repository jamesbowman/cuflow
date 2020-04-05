import sys
from PIL import Image
import math
import cuflow as cu
import svgout
from dazzler import Dazzler

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
        ls = []
        for c in self.pa:
            attr = c.attrib
            if c.tag == "wire" and attr["layer"] == "20":
                (x1, y1, x2, y2) = [float(attr[t]) for t in "x1 y1 x2 y2".split()]
                p0 = dc.copy().goxy(x1, y1)
                p1 = dc.copy().goxy(x2, y2)
                ls.append(sg.LineString([p0.xy, p1.xy]))
            elif c.tag == "circle" and attr["layer"] == "51":
                (x, y, radius) = [float(attr[t]) for t in "x y radius".split()]
                p = dc.copy().goxy(x, y)
                dc.board.hole(p.xy, 2 * radius)
            elif c.tag == "pad":
                (x, y, diameter, drill) = [float(attr[t]) for t in "x y diameter drill".split()]
                dc.push()
                dc.goxy(x, y)
                dc.board.hole(dc.xy, drill)
                n = {"circle" : 60, "octagon" : 8, "square" : 4}[attr.get("shape", "circle")]
                dc.n_agon(diameter / 2, n)
                self.pad(dc)
                nm = attr["name"]
                if nm not in ("RESERVED", ):
                    print(nm)
                    self.board.annotate(dc.xy[0], dc.xy[1], nm)
                dc.pop()
        g = so.linemerge(ls)
        brd.layers['GML'].add(g)

class ArduinoR3(LibraryPart):
    libraryfile = "adafruit.lbr"
    partname = "ARDUINOR3"
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

    Dazzler(brd.DCf((34, 26.5)))
    cu.M74VHC125(brd.DC((30, 20))).escape()
    # cu.W25Q16J(brd.DCf((50, 20))).escape()

    shield = ArduinoR3(brd.DCf((68.58, 0)))
    brd.save("arduino_dazzler")
    svgout.write(brd, "arduino_dazzler.svg")
