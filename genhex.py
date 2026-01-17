import sys
import json
import math
import time
import pickle

import shapely.geometry as sg
from PIL import Image

import cuflow as cu
import svgout
import dip
import sot
import eagle
from dazzler import Dazzler
from collections import defaultdict
from rp2040 import RP2040

import hex
from hexboard import HexBoard, river_ongrid, wire_ongrid

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
"GPIO13",   # Module_Serial.RTS

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
"VREG_VOUT",
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

class HexRP2040(RP2040):
    def hex_escape(self):
        brd = self.board

        banks = self.escape(used_pins)

        river_ongrid(cu.River(brd, banks[0][0:2]).w("f .5"))
        river_ongrid(cu.River(brd, banks[0][-4:-2]).w("f 0.8 r 60"))
        river_ongrid(cu.River(brd, banks[0][-2:]).w(""))
        river_ongrid(cu.River(brd, banks[1][:4 ]).right(30))
        river_ongrid(cu.River(brd, banks[1][5:7]).w("f 0.52 l 30")).hex("").wire()
        river_ongrid(cu.River(brd, banks[3][:1]).w("f 0.5 r 30"))
        river_ongrid(cu.River(brd, banks[3][1:3]).w("f 0.4 l 30"))
        river_ongrid(cu.River(brd, banks[3][-6:]).left(30))
        for nm in ("XIN", ):
            wire_ongrid(self.s(nm))
        self.pads[0].w("/").thermal(1).wire()

class W25Q128(cu.SOIC8):
    source = {'LCSC': 'C131025'}
    mfr = 'W25Q16JVSSIQ'
    footprint = "SOIC-8-208mil"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def setnames(self):
        [c.setname(nm) for (c, nm) in zip(self.pads, "CS IO1 IO2 GND IO0 CLK IO3 VCC".split())]


class USB(eagle.LibraryPart):
    libraryfile = "10118194-0001LF.lbr"
    partname = "AMPHENOL_10118194-0001LF"
    mfr = "AMPHENOL_10118194-0001LF"
    footprint = "SMD"
    source = {"LCSC": "C132563"}
    family = "J"

    def pnp_jlc(self):
        return self.center.copy().forward(1.3)

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
    source = {'LCSC': 'C176954'}
    mfr = "AP2127N-3.3TRG1"
    footprint = "SOT-23"
    family = "U"

    def pnp_jlc(self):
        return self.center.copy().right(90)

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

class SOT23_5(cu.Part):
    family = "U"
    footprint = "SOT-23-5"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def place(self, dc):
        self.chamfered(dc, 1.5, 2.9)

        dc.push()
        dc.goxy(-2.62 / 2, 0.95).right(180)
        self.train(dc, 3, lambda: self.rpad(dc, 0.62, 1.22), 0.95)
        dc.pop()

        dc.push()
        dc.goxy(2.62 / 2, -0.95)
        self.train(dc, 2, lambda: self.rpad(dc, 0.62, 1.22), 2 * 0.95)
        dc.pop()

class LDO_23_5(SOT23_5):
    source = {'LCSC': 'C81233'}
    mfr = "AP2127N-3.3TRG1"

    def hex_hookup(self, names):
        for (p,nm) in zip(self.pads, names):
            p.setname(nm) 
            if nm == "GND":
                p.w("i f 0.7 /").thermal(1)
            elif nm == "VCC":
                # p.w("o f 0.7")
                p.thermal(1)
            p.wire()
        self.s("5V").w("o f 0.1")
        self.s("CE").w("o f .4").goto(self.s("5V")).wire()
        wire_ongrid(self.s("5V"))

    def hex_escape(self):
        self.hex_hookup(('5V', 'GND', 'CE', '', 'VCC'))

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
    mfr = "LH133T-IG01"
    inBOM = False
    def place(self, dc):
        dc.right(90)
        self.train(dc, 12, lambda: self.rpad(dc, .35, 2), 0.7)

    def hex_escape(self):
        for (p, nm) in zip(self.pads, "GND  GND LEDA  VCC GND GND D/C GND SCL SDA RESET GND".split()):
            p.setname(nm)
            if nm == "GND":
                p.w("o f 0.5").wire()
            elif nm == "VCC":
                p.w("o f 5 / f 1").wire()
            elif nm == "RESET":
                wire_ongrid(p.w("o f 0.2"))
            else:
                wire_ongrid(p.w("i f 0.2"))

