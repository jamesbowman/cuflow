import sys

from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import dip
import svgout
from dazzler import Dazzler

__VERSION__ = "1.0.0"

def gentext(s):
    fn = "../../.fonts/Arista-Pro-Alternate-Light-trial.ttf"
    fn = "../../.fonts/IBMPlexSans-SemiBold.otf"
    font = ImageFont.truetype(fn, 120)
    im = Image.new("L", (2000, 1000))
    draw = ImageDraw.Draw(im)
    draw.text((200, 200), s, font=font, fill = 255)
    return im.crop(im.getbbox())

class padline(cu.Part):
    family = "J"
    inBOM = False
    def place(self, dc):
        self.train(dc, self.val, lambda: self.rpad(dc, 1.27, 2.54), 2.54)

    def escape(self, a = -45):
        tt = [t.copy().w("i") for t in self.pads][::-1]
        return self.board.enriver(tt, a)

class TXB0108(cu.TSSOP):
    N = 20
    def escape(self):
        # VCCA side runs 3.3V, VCCB side runs 5V
        for p,s in zip(self.pads, "A1 VCCA A2 A3 A4 A5 A6 A7 A8 OE GND B8 B7 B6 B5 B4 B3 B2 VCCB B1".split()):
            p.setname(s)
        for p in self.pads:
            if p.name == "GND":
                p.w("i -")
            elif p.name == "VCCA":
                p.setname("VCC").w("i f 0.4").wire()
            elif p.name == "VCCB":
                p.w("i f 1.5").wire()
            else:
                p.outside()
        a = [self.s(nm) for nm in "A1 A2 A3 A4 A5 A6 A7 A8".split()]
        b = [self.s(nm) for nm in "B8 B7 B6 B5 B4 B3 B2 B1".split()]

        oe = self.s("OE").w("i f 1.5").wire()
        oe.copy().via()

        return (a, b, oe)

def dazzler_console(dc):
    uart_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')
    brd.hole(dc.copy().w("r 180 f 4").xy, 2.5, 5.5)
    brd.hole(dc.copy().forward(4 + cu.inches(0.5)).xy, 2.5, 5.5)
    uart_port = padline(dc, 6)
    for p,nm in zip(uart_port.pads, uart_names):
        p.setname(nm)
        p.copy().goxy(0, 0).text(nm)
    uart_port.s("GND").setname("GL2").w("l 90 f 2").wire(layer = "GBL")
    tt = [uart_port.pads[i].w("i") for i in (2, 1)]
    return brd.enriver(tt, -45).wire()

class MD_60Sb(dip.PTH):
    family = "J"
    mfr = 'MD-60S'
    def place(self, dc):
        self.chamfered(dc, 14, 12.3)

        def mounting(dc, l):
            self.board.hole(dc.xy, l, l * 1.1)
            return
            dc.push()
            dc.newpath()
            dc.forward(l / 2)
            dc.right(180)
            dc.forward(l)
            dc.slot(.25)
            dc.pop()

        dc.right(180).forward(12.3 / 2).right(180)
        mounting(dc.copy().forward(4.70).right(90), 2.5)
        def pin(nm, x, y):
            self.gh(dc.copy().setname(nm).goxy(x, y).text(nm))

        pin("1",  2.6 / 2, 8.50)
        pin("2", -2.6 / 2, 8.50)
        pin("3", -6.5 / 2, 8.50)
        pin("5",  6.5 / 2, 8.50)

        pin("8", -6.5 / 2, 11)
        pin("6",  6.5 / 2, 11)

