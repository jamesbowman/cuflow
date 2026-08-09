import sys
import json
import math
import time

import shapely.geometry as sg

import cuflow as cu
import svgout
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


class PZ254RS(cu.Part):
    family = "J"
    footprint = "PZ254RS-11-NP-01"
    pitch = 2.54
    body_width = 2.5
    pad_width = 1.02
    pad_length = 2.3

    def place(self, dc):
        self.N = int(self.val)
        assert 2 <= self.N <= 40
        self.mfr = f"PZ254RS-11-{self.N:02d}P-01"
        self.val = ""

        self.chamfered(dc, self.body_width, self.N * self.pitch)
        pins = dc.copy().forward((self.N - 1) * self.pitch / 2).left(180)

        def pin():
            self.rpad(pins, self.pad_width, self.pad_length)

        self.train(pins, self.N, pin, self.pitch)
        for i, p in enumerate(self.pads, 1):
            p.setname(str(i))


class Module_LCD240x240(cu.Part):
    family = "U"
    mfr = "LH133T-IG01"
    footprint = "LCD240x240"
    width = 30
    height = 37.4
    connector_y = -7.8

    def place(self, dc):
        dc.copy().rect(self.width, self.height).silko()
        for x in (-self.width / 2, self.width / 2):
            for y in (-self.height / 2, self.height / 2):
                dc.copy().goxy(x, y).hole(2.5)

        pins = dc.copy().goxy(7.7 / 2, self.connector_y).left(90)
        self.train(pins, 12, lambda: self.rpad(pins, 0.35, 2), 0.7)
        names = "GND GND LEDA VCC GND GND D/C GND SCL SDA RESET GND".split()
        for p, nm in zip(self.pads, names):
            p.setname(nm)

        bar = dc.copy().goxy(-6, self.connector_y)
        bar.newpath()
        bar.right(90).forward(12).silk()
        self.pads[11].copy().w("f 2").text("12")
        self.pads[0].copy().w("f 2").text("1")


