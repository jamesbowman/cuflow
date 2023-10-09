import sys
from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
import svgout
from dazzler import Dazzler
from collections import defaultdict

import xml.etree.ElementTree as ET
import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so

class LibraryPart(cu.Part):
    libraryfile = None
    partname = None
    use_silk = True
    cut_outline = True
    use_pad_text = True
    def __init__(self, dc, val = None, source = None):
        tree = ET.parse(self.libraryfile)
        root = tree.getroot()
        x_packages = root.find("drawing").find("library").find("packages")
        packages = {p.attrib["name"]:p for p in x_packages}
        self.pa = packages[self.partname]
        cu.Part.__init__(self, dc, val, source)

    def place(self, dc):
        ls = defaultdict(list)
        for c in self.pa:
            attr = c.attrib
            if c.tag == "wire" and attr["layer"] in ("20", "21"):
                (x1, y1, x2, y2) = [float(attr[t]) for t in "x1 y1 x2 y2".split()]
                p0 = dc.copy().goxy(x1, y1)
                p1 = dc.copy().goxy(x2, y2)
                ls[attr["layer"]].append(sg.LineString([p0.xy, p1.xy]))
            elif c.tag == "hole":
                (x, y, drill) = [float(attr[t]) for t in "x y drill".split()]
                p = dc.copy().goxy(x, y)
                dc.board.hole(p.xy, drill)
            elif c.tag == "circle" and attr["layer"] == "51":
                (x, y, radius) = [float(attr[t]) for t in "x y radius".split()]
                p = dc.copy().goxy(x, y)
                dc.board.hole(p.xy, 2 * radius)
            elif c.tag == "smd":
                (x, y, dx, dy) = [float(attr[t]) for t in "x y dx dy".split()]
                p = dc.copy().goxy(x, y)
                p.rect(dx, dy)
                p.setname(attr["name"])
                self.pad(p)
            elif c.tag == "pad":
                (x, y, diameter, drill) = [float(attr[t]) for t in "x y diameter drill".split()]
                nm = attr["name"]

                dc.push()
                dc.goxy(x, y)
                dc.board.hole(dc.xy, drill)
                n = {"circle" : 60, "octagon" : 8, "square" : 4}[attr.get("shape", "circle")]
                p = dc.copy()
                p.n_agon(diameter / 2, n)

                p.setname(nm)
                p.part = self.id
                self.pads.append(p)
                p.contact()

                if self.use_pad_text and nm not in ("RESERVED", ):
                    self.board.annotate(dc.xy[0], dc.xy[1], nm)
                dc.pop()
        brd = self.board
        if self.cut_outline and ls["20"]:
            g = so.linemerge(ls["20"])
            brd.layers['GML'].add(g)
        if self.use_silk and ls["21"]:
            g = so.linemerge(ls["21"]).buffer(self.board.silk / 2)
            self.board.layers['GTO'].add(g)

class ArduinoR3(LibraryPart):
    libraryfile = "adafruit.lbr"
    partname = "ARDUINOR3"
    use_pad_text = False
    family = "J"
    inBOM = False
    def escape(self):
        for nm in ("GND", "GND1", "GND2"):
            self.s(nm).setname("GL2").thermal(1.3).wire(layer = "GBL")

        spi = [self.s(n) for n in "D13 D11 D10 D9 D8 D7 D1".split()]
        for t in spi:
            t.w("r 180 f 2").wire(layer = "GBL")
        spi0 = self.board.enriver90(spi[:4], -90).right(90).wire()
        spi1 = self.board.enriver90(spi[4:], 90).left(90).wire()
        return spi0.join(spi1)
        # self.s("D1").w("r 180 f 2 r 90 f 15 l 90 f 1").wire("GBL")
        # spio1 = cu.River(self.board, [self.s("D0")])
        # return spio.join(spio1).wire()

class SD(LibraryPart):
    libraryfile = "x.lbrSD_TF_holder.lbr"
    partname = "MICROSD"
    source = {'LCSC': 'C91145'}
    inBOM = True
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

class padline(cu.Part):
    family = "J"
    inBOM = False
    def place(self, dc):
        self.train(dc, self.val, lambda: self.rpad(dc, 1.27, 2.54), 2.54)

    def escape(self, a = -45):
        tt = [t.copy().w("i") for t in self.pads][::-1]
        return self.board.enriver(tt, a)

