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
from dazzler import Dazzler
from collections import defaultdict
from rp2040 import RP2040

import shapely.geometry as sg

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
        river_ongrid(cu.River(brd, banks[3][:2]).w("f 0.5 l 30"))
        river_ongrid(cu.River(brd, banks[3][-6:]).left(30))
        for nm in ("XIN", ):
            wire_ongrid(self.s(nm))
        self.pads[0].w("/").thermal(1).wire()

class HexW25Q128(cu.USON8):
    source = {'LCSC': 'C179171'}
    mfr = 'W25Q64JVSSIQ'
    def hex_escape(self):
        [c.setname(nm) for (c, nm) in zip(self.pads, "CS IO1 IO2 GND IO0 CLK IO3 VCC".split())]

        bootsel = self.s("CS").copy().w("i l 90 f 3 r 90").wire()

        for p in self.pads:
            if p.name == "GND":
                p.w("i f 1").wire().copy().w("/ f 1").wire()
            elif p.name == "VCC":
                p.w("o f 1").wire()
            else:
                p.copy().w("o f 0.5").ctext(p.name, scale = 0.4)
                p.w("o f .1")
                wire_ongrid(p)

        conn = dip.SIL(bootsel.copy().goxy(0, -1.8), "2")
        conn.pads[1].setname("GND").w("/ f 2").wire()

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
        self.s("GND").w("f 2 / f 1").wire()
        for nm in ('D-', 'D+'):
            p = self.s(nm)
            wire_ongrid(p.w("f 1"))
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
                p.w("i f 1").wire()
            if nm == "VCC":
                p.w("i f 1 / f 1").wire()

class SMT6(cu.Part):
    family = "J"
    def place(self, dc):
        self.chamfered(dc.copy().forward(-8), 13, 8, idoffset = (-0.5, -2))
        dc.w(f"l 90 f {cu.inches(.25)} r 180")
        self.train(dc, 6, lambda: self.rpad(dc, 1.2, 3), 2.54)

    def hex_escape(self):
        names = ('GND', 'CTS', 'VCC', 'TX', 'RX', 'DTR')
        for (p, nm) in zip(self.pads, names):
            p.setname(nm)
            p.copy().w("f 2.6").ctext(nm)
            if nm == "GND":
                p.w("o f 1 / f 1").wire()
            elif nm == "VCC":
                p.w("o f 1").wire()
            elif 0:
                p.text(nm, scale = 0.2)

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

def td2e():
    w = .4/3   # .127 is JLCPCB minimum
    w = 0.127
    brd = cu.Board(
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

    origin =  Hex.from_xy(21, 20)
    # hexgrid(brd, origin)
    xy = origin.to_plane()
    dc = brd.DC(xy)

    if 1:
        u1 = HexRP2040(dc.left(60))
        u1.hex_escape()

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
        u2 = HexW25Q128(brd.DC(Hex.from_xy(10, 20.8).to_plane()))
        u2.hex_escape()

        u2.s("IO3").hex("r 4f r 2f r 11f r 4f l").wire()
        u2.s("CLK").hex("r 2f r f r 10f r 4f l").wire()
        u2.s("IO0").hex("3r 9f r 4f l").wire()
        u2.s("IO2").hex("rflf").wire()
        u2.s("IO1").hex("rlf").wire()
        u2.s("CS") .hex("3f").wire()

    j1 = USB(brd.DC((15, 28.5)).right(180))
    j1.hex_escape()
    j1.s("D+").hex("3f").wire()
    j1.s("D-").hex("rlf").wire()
    j1.s("5V").hex("ll 9f l 2f r").wire()

    u3 = SOT23_LDO(brd.DC((5, 26)).right(180).left(90))
    u3.hex_escape()

    if 1:
        x1 = ST7789_12(brd.DC((11, 5)).setlayer('GBL'))
        x1.hex_escape()

    if 1:
        # GND is on *right*, viewed from this side
        x2 = SMT6(brd.DC((15, 12)))
        x2.hex_escape()

    if 1:
        y1 = Osc_12MHz(brd.DC((27.5, 17)))
        y1.escape()

    def cap(p):
        cn = cu.C0402_nolabel(p, '10nF')
        cn.pads[0].setname("GND").w("o f .5 / f .6").wire()
        cn.pads[1].setname("VCC").w("o f .3").wire()
    cap(brd.DC((21, 27)).right(90))
    cap(brd.DC((23, 27)).right(90))
    cap(brd.DC((27, 22)).right(90))
    cap(brd.DC((10, 24.7)))
    cap(brd.DC((8, 18)).right(180))
    cap(brd.DC((14, 18.5)))

    if 1:
        # Pico to flash
        for (a, b) in [
            ("QSPI_SD3"  , "IO3"),
            ("QSPI_SCLK" , "CLK"),
            ("QSPI_SD0"  , "IO0"),
            ("QSPI_SD2"  , "IO2"),
            ("QSPI_SD1"  , "IO1"),
            ("QSPI_SS_N" , "CS")
            ]:
            u1.s(a).goto(u2.s(b)).wire()

        j1.s("5V").goto(u3.s("5V")).wire()

    if 1:
        # Pico USB
        u1.s("USB_DP")
        d = 8
        j1.s("D-").hex(f"lf").wire()
        j1.s("D+").hex(f"lff").wire()

    if 1:
        # Pico to ST7789_12
        SDL = u1.s("GPIO14")
        SDA = u1.s("GPIO15")
        RES = u1.s("GPIO11")
        DC  = u1.s("GPIO10")

        SDA.hex("ll / 2r").w("r 30 f 13") .goto(x1.s("SDA"), False).wire()
        SDL.hex("10 f /").w("r 30 f 10")  .goto(x1.s("SCL"), False).wire()
        RES.hex("ll / rr 2f r ")          .goto(x1.s("RESET"), True).wire()
        DC .hex("2f / r").wire()          .goto(x1.s("D/C"), True).wire()

        if 0:
            for nm in "SDA SCL D/C RESET".split():
                x1.s(nm).copy().mark().forward(1).text(nm, scale = 0.2)

        # ST7789_12 backlight power
        r = cu.R0402(brd.DC((7, 3)).left(90))

        leda = x1.s("LEDA")
        leda.w("o f 1 r 90 f 3 / f 1").wire()
        leda.copy().goto(r.pads[0]).wire()
        r.pads[1].setname("VCC").w("o f 1").wire()

        r = cu.R0402(brd.DC((7, 8)).left(90))
        u1.s("GPIO1").hex("r").wire()
        PWM = u1.s("GPIO0")
        PWM.hex("f r l 3f r 18f").w("r 0").goto(r.pads[1]).wire()
        leda.copy().goto(r.pads[0]).wire()

    if 1:
        # Pico to SMT6

        DTR = u1.s("GPIO12")
        RX  = u1.s("GPIO9")
        TX  = u1.s("GPIO8")
        CTS = u1.s("GPIO13")

        TX.hex("3f").goto(x2.s("TX"), True).wire()
        RX.hex("").goto(x2.s("RX")).wire()
        CTS.hex("rl 4f r 7f <").goto(x2.s("CTS"), True).wire()
        DTR.hex("rl <<").goto(x2.s("DTR")).wire()

    if 1:
        # Pico to Osc y1
        u1.s("XIN").hex("ff l ").goto(y1.s("CLK"), True).wire()

    if 0:
        p0 = brd.DC(Hex(0, 0).to_plane())
        p1 = brd.DC(Hex(0, 100).to_plane())
        p0.mark()
        p1.mark()
        print(p0.distance(p1))

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("td2e")

if __name__ == "__main__":
    td2e()
