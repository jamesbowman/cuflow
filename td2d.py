import sys
import json
import math

import shapely.geometry as sg
from PIL import Image, ImageDraw, ImageFont

import cuflow as cu
import svgout
import dip
import eagle
from dazzler import Dazzler
from collections import defaultdict
from rp2040 import RP2040

import shapely.geometry as sg

used_pins = [
"SWCLK",    # Module_Serial_Debug.SWCLK
"GPIO1",    # Module_Serial_Debug.RX
"GPIO0",    # Module_Serial_Debug.TX
"SWD",      # Module_Serial_Debug.SWDIO
"GPIO14",   # Module_LCD240x240_breakout.SDL
"GPIO15",   # Module_LCD240x240_breakout.SDA
"GPIO11",   # Module_LCD240x240_breakout.RES
"GPIO10",   # Module_LCD240x240_breakout.DC
"GPIO12",   # Module_Serial.DTR
"GPIO9",    # Module_Serial.RX
"GPIO8",    # Module_Serial.TX
"GPIO13",   # Module_Serial.CTS

# "GPIO0",
# "GPIO1",
# "GPIO2",
# "GPIO3",
# "GPIO4",
# "GPIO5",
# "GPIO6",
# "GPIO7",
# "VCC",
# "GPIO8",
# "GPIO9",
# "GPIO10",       # LCD
# "GPIO11",       # LCD
# "GPIO12",
# "GPIO13",
# "GPIO14",       # LCD
# "GPIO15",       # LCD
# "TESTEN",
"XIN",
# "XOUT",
# "VCC",
# "DVDD",
# "SWCLK",
# "SWD",
# "RUN",
# "GPIO16",
# "GPIO17",
# "GPIO18",
# "GPIO19",
# "GPIO20",
# "VCC",
# "GPIO21",
# "GPIO22",
# "GPIO23",
# "GPIO24",
# "GPIO25",
# "GPIO26/ADC0",
# "GPIO27/ADC1",
# "GPIO28/ADC2",
# "GPIO29/ADC3",
# "VCC",
# "ADC_AVDD",
# "VREG_VIN",
# "VREG_VOUT",
"USB_DM",
"USB_DP",
# "VCC",
# "VCC",
"QSPI_SD3",
"QSPI_SCLK",
"QSPI_SD0",
"QSPI_SD2",
"QSPI_SD1",
"QSPI_SS_N",
]

from hex import Hex

def hexgrid(b, o):
    b.layers['GTO'].polys = []
    def pt(xy):
        b.layers['GTO'].add(sg.Point(xy).buffer(.03))
    if 0:
        R = 60
        for q in range(0, R):
            for r in range(0, R):
                (x, y) = Hex(q, r).to_plane()
                pt((x, y))
    else:
        for h in o.neighborhood(16):
            pt(h.to_plane())

def hex_occ(brd, origin):
    occ = []
    metal = sg.MultiPolygon([po for (nm,po) in brd.layers['GTL'].polys]).buffer(0.0)
    for h in origin.neighborhood(16):
        pt = sg.Point(*h.to_plane()).buffer(0.2)
        if pt.intersects(metal):
            occ.append(tuple(h - origin))
    return occ

def hex_sigs(brd, origin, pp):
    sigs = {}
    for p in pp:
        hh = Hex.from_xy(*p.xy)
        rp = brd.DC(hh.to_plane())
        assert rp.distance(p) < 0.010
        print(f"{p.name:10}", hh - origin)
        sigs[p.name] = tuple(hh - origin)
    return sigs

def hex_rp2040(brd, dc, origin):
    u = RP2040(dc)
    banks = u.escape(used_pins)

    if 0:
        for p in (banks[1] + banks[3]):
            hh = Hex.from_xy(*p.xy)
            p.goxy(*hh.best_forward(p)).wire() # .mark()

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
    def wire_ongrid(p):
        (dx, dy) = best_forward(p)
        p.goyx(dx, dy).wire()

    if 1:
        river_ongrid(cu.River(brd, banks[0][:2 ]).left(60))
        river_ongrid(cu.River(brd, banks[0][-4:]).left(60))
        river_ongrid(cu.River(brd, banks[1][:4 ]).right(30))
        river_ongrid(cu.River(brd, banks[3][:2]).right(30))
        river_ongrid(cu.River(brd, banks[3][-6:]).left(30))
    for nm in ("XIN", "SWCLK", "SWD"):
        wire_ongrid(u.s(nm))

    dump = {
        'name' : 'rp2040',
        'occ' : hex_occ(brd, origin),
        'sigs' : hex_sigs(brd, origin, [u.s(nm) for nm in used_pins])
    }
    return dump

def hex_c0402(brd, dc, origin):
    u = cu.C0402(dc)
    u.pads[0].w("o -")
    u.pads[1].setname("VCC").w("o f 0.4").wire()
    dump = {
        'name': 'c0402',
        'occ' : hex_occ(brd, origin),
        'sigs' : {},
    }
    return dump

def genpart(article):
    w = .4/3   # .127 is JLCPCB minimum
    brd = cu.Board(
        (30, 30),
        trace = w,
        space = .4 - w,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    brd.outline()

    origin =  Hex.from_xy(15, 15)
    hexgrid(brd, origin)
    xy = origin.to_plane()
    dc = brd.DC(xy)
    dump = article(brd, dc, origin)
    nm = dump["name"]
    with open(f"{nm}-hex.json", "wt") as f:
        json.dump(dump, f)

    if 0:
        p0 = brd.DC(Hex(0, 0).to_plane())
        p1 = brd.DC(Hex(0, 100).to_plane())
        p0.mark()
        p1.mark()
        print(p0.distance(p1))

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("td2d")
    # brd.postscript("td2d.ps")
    return dump

def td2d():
    u = genpart(hex_rp2040)
    # c = genpart(hex_c0402)

if __name__ == "__main__":
    td2d()