if __name__ == "__main__":
    brd = cu.Board(
        (50, 42),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    daz = Dazzler(brd.DC((68.58 - 43.59, 26.5)).right(180))
    sd = SD(brd.DC((53.6, 16.5)).right(0))
    (lvl_in, lvl_out) = cu.M74LVC245(brd.DC((60, 37)).right(90)).escape()
    shield = ArduinoR3(brd.DC((0, 0)))
    cu.C0402(brd.DC((65, 39.0)), '0.1 uF').escape_2layer()
    cu.C0402(brd.DC((59, 27.5)), '0.1 uF').escape_2layer()

    R1 = cu.R0402(brd.DC((51.5, 46.0)).right(90), '4.7K')
    R2 = cu.R0402(brd.DC((53.0, 46.0)).right(90), '4.7K')
    R1.pads[0].w("o l 90 f 0.5 -")
    daz.s("PGM").w("o f 1 r 90 f 13 r 45 f 5.5 l 45 f 2").wire()
    daz.s("5V").copy().w("i f 6 l 90 f 9.15 l 90 f 11.3 r 90 f 26.9 r 90 f 4").goto(R2.pads[0]).wire()

    def wii(i):
        y = 53.3 / 2 + i * (24.0 / 2)
        return cu.WiiPlug(brd.DC((76, y)).right(90)).escape()
    brd.layers['GML'].union(sg.box(68, 22, 80.8, 30))
    brd.layers['GML'].remove(sg.box(0, 4.5, 2.3, 15))
    brd.keepouts.append(sg.box(71, 22, 80.8, 30))
    wii1 = wii(-1)
    wii2 = wii(1)
    wii1.w("r 90 f 2").wire()
    wii2.w("f 10 r 45 f 4 r 45").wire()
    wii = wii2.join(wii1, 0.5).wire()
    wii.w("f 3").wire()

    for nm in ("G1", "G2", "G3", "G4", "6"):
        sd.s(nm).w("r 90 f 1.5 -")

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
    jtag0.w("f 15 r 45 f 3").meet(jtag1)

    for p,nm in zip(jtag_port.pads, jtag_names):
        p.text(nm)

    uart_names = ('DTR', 'OUT', 'IN', '3V3', 'CTS', 'GND')

    uart0 = daz.escapesM(["1", "2", "3"][::-1], -90).w("r 90").wire()

    uart_port = padline(brd.DC((2.0, 39.0)).left(180).setlayer("GBL"), 6)
    for p,nm in zip(uart_port.pads, uart_names):
        p.text(nm)
    uart_port.pads[5].copy().setname("GL2").w("i f 1").wire()
    tt = [uart_port.pads[i].w("i") for i in (2, 1, 0)]
    uart1 = brd.enriver(tt, 45).w("f 13 r 45").meet(uart0)

    daz_i2cbus = daz.escapesM(["8", "9", "10", "11", "12", "13"][::-1], 90)
    daz_i2cbus.meet(wii)

    daz_spibus = daz.escapes(["23", "24", "25", "26", "27", "28", "29"], 90)
    daz_spibus.w("l 90 f 1 l 90").wire()
    lvl_out.w("f 1.5 l 90").meet(daz_spibus)

    sd.s("4").setname("VCC").w("r 90 f 2").wire()
    for i in range(7):
        src = sd.s("1235789"[i])
        dst = daz.s(str(21 - i))
        src.w("l 90 f 1")
        dst.w("o f .1").wire()
        src.path.append(dst.xy)
        src.wire()

    a_spio = shield.escape()
    shield.s("D12").w("r 180 f 17 l 90").goto(daz.s("22")).wire()
    shield.s("5V").w("f 1.6 r 90 f 7.6 l 90 f 2.4 l 45 f 41 r 45").goto(daz.s("5V")).wire(width = 0.5)

    a_spio.w("f 7 l 90 f 10").meet(lvl_in)

    if 1:
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

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GL2")

    brd.save("arduino_dazzler")
    for n in brd.nets:
        print(n)
    svgout.write(brd, "arduino_dazzler.svg")
