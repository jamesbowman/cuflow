import sys
import json
import math

import shapely.geometry as sg
from PIL import Image, ImageDraw, ImageFont

import cuflow as cu
import svgout
import dip
import sot
import eagle

"""
16x8
PCB 257 wide
H width is 230, 213
"""

HSIZE = 257
VSIZE = 277
HSPACE = 15.212
VSPACE = 144.9 / 5

class NeoPixel5050(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc.copy().left(90), 5.0, 5.0, idoffset = (-0.5, .2))

        w = 3.2 + 1.5
        h = 2.1 + 1.1
        for _ in range(2):
            dc.push()
            dc.goxy(h / 2, w / 2).right(180)
            self.train(dc, 2, lambda: self.rpad(dc, 1.5, 1.1), w)
            dc.pop()
            dc.right(180)
        [p.setname(nm) for p,nm in zip(self.pads, ["VCC", "DIN", "GND", "DOUT", ])]

    def escape(self):
        self.s("GND").w("l 45 f 3 /").thermal(1).wire()
        self.s("VCC").thermal(1).wire()

def wordclock():
    d = 68.5      # pin-to-pin
    d1 = 4.0    # pin-to-edge
    brd = cu.Board(
        (HSIZE, VSIZE),
        trace = 0.4,
        space = 0.2,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(5))

    o = 8
    for x in (o, HSIZE - o):
        for y in (o, VSIZE - o):
            brd.hole((x, y), 3, 6, stencil_alignment = True)
    brd.hole((121, 123), 3, 6, stencil_alignment = False)
    brd.hole((132.5, 5.5), 3, 6, stencil_alignment = False)

    j1 = [dip.Screw1(brd.DC((HSIZE / 2 + d, 13))) for d in (-3, 3)]
    j1[0].pads[0].setname("VCC").thermal(3).wire()
    j1[1].pads[0].through().setname("GND").thermal(3).wire()
    for j,nm in zip(j1, ("+5V", "GND")):
        j.pads[0].copy().w("r 180 f 3").ctext(nm)
    
    j2 = dip.SIL_o(brd.DC((7.11 + HSPACE, 4)).right(90), "3")
    for p,nm in zip(j2.pads, ("GND", "+5V", "DIN")):
        p.setname(nm)
        p.copy().w("r 90 f 2").ctext(nm)
    j2.s("GND").through().thermal(1).wire()
    j2.s("+5V").setname("VCC").thermal(1).wire()

    def nps(n, p):
        a = []
        for i in range(n):
            np = NeoPixel5050(p.copy().right(0 + 45))
            np.escape()
            if i != 0:
                prev.s("DOUT").straight(np.s("DIN")).wire()
            if (i % 18) == 8:
                p.right(90).forward(HSPACE).right(90)
            elif (i % 18) == 17:
                p.left(90).forward(HSPACE).left(90)
            else:
                p.forward(VSPACE)
            prev = np
            a.append(np)
        return a

    # Top left LED is at (7.11, 15.7)
    all_n = nps(16 * 9, brd.DC((7.11, VSIZE - 15.7 - 8 * VSPACE)))

    j2.s("DIN").goto(all_n[0].s("DIN")).wire()

    brd.outline()
    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("wordclock")

if __name__ == "__main__":
    wordclock()