class SMT6(cu.Part):
    family = "J"
    source = {"LCSC": "C5142239"}
    mfr = "X6511FRS-06-C85D30"
    footprint = "SMD"
    def place(self, dc):
        self.chamfered(dc.copy().forward(-8), 13, 8, idoffset = (-0.5, -2))
        dc.w(f"l 90 f {cu.inches(.25)} r 180")
        self.train(dc, 6, lambda: self.rpad(dc, 1.2, 3), 2.54)
        names = ('GND', 'RTS', 'VCC', 'TX', 'RX', 'DTR')[::-1]
        for (p, nm) in zip(self.pads, names):
            p.setname(nm)
            p.copy().w("r 180 f 2.6").ctext(nm, scale = 1.1)
        self.s("GND").w("o -")
        self.s("VCC").w("o -")

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
        [p.setname(nm) for p,nm in zip(self.pads, ["DNC", "GND", "CLK", "VDD"])]

class Osc_12MHz(SMD_3225_4P):
    source = {'LCSC': 'C454611'}
    mfr = "TFOM12M4RHKCNT2T"
    footprint = "SMD3225-4P"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def escape(self):
        self.s("GND").w("l 90 f 1.5 / f 1").wire()
        self.s("VDD").setname("VCC")
        self.s("VCC").w("o f 0.5").wire()
        wire_ongrid(self.s("CLK").w("o"))

class pogo_pads(cu.Part):
    family  = "J"
    def place(self, dc):
        T = 25.4 / 10
        self.r = 1
        self.N = int(self.val)
        dc.forward(((self.N - 1) / 2) * T).left(180)
        self.train(dc, self.N, lambda: self.gh(dc), T)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

    def gh(self, dc, plate = 1.0):
        p = dc.copy()
        self.roundpad(p, 2 * plate * self.r)
        return

        p.n_agon(plate * self.r, 30)
        p.contact(('GTL', ))

        p = dc.copy()
        p.part = self.id
        self.pads.append(p)

class QFN20(cu.Part):
    # EFM8BB2 datasheet, figure 9.2 "QFN20 Land Pattern"
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 3, 3, drawid = False)

        C1 = 3.1
        C3 = 2.5
        X1 = 0.3
        Y1 = 0.9
        Y3 = 1.8

        dc.push()
        dc.rect(Y3, Y3)
        self.pad(dc)
        dc.pop()

        for i in range(4):
            dc.push()
            dc.goxy(-C3 / 2, C3 / 2).left(90)
            dc.rect(.3, .3)
            self.pad(dc)
            dc.pop()

            dc.push()
            dc.goxy(-C1 / 2, (Y3 - 0.3) / 2)
            dc.right(180)
            self.train(dc, 4, lambda: self.rpad(dc, X1, Y1), 0.5)
            dc.pop()

            dc.left(90)

class EFM8BB2(QFN20):
    # C406735
    def setnames(self):
        names = [
            "GND",
            "P0.1",
            "P0.0",
            "GND",
            "VCC",
            "RST",
            "P2.0",
            "P1.6",
            "P1.5",
            "P1.4",
            "P1.3",
            "P1.2",
            "GND",
            "P1.1",
            "P1.0",
            "P0.7",
            "P0.6",
            "P0.5",
            "P0.4",
            "P0.3",
            "P0.2",
        ]
        for (p,nm) in zip(self.pads, names):
            p.setname(nm)

class NeoPixel5050(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc.copy().left(90), 5.0, 5.0, idoffset = (-0.5, .2))

        w = 3.2 + 2.3
        h = 2.1 + 1.1
        for _ in range(2):
            dc.push()
            dc.goxy(h / 2, w / 2).right(180)
            self.train(dc, 2, lambda: self.rpad(dc, 2.3, 1.1), w)
            dc.pop()
            dc.right(180)
        [p.setname(nm) for p,nm in zip(self.pads, ["VCC", "DIN", "GND", "DOUT", ])]

    def escape(self):
        self.s("GND").w("l 45 f 3 /").thermal(1).wire()
        self.s("VCC").thermal(1).wire()

