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

__VERSION__ = "1.0.1"

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
            pad.right(90)
            pad.copy().w("f 4").text(nm)
            p = pad.copy().w("l 45 f 2 r 45 f 5 r 45 f 2").wire()
            dc.board.hole(p.xy, .8)
            p.n_agon(0.8, 60)
            p.contact()
            if nm != "GND":
                pad.setname(nm)

class Teensy40(dip.dip):
    family  = "U"
    width   = cu.inches(.6)
    N       = 28
    def place(self, dc):
        dip.dip.place(self, dc)
        for i in range(24):
            self.pads[i + 1].setname(str(i))
        for n in (0, -2):
            p = self.pads[n]
            p.setname("GL2").thermal(1.3).wire(layer = "GBL")
        self.pads[-1].setname("vin")

class SD(eagle.LibraryPart):
    libraryfile = "x.lbrSD_TF_holder.lbr"
    partname = "MICROSD"
    source = {'LCSC': 'C91145'}
    inBOM = True
    family = "J"

if __name__ == "__main__":
    brd = cu.Board(
        (90, 63),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))
    brd.outline()
    brd.layers['GML'].union(sg.box(-9.8, 0, 0, 16))

    target = sys.argv[1]
    # https://cdn-learn.adafruit.com/assets/assets/000/078/438/original/arduino_compatibles_Feather_M4_Page.png

    daz = Dazzler(brd.DC((28, 38)).left(90))
    if target == "pico":
        pico = Pico(brd.DC((70, 28)))
    elif target == "teensy":
        teensy = Teensy40(brd.DC((70, 28)))
    sd = SD(brd.DC((3, 12)).right(180))

    # ------------------------------ SD
    for nm in ("G1", "G2", "G3", "G4", "6"):
        sd.s(nm).w("r 90 f 1 -")
    sd.s("4").setname("VCC").w("r 90 f 2").wire()

    tt = [sd.s(c) for c in "1235789"]
    [t.left(90).forward(1) for t in tt]
    r0 = brd.enriver90(tt, 90).left(135).wire()

    tt = [daz.s(str(15 + i)) for i in range(7)]
    [t.w("o f .1") for t in tt]
    r1 = brd.enriver90(tt, 90).left(45).meet(r0)

    # ------------------------------ Wii
    def wii(i):
        y = 32.5 + 6 - i * 12
        return cu.WiiPlug(brd.DC((-5, y)).right(270)).escape()
    wii1 = wii(-1)
    wii2 = wii(1)
    wii1.w("r 90 f 2").wire()
    wii2.w("f 10 r 45 f 4 r 45").wire()
    wii = wii2.join(wii1, 0.5).wire()

    tt = [daz.s(str(i)) for i in (13, 12, 11, 10, 9, 8)]
    [t.w("i f 4") for t in tt]
    daz_i2cbus = brd.enriver90(tt, -90).wire()

    wii.w("f 9 r 90 f 3 /").meet(daz_i2cbus)

    # ------------------------------ Dazzler power
    daz.s("VCC").thermal(1).wire()
    for nm in ("GND", "GND1", "GND2"):
        daz.s(nm).inside().forward(2).wire(width = 0.5).w("-")

    daz_used = ("1", "2", "22", "23", "25", "26", "27", "28", "29", "PGM")
    tt = [daz.s(nm) for nm in daz_used]
    [p.w("i f 4").wire() for p in tt]
    daz.s("1").left(90)
    daz.s("2").forward(1).left(90)
    daz.s("PGM").right(90)
    cu.extend2(tt)
    b1 = brd.enriver90(tt[::-1], 90)

    if target == "pico":
        b1.w("l 90 f 2 r 45").wire()
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
        daz.s("5V").setwidth(0.5).w("o f 1 l 90 f 7 r 90 f 14 r 90 f 2.5").goto(pico.s("VBUS")).wire()
    elif target == "teensy":
        b1.w("l 45 f 2 r 45").wire()
        teensy_used = (
            "1", "8", "9", "10", "11", "12",
            "13", "14", "15", "16"
        )
        tt = [teensy.s(str(i)) for i in teensy_used]
        [p.setlayer("GBL").w("l 90 f 2").wire() for p in tt]
        rv0 = brd.enriver90(tt[:6][::-1], -90).wire()
        rv1 = brd.enriver90(tt[6:][::-1], 90).wire()
        b0 = rv1.join(rv0, 1).wire()
        b0.shuffle(b1, {    # Teensy       Dazzler
            "14": "1"  ,    # TX3          CONSOLE IN 
            "15": "2"  ,    # RX3          CONOLE OUT 
            "12": "22" ,    # MISO         MISO       
            "8" : "25" ,    # 8            GPU SEL    
            "9" : "26" ,    # 9            SD SEL     
            "10": "27" ,    # 10           DAZZLER SEL
            "11": "28" ,    # MOSI         MOSI       
            "13": "29" ,    # SCK          SCK        
            "16":"PGM" ,    # 16           PGM        
            "1" : "23" ,    # UART0 TX     UART       
        }).w("f 8").meet(b1)
        daz.s("5V").setwidth(0.5).w("o f 2 r 90 f 38 l 90 f 23").goto(teensy.s("vin")).wire()

    if 1:
        im = Image.open("img/gameduino-mono.png")
        brd.logo(15, 4, im)

        im = Image.open("img/dazzler-logo.png")
        brd.logo(36, 4, im)

        if target == "pico":
            brd.logo(pico.center.xy[0], pico.center.xy[1] - 15, gentext("PICO"))
        elif target == "teensy":
            brd.logo(teensy.center.xy[0], teensy.center.xy[1] - 24, gentext("TEENSY 4.0"))

        brd.logo(-5, 38.5 - 12, gentext("2").transpose(Image.ROTATE_270), scale = 0.9)
        brd.logo(-5, 38.5 + 12, gentext("1").transpose(Image.ROTATE_270), scale = 0.9)

        brd.logo(-4.8, 38.5, Image.open("img/oshw-logo-outline.png").transpose(Image.ROTATE_270), scale = 0.7)

        for i,s in enumerate(["(C) 2021", "EXCAMERA LABS", str(__VERSION__)]):
            brd.annotate(81, 60 - 1.5 * i, s)

    if 1:
        brd.fill_any("GTL", "VCC")
        brd.fill_any("GBL", "GL2")

    name = target + "_dazzler"
    brd.save(name)
    for n in brd.nets:
        print(n)
    svgout.write(brd, name + ".svg")