if __name__ == "__main__":
    brd = cu.Board(
        (100, 50),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    # Measurements from http://rc2014.co.uk/1377/module-template/

    d = brd.DC((0,0))
    d.w("f 34.849 r 45 f 21.228 r 45 f 78.995")
    # 5.1 mm radius
    cc = 2 * math.pi * 5.1
    for i in range(90):
        d.forward(cc / 360)
        d.right(1)
    d.w("f 44.760")
    d.outline()
    brd.hole((5.029, 33.122), 3.2, 7)

    def gnd(s):
        s.setname("GL2").thermal(1.1).wire(layer = "GBL")

    # ------------------------------ RC2014 bus
    bus = dip.SIL(brd.DC((2.54 * 19.5, 1.715)).right(270), "39")
    nms = "a15 a14 a13 a12 a11 a10 a9 a8 a7 a6 a5 a4 a3 a2 a1 a0 gnd 5v m1 rst clk int mreq wr rd iorq d0 d1 d2 d3 d4 d5 d6 d7 tx rx u1 u2 u3".split()
    for (nm, p) in zip(nms, bus.pads):
        p.setname(nm)
        p.copy().w("l 90 f 2").text(nm.upper())
        if nm != "gnd":
            p.left(90).forward(1)
    gnd(bus.s("gnd"))
    
    def routel(layer, sigs):
        zsig = [bus.s(nm) for nm in sigs]
        for i,t in enumerate(zsig):
            t.setlayer(layer)
        cu.extend2(zsig)
        zsig0 = brd.enriver90(zsig, -90)
        return zsig0.wire()
    for nm in "d7 d6 d5 d4 d3 d2 d1 d0".split():
        bus.s(nm).w("f 1 r 45 f 2 l 45 f 3")
    za = routel('GTL', "iorq wr int clk m1 a0 a1 a2 a3 a4 a5 a6 a7".split())
    zd = routel('GBL', "d7 d6 d5 d4 d3 d2 d1 d0".split())
    zd.w("f 38 / r 90").wire()
    za.w("r 90").wire()

    # ------------------------------ FTDI conn
    ftdi = dip.SIL(brd.DC((1.2, 24.6)).right(0), "6")
    ftdi_names = ('DTR', 'OUT', 'IN', '5V', 'CTS', 'GND')
    for p,nm in zip(ftdi.pads, ftdi_names):
        p.setname(nm)
        p.copy().w("l 90 f 2").text(nm)
    gnd(ftdi.s("GND"))
    i = ftdi.s("IN").w("l 90 f 4 r 90 f 8 l 90 f 4 r 45 f 5 r 45 f 4 l 90 f 1 l 90")
    ftdi_in = brd.river1(i).wire()

    # ------------------------------ PS/2
    # MD-60S from CUI, Future Electronics $1.10
    # 1: DATA  5: CLOCK
    ps2 = MD_60Sb(brd.DC((6.2, 10)).right(90))
    dc = [ps2.s("6"), ps2.s("1")]
    ps2.s("5").w("f 0 r 180 f 1 -")
    ps2.s("3").newpath().setlayer('GBL').w("r 45 f 3").wire()
    cu.extend2(dc)
    ps2b = brd.enriver90([t.w("f 4") for t in dc], -90).wire()
    
    zbus = zd.join(za, 0.5).join(ps2b).join(ftdi_in).wire()

    daz = Dazzler(brd.DC((73, 26)).right(0), "nosw")

    # ------------------------------ dazzler busses
    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")

    ss = [daz.s(str(i)) for i in (2, 1)]
    [s.w("i f 0.5") for s in ss]
    daz0 = brd.enriver90(ss, -90).wire()

    ss = [daz.s(str(i)) for i in range(15, 30)]
    [s.forward(1) for s in ss]
    daz1 = brd.enriver90(ss, 90).wire()

    ss = [daz.s(str(i)) for i in range(11, 2, -1)]
    [s.w("i f 1 .").setlayer('GBL').w("f 1") for s in ss]
    daz2 = brd.enriver90(ss, 90)
    daz2.w("l 45 f 15 r 45 f 6 / l 45").wire()

    daz.s("13").w("i f 1 / r 45 f 10 r 45 f 12 r 45 f 10.5 l 45 f 16 l 45 f 7 l 45 f 12").goto(ftdi.s("OUT")).wire()
    oe = daz.s("12").w("i f 1 / r 45 f 13.5 r 45 f 23").wire()

    # ------------------------------ dazzler console
    cx = dazzler_console(brd.DC((37.0, 48.0)).left(90).setlayer('GBL'))
    daz0.w("f 2 l 90 f 2 l 90")
    daz0.w("f 34 / l 45 f 12 r 90 f 3").wire()
    daz0.meet(cx)

    # ------------------------------ level shifters
    d = brd.DC((25, 42)).right(180)
    asig = []       # FPGA, 3.3V side
    bsig = []       # Z80, 5V side
    for i in range(3):
        cu.C0402(d.copy().goxy(-2.8, 4.5).left(180), '0.1 uF').escape_2layer()
        (a, b, _oe) = TXB0108(d).escape()
        oe.copy().goto(_oe).wire()
        asig = a + asig
        bsig += b
        d.forward(9)
    bbus = brd.enriver90(bsig, -90).wire()

    x = 24 - len(daz1)
    daz1.w("l 90 f 4 l 45").meet(brd.enriver(asig[x:], -45).wire())
    daz2.meet(brd.enriver(asig[:x], -45).wire())

    zbus.meet(bbus)

    # ------------------------------ 5V power
    v5 = bus.s("5v").setlayer('GBL').setwidth(0.6)
    v5.copy().w("f 2 r 90 f 22 / l 45 f 11 r 45 f 8").goto(daz.s("5V")).wire()
    lv5 = v5.copy().w("f 2 l 90 f 27 r 90 f 6").wire()
    lv5.copy().goto(ps2.s("3")).wire()
    lv5.w("r 45 f 10 l 45 / f 22").wire()

    """
    cu.C0402(brd.DC((65, 39.0)), '0.1 uF').escape_2layer()
    cu.C0402(brd.DC((59, 27.5)), '0.1 uF').escape_2layer()

    R1 = cu.R0402(brd.DC((51.5, 46.0)).right(90), '4.7K')
    R2 = cu.R0402(brd.DC((53.0, 46.0)).right(90), '4.7K')
    R1.pads[0].w("o l 90 f 0.5 -")
    daz.s("PGM").w("o f 1 r 90 f 13 r 45 f 5.5 l 45 f 2").wire()
    daz.s("5V").copy().w("i f 6 l 90 f 9.15 l 90 f 11.3 r 90 f 26.9 r 90 f 4").goto(R2.pads[0]).wire()

    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")

    jtag_names = ('TDI', 'TDO', 'TCK', 'TMS')
    jtag = [daz.s(nm) for nm in jtag_names]
    for i,t in enumerate(jtag):
        t.inside().forward(8 + 1 * i).wire().via().setlayer('GBL').right(45)
    cu.extend2(jtag)
    jtag0 = brd.enriver(jtag, 45)

    jtag_port = padline(brd.DC((11.0, 51.33)).left(90).setlayer("GBL"), 4)
    jtag1 = jtag_port.escape().wire()
    jtag0.w("f 15 r 45 f 3") # .meet(jtag1)

    for p,nm in zip(jtag_port.pads, jtag_names):
        p.text(nm)

    uart_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')

    uart0 = daz.escapesM(["1", "2", "3"][::-1], -90).w("r 90").wire()

    uart_port = padline(brd.DC((2.0, 39.0)).left(180).setlayer("GBL"), 6)
    for p,nm in zip(uart_port.pads, uart_names):
        p.text(nm)
    uart_port.pads[5].copy().setname("GL2").w("i f 1").wire()
    tt = [uart_port.pads[i].w("i") for i in (2, 1, 0)]
    uart1 = brd.enriver(tt, 45).w("f 13 r 45") # .meet(uart0)
    """

    if 0:
        im = Image.open("img/gameduino-mono.png")
        brd.logo(62, 46, im)

        im = Image.open("img/dazzler-logo.png")
        brd.logo(64, 30, im)

        brd.logo(75.8,  6.2, gentext("PLAYER 1"), scale = 0.4)
        brd.logo(75.8, 46.9, gentext("PLAYER 2"), scale = 0.4)

        brd.logo(76, 53.3 / 2 - 12, gentext("1").transpose(Image.ROTATE_90), scale = 1.0)
        brd.logo(76, 53.3 / 2 + 12, gentext("2").transpose(Image.ROTATE_90), scale = 1.0)

        brd.logo(75.8, 53.3 / 2, Image.open("img/oshw-logo-outline.png").transpose(Image.ROTATE_90), scale = 0.7)

        for i,s in enumerate(["(C) 2020", "EXCAMERA LABS", str(__VERSION__)]):
            brd.annotate(57.5, 8.5 - 1.5 * i, s)

    if 0:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GL2")

    brd.save("rc2014_dazzler")
    for n in brd.nets:
        print(n)
    svgout.write(brd, "rc2014_dazzler.svg")