class USBC(cu.Part):
    source = {'LCSC': 'C2927038'}   # Also C2765186 (better datasheet)
    family = "J"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def place(self, dc):
        self.chamfered(dc.copy().forward(7.35 / 2), 8.94, 7.35)

        dc.mark()

        holes = dc.copy().forward(6.28)
        for d in (-1, 1):
            holes.copy().goxy(d * 5.78 / 2, 0).hole(0.65, ko = 0.13)

        p = holes.copy().goxy(0, 1.07)
        a = p.copy().goxy(3.50 / 2, 0)
        self.train(a.left(90), 8, lambda: self.rpad(a, 0.3, 1.1), 0.5)
        a = p.copy().goxy(6.4 / 2, 0)
        self.train(a.left(90), 2, lambda: self.rpad(a, 0.6, 1.1), 0.8)
        a = p.copy().goxy(-4.8 / 2, 0)
        self.train(a.left(90), 2, lambda: self.rpad(a, 0.6, 1.1), 0.8)

        baseline = dc.copy().goxy(0, 2.6)
        baseline.mark()

        for d in (-1, 1):
            p = baseline.copy().goxy(d * 8.65 / 2, 0)
            p.left(90).mark().stadium(0.3, 60, 1.8 - 0.6)
            p = baseline.copy().goxy(d * 8.65 / 2, 4.2)
            p.left(90).stadium(0.3, 60, 2.1 - 0.6)

def pt(b, h):
    b.layers['GTO'].add(sg.Point(h.to_plane()).buffer(.05))

def hexgrid(b, o):
    b.layers['GTO'].polys = []
    def ln(xys):
        b.layers['GBO'].add(sg.LineString(xys).buffer(.01))
    for h in hex.inrect((0, 0), b.size):
        ln(h.hexagon())

class Pico(dip.dip):
    family  = "U"
    width   = 17.78
    N       = 40

    def padfoot(self, p):
        p.stadium(0.8, 60, 1.7)

    def place(self, dc):
        dip.dip.place(self, dc)

        dc.goxy(-dip.T, -(51 / 2 - 1.6)).right(90)
        self.train(dc, 3, self.gh, cu.inches(.1))

        for (i,p) in enumerate(self.pads, 1):
            p.setname(str(i))

        gpins = {3, 8, 13, 18, 23, 28, 33, 38, 42}
        io = set(range(1, 35)) - gpins
        for g in gpins:
            p = self.s(str(g)).copy()
            p.setname("GND").through().thermal(1.3).wire()
        pnames = [
            "GP0",
            "GP1",
            "GND",
            "GP2",
            "GP3",
            "GP4",
            "GP5",
            "GND",
            "GP6",
            "GP7",
            "GP8",
            "GP9",
            "GND",
            "GP10",
            "GP11",
            "GP12",
            "GP13",
            "GND",
            "GP14",
            "GP15",
            "GP16",
            "GP17",
            "GND",
            "GP18",
            "GP19",
            "GP20",
            "GP21",
            "GND",
            "GP22",
            "RUN",
            "GP26",
            "GP27",
            "GND",
            "GP28",
            "ADC_VREF",
            "3V3(OUT)",
            "3V3_EN",
            "GND",
            "VSYS",
            "VBUS",
            "SWCLK",
            "GND",
            "SWDIO",
        ]
        for pad,nm in zip(self.pads, pnames):
            pad.right(90)
            pad.copy().w("f 5").text(nm)
            # p = pad.copy().w("l 45 f 2 r 45 f 5 r 45 f 2").wire()
            # dc.board.hole(p.xy, .8)
            # p.n_agon(0.8, 60)
            # p.contact()
            pad.setname(nm)

class HexPart:
    lockpos = None
    def pads(self):
        return self.part.pads

class Hex_R0402(HexPart):
    nm = "R0402"
    def __init__(self, c):
        self.part = cu.R0402_nolabel(c.right(90))
        self.part.pads[0].name = "1"
        self.part.pads[1].name = "2"

class Hex_EFM8BB2(HexPart):
    nm = "EFM8BB2"
    def __init__(self, c):
        self.part = EFM8BB2(c.copy().right(30))
        self.part.setnames()
        self.part.s("VCC").w("o +")
        c.via('GL2')

        for i,p in enumerate(self.part.pads[1:]):
            if p.name == "GND":
                p.w("i f 1").wire()

    def pads(self):
        return self.part.pads[1:]

