import sys
import json
import math
import time

import shapely.geometry as sg

import cuflow as cu
import svgout
import dip
import sot
import eagle
from dazzler import Dazzler
from collections import defaultdict
from rp2040 import RP2040

from hex import Hex, axial_direction_vectors
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

class HexW25Q128(cu.SOIC8):
    source = {'LCSC': 'C131025'}
    mfr = 'W25Q16JVSSIQ'
    footprint = "SOIC-8-208mil"

    def pnp_jlc(self):
        return self.center.copy().right(90)

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

    def hex_escape(self):
        names = ('GND', 'CTS', 'VCC', 'TX', 'RX', 'DTR')[::-1]
        for (p, nm) in zip(self.pads, names):
            p.setname(nm)
            p.copy().w("r 180 f 2.6").ctext(nm, scale = 1.1)
            if nm == "GND":
                p.copy().w("o f 1 / f 1").wire()
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
    mfr = "TFOM12M4RHKCNT2T"
    footprint = "SMD3225-4P"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def escape(self):
        self.s("GND").w("l 90 f 1.5 / f 1").wire()
        self.s("VDD").setname("VCC")
        self.s("VCC").w("o f 0.5").wire()
        wire_ongrid(self.s("CLK").w("o"))

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

    o = 2
    for x in (o, 30 - o):
        for y in (o, 30 - o):
            brd.hole((x, y), 2, 2.5, stencil_alignment = True)

    if 0:
        for xy in ((2, 9), (30 - 2, 9)):
            dc = brd.DC(xy)
            dc.rect(1, 8)
            slot = dc.poly().buffer(0.5)
            brd.keepouts.append(slot.buffer(.2))
            brd.layers['GML'].route(slot)

    origin =  Hex.from_xy(21, 20)
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

    j3 = dip.SIL(brd.DC((28, 19.5)).right(180), "3")
    j3.inBOM = False
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
        
        pinxy = (6.27, 11.15)       # Careful measurement of center of L pin
        lcdsz = (26.16, 29.28)      # Module size
        x = (30 - lcdsz[0]) / 2 + pinxy[0]
        y = (30 - lcdsz[1]) / 2 + pinxy[1]
        x1 = ST7789_12(brd.DC((x, y)).right(0).setlayer('GBL'))
        x1.hex_escape()
        p = brd.DC((15, 15)).setlayer("GBO")
        p.copy().rect(*lcdsz).wire()
        p.goxy(lcdsz[0] / 2, -lcdsz[1] / 2).mark()
        h0 = p.copy().goxy(-(10.3 + 1), 9.13)
        brd.layers['GBO'].add(sg.Point(h0.xy).buffer(0.5))
        h0.goxy(-10, 0)
        brd.layers['GBO'].add(sg.Point(h0.xy).buffer(0.5))

    if 1:
        # GND is on *right*, viewed from this side
        x2 = SMT6(brd.DC((15, 10)))
        x2.hex_escape()
        x2.inBOM = False

    def ucap(p, val = '100nF'):
        cn = cu.C0402_nolabel(p, val)
        cn.pads[0].setname("GND").w("o f .5 / f .6").wire()
        return cn
    def cap(p, val = '100nF'):
        cn = ucap(p, val)
        cn.pads[1].setname("VCC").w("o f .3").wire()
    def hcap(p, val = '100nF'):
        cn = ucap(p, val)
        wire_ongrid(cn.pads[1].w("o f .2"))
        return cn
    if 1:
        cap(brd.DC((9, 14)))
        cap(brd.DC((26.5, 25.6)).right(180))
        cap(brd.DC((26.5, 24.1)).right(180))
        cap(brd.DC((25, 11)).left(90))
        cap(brd.DC((15, 16.5)).left(60))

        cap(brd.DC((6, 24.5)).left(0), '1uF')
        cn = hcap(brd.DC((6, 23.0)), '1uF')

        ci0 = hcap(brd.DC((22, 28)).left(180), '1uF')
        ci = hcap(brd.DC((22, 26.5)).left(180), '1uF')
        u1.s("VREG_VOUT").hex("r 5 f").wire()

    if 1:
        y1 = Osc_12MHz(brd.DC((27.5, 12)).right(180))
        y1.escape()

    if 1:
        # ST7789_12 backlight power
        r1 = cu.R0402(brd.DC((5, 3)).left(90), "7.5")

        r1.pads[1].setname("VCC").w("o f 1").wire()
        wire_ongrid(r1.pads[0].w("o / f .4"))

    if 1:
        h = Hex.from_xy(12, 23.5)
        r3 = cu.R0402(brd.DC(h.to_plane()), "270")
        h += Hex(0, -3)
        r4 = cu.R0402(brd.DC(h.to_plane()), "270")
        for p in r3.pads + r4.pads:
            wire_ongrid(p.w("o f 0"))

    if 1:
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
        def note(p, nm):
            return
            dc = p.copy()
            dc.dir = 0
            dc.text(nm, scale = 0.2)
        note(SDL, "SDL")
        note(SDA, "SDA")
        note(RES, "RES")
        note(DC, "DC")

        u1.s("GPIO8").hex("3f / f").wire()
        x2.s("TX").hex("3f r f l 4f / f").wire()

        t0 = time.monotonic()
        brd.hex_setup()
        t1 = time.monotonic()
        print("Starting route")

        brd.hex_route(j1.s("5V"), u3.s("5V"))
        brd.hex_route(cn.pads[1], u3.s("5V"))
        brd.hex_route(ci0.pads[1], ci.pads[1])
        brd.hex_route(ci.pads[1], u1.s("VREG_VOUT"))

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

        for nm in "SCL SDA RESET D/C".split():
            note(x1.s(nm), nm)

        if 1:
            brd.hex_route(SDL, x1.s("SCL"))
            brd.hex_route(SDA, x1.s("SDA"))
            brd.hex_route(DC,  x1.s("D/C"))
            brd.hex_route(RES, x1.s("RESET"))
        if 1:
            brd.hex_route(r1.pads[0], x1.s("LEDA"))

        note(u1.s("GPIO8"), "TX")

        if 1:
            brd.hex_route(u1.s("GPIO8"), x2.s("TX"))
            brd.hex_route(u1.s("GPIO9"), x2.s("RX"))
            brd.hex_route(u1.s("GPIO13"), x2.s("CTS"))
            brd.hex_route(u1.s("GPIO12"), x2.s("DTR"))

        brd.hex_route(u1.s("XIN"), y1.s("CLK"))

        brd.hex_route(u1.s("SWD"), j3.s("SWD"))
        brd.hex_route(u1.s("SWCLK"), j3.s("SWCLK"))

        # Hack, rescue a ground island
        x2.s("GND").w("l 180 f 0.5 r 90 f 1.2 / f 1").wire()

        t2 = time.monotonic()
        print(f"Hex setup:   {t1-t0:.3f} s")
        print(f"Hex route:   {t2-t1:.3f} s")

        brd.hex_render()
        brd.wire_routes()

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")


    brd.save("td2e2")
    print("Saved")

if __name__ == "__main__":
    td2e()
