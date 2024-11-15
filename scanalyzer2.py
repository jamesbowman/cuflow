import os
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

def gentext(size, s):
    fn = "../../.fonts/Arista-Pro-Alternate-Light-trial.ttf"
    fn = os.getenv("HOME") + "/.fonts/IBMPlexSans-SemiBold.otf"
    font = ImageFont.truetype(fn, size)
    im = Image.new("L", (2000, 1000))
    draw = ImageDraw.Draw(im)
    draw.text((200, 200), s, font=font, fill = 255)
    return im.crop(im.getbbox())

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

def ldo(p):
    r = cu.SOT223(p)
    p.goxy(-2.3/2, -5.2).w("r 180")
    cu.C0603(p, val = '4.7 uF', source = {'LCSC' : 'C19666'})
    p.forward(2)
    pa = cu.C0603(p, val = '22 uF', source = {'LCSC': 'C159801'}).pads
    pa[0].w("l 90 f 3").wire(width = 0.4)
    pa[1].w("r 90 f 3").wire(width = 0.4)
    return r.escape()

class Screw16(cu.Part):
    family  = "J"
    source = {'Digikey': '277-1591-ND'}
    width   = 5
    N       = 16
    r       = 1.2

    def place(self, dc):
        self.chamfered(dc, 10, 10)
        hdr.place(self, dc)

    def escape(self):
        return