class Hex_SIL4(HexPart):
    nm = "SIL4"
    def __init__(self, c):
        self.part = dip.SIL(c.copy().right(90), "4")

class Hex_Pico(HexPart):
    nm = "Pico"
    def __init__(self, c):
        self.part = Pico(c.copy())

class Hex_RP2040(HexPart):
    nm = "RP2040"
    def __init__(self, c):
        self.part = RP2040(c.copy().right(30))
        self.part.setnames()
        for i,p in enumerate(self.part.pads[1:]):
            print(p.name)
            if p.name in ("IOVDD", "VREG_VIN", "USB_VDD", "RUN"):
                p.w("i +")
                p.setname("VCC")
        self.part.s("ADC_AVDD").w("o +").setname("VCC")

class Hex_Osc(HexPart):
    nm = "Osc12MHz"
    def __init__(self, c):
        self.part = Osc_12MHz(c.copy().right(30))
        self.part.s("VDD").setname("VCC")
        self.part.s("VCC").w("i +")
        self.part.s("GND").w("i -")

class Hex_W25Q128(HexPart):
    nm = "W25Q128"
    def __init__(self, c):
        self.part = W25Q128(c.copy().right(30))
        self.part.setnames()
        self.part.s("VCC").w("i +")
        self.part.s("GND").w("i -")

class Hex_USBC(HexPart):
    nm = "USBC"
    def __init__(self, c):
        self.part = USBC(c.copy().right(180))

class Hex_SMT6(HexPart):
    nm = "SMT6"
    def __init__(self, c):
        brd = c.board
        self.lock_to(15, 10, c)
        self.part = SMT6(c.copy())
    def lock_to(self, x, y, c):
        self.lockpos = (x, y)
        h = hex.Hex.from_xy(x, y)
        (xh, yh) = h.to_plane()
        print("corrected", x - xh, y - yh)
        c.goxy(x - xh, y - yh)

def genhex():
    hex.setsize(0.3)
    w = 0.1
    parts = [
        Hex_R0402,
        Hex_SIL4,
        Hex_Pico,
        Hex_EFM8BB2,
        Hex_RP2040,
        Hex_Osc,
        Hex_W25Q128,
        Hex_USBC,
        Hex_SMT6
    ]
    # parts = parts[-1:]

    for fpart in parts:
        brd = HexBoard(
            (37, 54),
            trace = w,
            space = hex.size - w,
            via_hole = 0.15,
            via = 0.25,
            via_space = cu.mil(5),
            silk = cu.mil(5))

        origin =  hex.Hex.from_xy(brd.size[0] / 2, brd.size[1] / 2)
        c = brd.DC(origin.to_plane())
        part = fpart(c)

        allcells = list(hex.inrect((0, 0), brd.size))
        def within(cell, poly):
            return sg.Point(cell.to_plane()).buffer(brd.trace / 2).covered_by(poly)
        def touches(cell, poly):
            return sg.Point(cell.to_plane()).buffer(hex.size / 2).intersects(poly)

        padlist = {}
        for p in part.pads():
            if p.name not in ("VCC", "GND", "DNC"):
                x0,y0,x1,y1 = p.boundary.bounds
                e = hex.size * 2
                cells = list(hex.inrect((x0 - e, y0 - e), (x1 + e, y1 + e)))
                connected = [c - origin for c in cells if within(c, p.boundary)]
                touching = [c - origin for c in cells if touches(c, p.boundary)]
                if connected == []:
                    p.w("o")
                    wire_ongrid(p).wire()
                    connected = [hex.Hex.from_xy(*p.xy) - origin]
                for h in connected:
                    pt(brd, h + origin)
                padlist[p.name] = {
                    'connected' : connected,
                    'touching' : touching
                }

        layers = [l for l in "GTS GTP GTO GTL".split()]

        ob = {l:brd.layers[l].capture(c.xy) for l in layers}
        ob.update({
            'hex.size' : hex.size,
            'lockpos' : part.lockpos,
            'family' : part.part.family,
            'padlist' : padlist,
        })
        with open(f"{part.nm}.pickle", "wb") as f:
            pickle.dump(ob, f)

    # hexgrid(brd, origin)
    brd.save("hexpreview")
    print("Saved")

if __name__ == "__main__":
    genhex()