class LDO_1117_3V3(cu.SOT223):
    source = {'LCSC': 'C26537'}
    mfr = "ZLDO1117QG33TA"
    drawid = False

    def place(self, dc):
        super().place(dc)
        for p, nm in zip(self.pads, ("VCC", "GND", "VCC", "5V")):
            p.setname(nm)

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
        (61, 49),
        trace = w,
        space = .4 - w,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(5))

    layout_offset = Hex(-12, 24)
    layout_dx, layout_dy = layout_offset.to_plane()

    def layout_xy(xy):
        x, y = xy
        return (x + layout_dx, y + layout_dy)

    def layout_dc(xy):
        return brd.DC(layout_xy(xy))

    if 0:
        for xy in ((2, 9), (30 - 2, 9)):
            dc = layout_dc(xy)
            dc.rect(1, 8)
            slot = dc.poly().buffer(0.5)
            brd.keepouts.append(slot.buffer(.2))
            brd.layers['GML'].route(slot)

    origin = Hex.from_xy(21, 20) + layout_offset
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
            "GPIO0"     : "PWM0",
            "GPIO1"     : "PWM1",
        }
        for nm in nick:
            dc = u1.s(nm).copy()
            dc.dir = 0
            dc.text(nick[nm], scale = 0.2)

    if 1:
        h = Hex.from_xy(9, 17.5) + layout_offset
        u2 = HexW25Q128(brd.DC(h.to_plane()).right(180))
        if DO_ROUTING:
            u2.hex_escape()

    # Match the legacy SPIDriver's 6.25 mm top-edge offset.
    j1 = USBC(brd.DC((0, brd.size[1] - 6.25)).right(90))
    HAVEUSB = 0

    j2 = PZ254RS(brd.DC((50.0, 38.65)), 6)
    for p, nm in zip(j2.pads, ("GND", "GND", "VCC", "VCC", "5V", "5V")):
        p.setname(nm)
    label_x = j2.center.xy[0] + 7.1
    pair_centers = []
    for pair, label in zip((j2.pads[0:2], j2.pads[2:4], j2.pads[4:6]),
                           ("GND", "3.3 V", "5V")):
        y = sum(p.xy[1] for p in pair) / 2
        pair_centers.append(y)
        brd.DC((label_x, y)).ctext(label, scale = 1.32)
    bar_ys = [pair_centers[0] + j2.pitch]
    bar_ys += [(a + b) / 2 for a, b in zip(pair_centers, pair_centers[1:])]
    bar_ys.append(pair_centers[-1] - j2.pitch)
    bar_width = 0.4
    bar_length = 6.3
    half_line = (bar_length - bar_width) / 2
    for y in bar_ys:
        line = sg.LineString(((label_x - half_line, y),
                              (label_x + half_line, y)))
        brd.layers["GTO"].add(line.buffer(bar_width / 2))

    j2_top = j2.center.xy[1] + j2.N * j2.pitch / 2
    edge_clearance = brd.size[1] - j2_top
    j3_pins = 8
    j3_y = edge_clearance + j3_pins * j2.pitch / 2
    j3 = PZ254RS(brd.DC((j2.center.xy[0], j3_y)), j3_pins)
    j3_names = ["SCK", "MOSI", "MISO", "IO2", "IO3", "CS", "A", "B"]
    for p, nm in zip(j3.pads, j3_names):
        p.setname(nm)
        brd.DC((label_x, p.xy[1])).ctext(nm, scale = 1.32)

    lcd = Module_LCD240x240(brd.DC((brd.size[0] / 2, brd.size[1] / 2)))

    j2_bottom = j2.center.xy[1] - j2.N * j2.pitch / 2
    j3_top = j3.center.xy[1] + j3.N * j3.pitch / 2
    ldo_y = (j2_bottom + j3_top) / 2
    u3 = LDO_1117_3V3(brd.DC((j2.center.xy[0] + 4, ldo_y)).right(90))

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
        cap_xs = iter(range(4, 40, 4))
        def south_cap():
            return brd.DC((next(cap_xs), 2.0))

        cap(south_cap())
        cap(south_cap())
        cap(south_cap())
        cap(south_cap())
        cap(south_cap())

        cap(south_cap(), '1uF')
        cn = hcap(south_cap(), '1uF')

        ci0 = hcap(south_cap(), '1uF')
        ci = hcap(south_cap(), '1uF')
        if DO_ROUTING:
            u1.s("VREG_VOUT").hex("r 5 f").wire()

    if 1:
        y1 = Osc_12MHz(layout_dc((27.5, 12)).right(180))
        if DO_ROUTING:
            y1.escape()

    if 1:
        h = Hex.from_xy(12, 23.5) + layout_offset
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
        if HAVEUSB:
            brd.hex_route(j1.s("D-"), r3.pads[0])
            brd.hex_route(j1.s("D+"), r4.pads[0])
        if HAVEUSB:
            brd.hex_route(u1.s("USB_DM"), r3.pads[1])
        brd.hex_route(u1.s("USB_DP"), r4.pads[1])

        brd.hex_route(u1.s("XIN"), y1.s("CLK"))

        t2 = time.monotonic()
        print(f"Hex setup:   {t1-t0:.3f} s")
        print(f"Hex route:   {t2-t1:.3f} s")

        brd.hex_render()
        brd.wire_routes()

    brd.outline()
    brd.fill()

    if DO_ROUTING:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    if 0:
        layout_dc((25.5, 6.4)).ctext("(C) EXCAMERA", scale = 1.1)
        layout_dc((25.5, 5.0)).ctext("LABS 2025", scale = 1.1)

    # hexgrid(brd, origin)

    brd.save("spiq_a")
    print("Saved")

if __name__ == "__main__":
    spiq_a()
