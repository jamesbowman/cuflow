import sys
from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import svgout
from dazzler import Dazzler
from collections import defaultdict

from arduino_dazzler import LibraryPart, padline
import dip

class SD(LibraryPart):
    libraryfile = "x.lbrSD_TF_holder.lbr"
    partname = "MICROSD"
    family = "J"

def thermal(t, layer, d = 1.3):
    t.setname(layer).thermal(d).wire(layer = layer)

__VERSION__ = "1.0.0"

def gentext(s):
    fn = "../../.fonts/Arista-Pro-Alternate-Light-trial.ttf"
    fn = "../../.fonts/IBMPlexSans-SemiBold.otf"
    font = ImageFont.truetype(fn, 120)
    im = Image.new("L", (2000, 1000))
    draw = ImageDraw.Draw(im)
    draw.text((200, 200), s, font=font, fill = 255)
    return im.crop(im.getbbox())

class IRMH6XXT(cu.Part):
    # https://datasheet.lcsc.com/szlcsc/1810121714_Everlight-Elec-IRM-H638T-TR2_C91447.pdf
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 4, 5)
        for _ in range(2):
            dc.push()
            dc.goxy(-2.7, 1.27).left(180)
            self.train(dc, 2, lambda: self.rpad(dc, 0.7, 1.4), 2.54)
            dc.pop()
            dc.right(180)
    def escape(self):
        self.pads[0].w("i - ")
        self.pads[1].w("i - ")
        self.pads[3].setname("VCC").w("i f 1").wire()
        return self.pads[2]

class Amphenol10118194(cu.Part):
    # https://www.amphenol-icc.com/media/wysiwyg/files/drawing/10118194.pdf
    family = "J"
    def place(self, dc):
        def local(x, y):
            p = dc.copy()
            return p.goxy(x - 25, y - 21)

        def slot(dc, l, r):
            dc.push()
            dc.newpath()
            dc.forward(l / 2)
            dc.right(180)
            dc.forward(l)
            dc.platedslot(r)
            dc.pop()

        self.chamfered(dc.copy().forward(3), 8.0, 6)
        for x in (-3.5, 3.5):
            slot(dc.copy().goxy(x, 1.45), 1.15 - 2 * 0.25, 0.25)
        for x in (-2.5, 2.5):
            slot(dc.copy().goxy(x, 4.15).right(90), 0.85 - 2 * 0.275, 0.275)
        pads = dc.goxy(-2 * 0.65, 4.15).right(90)
        self.train(pads, 5, lambda: self.rpad(dc, 0.40, 1.35), 0.65)

    def escape(self):
        pass

class W65C02S(dip.dip):
    family  = "U"
    width   = cu.inches(.6)
    N       = 40
    def place(self, dc):
        dip.dip.place(self, dc)
        nms = [
            "VPB", "RDY", "PHI1O", "IRQB", "MLB", "NMIB", "SYNC", "VDD", "A0", "A1",
            "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "VSS",
            "A12", "A13", "A14", "A15", "D7", "D6", "D5", "D4", "D3", "D2", "D1",
            "D0", "RWB", "NC", "BE", "PHI2", "SOB", "PHI2C", "RESB" ]
        assert len(nms) == 40

        for p,nm in zip(self.pads, nms):
            p.setname(nm)

        thermal(self.s("VSS"), "GBL")
        tied = "VDD NMIB IRQB RDY SOB".split()
        for t in tied:
            thermal(self.s(t), "GTL")

    def escape(self):
        s1 = [
            "A0", "A1",
            "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11"]
        s2 = [
            "A12", "A13", "A14", "A15", "D7", "D6", "D5", "D4", "D3", "D2", "D1",
            "D0", "RWB", "PHI2", "RESB" ]
        p1 = [self.s(s) for s in s1[::-1]]
        [p.left(90).forward(2) for p in p1]
        r1 = self.board.enriver90(p1, -90).wire()

        p2 = [self.s(s) for s in s2[::-1]]
        [p.left(90).forward(2) for p in p2]
        r2 = self.board.enriver90(p2, 90).wire()

        return r2.join(r1).wire()

if __name__ == "__main__":
    brd = cu.Board(
        (81, 64),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    daz = Dazzler(brd.DC((33, 25)).right(90))
    # cu.C0402(brd.DC((70, 20)).right(90), '0.1 uF').escape_2layer()
    usb = Amphenol10118194(brd.DC((6, 0)))
    mcu = W65C02S(brd.DC((71, 27)))

    uart0 = daz.escapesI(["2", "1"], -90).w("r 90").wire()
    uart_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')
    brd.hole((2, 39 + 4), 2.5, 5.5)
    brd.hole((2, 39 - cu.inches(.5) - 4), 2.5, 5.5)
    uart_port = padline(brd.DC((2.0, 39.0)).left(180), 6)
    for p,nm in zip(uart_port.pads, uart_names):
        p.copy().goxy(0, -3).text(nm)
    uart_port.pads[5].copy().w("i -")
    tt = [uart_port.pads[i].w("i") for i in (2, 1)]
    uart1 = brd.enriver(tt, 45).w("f 16 l 45").meet(uart0)

    usb.pads[0].left(90).goto(daz.s("5V")).wire(width = 0.4)
    usb.pads[4].setwidth(0.4).w("i -")

    d1 = daz.escapes([str(i) for i in range(3, 15)], -90).forward(5).right(45).wire()
    d2 = daz.escapes([str(i) for i in range(15, 30)], 90).forward(4).left(45).wire()
    daz12 = d1.join(d2, 0.5).wire()

    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")

    mcu12 = mcu.escape()
    mcu12.w("f 2 l 90 f 4 l 45").wire()

    mcu12.meet(daz12)

    if 0:
        im = Image.open("img/gameduino-mono.png")
        brd.logo(59, 45, im)

        im = Image.open("img/dazzler-logo.png")
        brd.logo(64, 30, im)

        brd.logo(75.8,  6.2, gentext("PLAYER 1"), scale = 0.4)
        brd.logo(75.8, 46.9, gentext("PLAYER 2"), scale = 0.4)

        brd.logo(76, 53.3 / 2 - 12, gentext("1").transpose(Image.ROTATE_90), scale = 1.0)
        brd.logo(76, 53.3 / 2 + 12, gentext("2").transpose(Image.ROTATE_90), scale = 1.0)

        brd.logo(75.8, 53.3 / 2, Image.open("img/oshw-logo-outline.png").transpose(Image.ROTATE_90), scale = 0.7)

        for i,s in enumerate(["(C) 2020", "EXCAMERA LABS", str(__VERSION__)]):
            brd.annotate(57.5, 8.5 - 1.5 * i, s)

    brd.outline()
    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GL2")

    brd.save("6502")
    for n in brd.nets:
        print(n)
    svgout.write(brd, "6502.svg")
