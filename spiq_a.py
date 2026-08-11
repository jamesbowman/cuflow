import sys
import json
import math
import time
from pathlib import Path

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
# Module_Serial_Debug
"SWCLK",
# "GPIO1",    # Module_Serial_Debug.RX
# "GPIO0",    # Module_Serial_Debug.TX
"SWD",

"GPIO0",
"GPIO1",
"GPIO2",
"GPIO3",
"GPIO4",
"GPIO5",
"GPIO6",
"GPIO7",
# "VCC",
"GPIO8",
"GPIO9",
"GPIO10",
"GPIO11",
# "GPIO12",
# "GPIO13",
"GPIO14",
"GPIO15",
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

        by_name = {pad.name: pad for bank in banks for pad in bank}

        def river(names):
            return cu.River(brd, [by_name[name] for name in names])

        river_ongrid(river(tuple(f"GPIO{i}" for i in range(0, 10)))
                     .w("f 0.8 l 60"))
        river_ongrid(river(("GPIO10", "GPIO11")))
        river_ongrid(river(("GPIO14", "GPIO15")).right(30))
        river_ongrid(river(("SWCLK", "SWD")).w("f 0.52 l 30")).wire()
        river_ongrid(river(("VREG_VOUT",)).w("f 0.5 r 30"))
        river_ongrid(river(("USB_DM", "USB_DP")).w("f 0.4 l 30"))
        river_ongrid(river((
            "QSPI_SD3", "QSPI_SCLK", "QSPI_SD0",
            "QSPI_SD2", "QSPI_SD1", "QSPI_SS_N")).left(30))
        for nm in ("XIN", ):
            wire_ongrid(self.s(nm))
        self.pads[0].w("-").wire()

        return

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
                p.w("i -")
            elif p.name == "VCC":
                p.w("i +")
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

        pad_names = (
            "B8", "A5", "B7", "A6", "A7", "B6", "A8", "B5",
            "A1/B12", "A4/B9", "B4/A9", "B1/A12",
        )
        for pad, name in zip(self.pads, pad_names):
            pad.setname(name)
        self.s("A6").mark()

        baseline = dc.copy().goxy(0, 2.6)
        baseline.mark()

        for d in (-1, 1):
            p = baseline.copy().goxy(d * 8.65 / 2, 0)
            p.left(90).mark().stadium(0.3, 60, 1.8 - 0.6)
            p = baseline.copy().goxy(d * 8.65 / 2, 4.2)
            p.left(90).stadium(0.3, 60, 2.1 - 0.6)

    def hex_escape(self):
        power_width = 2 * self.board.trace
        for name in ("A1/B12", "B1/A12"):
            self.s(name).setwidth(power_width).w("o -")

        via_escape = self.board.via_space + self.board.via / 2
        vbus0 = self.s("A4/B9").copy().setwidth(power_width)
        vbus1 = self.s("B4/A9").copy().setwidth(power_width)
        vbus0.w(f"o f {via_escape} /")
        vbus1.w(f"o f {via_escape} /")
        vbus0.left(90).goto(vbus1).wire()

        self.s("A6").copy().w("i f 0.4 r 90").goto(
            self.s("B6"), twist=True).wire()
        self.s("B7").copy().w("o f 0.4 l 90").goto(
            self.s("A7"), twist=True).wire()

        r7_center = self.s("B5").copy().w(
            "o f 2 l 90 f 0.65 l 90").setname(None)
        r6_center = self.board.DC(
            (r7_center.xy[0] + 1.1, r7_center.xy[1]), r7_center.dir)
        r6 = cu.R0402(r6_center, "5K1")
        r7 = cu.R0402(r7_center, "5K1")

        self.s("A5").copy().w("o").goto(
            r6.pads[0], twist=True).wire()
        self.s("B5").copy().w("o").goto(r7.pads[0]).wire()
        for resistor in (r6, r7):
            resistor.pads[1].w("o -")


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


