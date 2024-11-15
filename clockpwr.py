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

def clockpwr():
    d = 68.5      # pin-to-pin
    d1 = 4.0    # pin-to-edge
    brd = cu.Board(
        (d + 2 * d1, 24),
        trace = 0.4,
        space = 0.2,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(5))

    j1 = dip.SIL_o(brd.DC((d1, 12.0)), "6")
    j2 = dip.SIL_o(brd.DC((d1 + d, 12.0)), "6")

    x = d1 + d / 2
    j3s = [dip.Screw1(brd.DC((x + d, 24 - 4.5))) for d in (-5, 0, 5)]
    j4s = [dip.Screw1(brd.DC((x + d,      4.5))) for d in (-5, 0, 5)]

    for j in (j1, j2):
        j.pads[0].setname("VCC").thermal(1).wire()
        j.pads[5].through().setname("GND").thermal(1).wire()

    for j3 in j3s:
        j3.pads[0].setname("VCC").thermal(2).wire()
    for j4 in j4s:
        j4.pads[0].through().setname("GND").thermal(2).wire()

    for i in range(1, 5):
        print(i)
        j1.pads[i].goto(j2.pads[i]).wire()

    brd.outline()
    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("clockpwr")

if __name__ == "__main__":
    clockpwr()
