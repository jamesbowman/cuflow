import sys
import json
import math
import time
from pathlib import Path

import shapely.geometry as sg
from PIL import Image

import cuflow as cu
import htmlout
import svgout
import dip
import sot
from dazzler import Dazzler
from collections import defaultdict
from rp2040 import RP2040
from usb_c import USBC

import hex
from hex import Hex, axial_direction_vectors
from hexboard import HexBoard, wire_ongrid, wire_ongrid2

hex.set_grid_size(0.41)

PREFLIGHT_NAME_ATLAS = {
    "ic_roots_by_lcsc": {
        "C2040": "RP2040",
        "C131025": "W25Q16",
        "C81233": "ME6212",
    },
    "header_pins": {
        "J3": {
            "names": ("DTR", "RX", "TX", "VCC", "RTS", "GND"),
            "external_pad_numbers": (1, 2, 3, 4, 5, 6),
        },
    },
}

# Update only after intentionally reviewing a connectivity change.
PREFLIGHT_NETLIST_HASH = (
    "0db235d53418143e560c255d922c524166c6bb4a10b2db7f5ac05983325f144c")

ROUTING = 0
LCD_ROUTING = 1
SERIAL_ROUTING = ("GPIO12", "GPIO9", "GPIO8", "GPIO13")
FLASH_ROUTING = 1
CLOCK_ROUTING = 1
DEBUG_ROUTING = 1
USB_MCU_ROUTING = 1
USB_CONNECTOR_ROUTING = 1
USB_CC_ROUTING = 1
VREG_ROUTING = 1
BACKLIGHT_ROUTING = 1
POWER_ROUTING = 1
CAPS = 1

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
"SWDIO",
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

def fanout_ongrid(river):
    for trace in river.tt:
        wire_ongrid2(trace)
    return river

class HexRP2040(RP2040):
    def hookup_usb_vdd(self, pad):
        wire_ongrid2(pad.w("o")).via("GL3")

    def hex_escape(self):
        brd = self.board

        banks = self.escape(
            used_pins, four_layer=True,
            usb_vdd_via_on_iovdd=True)

        # fanout_ongrid(cu.River(brd, banks[0][0:2]).w("f .5"))
        # fanout_ongrid(cu.River(brd, banks[0][-4:-2]).w("f 0.8 r 60"))
        # fanout_ongrid(cu.River(brd, banks[0][-2:]).w(""))
        # fanout_ongrid(cu.River(brd, banks[1][:4 ]).right(30))
        # fanout_ongrid(cu.River(brd, banks[3][:1]).w("f 0.5 r 30"))
        # fanout_ongrid(cu.River(brd, banks[3][1:3]).w("f 0.4 l 30"))
        fanout_ongrid(cu.River(brd, banks[3][-6:]).left(30))
        for nm in ("XIN", ):
            wire_ongrid2(self.s(nm))
        self.pads[0].w("-").wire()

        wire_ongrid2(self.s("VREG_VOUT")).wire()

        wire_ongrid2(self.s("SWDIO")).hex("l").wire()
        wire_ongrid2(self.s("SWCLK")).wire()

        # USB
        wire_ongrid2(self.s("USB_DM").w("o")).hex("").wire()
        wire_ongrid2(self.s("USB_DP")).hex("").wire()

        # Serial
        wire_ongrid2(self.s("GPIO8")).hex("f").wire()
        wire_ongrid2(self.s("GPIO9")).hex("3f").wire()
        wire_ongrid2(self.s("GPIO12")).hex("r l r 3f / 3f / 5f").wire()
        wire_ongrid2(self.s("GPIO13")).hex("l r").wire()

        # LCD
        wire_ongrid2(self.s("GPIO10")).hex("f /")
        wire_ongrid2(self.s("GPIO11")).hex("l f /")
        wire_ongrid2(self.s("GPIO14")).hex("l r / f").wire()
        wire_ongrid2(self.s("GPIO15")).hex("l /")

