import sys
from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import svgout
from dazzler import Dazzler
from collections import defaultdict

from arduino_dazzler import LibraryPart, padline

class SD(LibraryPart):
    libraryfile = "x.lbrSD_TF_holder.lbr"
    partname = "MICROSD"
    family = "J"

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

if __name__ == "__main__":
    brd = cu.Board(
        (75, 60),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    daz = Dazzler(brd.DC((33, 25)).right(90))
    sd = SD(brd.DC((63, 16.5)).right(90))
    cu.C0402(brd.DC((70, 20)).right(90), '0.1 uF').escape_2layer()
    usb = Amphenol10118194(brd.DC((6, 0)))
    ir = IRMH6XXT(brd.DC((6, 54)))
    irs = ir.escape()

    uart0 = daz.escapesI(["3", "2", "1"], -90).w("r 90").wire()
    uart_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')
    brd.hole((2, 39 + 4), 2.5, 5.5)
    brd.hole((2, 39 - cu.inches(.5) - 4), 2.5, 5.5)
    uart_port = padline(brd.DC((2.0, 39.0)).left(180), 6)
    for p,nm in zip(uart_port.pads, uart_names):
        p.copy().goxy(0, -3).text(nm)
    uart_port.pads[5].copy().w("i -")
    tt = [uart_port.pads[i].w("i") for i in (2, 1, 0)]
    uart1 = brd.enriver(tt, 45).w("f 16 l 45").meet(uart0)

    irs.left(90).goto(daz.s("29")).wire()

    usb.pads[0].left(90).goto(daz.s("5V")).wire(width = 0.4)
    usb.pads[4].setwidth(0.4).w("i -")

    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")

    for nm in ("G1", "G2", "G3", "G4", "6"):
        sd.s(nm).w("r 90 f 1.5 -")

    sd.s("4").setname("VCC").w("r 90 f 2").wire()
    sd1 = brd.enriver([sd.s(c).w("l 90 f 2") for c in "1235789"], 45).w("l 45 f 8").wire()

    sd0 = brd.enriver([daz.s(str(15 + i)) for i in range(7)], 45).w("r 45 f 18 r 90").meet(sd1)

    if 0:
        for i in range(7):
            src = sd.s("1235789"[i])
            dst = daz.s(str(21 - i))
            src.w("l 90 f 1")
            dst.w("o f .1").wire()
            src.path.append(dst.xy)
            src.wire()

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

    brd.save("tt")
    for n in brd.nets:
        print(n)
    svgout.write(brd, "tt.svg")
