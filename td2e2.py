import sys
import json
import math
import time

import shapely.geometry as sg
from shapely.strtree import STRtree
from PIL import Image, ImageDraw, ImageFont

import numpy as np

import cuflow as cu
import svgout
import dip
import sot
import eagle
from dazzler import Dazzler
from collections import defaultdict
from rp2040 import RP2040

import shapely.geometry as sg

twenty_rgb = [
(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180), (0, 0, 128), (128, 128, 128), (255, 255, 255), (0, 0, 0)
]

used_pins = [
# "SWCLK",    # Module_Serial_Debug.SWCLK
# "GPIO1",    # Module_Serial_Debug.RX
# "GPIO0",    # Module_Serial_Debug.TX
# "SWD",      # Module_Serial_Debug.SWDIO
"GPIO14",   # Module_LCD240x240_breakout.SDL
"GPIO15",   # Module_LCD240x240_breakout.SDA
"GPIO11",   # Module_LCD240x240_breakout.RES
"GPIO10",   # Module_LCD240x240_breakout.DC
"GPIO12",   # Module_Serial.DTR
"GPIO9",    # Module_Serial.RX
"GPIO8",    # Module_Serial.TX
"GPIO13",   # Module_Serial.CTS

"GPIO0",
"GPIO1",
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
"SWCLK",
"SWD",
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

from hex import Hex, axial_direction_vectors

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
        for h in o.neighborhood(38):
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
    return rr

def wire_ongrid(p):
    (dx, dy) = best_forward(p)
    p.goyx(dx, dy).wire()
    p.dir = 30 + 60 * round((p.dir - 30) / 60)

class HexRP2040(RP2040):
    def hex_escape(self):
        brd = self.board

        banks = self.escape(used_pins)

        river_ongrid(cu.River(brd, banks[0][0:2]).w("f .5"))
        river_ongrid(cu.River(brd, banks[0][-4:-2]).w("f 0.8 r 60"))
        river_ongrid(cu.River(brd, banks[0][-2:]).w(""))
        river_ongrid(cu.River(brd, banks[1][:4 ]).right(30))
        river_ongrid(cu.River(brd, banks[1][5:7]).w("f 0.52 l 30")).hex("l 5f").wire()
        river_ongrid(cu.River(brd, banks[3][:2]).w("f 0.4 l 30"))
        river_ongrid(cu.River(brd, banks[3][-6:]).left(30))
        for nm in ("XIN", ):
            wire_ongrid(self.s(nm))
        self.pads[0].w("/").thermal(1).wire()

class HexW25Q128(cu.SOIC8):
    source = {'LCSC': 'C6604692'}
    mfr = 'W25Q64JVSSIQ'
    def hex_escape(self):
        [c.setname(nm) for (c, nm) in zip(self.pads, "CS IO1 IO2 GND IO0 CLK IO3 VCC".split())]

        # bootsel = self.s("CS").copy().w("i l 90 f 3 r 90").wire()

        for p in self.pads:
            if p.name == "GND":
                p.w("i f 1").wire().copy().w("/ f 1").wire()
            elif p.name == "VCC":
                p.w("i f 1").wire()
            else:
                # p.copy().w("o f 0.5").ctext(p.name, scale = 0.4)
                p.w("o f .1")
                wire_ongrid(p)
                p.wire()


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

class USB(eagle.LibraryPart):
    libraryfile = "10118194-0001LF.lbr"
    partname = "AMPHENOL_10118194-0001LF"
    family = "J"

    def setnames(self):
        [p.setname(nm) for (p,nm) in zip(self.pads, ('5V', 'D-', 'D+', '', 'GND'))]

    def hex_escape(self):
        self.setnames()
        self.s("GND").w("i f .3 l 90 f 2 / f 1").wire()
        for nm in ('D-', 'D+'):
            p = self.s(nm)
            wire_ongrid(p.w("o f 0.1"))
        wire_ongrid(self.s("5V").w("i"))

class SOT23_LDO(sot.SOT23):
    family = "U"
    def hex_hookup(self, names):
        for (p,nm) in zip(self.pads, names):
            p.setname(nm) 
            if nm == "GND":
                p.w("i f 0.7 / f 1")
            elif nm == "VCC":
                p.w("o f 0.7")
            else:
                wire_ongrid(p.w("o f 1"))
            p.wire()

    def hex_escape(self):
        self.hex_hookup(('GND', 'VCC', '5V'))

#  1 GND        GND
#  2 LEDK       GND
#  3 LEDA       LEDA
#  4 VDD        VCC
#  5 GND        GND
#  6 GND        GND
#  7 D/C        D/C
#  8 CS         GND
#  9 SCL        SCL
# 10 SDA        SDA
# 11 RESET      RESET
# 12 GND        GND

class ST7789_12(cu.Part):
    family = "U"
    def place(self, dc):
        dc.right(90)
        self.train(dc, 12, lambda: self.rpad(dc, .35, 2), 0.7)

    def hex_escape(self):
        for (p, nm) in zip(self.pads, "GND  GND LEDA  VCC GND GND D/C GND SCL SDA RESET GND".split()):
            p.setname(nm)
            if nm == "GND":
                p.w("o f 1").wire()
            elif nm == "VCC":
                p.w("o f 1 / f 1").wire()
            else:
                wire_ongrid(p.w("i f 0.2"))

class SMT6(cu.Part):
    family = "J"
    def place(self, dc):
        self.chamfered(dc.copy().forward(-8), 13, 8, idoffset = (-0.5, -2))
        dc.w(f"l 90 f {cu.inches(.25)} r 180")
        self.train(dc, 6, lambda: self.rpad(dc, 1.2, 3), 2.54)

    def hex_escape(self):
        names = ('GND', 'CTS', 'VCC', 'TX', 'RX', 'DTR')[::-1]
        for (p, nm) in zip(self.pads, names):
            p.setname(nm)
            p.copy().w("f 2.6").ctext(nm)
            if nm == "GND":
                p.w("i f 1 / f 1").wire()
            elif nm == "VCC":
                p.w("o f 0.5").wire()
            elif nm in ("TX", "RX", "CTS"):
                wire_ongrid(p.w("i"))
            else:
                wire_ongrid(p.w("o"))

class SMD_3225_4P(cu.Part):
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

class Osc_12MHz(SMD_3225_4P):
    source = {'LCSC': 'C454611'}
    def escape(self):
        self.s("GND").w("l 90 f 1.5 / f 1").wire()
        self.s("VDD").setname("VCC")
        self.s("VCC").w("o f 0.5").wire()
        wire_ongrid(self.s("CLK").w("o"))

class ByteGrid:
    def __init__(self, w, h):
        (self.q0, self.r1) = Hex.from_xy(0, h)
        (self.q1, _      ) = Hex.from_xy(w, 0)
        self.valid = self.zeros(np.uint8)
        for r in range(self.r1):
            for q in range(self.q0, self.q1):
                (x,y) = Hex(q, r).to_plane()
                if (0 <= x < w) and (0 <= y < h):
                    self.valid[q, r] = 1

    def zeros(self, type):
        return np.zeros([self.q1 - self.q0, self.r1], type)

    def show(self):
        for r in range(self.r1):
            for q in range(self.q0, self.q1):
                val = self.valid[q,r]
                print(f"{val:2x} ", end = '')
            print()
    
    def valids(self):
        for r in range(self.r1):
            for q in range(self.q0, self.q1):
                if self.valid[q, r]:
                    yield Hex(q, r)

def shift_array(arr, shift_x, shift_y):
    shifted_arr = np.zeros_like(arr)
    rows, cols = arr.shape

    if shift_x >= 0:
        x_src_start = 0
        x_src_end = rows - shift_x
        x_dst_start = shift_x
        x_dst_end = rows
    else:
        x_src_start = -shift_x
        x_src_end = rows
        x_dst_start = 0
        x_dst_end = rows + shift_x

    if shift_y >= 0:
        y_src_start = 0
        y_src_end = cols - shift_y
        y_dst_start = shift_y
        y_dst_end = cols
    else:
        y_src_start = -shift_y
        y_src_end = cols
        y_dst_start = 0
        y_dst_end = cols + shift_y

    shifted_arr[x_dst_start:x_dst_end, y_dst_start:y_dst_end] = \
        arr[x_src_start:x_src_end, y_src_start:y_src_end]

    return shifted_arr

class HexBoard(cu.Board):
    
    def hex_setup(self):
        (hd, _) = (Hex(1, 0).to_plane())    # hd is the center-center distance
        self.hr = hd / 2                         # hr is the hex radius

        self.gr = ByteGrid(30, 30)
        self.blocked = {layer: self.layer_blocks(layer) for layer in ('GTL', 'GBL')}
        self.routes = []

    def layer_blocks(self, nm):
        layer_poly = sg.MultiPolygon([p for (nm, p) in self.layers[nm].polys]).buffer(0)
        blocked = self.gr.zeros(np.uint8) | (self.gr.valid == 0)
        vv = list(self.gr.valids())
        hexes = [sg.Point(h.to_plane()).buffer(self.hr) for h in vv]
        s = STRtree(hexes)
        result = s.query_nearest(layer_poly)
        for i in result:
            h = vv[i]
            blocked[h.q, h.r] = 1
        return blocked

    def hex_route(self, a, b):
        layer = a.layer
        assert b.layer == a.layer
        a = Hex.from_xy(*a.xy)
        b = Hex.from_xy(*b.xy)

        wavefront = set([tuple(a)])
        dirs = [Hex(dq,dr) for (dq, dr) in axial_direction_vectors]

        valid = {(h.q, h.r) for h in self.gr.valids()}
        blocked = self.blocked[layer].copy()
        blocked[b.q, b.r] = 0
        distance = self.gr.zeros(np.uint8)

        i = 1
        while tuple(b) not in wavefront:
            wavefront2 = set()
            for p in wavefront:
                h = Hex(*p)
                for d in dirs:
                    n = h + d
                    if tuple(n) in valid and not blocked[n.q, n.r]:
                        wavefront2.add(tuple(n))
                        blocked[n.q, n.r] = 1
                        distance[n.q, n.r] = i
            assert wavefront2 != wavefront, f"Signal failed to route"
            wavefront = wavefront2
            # print(f"{i=} {wavefront=}")

            i += 1
        
        route = [b]
        p = b
        while distance[p.q, p.r] != 1:
            n = distance[p.q, p.r]
            assert n != 0
            for d in dirs:
                if distance[p.q + d.q, p.r + d.r] == (n - 1):
                    p = p + d
                    route.append(p)
                    self.blocked[layer][p.q, p.r] = 1
                    break
        route.append(a)
        self.routes.append((layer, route))

    def hex_render(self):
        (hd, _) = (Hex(1, 0).to_plane())    # hd is the center-center distance
        hr = hd / 2                         # hr is the hex radius

        ppmm = 25   # pixels per mm
        im = Image.new("RGB", (30 * ppmm, 30 * ppmm), 'black')
        dr = ImageDraw.Draw(im)
        def xf(xy):
            (x, y) = xy
            return (x * ppmm, (30  - y) * ppmm)

        for (nm, p) in self.layers['GTL'].polys:
            pts = [xf(p) for p in p.exterior.coords]
            dr.polygon(pts, fill = (60, 60, 160))

        for h in self.gr.valids():
            if not self.blocked['GTL'][h.q, h.r]:
                dr.circle(xf(h.to_plane()), outline = (110, 110, 110), radius = hd * ppmm / 2)

        if 0:
            for color,(layer, r) in zip(twenty_rgb, self.routes):
                for e in r:
                    dr.circle(xf(e.to_plane()), fill = color, radius = hd * ppmm / 2)

        im.save("out.png")

def td2e():
    w = .4/3   # .127 is JLCPCB minimum
    w = 0.127
    brd = HexBoard(
        (30, 30),
        trace = w,
        space = .4 - w,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(5))

    brd.outline()

    o = 1.5
    for x in (o, 30 - o):
        for y in (o, 30 - o):
            brd.hole((x, y), 1, 1.5)

    for xy in ((2, 9), (30 - 2, 9)):
        dc = brd.DC(xy)
        dc.rect(1, 8)
        slot = dc.poly().buffer(0.5)
        brd.keepouts.append(slot.buffer(.2))
        brd.layers['GML'].route(slot)


    origin =  Hex.from_xy(21, 20)
    # hexgrid(brd, origin)
    xy = origin.to_plane()
    dc = brd.DC(xy)

    if 1:
        u1 = HexRP2040(dc.left(60))
        u1.hex_escape()

    if 0:
        nick = {
            "QSPI_SD3"  : "IO3",
            "QSPI_SCLK" : "CLK",
            "QSPI_SD0"  : "IO0",
            "QSPI_SD2"  : "IO2",
            "QSPI_SD1"  : "IO1",
            "QSPI_SS_N" : "CS",
            "USB_DP"    : "D+",
            "USB_DM"    : "D-",
            "XIN"       : "XIN",
            "GPIO14"    : "SDL",
            "GPIO15"    : "SDA",
            "GPIO11"    : "RES",
            "GPIO10"    : "DC",
            "GPIO12"    : "DTR",
            "GPIO9"     : "RX",
            "GPIO8"     : "TX",
            "GPIO0"     : "PWM0",
            "GPIO1"     : "PWM1",
            "GPIO13"    : "CTS",
        }
        for nm in nick:
            dc = u1.s(nm).copy()
            dc.dir = 0
            dc.text(nick[nm], scale = 0.2)

    if 1:
        u2 = HexW25Q128(brd.DC(Hex.from_xy(9, 17.5).to_plane()).right(180))
        u2.hex_escape()

    j1 = USB(brd.DC((15, 28.5)).right(180))
    j1.hex_escape()

    if 0:
        j2 = dip.SIL(brd.DC((1, 18)), "2")
        j2.pads[0].setname("GND").w("/ f 1.2").wire()
        wire_ongrid(j2.pads[1].w("f 1"))

    j3 = dip.SIL(brd.DC((23.5, 28)).right(90), "3")
    names = ('SWCLK', '0', 'SWD')
    for (p, nm) in zip(j3.pads, names):
        p.setname(nm)
        p.copy().w("l 90 f 1.6").ctext(nm)
    wire_ongrid(j3.pads[0].w("l 90 f .7"))
    j3.pads[1].setname("GND").w("/ f 1.2").wire()
    wire_ongrid(j3.pads[2].w("l 90 f .7"))

    u3 = SOT23_LDO(brd.DC((7, 27.5)).right(180).left(90))
    u3.hex_escape()

    if 1:
        x1 = ST7789_12(brd.DC((11, 5)).setlayer('GBL'))
        x1.hex_escape()

    if 1:
        # GND is on *right*, viewed from this side
        x2 = SMT6(brd.DC((15, 10)))
        x2.hex_escape()

    def cap(p, val = '10nF'):
        cn = cu.C0402_nolabel(p, val)
        cn.pads[0].setname("GND").w("o f .5 / f .6").wire()
        cn.pads[1].setname("VCC").w("o f .3").wire()
    if 1:
        cap(brd.DC((9, 14)))
        cap(brd.DC((23, 25.5)).right(180))
        cap(brd.DC((25, 24.0)).right(180))
        cap(brd.DC((25, 11)).left(90))
        cap(brd.DC((15, 16.5)).left(60))

        cap(brd.DC((6, 23.6)).left(90), '1uF')
        p = brd.DC((8, 23.6)).left(90)
        cn = cu.C0402_nolabel(p, '1uF')
        cn.pads[0].setname("GND").w("o f .5 / f .6").wire()
        wire_ongrid(cn.pads[1].w("o f .3"))

    if 1:
        y1 = Osc_12MHz(brd.DC((27.5, 16)).right(180))
        y1.escape()

    if 1:
        # ST7789_12 backlight power
        r1 = cu.R0402(brd.DC((5, 3)).left(90))
        r2 = cu.R0402(brd.DC((5, 8)).left(90))

        r1.pads[1].setname("VCC").w("o f 1").wire()
        wire_ongrid(r1.pads[0].w("o / f .4"))
        wire_ongrid(r2.pads[0].w("o / f .4"))
        wire_ongrid(r2.pads[1].w("o f .4"))

        PWM = u1.s("GPIO0")
        u1.s("GPIO1").hex("<< f").wire()

    if 1:
        h = Hex.from_xy(12, 23.5)
        r3 = cu.R0402(brd.DC(h.to_plane()), "270")
        h += Hex(0, -3)
        r4 = cu.R0402(brd.DC(h.to_plane()), "270")
        for p in r3.pads + r4.pads:
            wire_ongrid(p.w("o f 0"))

    # Move these for VCC fill clearance
    u1.s("USB_DM").hex("6f").wire()
    u1.s("USB_DP").hex("7f").wire()

    SDL = u1.s("GPIO14")
    SDA = u1.s("GPIO15")
    RES = u1.s("GPIO11")
    DC  = u1.s("GPIO10")
    SDL.hex("3 f / f").wire()
    SDA.hex("1f l / r").wire()
    DC .hex("f / f").wire()
    RES.hex("3l / < f").wire()

    u1.s("GPIO8").hex("3f / f").wire()
    x2.s("TX").hex("3f / f").wire()

    t0 = time.monotonic()
    brd.hex_setup()
    t1 = time.monotonic()
    print("Starting route")

    brd.hex_route(j1.s("5V"), u3.s("5V"))
    brd.hex_route(cn.pads[1], u3.s("5V"))

    if 1:
        brd.hex_route(u2.s("CS"), u1.s("QSPI_SS_N"))
        brd.hex_route(u2.s("IO1"), u1.s("QSPI_SD1"))
        brd.hex_route(u2.s("IO2"), u1.s("QSPI_SD2"))
        brd.hex_route(u2.s("IO0"), u1.s("QSPI_SD0"))
        brd.hex_route(u2.s("CLK"), u1.s("QSPI_SCLK"))
        brd.hex_route(u2.s("IO3"), u1.s("QSPI_SD3"))
    if 0:
        brd.hex_route(j2.pads[1], u2.s("CS"))

    brd.hex_route(j1.s("D-"), r3.pads[0])
    brd.hex_route(j1.s("D+"), r4.pads[0])
    brd.hex_route(u1.s("USB_DM"), r3.pads[1])
    brd.hex_route(u1.s("USB_DP"), r4.pads[1])

    brd.hex_route(SDL, x1.s("SCL"))
    brd.hex_route(SDA, x1.s("SDA"))
    brd.hex_route(RES, x1.s("RESET"))
    brd.hex_route(DC,  x1.s("D/C"))
    brd.hex_route(r1.pads[0], x1.s("LEDA"))
    brd.hex_route(r1.pads[0], r2.pads[0])


    brd.hex_route(u1.s("GPIO8"), x2.s("TX"))
    brd.hex_route(u1.s("GPIO9"), x2.s("RX"))
    brd.hex_route(u1.s("GPIO13"), x2.s("CTS"))
    brd.hex_route(u1.s("GPIO12"), x2.s("DTR"))

    brd.hex_route(u1.s("XIN"), y1.s("CLK"))

    brd.hex_route(u1.s("SWD"), j3.s("SWD"))
    brd.hex_route(u1.s("SWCLK"), j3.s("SWCLK"))

    brd.hex_route(PWM, r2.pads[1])

    t2 = time.monotonic()
    print(f"Hex setup:   {t1-t0:.3f} s")
    print(f"Hex route:   {t2-t1:.3f} s")

    brd.hex_render()

    for (layer, r) in brd.routes:
        d = brd.DC(r[0].to_plane()).setlayer(layer)
        for p in r[1:]:
            d.path.append(p.to_plane())
        d.wire()

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("td2e2")
    print("Saved")

if __name__ == "__main__":
    td2e()