class HexW25Q128(cu.SOIC8b):
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
                p.w("i -")
            elif nm == "VCC":
                p.w("o +")
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
    mfr = "ME6212C33M5G"

    def hex_hookup(self, names):
        for (p,nm) in zip(self.pads, names):
            p.setname(nm) 
            if nm == "GND":
                p.w("i -")
            elif nm == "VCC":
                p.w("i +")
            p.wire()
        power_width = 2 * self.board.trace
        for name in ("5V", "CE"):
            wire_ongrid(
                self.s(name).setwidth(power_width).w("o"))

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
                if p is self.pads[-1]:
                    p.w("i -")
                else:
                    p.w("o f 3.5 -")
            elif nm == "VCC":
                p.w("o f 3.5 +")
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
        names = ('GND', 'RTS', 'VCC', 'TX', 'RX', 'DTR')[::-1]
        for (p, nm) in zip(self.pads, names):
            p.setname(nm)
            p.copy().w("r 180 f 2.6").ctext(nm, scale = 1.1)
            if nm == "GND":
                p.copy().w("o -")
            elif nm == "VCC":
                p.w("o +")

class SMD_3225_4P(cu.Part):
    family = "Y"
    def place(self, dc):
        self.chamfered(dc, 2.8, 3.5, idoffset = (1.4, .2))

        for _ in range(2):
            dc.push()
            dc.goxy(-1.75 / 2, 2.20 / 2).right(180)
            self.train(dc, 2, lambda: self.rpad(dc, 1.3, 1.2), 2.20)
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
        self.s("GND").w("r 90 f 0.6 -")
        self.s("VDD").setname("VCC")
        self.s("VCC").w("r 90 f 0.6 +")

class pogo_pads(dip.PTH):
    family  = "J"
    def place(self, dc):
        T = 25.4 / 10
        self.r = 0.6
        self.N = int(self.val)
        dc.forward(((self.N - 1) / 2) * T).left(180)
        self.train(dc, self.N, lambda: self.gh(dc), T)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

    def gh(self, dc, plate = 1.0):
        p = dc.copy()
        self.roundpad(p, 2 * plate * self.r, paste = False)
        return

        p.n_agon(plate * self.r, 30)
        p.contact(('GTL', ))

        p = dc.copy()
        p.part = self.id
        self.pads.append(p)