class Module_Serial_Debug(PZ254RS):
    def place(self, dc):
        super().place(dc)
        names = ("GND", "SWDIO", "VCC", "TX", "RX", "SWCLK")
        for pad, name in zip(self.pads, names):
            pad.setname(name)
            pad.copy().forward(4.5).ctext(
                name, scale=0.8, angle=90)

    def hex_escape(self):
        for pad in self.pads:
            route = pad.copy().right(180)
            if pad.name == "GND":
                route.w("o f 0.5 -")
            elif pad.name == "VCC":
                route.w("o f 0.5 +")
            else:
                wire_ongrid(route.w("o f 0.2"))


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

    def hex_escape(self):
        for pad in self.pads:
            if pad.name == "GND":
                pad.w("o f 0.5").wire()
            elif pad.name == "VCC":
                pad.w("o f 5 / f 1").wire()
            elif pad.name == "RESET":
                wire_ongrid(pad.w("o f 0.2"))
            else:
                wire_ongrid(pad.w("i f 0.2"))


class LDO_1117_3V3(cu.SOT223):
    source = {'LCSC': 'C26537'}
    mfr = "ZLDO1117QG33TA"
    drawid = False

    def place(self, dc):
        super().place(dc)
        for p, nm in zip(self.pads, ("VCC", "GND", "VCC", "5V")):
            p.setname(nm)

    def hex_escape(self):
        return self.escape()


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

    def hex_escape(self):
        names = ("5V", "GND", "CE", "", "VCC")
        for p, nm in zip(self.pads, names):
            p.setname(nm)
        self.s("5V").mark()
        self.s("GND").w("i -")
        self.s("VCC").w("i +")
        self.s("CE").w("o f 0.4").goto(self.s("5V")).wire()


class VSSOP10(cu.Part):
    family = "U"
    footprint = "VSSOP-10"
    N = 10

    def place(self, dc):
        self.chamfered(dc, 3, 3)
        pins_per_side = self.N // 2
        pitch = 0.5
        for _ in range(2):
            dc.push()
            dc.forward(pitch * (pins_per_side - 1) / 2)
            dc.left(90)
            dc.forward(4.4 / 2)
            dc.left(90)
            self.train(
                dc, pins_per_side,
                lambda: self.rpad(dc, 0.3, 1.45), pitch)
            dc.pop()
            dc.right(180)


class INA226(VSSOP10):
    mfr = "INA226AIDGSR"

    def place(self, dc):
        super().place(dc)
        names = "A1 A0 Alert SDA SCL VCC GND VBUS IN- IN+".split()
        for pad, name in zip(self.pads, names):
            pad.setname(name)

    def hex_escape(self):
        self.s("A0").goto(self.s("A1")).wire()
        self.s("A1").w("o -")
        self.s("VBUS").goto(self.s("IN-")).wire()
        self.s("GND").w("o -")
        self.s("VCC").w("o r 90 f .5 +")

class R1206(cu.Part):
    family = "R"
    footprint = "1206"
    source = {"LCSC": "C22464903"}

    def place(self, dc):
        for direction in (-90, 90):
            dc.push()
            dc.right(direction)
            dc.forward(3.2 / 2)
            dc.rect(1.6, 1)
            self.pad(dc)
            dc.pop()

        dc.rect(3.2, 1.6)
        dc.silko()
        dc.push()
        dc.right(90)
        dc.forward(2.65)
        self.label(dc)
        dc.pop()


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

    def hex_escape(self):
        self.s("GND").w("o -")
        self.s("VDD").w("o +")
        wire_ongrid(self.s("CLK").w("o"))

