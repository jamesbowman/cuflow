import sys

from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import dip
import svgout
from dazzler import Dazzler
import eagle

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
                p.w("i f 1").wire()
            else:
                p.outside()
        a = [self.s(nm) for nm in "A1 A2 A3 A4 A5 A6 A7 A8".split()]
        b = [self.s(nm) for nm in "B8 B7 B6 B5 B4 B3 B2 B1".split()]

        return (a, b)

class MD_60S(eagle.LibraryPart):
    libraryfile = "MD-60S.lbr"
    partname = "CUI_MD-60S"
    use_pad_text = False
    family = "J"

def dazzler_console(dc):
    uart0 = daz.escapesI(["3", "2", "1"], -90).w("r 90").wire()
    uart_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')
    # brd.hole((2, 39 + 4), 2.5, 5.5)
    # brd.hole((2, 39 - cu.inches(.5) - 4), 2.5, 5.5)
    uart_port = padline(dc, 6)
    for p,nm in zip(uart_port.pads, uart_names):
        p.copy().goxy(0, -3).text(nm)
    uart_port.pads[5].copy().w("i -")
    tt = [uart_port.pads[i].w("i") for i in (2, 1)]
    return brd.enriver(tt, 45)

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

    # ------------------------------ RC2014 bus
    bus = dip.SIL(brd.DC((2.54 * 19.5, 1.715)).right(270), "39")
    nms = "a15 a14 a13 a12 a11 a10 a9 a8 a7 a6 a5 a4 a3 a2 a1 a0 gnd 5v m1 rst clk int mreq wr rd iorq d0 d1 d2 d3 d4 d5 d6 d7 tx rx u1 u2 u3".split()
    for (nm, p) in zip(nms, bus.pads):
        p.setname(nm)
        p.copy().w("l 90 f 2").text(nm.upper())
        p.left(90).forward(1)
    
    def routel(layer, sigs):
        zsig = [bus.s(nm) for nm in sigs]
        for i,t in enumerate(zsig):
            t.setlayer(layer)
        cu.extend2(zsig)
        zsig0 = brd.enriver90(zsig, -90)
        return zsig0.wire()
    b_names = "d7 d6 d5 d4 d3 d2 d1 d0 iorq wr int clk m1 a0 a1 a2 a3 a4 a5 a6 a7".split()
    za = routel('GTL', "iorq wr int clk m1 a0 a1 a2 a3 a4 a5 a6 a7".split())
    zd = routel('GBL', "d7 d6 d5 d4 d3 d2 d1 d0".split())
    zd.w("r 30 f 10 l 30 f 27 / r 90").wire()
    za.w("r 90").wire()

    # PS/2 keyboard: MD-60S from CUI, Future Electronics $1.10
    # 1: DATA  5: CLOCK
    ps2 = MD_60S(brd.DC((6.2, 12)).right(90))
    dc = [ps2.s("5"), ps2.s("1")]
    ps2.s("1").w("f 1").wire()
    ps2.s("3").w("f 0 l 90 f 2 -")
    ps2.s("5").w("f 0.5 r 90 f 2 l 90 f 0.5").wire()
    ps2b = brd.enriver90([t.w("f 4") for t in dc], -90).wire()
    
    zbus = zd.join(za, 0.5).join(ps2b).wire()
    print(len(zbus))

    daz = Dazzler(brd.DC((73, 26)).right(0), "nosw")

    if 0:
        (lvl_a, lvl_d, lvl_b) = cu.M74LVC245(brd.DC((60, 37)).right(45)).escape2()
        lvl_a.w("l 45 f 3").wire()
        lvl_d.setname("VCC").w("o f 0.5").wire()
        lvl_b.w("l 45 r 90 f 5 r 90")
        lvl_b.through()
        lvl_b.through()

    # ------------------------------ dazzler busses
    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")
    ss = [daz.s(str(i)) for i in range(15, 30)]
    [s.forward(1) for s in ss]
    daz1 = brd.enriver90(ss, 90).wire()

    ss = [daz.s(str(i)) for i in range(11, 2, -1)]
    [s.w("i f 1 .").setlayer('GBL').w("f 1") for s in ss]
    daz2 = brd.enriver90(ss, 90)
    daz2.w("l 45 f 15 r 45 f 6 / l 45").wire()

    # ------------------------------ level shifters
    d = brd.DC((25, 42)).right(180)
    asig = []       # FPGA, 3.3V side
    bsig = []       # Z80, 5V side
    for i in range(3):
        (a, b) = TXB0108(d).escape()
        asig = a + asig
        bsig += b
        d.forward(8)
    bbus = brd.enriver90(bsig, -90).wire()

    x = 24 - len(daz1)
    daz1.w("l 90 f 4 l 45").meet(brd.enriver(asig[x:], -45).wire())
    daz2.meet(brd.enriver(asig[:x], -45).wire())

    zbus.meet(bbus)

    # ------------------------------ 5V power
    bus.s("5v").setlayer('GBL').setwidth(1).w("f 2").wire()

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