def td2f():
    w = 0.1
    brd = HexBoard(
        (30, 30),
        trace = w,
        space = hex.size - w,
        via_hole = 0.3,
        via = 0.4,
        via_space = cu.mil(5),
        silk = cu.mil(5))
    brd.hex_clearance = 0.095

    brd.outline()

    o = 2
    for x in (o, 30 - o):
        for y in (o, 30 - o):
            brd.hole((x, y), 2, 2.5)

    if 0:
        for xy in ((2, 9), (30 - 2, 9)):
            dc = brd.DC(xy)
            dc.rect(1, 8)
            slot = dc.poly().buffer(0.5)
            brd.keepouts.append(slot.buffer(.2))
            brd.layers['GML'].route(slot)

    origin =  Hex.from_xy(21, 20)
    xy = origin.to_plane()
    dc = brd.DC((xy[0] + 1.5, xy[1] - 2.5))

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
            "GPIO13"    : "RTS",
        }
        for nm in nick:
            dc = u1.s(nm).copy()
            dc.dir = 0
            dc.text(nick[nm], scale = 0.2)

    if 1:
        u2 = HexW25Q128(
            brd.DC(
                (Hex.from_xy(10, 17.5) + Hex(0, -1)).to_plane()
            ).right(180 + 0))
        u2.hex_escape()

    j1 = USBC(brd.DC((15, 30)).right(180))

    if 0:
        j2 = dip.SIL(brd.DC((1, 18)), "2")
        j2.pads[0].setname("GND").w("o -")
        wire_ongrid(j2.pads[1].w("f 1"))

    j2 = pogo_pads(brd.DC((28.8, 19.5)).right(180), "3")
    j2.inBOM = False
    names = ('SWCLK', '0', 'SWD')
    for (p, nm) in zip(j2.pads, names):
        p.setname(nm)
        p.copy().w("l 90 f 0.7").rtext(nm)
    j2.pads[1].setname("GND").w("o -")

    # u3 = SOT23_LDO(brd.DC((7, 27.5)).right(180).left(90))
    u3 = LDO_23_5(brd.DC((6.5, 27.5)).right(180))
    u3.hex_escape()

    if 1:
        
        pinxy = (6.27, 11.15)       # Careful measurement of center of L pin
        lcdsz = (26.16, 29.28)      # Module size
        x = (30 - lcdsz[0]) / 2 + pinxy[0]
        y = (30 - lcdsz[1]) / 2 + pinxy[1]
        u4 = ST7789_12(brd.DC((x, y)).right(0).setlayer('GBL'))
        u4.hex_escape()
        p = brd.DC((15, 15)).setlayer("GBO")
        p.copy().rect(*lcdsz).wire()
        p.goxy(lcdsz[0] / 2, -lcdsz[1] / 2)
        h0 = p.copy().goxy(-(10.3 + 1), 9.13)
        brd.layers['GBO'].add(sg.Point(h0.xy).buffer(0.5))
        h0.goxy(-10, 0)
        brd.layers['GBO'].add(sg.Point(h0.xy).buffer(0.5))

    if 1:
        # GND is on *right*, viewed from this side
        j3 = SMT6(brd.DC((15, 10)))
        j3.hex_escape()
        j3.inBOM = True

    capacitor_lcsc = {
        "100nF": "C1525",
        "1uF": "C52923",
    }
    def ucap(p, val = '100nF'):
        cn = cu.C0402_nolabel(
            p, val, source={"LCSC": capacitor_lcsc[val]})
        cn.pads[0].setname("GND").w("o -")
        return cn
    def cap(p, val = '100nF'):
        cn = ucap(p, val)
        cn.pads[1].setname("VCC").w("o +")
        return cn
    def hcap(p, val='100nF', width=None):
        cn = ucap(p, val)
        signal = cn.pads[1]
        if width is not None:
            signal.setwidth(width)
        return cn
    c6_cell = Hex.from_xy_fine(6.6, 25.2)
    if CAPS:
        hx = Hex.from_xy_fine(25, 22.2)
        c1 = cap(brd.DC(hx.to_plane()).right(30))
        hx += Hex(0, 3)
        c2 = cap(brd.DC(hx.to_plane()).right(30))
        hx += Hex(0, 3)
        c3 = cap(brd.DC(hx.to_plane()).right(30))
        vreg_vin_cap_cell = hx + Hex(0, 3)

        hx = Hex.from_xy_fine(17.9, 15.0)
        # brd.DC(hx.to_plane()).mark()
        c4 = cap(brd.DC(hx.to_plane()).right(30))

        c5 = cap(brd.DC((9.9, 14)))

        c6 = cap(brd.DC(c6_cell.to_plane()), '1uF')
        brd.DC((5.4, c6.center.xy[1])).ctext("C6", scale=0.5)

    c7_cell = c6_cell + Hex(2, -3)
    c7 = hcap(
        brd.DC(c7_cell.to_plane()), '1uF', width=2 * brd.trace)
    if CAPS:
        brd.DC((5.4, c7.center.xy[1])).ctext("C7", scale=0.5)

    c9_cell = Hex.from_xy_fine(22.7, 23.8) + Hex(0, 2) + Hex(-2, 0)
    block_step = Hex(0, 3)
    c8_cell = c9_cell + block_step
    r4_cell = c8_cell + block_step
    r5_cell = r4_cell + block_step

    c8 = hcap(brd.DC(c8_cell.to_plane()).right(210), '1uF')
    c9 = hcap(brd.DC(c9_cell.to_plane()).right(210), '1uF')
    brd.DC((23.3, c8.center.xy[1])).ctext("C8", scale=0.5)
    brd.DC((23.3, c9.center.xy[1])).ctext("C9", scale=0.5)
    if not CAPS:
        for capacitor, designator in ((c7, "C7"), (c8, "C8"), (c9, "C9")):
            capacitor.id = designator
            for pad in capacitor.pads:
                pad.part = designator

    if CAPS:
        c10 = cu.C0603(
            brd.DC((6, 5)).left(90), '10 uF, 16V',
            source={"LCSC": "C70225"})
        c10.pads[0].setname("GND").w("o -")
        c10.pads[1].setname("VCC").w("o +")

        y1_cap_cell = Hex.from_xy_fine(27.5, 9.6) + Hex(2, -4)
        c11 = cap(brd.DC(y1_cap_cell.to_plane()).right(180))

        # Local decoupling for the RP2040's internal regulator input.
        c12 = cap(
            brd.DC(vreg_vin_cap_cell.to_plane()).right(30), '1uF')

    if 1:
        y1_cell = Hex.from_xy_fine(27.5, 12) + Hex(1, -2)
        y1 = Osc_12MHz(brd.DC(y1_cell.to_plane()).right(180))
        y1.escape()

    if 1:
        # ST7789_12 backlight power
        r1 = cu.R0402(
            brd.DC((6, 11)).right(90), "7.5",
            source={"LCSC": "C47764"})

        r1.pads[1].setname("VCC").w("o +")
        wire_ongrid(r1.pads[0].w("o / f .4"))

    if 1:
        r3_cell = Hex.from_xy_fine(16.6, 19.8) + Hex(0, 1)
        r2_cell = r3_cell + Hex(0, 2)
        r2 = cu.R0402(
            brd.DC(r2_cell.to_plane()), "270",
            source={"LCSC": "C25099"})
        r3 = cu.R0402(
            brd.DC(r3_cell.to_plane()), "270",
            source={"LCSC": "C25099"})

        r4, r5 = j1.hex_escape(
            cc_positions=(r4_cell.to_plane(), r5_cell.to_plane()),
            bridge_dplus=False,
            hardwire_cc=False,
            escape_left_vbus=True,
            cc_rotation=30)

    power_net = (j1.s("A4/B9"), u3.s("5V"), u3.s("CE"), c7.pads[1])
    power_route_net = power_net[:-1] + (brd.pad_endpoint(c7.pads[1]),)

    airwire_nets = (
        power_net,
        (c8.pads[1], c9.pads[1], u1.s("VREG_VOUT")),
        (u2.s("CS"), u1.s("QSPI_SS_N")),
        (u2.s("IO1"), u1.s("QSPI_SD1")),
        (u2.s("IO2"), u1.s("QSPI_SD2")),
        (u2.s("IO0"), u1.s("QSPI_SD0")),
        (u2.s("CLK"), u1.s("QSPI_SCLK")),
        (u2.s("IO3"), u1.s("QSPI_SD3")),
        (j1.s("B7"), r2.pads[0]),
        (j1.s("A6"), j1.s("B6"), r3.pads[0]),
        (j1.s("A5"), r4.pads[0]),
        (j1.s("B5"), r5.pads[0]),
        (u1.s("USB_DM"), r2.pads[1]),
        (u1.s("USB_DP"), r3.pads[1]),
        (u1.s("GPIO14"), u4.s("SCL")),
        (u1.s("GPIO15"), u4.s("SDA")),
        (u1.s("GPIO10"), u4.s("D/C")),
        (u1.s("GPIO11"), u4.s("RESET")),
        (r1.pads[0], u4.s("LEDA")),
        (u1.s("GPIO8"), j3.s("TX")),
        (u1.s("GPIO9"), j3.s("RX")),
        (u1.s("GPIO13"), j3.s("RTS")),
        (u1.s("GPIO12"), j3.s("DTR")),
        (u1.s("XIN"), y1.s("CLK")),
        (u1.s("SWDIO"), j2.s("SWD")),
        (u1.s("SWCLK"), j2.s("SWCLK")),
    )

    lcd_routes = (
        (u1.s("GPIO15"), u4.s("SDA")),
        (u1.s("GPIO14"), u4.s("SCL")),
        (u1.s("GPIO10"), u4.s("D/C")),
        (u1.s("GPIO11"), u4.s("RESET")),
    )

    serial_routes = (
        (u1.s("GPIO8"), j3.s("TX")),
        (u1.s("GPIO9"), j3.s("RX")),
        (u1.s("GPIO13"), j3.s("RTS")),
        (u1.s("GPIO12"), j3.s("DTR")),
    )

    flash_routes = (
        (u2.s("CS"), u1.s("QSPI_SS_N")),
        (u2.s("IO1"), u1.s("QSPI_SD1")),
        (u2.s("IO2"), u1.s("QSPI_SD2")),
        (u2.s("IO0"), u1.s("QSPI_SD0")),
        (u2.s("CLK"), u1.s("QSPI_SCLK")),
        (u2.s("IO3"), u1.s("QSPI_SD3")),
    )

    clock_route = (u1.s("XIN"), y1.s("CLK"))

    debug_routes = (
        (u1.s("SWDIO"), j2.s("SWD")),
        (u1.s("SWCLK"), j2.s("SWCLK")),
    )

    usb_mcu_routes = (
        (u1.s("USB_DP"), r3.pads[1]),
        (u1.s("USB_DM"), r2.pads[1]),
    )

    usb_dplus_net = (r3.pads[0], j1.s("A6"), j1.s("B6"))
    usb_dplus_route_net = (
        brd.pad_endpoint(r3.pads[0]), j1.s("A6"), j1.s("B6"))
    usb_dminus_route = (r2.pads[0], j1.s("B7"))
    usb_cc_routes = (
        (j1.s("A5"), r4.pads[0]),
        (j1.s("B5"), r5.pads[0]),
    )
    vreg_net = (u1.s("VREG_VOUT"), c8.pads[1], c9.pads[1])
    vreg_route_net = (
        u1.s("VREG_VOUT"),
        brd.pad_endpoint(c8.pads[1]),
        brd.pad_endpoint(c9.pads[1]),
    )
    backlight_route = (r1.pads[0], u4.s("LEDA"))
    if (LCD_ROUTING or SERIAL_ROUTING or FLASH_ROUTING or
            CLOCK_ROUTING or DEBUG_ROUTING or USB_MCU_ROUTING or
            USB_CONNECTOR_ROUTING or USB_CC_ROUTING or
            VREG_ROUTING or BACKLIGHT_ROUTING or POWER_ROUTING) and not ROUTING:
        brd.hex_setup()
        if POWER_ROUTING:
            print("Starting 5V route")
            assert all(terminal.layer == "GTL" for terminal in power_net)
            brd.hex_route_net(power_route_net, width=2 * brd.trace)
        if USB_CC_ROUTING:
            print("Starting USB CC route")
            for source, target in usb_cc_routes:
                assert source.layer == target.layer == "GTL"
                brd.hex_route(source, brd.pad_endpoint(target))
        if VREG_ROUTING:
            print("Starting VREG route")
            assert all(terminal.layer == "GTL" for terminal in vreg_net)
            brd.hex_route_net(vreg_route_net)
        if LCD_ROUTING:
            print("Starting LCD route")
            for source, target in lcd_routes:
                assert source.layer == target.layer == "GBL"
                brd.hex_route(source, target)
        if BACKLIGHT_ROUTING:
            print("Starting backlight route")
            source, target = backlight_route
            assert source.layer == target.layer == "GBL"
            brd.hex_route(source, target)
        if SERIAL_ROUTING:
            print("Starting serial route")
            selected_serial_routes = (
                (source, target)
                for source, target in serial_routes
                if source.name in SERIAL_ROUTING
            )
            for source, target in selected_serial_routes:
                assert source.layer == target.layer == "GTL"

            serial_by_gpio = {
                source.name: (source, target)
                for source, target in serial_routes
            }
            for name in ("GPIO13", "GPIO9", "GPIO8", "GPIO12", ):
                if name in SERIAL_ROUTING:
                    source, target = serial_by_gpio[name]
                    if name == "GPIO12":
                        brd.hex_route(brd.pad_endpoint(target), source)
                    else:
                        brd.hex_route(source, brd.pad_endpoint(target))
        if FLASH_ROUTING:
            print("Starting flash route")
            for source, target in flash_routes:
                assert source.layer == target.layer
                brd.hex_route(target, brd.pad_endpoint(source))
        if CLOCK_ROUTING:
            print("Starting clock route")
            source, target = clock_route
            assert source.layer == target.layer
            brd.hex_route(source, brd.pad_endpoint(target))
        if DEBUG_ROUTING:
            print("Starting debug route")
            for source, target in debug_routes:
                assert source.layer == target.layer
                brd.hex_route(source, brd.pad_endpoint(target))
        if USB_MCU_ROUTING:
            print("Starting USB MCU route")
            for source, target in usb_mcu_routes:
                assert source.layer == target.layer
                brd.hex_route(source, brd.pad_endpoint(target))
        if USB_CONNECTOR_ROUTING:
            print("Starting USB connector route")
            assert all(terminal.layer == "GTL" for terminal in usb_dplus_net)
            brd.hex_route_net(usb_dplus_route_net)
            source, target = usb_dminus_route
            assert source.layer == target.layer == "GTL"
            brd.hex_route(brd.pad_endpoint(source), target)
        brd.hex_render()
        brd.wire_routes()

    if ROUTING:
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

        t0 = time.monotonic()
        brd.hex_setup()
        t1 = time.monotonic()
        print("Starting route")

        brd.hex_route(j1.s("A4/B9"), u3.s("5V"))
        brd.hex_route(brd.pad_endpoint(c7.pads[1]), u3.s("5V"))
        brd.hex_route(
            brd.pad_endpoint(c8.pads[1]),
            brd.pad_endpoint(c9.pads[1]))
        brd.hex_route(brd.pad_endpoint(c9.pads[1]), u1.s("VREG_VOUT"))

        if 1:
            brd.hex_route(u1.s("QSPI_SS_N"), brd.pad_endpoint(u2.s("CS")))
            brd.hex_route(u1.s("QSPI_SD1"), brd.pad_endpoint(u2.s("IO1")))
            brd.hex_route(u1.s("QSPI_SD2"), brd.pad_endpoint(u2.s("IO2")))
            brd.hex_route(u1.s("QSPI_SD0"), brd.pad_endpoint(u2.s("IO0")))
            brd.hex_route(u1.s("QSPI_SCLK"), brd.pad_endpoint(u2.s("CLK")))
            brd.hex_route(u1.s("QSPI_SD3"), brd.pad_endpoint(u2.s("IO3")))
        if 0:
            brd.hex_route(j2.pads[1], brd.pad_endpoint(u2.s("CS")))

        brd.hex_route(j1.s("A7"), brd.pad_endpoint(r2.pads[0]))
        brd.hex_route(j1.s("B6"), brd.pad_endpoint(r3.pads[0]))
        brd.hex_route(u1.s("USB_DM"), brd.pad_endpoint(r2.pads[1]))
        brd.hex_route(u1.s("USB_DP"), brd.pad_endpoint(r3.pads[1]))

        for nm in "SCL SDA RESET D/C".split():
            note(u4.s(nm), nm)

        if 1:
            brd.hex_route(SDL, u4.s("SCL"))
            brd.hex_route(SDA, u4.s("SDA"))
            brd.hex_route(DC,  u4.s("D/C"))
            brd.hex_route(RES, u4.s("RESET"))
        if 1:
            brd.hex_route(r1.pads[0], u4.s("LEDA"))

        note(u1.s("GPIO8"), "TX")

        if 1:
            brd.hex_route(u1.s("GPIO8"), brd.pad_endpoint(j3.s("TX")))
            brd.hex_route(u1.s("GPIO9"), brd.pad_endpoint(j3.s("RX")))
            brd.hex_route(u1.s("GPIO13"), brd.pad_endpoint(j3.s("RTS")))
            brd.hex_route(brd.pad_endpoint(j3.s("DTR")), u1.s("GPIO12"))

        brd.hex_route(u1.s("XIN"), brd.pad_endpoint(y1.s("CLK")))

        brd.hex_route(u1.s("SWDIO"), brd.pad_endpoint(j2.s("SWD")))
        brd.hex_route(u1.s("SWCLK"), brd.pad_endpoint(j2.s("SWCLK")))

        # Hack, rescue a ground island
        j3.s("GND").w("o -")

        t2 = time.monotonic()
        print(f"Hex setup:   {t1-t0:.3f} s")
        print(f"Hex route:   {t2-t1:.3f} s")

        brd.hex_render()
        brd.wire_routes()

    airwire_records = brd.add_airwires(airwire_nets)
    brd.print_airwire_report(airwire_records)

    if 1:
        brd.fill()

    logo_path = Path("../td2/marketing/logo_pcb.png")
    if logo_path.exists():
        logo_line = (
            Image.open(logo_path).convert("L").
            transpose(Image.Transpose.ROTATE_90)
        )
        brd.logo(2.2, 15, logo_line, .29)
    brd.DC((25.5, 6.4)).ctext("(C) EXCAMERA", scale = 1.1)
    brd.DC((25.5, 5.0)).ctext("LABS", scale = 1.1)

    brd.add_hex_grid()

    generated_records = brd.save("td2f")
    generated_records["netlist"] = brd.save_netlist(
        "td2f", airwire_nets)
    htmlout.write(brd, "td2f.html", generated_records)
    print("Saved")

if __name__ == "__main__":
    td2f()
