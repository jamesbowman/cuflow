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

import hex
from hex import Hex, axial_direction_vectors
from hexboard import HexBoard, river_ongrid, wire_ongrid

DO_ROUTING = 0

used_pins = [
# "SWCLK",    # Module_Serial_Debug.SWCLK
# "GPIO1",    # Module_Serial_Debug.RX
# "GPIO0",    # Module_Serial_Debug.TX
# "SWD",      # Module_Serial_Debug.SWDIO
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
# "GPIO10",
# "GPIO11",
# "GPIO12",
# "GPIO13",
# "GPIO14",
# "GPIO15",
# "TESTEN",
"XIN",
# "XOUT",
# "VCC",
# "DVDD",
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


class USBmicro(eagle.LibraryPart):
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
        names = ('GND', 'RTS', 'VCC', 'TX', 'RX', 'DTR')[::-1]
        for (p, nm) in zip(self.pads, names):
            p.setname(nm)
            p.copy().w("r 180 f 2.6").ctext(nm, scale = 1.1)
            if nm == "GND":
                p.copy().w("o f 1 / f 1").wire()
            elif nm == "VCC":
                p.w("o f 0.5").wire()
            elif nm in ("TX", "RX", "RTS"):
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

def hexgrid(b, o):
    b.layers['GTO'].polys = []
    def ln(xys):
        b.layers['GBO'].add(sg.LineString(xys).buffer(.01))
    for h in hex.inrect((0, 0), b.size):
        ln(h.hexagon())

def spiq_a():
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
        if DO_ROUTING:
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
            "GPIO12"    : "DTR",
            "GPIO9"     : "RX",
            "GPIO8"     : "TX",
            "GPIO0"     : "PWM0",
            "GPIO1"     : "PWM1",
            "GPIO13"    : "RTS",
        }
        for nm in nick:
            dc = u1.s(nm).copy()
            dc.dir = 0
            dc.text(nick[nm], scale = 0.2)

    if 1:
        u2 = HexW25Q128(brd.DC(Hex.from_xy(9, 17.5).to_plane()).right(180))
        if DO_ROUTING:
            u2.hex_escape()

    if 1:
        j1 = USBmicro(brd.DC((15, 28.5)).right(180))
        if DO_ROUTING:
            j1.hex_escape()
        HAVEUSB = 1
    else:
        j1 = USBC(brd.DC((14, 31.0)).right(180))
        HAVEUSB = 0

    if 0:
        j2 = dip.SIL(brd.DC((1, 18)), "2")
        j2.pads[0].setname("GND")
        if DO_ROUTING:
            j2.pads[0].w("/ f 1.2").wire()
            wire_ongrid(j2.pads[1].w("f 1"))

    # u3 = SOT23_LDO(brd.DC((7, 27.5)).right(180).left(90))
    u3 = LDO_23_5(brd.DC((6.5, 27.5)).right(180))
    if DO_ROUTING:
        u3.hex_escape()

    if 1:
        # GND is on *right*, viewed from this side
        x2 = SMT6(brd.DC((15, 10)))
        if DO_ROUTING:
            x2.hex_escape()
        x2.inBOM = False

    def ucap(p, val = '100nF'):
        cn = cu.C0402_nolabel(p, val)
        cn.pads[0].setname("GND")
        if DO_ROUTING:
            cn.pads[0].w("o f .5 / f .6").wire()
        return cn
    def cap(p, val = '100nF'):
        cn = ucap(p, val)
        cn.pads[1].setname("VCC")
        if DO_ROUTING:
            cn.pads[1].w("o f .3").wire()
    def hcap(p, val = '100nF'):
        cn = ucap(p, val)
        if DO_ROUTING:
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
        if DO_ROUTING:
            u1.s("VREG_VOUT").hex("r 5 f").wire()

    if 1:
        y1 = Osc_12MHz(brd.DC((27.5, 12)).right(180))
        if DO_ROUTING:
            y1.escape()

    if 1:
        h = Hex.from_xy(12, 23.5)
        r3 = cu.R0402(brd.DC(h.to_plane()), "270")
        h += Hex(0, -3)
        r4 = cu.R0402(brd.DC(h.to_plane()), "270")
        if DO_ROUTING:
            for p in r3.pads + r4.pads:
                wire_ongrid(p.w("o f 0"))

    if DO_ROUTING:
        # Move these for VCC fill clearance
        u1.s("USB_DM").hex("6f").wire()
        u1.s("USB_DP").hex("7f").wire()

        def note(p, nm):
            return
            dc = p.copy()
            dc.dir = 0
            dc.text(nm, scale = 0.2)

        u1.s("GPIO8").hex("3f / f").wire()
        x2.s("TX").hex("3f r f l 4f / f").wire()

        t0 = time.monotonic()
        brd.hex_setup()
        t1 = time.monotonic()
        print("Starting route")

        if HAVEUSB:
            brd.hex_route(j1.s("5V"), u3.s("5V"))
        brd.hex_route(cn.pads[1], u3.s("5V"))
        brd.hex_route(ci0.pads[1], ci.pads[1])
        if HAVEUSB:
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

        if HAVEUSB:
            brd.hex_route(j1.s("D-"), r3.pads[0])
            brd.hex_route(j1.s("D+"), r4.pads[0])
        if HAVEUSB:
            brd.hex_route(u1.s("USB_DM"), r3.pads[1])
        brd.hex_route(u1.s("USB_DP"), r4.pads[1])

        note(u1.s("GPIO8"), "TX")

        if 1:
            brd.hex_route(u1.s("GPIO8"), x2.s("TX"))
            brd.hex_route(u1.s("GPIO9"), x2.s("RX"))
            brd.hex_route(u1.s("GPIO13"), x2.s("RTS"))
            brd.hex_route(u1.s("GPIO12"), x2.s("DTR"))

        brd.hex_route(u1.s("XIN"), y1.s("CLK"))

        # Hack, rescue a ground island
        x2.s("GND").w("l 180 f 0.5 r 90 f 1.2 / f 1").wire()

        t2 = time.monotonic()
        print(f"Hex setup:   {t1-t0:.3f} s")
        print(f"Hex route:   {t2-t1:.3f} s")

        brd.hex_render()
        brd.wire_routes()

    if DO_ROUTING:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    if 0:
        brd.DC((25.5, 6.4)).ctext("(C) EXCAMERA", scale = 1.1)
        brd.DC((25.5, 5.0)).ctext("LABS 2025", scale = 1.1)

    # hexgrid(brd, origin)

    brd.save("spiq_a")
    print("Saved")

if __name__ == "__main__":
    spiq_a()