def hexgrid(b):
    width, height = b.size
    bounds = sg.box(0, 0, width, height)
    margin_x = 2 * hex.height
    margin_y = 2 * hex.size
    for h in hex.inrect(
            (-margin_x, -margin_y),
            (width + margin_x, height + margin_y)):
        clipped = sg.LineString(h.hexagon()).intersection(bounds)
        lines = clipped.geoms if hasattr(clipped, "geoms") else (clipped,)
        for line in lines:
            if isinstance(line, sg.LineString) and not line.is_empty:
                b.layers["HEX"].add(line)

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
    dc = brd.DC((xy[0] - 14, xy[1]))

    if 1:
        u1 = HexRP2040(dc.left(120))

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
        h = Hex.from_xy(9, 10)
        u2_xy = h.to_plane()
        u2 = HexW25Q128(
            brd.DC((u2_xy[0], u2_xy[1])).right(180).left(120))

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
    serial_debug = Module_Serial_Debug(
        brd.DC((brd.size[0] / 2, brd.size[1] / 2))
        .setlayer("GBL").right(90), 6)

    j2_bottom = j2.center.xy[1] - j2.N * j2.pitch / 2
    j3_top = j3.center.xy[1] + j3.N * j3.pitch / 2
    ldo_y = (j2_bottom + j3_top) / 2
    ldo_1117 = LDO_1117_3V3(
        brd.DC((j2.center.xy[0] + 4, ldo_y)).right(90))
    ldo_ap2127 = LDO_23_5(layout_dc((12.0, 29.8)))
    ldo_5v = ldo_ap2127.pads[0]
    nearest_usb_5v = min(
        (j1.s("A4/B9"), j1.s("B4/A9")), key=ldo_5v.distance)
    ldo_5v.copy().setlayer("GTL").setwidth(
        2 * brd.trace).goto(nearest_usb_5v).wire()

    ina226 = INA226(brd.DC((29.5, 46.0)))

    shunt = R1206(brd.DC((35.0, 46.0)).right(90))
    shunt.pads[0].setname("5V")
    shunt.pads[1].setname("VBUS")

    i2c_pullups = []
    for x, signal in ((16.8, "SDA"), (21.0, "SCL")):
        resistor = cu.R0402(brd.DC((x, 46.0)).right(90), "4K7")
        resistor.pads[0].w("o +").wire()
        resistor.pads[1].setname(signal)
        i2c_pullups.append(resistor)

    i2c_pullups[1].pads[1].goto(ina226.s("SCL")).wire()

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

    if 1:
        usb_body_south = j1.center.xy[1] - 8.94 / 2
        series_resistor_y = usb_body_south - 1.0 - 1.1
        r3 = cu.R0402(
            brd.DC((3.9, series_resistor_y)).right(90), "27")
        r4 = cu.R0402(
            brd.DC((2.8, series_resistor_y)).right(90), "27")
        j1.s("B7").copy().w("i").goto(
            r3.pads[0], twist=True).wire()
        j1.s("A6").copy().w("i").goto(
            r4.pads[0], twist=True).wire()
        if DO_ROUTING:
            for p in r3.pads + r4.pads:
                wire_ongrid(p.w("o f 0"))

    for parts in brd.parts.values():
        for part in parts:
            part.hex_escape()

    if DO_ROUTING:
        # Move these for VCC fill clearance
        u1.s("USB_DM").hex("6f").wire()
        u1.s("USB_DP").hex("7f").wire()

    if 1:
        t0 = time.monotonic()
        brd.hex_setup()
        t1 = time.monotonic()
        print("Starting route")

    if 0:

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
        brd.hex_route(serial_debug.s("SWCLK"), u1.s("SWCLK"))
        brd.hex_route(serial_debug.s("RX"), u1.s("GPIO1"))
        brd.hex_route(serial_debug.s("TX"), u1.s("GPIO0"))
        brd.hex_route(serial_debug.s("SWDIO"), u1.s("SWD"))
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

    if 1:
        brd.hex_render()
        brd.wire_routes()

    pinout_modules = {
        "Module_LCD240x240": lcd,
        "Module_spiq_pwr": ina226,
        "Module_spiq_ios": j3,
    }
    airwires = []
    current_measurement_bus_sources = {}

    pinout_path = Path(__file__).with_name("spiq_a.pinout")
    for line in pinout_path.read_text().splitlines():
        source_name, target_name = line.split()
        module_name, target_pin = target_name.rsplit(".", 1)
        if target_pin == "None":
            continue
        source_pin = "GPIO" + source_name.removeprefix("GP")
        source = u1.s(source_pin)
        target = pinout_modules[module_name].s(target_pin)
        if (module_name == "Module_spiq_pwr" and
                target_pin in ("SDA", "SCL")):
            current_measurement_bus_sources[target_pin] = source
        else:
            airwires.append((source, target))

    qspi_airwires = (
        ("QSPI_SS_N", "CS"),
        ("QSPI_SD1", "IO1"),
        ("QSPI_SD2", "IO2"),
        ("QSPI_SD0", "IO0"),
        ("QSPI_SCLK", "CLK"),
        ("QSPI_SD3", "IO3"),
    )
    for rp2040_pin, flash_pin in qspi_airwires:
        airwires.append((u1.s(rp2040_pin), u2.s(flash_pin)))
    airwires.append((u1.s("XIN"), y1.s("CLK")))

    usb_airwires = (
        (r3.pads[1], u1.s("USB_DM")),
        (r4.pads[1], u1.s("USB_DP")),
    )
    airwires.extend(usb_airwires)

    sda_pullup, scl_pullup = i2c_pullups
    current_measurement_airwires = (
        (ina226.s("IN+"), shunt.s("5V")),
        (ina226.s("IN-"), shunt.s("VBUS")),
        (current_measurement_bus_sources["SDA"],
         ina226.s("SDA"), sda_pullup.s("SDA")),
        (current_measurement_bus_sources["SCL"],
         ina226.s("SCL"), scl_pullup.s("SCL")),
    )
    airwires.extend(current_measurement_airwires)

    airwire_rows = []
    total_airwire_distance = 0.0

    def minimum_spanning_tree(net):
        assert len(net) >= 2
        reached = {0}
        unreached = set(range(1, len(net)))
        tree = []
        while unreached:
            distance, source_index, target_index = min(
                (net[source_index].distance(net[target_index]),
                 source_index, target_index)
                for source_index in reached
                for target_index in unreached
            )
            tree.append((net[source_index], net[target_index], distance))
            reached.add(target_index)
            unreached.remove(target_index)
        return tree

    for net in airwires:
        for source, target, distance in minimum_spanning_tree(net):
            brd.layers["AIR"].add(sg.LineString((source.xy, target.xy)))
            airwire_rows.append((
                f"{source.part}.{source.name}",
                f"{target.part}.{target.name}",
                f"{distance:.3f}" if distance else "",
            ))
            total_airwire_distance += distance

    airwire_headers = ("src", "dest", "distance (mm)")
    airwire_widths = [
        max(len(header), *(len(row[column]) for row in airwire_rows))
        for column, header in enumerate(airwire_headers)
    ]
    print("  ".join(
        header.ljust(airwire_widths[column])
        for column, header in enumerate(airwire_headers)))
    print("  ".join("-" * width for width in airwire_widths))
    for row in airwire_rows:
        print("  ".join(
            value.rjust(airwire_widths[column]) if column == 2 else
            value.ljust(airwire_widths[column])
            for column, value in enumerate(row)))
    print("  ".join("-" * width for width in airwire_widths))
    total_row = ("total", "", f"{total_airwire_distance:.3f}")
    print("  ".join(
        value.rjust(airwire_widths[column]) if column == 2 else
        value.ljust(airwire_widths[column])
        for column, value in enumerate(total_row)))

    brd.outline()
    brd.fill()

    if DO_ROUTING:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    if 0:
        layout_dc((25.5, 6.4)).ctext("(C) EXCAMERA", scale = 1.1)
        layout_dc((25.5, 5.0)).ctext("LABS 2025", scale = 1.1)

    hexgrid(brd)

    missing_hex_escape = [
        part.id
        for parts in brd.parts.values()
        for part in parts
        if not callable(getattr(part, "hex_escape", None))
    ]
    assert not missing_hex_escape, (
        "Parts missing hex_escape(): " + ", ".join(missing_hex_escape))

    brd.save("spiq_a")
    print("Saved")

if __name__ == "__main__":
    spiq_a()
