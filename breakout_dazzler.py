import sys
from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import svgout
from dazzler import Dazzler, DazzlerSocket
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

labels = {
 1   : "< CONSOLE IN",
 2   : "> CONSOLE OUT",
 8   : "> P2 SCL",
 9   : "< P2 DETECT",
 10  : "> P2 SDA",
 11  : "> P1 SCL",
 12  : "< P1 DETECT",
 13  : "> P1 SDA",
 17  : "< SD MISO",
 18  : "> SD SCK",
 19  : "> SD MOSI",
 20  : "> SD CS",
 22  : "> MISO",
 23  : "< UART",
 25  : "< GPU SEL",
 26  : "< SD SEL",
 27  : "< DAZZLER SEL",
 28  : "< MOSI",
 29  : "< SCK",
}

if __name__ == "__main__":
    brd = cu.Board(
        (76, 76),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    daz = Dazzler(brd.DC((33, 25)).right(90))
    daz.labels()
    # cu.C0402(brd.DC((70, 20)).right(90), '0.1 uF').escape_2layer()

    tt = [daz.s(nm).copy().inside() for nm in ("2", "1")]
    uart0 = brd.enriver(tt, 45).wire()

    conn = dip.SIL(brd.DC((66.5, 38)).left(180), "29")
    [p.setname(str(i)) for (i, p) in enumerate(conn.pads, 1)]
    for p in conn.pads:
        p.copy().goxy(-3, 0).text(str(p.name))
        l = labels.get(int(p.name), "")
        if l:
            p.copy().goxy(1, 0).ltext(l)
    [p.left(90) for p in conn.pads]
    # connb0 = brd.enriver(conn.pads[0:14][::-1], 45).wire()
    # connb1 = brd.enriver(conn.pads[14:][::-1], 45).wire()
    for i in range(1, 15):
        nm = str(i)
        conn.s(nm).forward(2).meet(daz.s(nm).outside().forward(2).wire())
    tt = [daz.s(str(i)) for i in range(15, 30)]
    for i,t in enumerate(tt):
        t.forward(1 + i * 1.2).right(90).forward(8.5)
    cu.extend2(tt)
    [t.meet(conn.s(t.name).forward(2).wire()) for t in tt]


    def gnd(s):
        s.setname("GL2").thermal(1.1).wire(layer = "GBL")

    # ------------------------------ FTDI conn
    ftdi = dip.SIL(brd.DC((3, 65)).right(0), "6")
    ftdi_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')
    for p,nm in zip(ftdi.pads, ftdi_names):
        p.setname(nm)
        p.copy().w("l 90 f 2").ltext(nm)
    gnd(ftdi.s("GND"))
    uart1 = brd.enriver([ftdi.pads[t].setlayer('GBL').left(90) for t in (2, 1)], 45).forward(10).wire()
    uart0.w("f 1 / f 50").wire()
    uart1.meet(uart0)

    # ------------------------------ JTAG conn
    jtag = dip.SIL(brd.DC((3, 38 - cu.inches(.1))).right(0), "7")
    jtag_names = ('TMS', 'TCK', 'TDO', 'TDI', 'PGM', 'GND', 'VCC')
    for p,nm in zip(jtag.pads, jtag_names):
        p.setname(nm)
        p.copy().w("l 90 f 2").ltext(nm)
    gnd(jtag.s("GND"))
    jtag.s("VCC").thermal(1).wire()
    for nm in jtag_names[:5]:
        daz.s(nm).forward(2).meet(jtag.s(nm).w("l 45 f 1 l 45 f 4").wire())

    # ------------------------------ 5V power
    pwr5 = dip.SIL(brd.DC((3, 16 - cu.inches(0.05))).right(0), "2")
    for p,nm in zip(pwr5.pads, ("5V", "GND")):
        p.setname(nm)
        p.copy().w("l 90 f 2").ltext(nm)
    gnd(pwr5.s("GND"))
    pwr5.s("5V").setwidth(0.4).meet(daz.s("5V"))

    # d1 = daz.escapes([str(i) for i in range(1, 15)], -90).forward(5).right(45).wire()
    # d2 = daz.escapes([str(i) for i in range(15, 30)], 90).forward(4).spread(1.2).wire()
    # daz12 = d1.join(d2, 0.5).wire()

    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")

    brd.outline()
    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GL2")

    if 1:
        im = Image.open("img/dazzler-logo.png").transpose(Image.ROTATE_270)
        brd.logo(13, 64, im)
        im = Image.open("img/gd3x-logo.png")
        brd.logo(15.7, 71.2, im, 0.8)
        im = Image.open("img/oshw-logo-outline.png")
        brd.logo(6, 5, im, 0.5)

    brd.save("breakout_dazzler")
    for n in brd.nets:
        print(n)
    svgout.write(brd, "breakout_dazzler.svg")