class Wago32(dip.PTH):
    family  = "J"
    source = {'Digikey' : '2946-736-108-ND'}
    r = 1.3
    def place(self, dc):
        self.N = 16
        G = 5   # gap
        dc.forward(((self.N - 1) / 2) * G).left(180)
        l0 = dc.copy()
        self.train(l0, self.N, lambda: self.gh(l0), G)
        dc.w("r 90 f 15 l 90")
        l0 = dc.copy()
        self.train(l0, self.N, lambda: self.gh(l0), G)
        self.pads = [self.pads[(i % 2) * 16 + (i // 2)] for i in range(32)]

def addlabels(part):
    shift = 3
    for pad in part.pads:
        nm = pad.name
        if nm is not None:
            p = pad.copy().right(90)
            p.copy().forward(shift).text(nm)
            shift = {3:4, 4:3}[shift]

class MCP23017(cu.SOIC28):
    source = {'Digikey': ''}
    mfr = 'W25Q64JVSSIQ'

    @staticmethod
    def tie(p, v : int):
        assert v in (0, 1)
        if v == 0:
            p.setname("GL2").w("o f 1 -")
        else:
            p.setname("GL3").w("o f 1").wire()

    def escape(self):
        s = "GPB0 GPB1 GPB2 GPB3 GPB4 GPB5 GPB6 GPB7 VCC GND NC SCL SDA NC A0 A1 A2 RESETQ INTB INTA GPA0 GPA1 GPA2 GPA3 GPA4 GPA5 GPA6 GPA7".split()
        [c.setname(nm) for (c, nm) in zip(self.pads, s)]
        for i in range(3):
            self.tie(self.s(f"A{i}"), 1 & (int(self.val) >> i))

        self.tie(self.s("GND"), 0)
        for s in ("VCC", "RESETQ"):
            self.tie(self.s(s), 1)

class MCP24AA02(cu.SOIC8):
    source = {'LCSC': 'C179171'}
    mfr = 'W25Q64JVSSIQ'
    def escape(self):
        [c.setname(nm) for (c, nm) in zip(self.pads, "A0 A1 A2 GND SDA SCL NC VCC".split())]
        for s in ("A0", "A1", "A2", "GND"):
            self.s(s).setname("GL2").w("o f 1 -")
        self.s("VCC").setname("GL3").w("o f 1").wire()

class I2Cconn(dip.SIL_o):
    def __init__(self, p):
        super().__init__(p, "4")

    def escape(self):
        [c.setname(nm) for (c, nm) in zip(self.pads, "SCL SDA VCC GND".split())]
        addlabels(self)
        self.s("GND").setname("GL2").w("r 90 f 2 -")
        self.s("VCC").setname("GL3").w("r 90 f 2").wire()

class PowerLED(cu.Part):
    family = "D"
    inBOM = False
    def place(self, dc):
        d1 = cu.D0603(dc)
        dc.w("f 2")
        r1 = cu.R0402(dc)

        d1.pads[0].setname("GL2").w("o -")
        d1.pads[1].goto(r1.pads[1]).wire()
        r1.pads[0].setname("GL3").w("o f 2").wire()

class Decoupler(cu.C0402):
    def escape(self):
        self.pads[0].w("o -")
        self.pads[1].setname("GL3").w("o f 1").wire()

def scanalyzer2():
    brd = cu.Board(
        (100, 56),
        trace = cu.mil(6),
        space = cu.mil(6) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))
    brd.outline()

    if 1:
        for x in (3.5, 100 - 3.5):
            for y in (3.5, 56 - 3.5):
                brd.hole((x, y), 2.7, 6)

    p = brd.DC((50, 50)).left(90)
    if 0:
        conn = dip.SIL_o(p, "4")
        [c.setname(nm) for (c, nm) in zip(conn.pads, "SCL SDA VCC GND".split())]
        addlabels(conn)
        conn.s("GND").setname("GL2").w("r 90 f 2 -")
        conn.s("VCC").setname("GL3").w("r 90 f 2").wire()
    else:
        conn = I2Cconn(p)
        conn.escape()

    p = brd.DC((70, 45))
    PowerLED(p)

    p = brd.DC((30, 45))
    u1 = MCP24AA02(p)
    u1.escape()
    Decoupler(p.goxy(3, 4), '10nF').escape()

    p = brd.DC((50, 30)).right(180)
    u2 = MCP23017(p, "0")
    u2.escape()
    Decoupler(p.right(180).goxy(10, 2).right(180), '10nF').escape()

    p = brd.DC((50, 14)).left(90)
    j2 = dip.Screw16(p, "16")
    for (p,nm) in zip(j2.pads, "ABCDEFGHIJKLMNOP"):
        p.setname(nm)
        d = p.copy().w("r 90 f 8")
        # d.text(nm)
        brd.logo(d.xy[0], d.xy[1], gentext(130, nm), scale = 1.0)

    u1.s("SCL").w("o f 4 / f 1").goto(conn.s("SCL"), True).wire()
    u1.s("SDA").w("o f 2 / f 1").goto(conn.s("SDA"), True).wire()

    u2.s("SCL").w("i f 3 r 90 f 5").goto(conn.s("SCL")).wire()
    u2.s("SDA").w("i f 2 r 90 f 5").goto(conn.s("SDA")).wire()

    j2.s("A").goto(u2.s("GPA0")).wire()
    j2.s("B").goto(u2.s("GPA1")).wire()
    j2.s("C").goto(u2.s("GPA2")).wire()
    j2.s("D").goto(u2.s("GPA3")).wire()
    j2.s("E").goto(u2.s("GPA4")).wire()
    j2.s("F").goto(u2.s("GPA5")).wire()
    j2.s("G").goto(u2.s("GPA6")).wire()
    j2.s("H").goto(u2.s("GPA7")).wire()

    j2.s("I").goto(u2.s("GPB0")).wire()
    j2.s("J").goto(u2.s("GPB1")).wire()
    j2.s("K").goto(u2.s("GPB2")).wire()
    j2.s("L").goto(u2.s("GPB3")).wire()
    j2.s("M").goto(u2.s("GPB4")).wire()
    j2.s("N").goto(u2.s("GPB5")).wire()
    j2.s("O").goto(u2.s("GPB6")).wire()
    j2.s("P").goto(u2.s("GPB7")).wire()

    if 1:
        brd.fill_any("GTL", "GL3")
        brd.fill_any("GBL", "GL2")

    name = "scanalyzer2"
    brd.save(name)
    for n in brd.nets:
        print(n)
    svgout.write(brd, name + ".svg")

def scanalyzer2a():
    brd = cu.Board(
        (100, 56),
        trace = cu.mil(6),
        space = cu.mil(6) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))
    brd.outline()

    if 1:
        for x in (3.5, 100 - 3.5):
            for y in (3.5, 56 - 3.5):
                brd.hole((x, y), 2.7, 6)

    p = brd.DC((50, 50)).left(90)
    if 0:
        conn = dip.SIL_o(p, "4")
        [c.setname(nm) for (c, nm) in zip(conn.pads, "SCL SDA VCC GND".split())]
        addlabels(conn)
        conn.s("GND").setname("GL2").w("r 90 f 2 -")
        conn.s("VCC").setname("GL3").w("r 90 f 2").wire()
    else:
        conn = I2Cconn(p)
        conn.escape()

    p = brd.DC((70, 47))
    PowerLED(p)

    p = brd.DC((30, 47))
    u1 = MCP24AA02(p)
    u1.escape()
    Decoupler(p.goxy(3, 4), '10nF').escape()

    p = brd.DC((30, 32)).right(180)
    u2 = MCP23017(p, "0")
    u2.escape()
    Decoupler(p.right(180).goxy(10, 2).right(180), '10nF').escape()

    p = brd.DC((30 + 8 * 5, 32)).right(180)
    u3 = MCP23017(p, "1")
    u3.escape()
    Decoupler(p.right(180).goxy(10, 2).right(180), '10nF').escape()

    p = brd.DC((50, 18)).left(90)
    j2 = Wago32(p)

    for (i, (p,nm)) in enumerate(zip(j2.pads, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")):
        p.setname(nm)
        if (i % 2) == 1:
            p.w("f 2.5 l 90 f 15")
        else:
            p.w("l 90")
        p.forward(3).wire()
        # d = p.copy().w("r 90 f 8")
        # d.text(nm)
        # brd.logo(d.xy[0], d.xy[1], gentext(130, nm), scale = 1.0)

    if 1:
        u1.s("SCL").copy().w("i f 2 l 90 f 3").goto(u2.s("SCL"), True).wire()
        u1.s("SDA").copy().w("i f 1 l 90 f 3").goto(u2.s("SDA"), True).wire()

        u1.s("SCL").w("o f 4 / f 1").goto(conn.s("SCL"), True).wire()
        u1.s("SDA").w("o f 2 / f 1").goto(conn.s("SDA"), True).wire()

        u3.s("SCL").w("i f 3 r 90 f 5").goto(conn.s("SCL")).wire()
        u3.s("SDA").w("i f 2 r 90 f 5").goto(conn.s("SDA")).wire()

    conns = (
        "GPA0",
        "GPA1",
        "GPA2",
        "GPA3",
        "GPA4",
        "GPA7",
        "GPA6",
        "GPA5",

        "GPB1",
        "GPB0",
        "GPB2",
        "GPB3",
        "GPB4",
        "GPB5",
        "GPB6",
        "GPB7",
    )
    for a,b in zip(j2.pads, conns):
        a.goto(u2.s(b), True).wire()
    for a,b in zip(j2.pads[16:], conns):
        a.goto(u3.s(b), True).wire()

    if 0:
        j2.s("D").goto(u2.s("GPA3")).wire()
        j2.s("E").goto(u2.s("GPA4")).wire()
        j2.s("F").goto(u2.s("GPA5")).wire()
        j2.s("G").goto(u2.s("GPA6")).wire()
        j2.s("H").goto(u2.s("GPA7")).wire()

        j2.s("I").goto(u2.s("GPB0")).wire()
        j2.s("J").goto(u2.s("GPB1")).wire()
        j2.s("K").goto(u2.s("GPB2")).wire()
        j2.s("L").goto(u2.s("GPB3")).wire()
        j2.s("M").goto(u2.s("GPB4")).wire()
        j2.s("N").goto(u2.s("GPB5")).wire()
        j2.s("O").goto(u2.s("GPB6")).wire()
        j2.s("P").goto(u2.s("GPB7")).wire()

    if 1:
        brd.fill_any("GTL", "GL3")
        brd.fill_any("GBL", "GL2")

    name = "scanalyzer2a"
    brd.save(name)
    for n in brd.nets:
        print(n)
    svgout.write(brd, name + ".svg")

if __name__ == "__main__":
    # scanalyzer2()
    scanalyzer2a()
