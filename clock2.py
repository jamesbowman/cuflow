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

class Pico(dip.dip):
    family  = "U"
    width   = 17.78
    N       = 40

    def padfoot(self, p):
        p.stadium(0.8, 60, 1.7)

    def place(self, dc):
        dip.dip.place(self, dc)

        dc.goxy(-dip.T, -(51 / 2 - 1.6)).right(90)
        # self.train(dc, 3, self.gh, cu.inches(.1))

        for (i,p) in enumerate(self.pads, 1):
            p.setname(str(i))

        gpins = {3, 8, 13, 18, 23, 28, 33, 38}
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
            # "SWCLK",
            # "GND",
            # "SWDIO",
        ]
        for pad,nm in zip(self.pads, pnames):
            pad.part = self
            pad.right(90)
            pad.copy().w("f 5").text(nm)
            pad.setname(nm)
        self.s("VBUS").setname("VCC").thermal(1.3).wire()
        self.s("VSYS").setname("VCC").thermal(1.3).wire()

    def wire_escape(self, p):
        p.dir = 90
        wire_ongrid(p.w("f 3"))
        
    def escape(self):
        pp = [p for p in self.pads if p.name not in ("GND", "VCC")]
        c = self.board.c
        n = 15
        pivot = pp[n].copy().left(180)  # bottom left pad
        w = pivot.distance(pp[n + 1])

        order = pp[0:n+1][::-1] + pp[n+1:30][::-1]
        for i,p in enumerate(order):
            dst = pivot.copy().forward((w / 2) - (c * len(order) / 2) + c * i)
            p.left(180).forward(0.5 + c + (n - abs(i - n)) * c).right(90)
            p.goto(self.board.DC((p.xy[0], pivot.xy[1])))
        for p in pp:
            p.dir = 180
            p.forward(3).wire()
        return pp[:n+1][::-1] + [self.s("SWCLK"), self.s("SWDIO")] + pp[n+1:n+15][::-1]
        return (pp[:n][::-1] + [pp[30], pp[32]] + pp[n:30])

class GPS_NEO_6M(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 27.6, 26.6)
        dc.goxy((26.6/2) + 0.1, -cu.inches(0.2))
        self.train(dc, 5, lambda: self.rpad(dc, 2, 4), cu.inches(0.1))

        for p,nm in zip(self.pads, ["PPS", "RX", "TX", "GND", "VCC"]):
            p.part = self
            p.setname(nm)
            p.copy().w("o f 2").ctext(str(nm))
        self.s("VCC").w("i f 2").wire()
        self.s("GND").w("i f 2 /").thermal(1).wire()

    def wire_escape(self, p):
        wire_ongrid(p.w("o f 0.4"))

    def escape(self):
        pp = self.pads
        pp[3].setname("GL2").w("o f 1 -")
        [pp[i].w("o f 1 /") for i in (0, 1, 2, 4)]

class SEG7(cu.Part):
    family = "J"
    def place(self, dc):
        j1 = dip.SIL(dc, "6")
        for p,nm in zip(j1.pads, ["GND", "LAT", "CLK", "SER", "VCC", "12V"]):
            p.part = self
            p.copy().right(90).forward(2).ctext(str(nm))
            p.setname(nm)
        self.pads = j1.pads
        self.s("VCC").thermal(1.3).wire()
        j1.s("GND").through().thermal(1.3).wire()

    def wire_escape(self, p):
        p.dir = 90
        wire_ongrid(p.w("r 90 f 1"))

class LDO(cu.SOT223):
    family = "U"
    def place(self, dc):
        super().place(dc)
        for p,nm in zip(self.pads, ["OUT1", "GND", "OUT2", "IN", ]):
            p.part = self
            p.copy().ctext(str(nm))
            p.setname(nm)
        self.s("OUT1").setname("VCC").thermal(3).wire()
        self.s("OUT2").setname("VCC").thermal(1.35).wire()
        self.s("GND").w("f 2 /").thermal(1.4).wire()

    def wire_escape(self, p):
        wire_ongrid(p.w("f 1"))

def clock2():
    w = 0.127
    brd = HexBoard(
        (56, 53.0),
        trace = w,
        space = .4 - w,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(5))

    brd.outline()

    brd.hole((53,  3), 2, 2.5)
    brd.hole((53, 50), 2, 2.5)

    dc = brd.DC((15, brd.size[1] / 2)).right(180)
    m1 = Pico(dc)

    m2 = GPS_NEO_6M(brd.DC((42, 19)).right(90))

    j1 = SEG7(brd.DC((42, 49)).left(90))

    u1 = LDO(brd.DC((43, 39)).left(90))

    connects = [
        (m1.s("GP10"),  m2.s("PPS")),
        (m1.s("GP1"),   m2.s("RX")),
        (m1.s("GP0"),   m2.s("TX")),
        (m1.s("GP11"),  j1.s("LAT")),
        (m1.s("GP12"),  j1.s("CLK")),
        (m1.s("GP13"),  j1.s("SER")),
        (u1.s("IN"),    j1.s("12V")),
    ]

    def cap(p, val = '10nF'):
        cn = cu.C0402_nolabel(p, val)
        cn.pads[0].setname("GND").w("o f .5 / f .6").wire()
        cn.pads[1].setname("VCC").w("o f .3").wire()
    if 0:
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
        t0 = time.monotonic()

        for (a, b) in connects:
            a.part.wire_escape(a)
            b.part.wire_escape(b)

        brd.hex_setup()
        t1 = time.monotonic()
        print("Starting route")

        t2 = time.monotonic()
        print(f"Hex setup:   {t1-t0:.3f} s")
        print(f"Hex route:   {t2-t1:.3f} s")

        for (a, b) in connects[:]:
            brd.hex_route(a, b)

        brd.hex_render()

        brd.wire_routes()

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GND")

    brd.save("clock2")
    print("Saved")

if __name__ == "__main__":
    clock2()
