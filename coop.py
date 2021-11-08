import sys
from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import svgout
import dip
import eagle
from dazzler import Dazzler
from collections import defaultdict

import shapely.geometry as sg

__VERSION__ = "1.0.0"

def thermal(t, layer, d = 1.3):
    t.setname(layer).thermal(d).wire(layer = layer)

def thermal_gnd(t, d = 1.3):
    t.setname("GL2").thermal(d).wire(layer = "GBL")

class Pico(dip.dip):
    family  = "U"
    width   = 17.78
    N       = 40
    def place(self, dc):
        dip.dip.place(self, dc)
        for i in range(40):
            self.pads[i].setname(str(i + 1))

        gpins = {3, 8, 13, 18, 23, 28, 33, 38}
        io = set(range(1, 35)) - gpins
        for g in gpins:
            p = self.s(str(g)).copy()
            p.setname("GL2").thermal(1.3).wire(layer = "GBL")
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
            "VBUS"
        ]
        for pad,nm in zip(self.pads, pnames):
            if nm != "GND":
                pad.setname(nm)

class EDS(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 18.0, 18)
        dc.goxy(-8, cu.inches(0.15)).left(180)
        self.train(dc, 4, lambda: self.rpad(dc, 2, 2), cu.inches(0.1))
    def escape(self):
        pp = self.pads
        pp[0].setname("GL2").w("o f 1 -")
        pp[1].setname("GL3").w("o f 1").wire()
        # pp[1].setname("GTL").w("i f 1").wire(layer = "GTL")
        # pp[2].w("i f 2").wire().via().setlayer("GBL")
        # pp[3].w("i f 2").wire().via().setlayer("GBL")
        return (pp[2], pp[3])

def coop():
    brd = cu.Board(
        (90, 63),
        trace = cu.mil(6),
        space = cu.mil(6) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))
    brd.outline()

    j1 = dip.Screw2(brd.DC((83, 51)).right(90))
    thermal_gnd(j1.s("1"), 2)
    vin = j1.s("2")

    (sda0, scl0) = EDS(brd.DC((17, 44)).right(90)).escape()
    (sda1, scl1) = EDS(brd.DC((17, 24)).right(90)).escape()

    target = "pico"
    pico = Pico(brd.DC((50, 28)))

    pico.s("GP26").mark()

    R1 = cu.R0402(brd.DC((61, 29)).right(90), '4.7K')
    R2 = cu.R0402(brd.DC((63, 29)).right(90), '4.7K')
    R1.pads[1].w("o f 0.5 -")
    R2.pads[1].w("o").goto(vin).wire()
    R2.pads[0].goto(R1.pads[0]).goto(pico.s("GP26")).wire()

    def ldo(p):
        r = cu.SOT223(p)
        p.goxy(-2.3/2, -5.2).w("r 180")
        cu.C0603(p, val = '4.7 uF', source = {'LCSC' : 'C19666'})
        p.forward(2)
        pa = cu.C0603(p, val = '22 uF', source = {'LCSC': 'C159801'}).pads
        pa[0].w("l 90 f 3").wire(width = 0.4)
        pa[1].w("r 90 f 3").wire(width = 0.4)
        return r.escape()

    conn = dip.SIL(brd.DC((31, 56)).left(90), "6")

    L = ldo(brd.DC((66, 46.5)))
    L[0].goto(vin).wire(width = 0.5)
    L[1].goto(pico.s("VSYS")).wire(width = 0.5)

    # I2C hookup

    sda0.goto(sda1).wire()
    pico.s("GP14").goto(sda1).wire()
    scl0.goto(scl1).wire()
    pico.s("GP15").goto(scl1).wire()

    """
    pico_used = (
        "GP0",
        "GP2", "GP3", "GP4", "GP5",
        "GP6", "GP7", "GP8", "GP9", "GP10"
    )
    tt = [pico.s(str(i)) for i in pico_used]
    [p.setlayer("GBL").w("r 180 f 2").wire() for p in tt]
    b0 = brd.enriver90(tt[::-1], -90).wire()

    b0.shuffle(b1, {         # Pico         Dazzler    
        "GP8": "1"  ,    # UART1 TX     CONSOLE IN 
        "GP9": "2"  ,    # UART1 RX     CONOLE OUT 
        "GP4": "22" ,    # SPI0 RX      MISO       
        "GP5": "25" ,    # GP5          GPU SEL    
        "GP6": "26" ,    # GP6          SD SEL     
        "GP7": "27" ,    # GP7          DAZZLER SEL
        "GP3": "28" ,    # SPI0 TX      MOSI       
        "GP2": "29" ,    # SPI0 SCK     SCK        
        "GP10":"PGM",    # GP10         PGM        
        "GP0": "23" ,    # UART0 TX     UART       
    }).w("f 9 l 45").meet(b1)
    """

    pico.s("3V3(OUT)").setname("GL3").thermal(1.3).wire(layer = "GTL")

    conn.s("1").setname("GL3").thermal(1.3).wire(layer = "GTL")
    conn.s("6").setname("GL2").thermal(1.3).wire(layer = "GBL")

    serial0 = brd.enriver([pico.s(s).right(90) for s in ("GP4", "GP5")], 45).w("f 7").wire()
    serial1 = brd.enriver([conn.s(s).setlayer("GBL").right(90) for s in ("3", "4")], -45).w("f 1").wire()
    serial0.shuffle(serial1, {
        "GP4" : "3",
        "GP5" : "4"}).w("r 90 f 2").wire().meet(serial1)

    # serial.shuffle(
    # print(serial.board.c)

    # pico.s("GP4").goto(conn.s("3")).wire()
    # pico.s("GP5").goto(conn.s("4")).wire()

    if 0:
        brd.fill_any("GTL", "GL3")
        brd.fill_any("GBL", "GL2")

    name = "coop"
    brd.save(name)
    for n in brd.nets:
        print(n)
    svgout.write(brd, name + ".svg")

if __name__ == "__main__":
    coop()
