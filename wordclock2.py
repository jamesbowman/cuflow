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
from hexboard import HexBoard
from dualflash import (
    TRACE_WIDTH, TRACE_SPACE, VIA_HOLE, VIA_DIAMETER, VIA_SPACE, SILK_WIDTH,
)

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
    mfr = "WS2812B-B/W"
    footprint = "SMD5050-4P"
    source = {"LCSC": "C114586"}
    def place(self, dc):
        self.chamfered(dc.copy().left(90), 5.0, 5.0, idoffset = (-0.5, .2))

        # Extend pads outward for hand soldering, keeping the inner gap.
        w = 3.2 + 2.5
        h = 2.1 + 1.1
        for _ in range(2):
            dc.push()
            dc.goxy(h / 2, w / 2).right(180)
            self.train(dc, 2, lambda: self.rpad(dc, 2.5, 1.5), w)
            dc.pop()
            dc.right(180)
        [p.setname(nm) for p,nm in zip(self.pads, ["VCC", "DIN", "GND", "DOUT", ])]

    def escape(self):
        self.s("GND").w("l 45 f 3 /").thermal(1).wire()
        self.s("VCC").thermal(1).wire()

def wordclock2():
    d = 68.5      # pin-to-pin
    d1 = 4.0    # pin-to-edge
    brd = HexBoard(
        (HSIZE, VSIZE),
        trace = TRACE_WIDTH,
        space = TRACE_SPACE,
        via_hole = VIA_HOLE,
        via = VIA_DIAMETER,
        via_space = VIA_SPACE,
        silk = SILK_WIDTH)

    o = 8
    for x in (o, HSIZE - o):
        for y in (o, VSIZE - o):
            brd.hole((x, y), 3, 6, stencil_alignment = True)
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
        fixture_offset = 6 / math.sqrt(2)
        for i in range(n):
            np = NeoPixel5050(p.copy().right(0 + 45))
            x, y = p.xy
            # Fixture holes 6 mm NW and SE from the LED center.
            for dx, dy in ((-fixture_offset, fixture_offset),
                           (fixture_offset, -fixture_offset)):
                xy = (x + dx, y + dy)
                brd.hole(xy, 2)
            np.escape()
            if (i % 18) == 8:
                p.right(90).forward(HSPACE).right(90)
            elif (i % 18) == 17:
                p.left(90).forward(HSPACE).left(90)
            else:
                p.forward(VSPACE)
            a.append(np)
        return a

    # Top left LED is at (7.11, 15.7)
    all_n = nps(16 * 9, brd.DC((7.11, VSIZE - 15.7 - 8 * VSPACE)))

    brd.outline()
    brd.hex_clearance = TRACE_SPACE
    brd.hex_edge_clearance = 0.5
    # DIN is a plated terminal, not a mechanical routing obstacle. Exempt
    # its own drill/keepout while planning, restoring both before export.
    din = j2.s("DIN")
    holes, keepouts = brd.holes, brd.keepouts
    try:
        brd.holes = holes.copy()
        for diameter, locations in holes.items():
            brd.holes[diameter] = [xy for xy in locations if xy != din.xy]
        brd.keepouts = [g for g in keepouts
                        if not g.covers(sg.Point(din.xy))]
        brd.hex_setup()
        # Route directly between the available cells inside the large pads.
        brd.hex_route(
            brd.pad_endpoint(din),
            brd.pad_endpoint(all_n[0].s("DIN")),
        )
    finally:
        brd.holes, brd.keepouts = holes, keepouts
    for i, (src, dst) in enumerate(zip(all_n, all_n[1:]), 1):
        brd.hex_route(
            brd.pad_endpoint(src.s("DOUT")),
            brd.pad_endpoint(dst.s("DIN")),
        )
        if i % 16 == 0 or i == len(all_n) - 1:
            print(f"Routed {i}/{len(all_n) - 1} LED links", flush=True)
    brd.wire_routes()
    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("wordclock2")

if __name__ == "__main__":
    wordclock2()
