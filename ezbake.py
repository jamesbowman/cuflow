import os
import sys
from datetime import datetime
import math
import collections
from collections import defaultdict, namedtuple

from PIL import Image, ImageDraw, ImageFont
import cuflow as cu
import svgout
import dip
import eagle
from dazzler import Dazzler

from arduino_dazzler import LibraryPart
from EDS import EDS

import shapely.geometry as sg

__VERSION__ = "1.0.1"

def gentext(s):
    fn = "../../.fonts/Arista-Pro-Alternate-Light-trial.ttf"
    fn = os.getenv("HOME") + "/.fonts/IBMPlexSans-SemiBold.otf"
    font = ImageFont.truetype(fn, 120)
    im = Image.new("L", (2000, 1000))
    draw = ImageDraw.Draw(im)
    draw.text((200, 200), s, font=font, fill = 255)
    return im.crop(im.getbbox())

I2CBus = namedtuple('I2CBus', ['sda', 'scl'])

# https://cdn-learn.adafruit.com/assets/assets/000/078/438/original/arduino_compatibles_Feather_M4_Page.png
class Feather(dip.dip):
    family = "U"
    width   = cu.inches(.8)
    N       = 32
    N2      = (16, 12)
    def place(self, dc):
        dip.dip.place(self, dc)
        names = "RESET 3V AREF GND A0 A1 A2 A3 A4 A5 SCK MOSI MISO RX TX D4 SDA SCL D5 D6 D9 D10 D11 D12 D13 USB EN BAT"
        for p,nm in zip(self.pads, names.split()):
            p.setname(nm)
        self.s("GND").copy().setname("GL2").thermal(1.3).wire(layer = "GBL")
        self.s("3V").copy().setname("GL3").thermal(1.3).wire(layer = "GTL")
        # pico.s("3V3(OUT)").setname("GL3").thermal(1.3).wire(layer = "GTL")

    def escape(self):
        pp = [p for p in self.pads if p.name not in ("GND", "3V")]
        c = self.board.c
        n = 13
        pivot = pp[n].copy().left(90)  # bottom left pad
        w = pivot.distance(pp[n + 1])

        order = pp[0:14][::-1] + pp[14:][::-1]
        for i,p in enumerate(order):
            dst = pivot.copy().forward((w / 2) - (c * len(order) / 2) + c * i)
            p.goto(dst)
            p.dir = order[0].dir
        r = cu.River(self.board, order)
        return r

    def interface(self, name):
        if name == "analog":
            return "A0"
        return {
            "tx" : "TX",
            "rx" : "RX",
            "sda" : "SDA",
            "scl" : "SCL",
            "sck" : "SCK",
            "mosi" : "MOSI",
            "miso" : "MISO",
            "d5" : "D5",
            "d6" : "D6",
            "d9" : "D9",
            "d10" : "D10",
            "5v" : "BAT",
        }.get(name, name)

class Pico(dip.dip):
    family  = "U"
    width   = 17.78
    N       = 40

    def padfoot(self, p):
        p.stadium(0.8, 60, 1.7)

    def place(self, dc):
        dip.dip.place(self, dc)

        dc.goxy(-dip.T, -(51 / 2 - 1.6)).right(90)
        self.train(dc, 3, self.gh, cu.inches(.1))

        for (i,p) in enumerate(self.pads, 1):
            p.setname(str(i))

        gpins = {3, 8, 13, 18, 23, 28, 33, 38, 42}
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
            "SWCLK",
            "GND",
            "SWDIO",
        ]
        for pad,nm in zip(self.pads, pnames):
            pad.right(90)
            pad.copy().w("f 5").text(nm)
            # p = pad.copy().w("l 45 f 2 r 45 f 5 r 45 f 2").wire()
            # dc.board.hole(p.xy, .8)
            # p.n_agon(0.8, 60)
            # p.contact()
            pad.setname(nm)
        self.s("3V3(OUT)").setname("VCC").thermal(1.3).wire()
        self.pool = {
            "analog" : ["GP26", "GP27", "GP28"],
            "digital" : ["GP10", "GP11", "GP12", "GP13", "GP14"],
            "tx" : ["GP0", "GP8"],
            "rx" : ["GP1", "GP9"],
        }

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

    def interface(self, name):
        if name in self.pool:
            return self.pool[name].pop(0)
        self.pool = {nm:sorted(set(sigs) - {name}) for (nm,sigs) in self.pool.items()}
        return {
            "sda" : "GP14",
            "scl" : "GP15",
            "5v" : "VSYS",
        }.get(name, name)

class QFN56(cu.Part):
    family = "U"
    footprint = "QFN56"
    def place(self, dc):
        # Ground pad
        dc.push()
        dc.rect(3.20, 3.20)
        self.pad(dc)
        dc.via('GL2')
        dc.pop()
        """
        g = 7.15 / 3
        for i in (-g, 0, g):
            for j in (-g, 0, g):
                dc.push()
                dc.forward(i)
                dc.left(90)
                dc.forward(j)
                dc.square(g - 0.5)
                self.pad(dc)
                dc.via('GL2')
                dc.pop()
        self.pads = self.pads[:1]
        """

        # Silk outline of the package
        self.chamfered(dc, 7, 7)

        for i in range(4):
            dc.push()
            w = 6.0 / 2 + 0.875 / 2
            dc.goxy(-w, 5.4 / 2 - 0.10)
            dc.left(180)
            self.train(dc, 14, lambda: self.rpad(dc, 0.20, 0.875), 0.40)
            dc.pop()
            dc.left(90)



def addlabels(part):
    shift = 3
    for pad in part.pads:
        nm = pad.name
        if nm is not None:
            p = pad.copy().right(90)
            p.copy().forward(shift).text(nm)
            shift = {3:4, 4:3}[shift]

class SD(eagle.LibraryPart):
    libraryfile = "x.lbrSD_TF_holder.lbr"
    partname = "MICROSD"
    source = {'LCSC': 'C91145'}
    inBOM = True
    family = "J"

class Distributor(cu.Part):
    family = "J"
    def place(self, dc):
        N = int(self.val)
        brd = self.board
        self.gap = (brd.via / 2) + (brd.via_space) + (brd.trace / 2)
        self.bars = []
        def w():
            self.bars.append(dc.copy().right(90))
            self.pads.append(dc.copy().left(90))
        self.train(dc, N, w, self.gap)
        self.rails = [p.copy().right(180) for p in self.pads]
        self.othernames = ["VH"]

    def escape(self, n):
        return self.pads

    def breakout(self, bus):
        for (pa, ra, nm) in zip(self.pads, self.rails, self.othernames + [t.name for t in bus]):
            pa.name = ra.name = nm

        if 1:
            for i,r in enumerate(self.rails):
                r.forward(2 + 6 * (i % 2))
                r.text(str(r.name))

    def via(self, name, conn):
        (r,b) = {r.name:(r,b) for (r,b) in zip(self.rails, self.bars)}[name]
        (sideways, forward) = r.seek(conn)
        r.copy().forward(forward).via().through().right(90).forward(sideways).wire(width = conn.width)

    def finish(self):
        for b in self.bars:
            b.forward(70).wire()

class ArduinoR3(LibraryPart):
    libraryfile = "adafruit.lbr"
    partname = "ARDUINOR3"
    use_pad_text = True
    cut_outline = False
    family = "J"
    inBOM = False
    def escape(self):
        for nm in ("GND", "GND1", "GND2"):
            self.s(nm).setname("GL2").thermal(1.3).wire(layer = "GBL")


class Protoboard:

    def __init__(self, name = None):
        self.name = name
        self.brd = cu.Board(
            (100, 100),
            trace = 0.127,
            space = 0.127 * 1.3,
            via_hole = 0.3,
            via = 0.6,
            via_space = 0.2,
            silk = cu.mil(6))

        self.upper_edge = 32
        self.lower_edge = 22

    def mcu_feather(self):
        brd = self.brd
        mcu = Feather(brd.DC((16, 73)))
        addlabels(mcu)
        self.common_mcu(mcu, brd.DC((20.6, 38)))

    def mcu_pico(self, flush = False):
        brd = self.brd
        if not flush:
            p = brd.DC((16, 67))
        else:
            p = brd.DC((16, 73.2))
        mcu = Pico(p)
        self.common_mcu(mcu, brd.DC((24, 24)))

    def mcu_rp2040(self):
        brd = self.brd
        p = brd.DC((16, 67))
        mcu = RP2040(p)
        if 0:
            cap = p.copy().forward(8).mark()
            c0 = cu.C0402(cap, '10nF')
            c0.pads[0].w("o -")
            c0.pads[1].setname("VCC").w("o f 1").wire()
        self.common_mcu(mcu, brd.DC((24, 20)))

    def common_mcu(self, mcu, dp):
        mb = mcu.escape()

        du = Distributor(dp, str(len(mb) + 0))
        md = du.escape(len(mb))
        du.breakout(mb)
        self.mcu = mcu
        self.du = du

        [p.wire() for p in mb]

        self.du.finish()
        for a,b in zip(mb, md):
            a.right(90).goto(b).wire()
        # md.meet(mb)
        # mb.wire()

    logo_center = (50, 13)

    def finish(self, mount_holes = True):
        brd = self.brd

        if self.name:
            (x, y) = self.logo_center
            brd.logo(x, y, gentext(self.name), scale = 2.0)
            brd.logo(x, y - 7, gentext(datetime.now().replace(microsecond=0).isoformat()), scale = 0.5)

        brd.outline()

        if mount_holes:
            for x in (4, 100 - 4):
                for y in (4, 100 - 4):
                    brd.hole((x, y), 2.7, 6)

        if 1:
            brd.fill_any("GTL", "VCC")
            brd.fill_any("GBL", "GND")

    def save(self, name):
        brd = self.brd
        brd.save(name)
        svgout.write(brd, name + ".svg")

    def add_module(self, mod, *args):
        mod_signals = mod(*((self, ) + args))

        du = self.du
        mcu = self.mcu

        for (nm, p) in mod_signals:
            i = mcu.interface(nm)
            du.via(i, p)
            print(f"{i:5} {mod.__name__}.{p.name}")

def Module_i2c_pullups_0402(pb):
    brd = pb.brd
    dc = brd.DC((pb.lower_edge + 0, 11)).right(90)
    pb.lower_edge += 4
    r0 = cu.R0402(dc, '4K7')
    dc.forward(2)
    r1 = cu.R0402(dc, '4K7')
    r0.pads[1].setname("GL3").w("o f 1").wire()
    r1.pads[1].setname("GL3").w("o f 1").wire()

    return {"sda": r0.pads[0], "scl": r1.pads[0]}.items()

def Module_EDS(pb):
    brd = pb.brd
    (sda0, scl0) = EDS(brd.DC((pb.lower_edge + 10, 11)).right(90)).escape()
    pb.lower_edge += 20
    [s.w("o f 1 /") for s in (sda0, scl0)]
    return {"sda" : sda0, "scl" : scl0}.items()

def Module_I2C(pb):
    brd = pb.brd
    p = brd.DC((pb.lower_edge + 10, 2))
    pb.lower_edge += 20
    conn = dip.SIL_o(p.copy().right(90), "4")
    names = ['GND', 'VCC', 'SDA', 'SCL']
    [c.setname(nm) for (c, nm) in zip(conn.pads, names)]
    addlabels(conn)
    conn.s("VCC").w("r 90 f 2").wire()
    conn.s("GND").w("/ r 90 f 2").wire()
    return (
        ("sda", conn.s("SDA")),
        ("scl", conn.s("SCL")),
    )

class GPS_NEO_6M(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 27.6, 26.6)
        dc.goxy((26.6/2) + 0.1, -cu.inches(0.2))
        self.train(dc, 5, lambda: self.rpad(dc, 2, 4), cu.inches(0.1))

    def escape(self):
        pp = self.pads
        pp[3].setname("GL2").w("o f 1 -")
        [pp[i].w("o f 1 /") for i in (0, 1, 2, 4)]

def Module_GPS_NEO_6M(pb):
    brd = pb.brd
    m = GPS_NEO_6M(brd.DC((pb.upper_edge + 14, 85)).right(90))
    m.escape()
    pb.upper_edge += 28

    p = m.pads
    return {"digital" : m.pads[0],
            "rx" : m.pads[1],
            "tx" : m.pads[2],
            "5v" : m.pads[4]}.items()

def Module_RYLR896(pb):
    brd = pb.brd
    conn = dip.SIL(brd.DC((pb.upper_edge + 10, 83)).left(90), "6")
    conn.s("1").setname("GL3").thermal(1.3).wire(layer = "GTL")
    conn.s("6").setname("GL2").thermal(1.3).wire(layer = "GBL")
    pb.upper_edge += 20
    return {"tx" : conn.s("3"),
            "rx" : conn.s("4")}.items()

def Module_einks(pb):
    # https://learn.adafruit.com/adafruit-eink-display-breakouts/circuitpython-code-2
    brd = pb.brd
    conn = dip.SIL(brd.DC((pb.upper_edge + 18, 96)).left(90), "13")
    for (i,(p,l)) in enumerate(zip(conn.pads, "VIN 3V3 GND SCK MISO MOSI ECS D/C SRCS SDCS RST BUSY ENA".split())):
        p.copy().right(90).forward(2 + (i & 1)).text(l)
    conn.s("1").setname("GL3").thermal(1.3).wire(layer = "GTL")
    conn.s("3").setname("GL2").thermal(1.3).wire(layer = "GBL")
    pb.upper_edge += 36
    return {"sck"   : conn.s("4"),
            "miso"  : conn.s("5"),
            "mosi"  : conn.s("6"),
            "d9"    : conn.s("7"),
            "d10"   : conn.s("8"),
            "d5"    : conn.s("11"),
            "d6"    : conn.s("12"),
            }.items()


def ldo(p):
    r = cu.SOT223(p)
    p.goxy(-2.3/2, -5.2).w("r 180")
    cu.C0603(p, val = '4.7 uF', source = {'LCSC' : 'C19666'})
    p.forward(2)
    pa = cu.C0603(p, val = '22 uF', source = {'LCSC': 'C159801'}).pads
    pa[0].w("l 90 f 3").wire(width = 0.4)
    pa[1].w("r 90 f 3").wire(width = 0.4)
    return r.escape()

def Module_VIN(pb, sensing = True):
    brd = pb.brd
    x = pb.upper_edge + 5
    pb.upper_edge += 10
    pt = brd.DC((x, 94)).right(180)
    j1 = dip.Screw2(pt)
    j1.s("1").setname("GL2").thermal(1.5).wire(layer = "GBL")
    vin = j1.s("2")

    pt.w("f 14 r 90 f 0.5 l 90")
    L = ldo(pt.copy())
    L[0].copy().goto(vin).wire(width = 0.5)
    L[1].setwidth(0.5).w("o f 1 l 45 f 1 /")

    vinp = vin.copy().w("/ f 1").wire(width = 0.5)
    if not sensing:
        return {"5v" : L[1], "VH" : vinp}.items()

    pt.w("f 7 r 90 f 2 l 90")

    R2 = cu.R0402(pt, '4K7')
    pt.forward(3)
    R1 = cu.R0402(pt, '330')

    R1.pads[1].w("o l 90 f 0.5 -")
    R2.pads[1].w("o").goto(L[0]).wire()
    vsense = R2.pads[0].goto(R1.pads[0]).w("o r 90 f 1 /")
    
    return {"5v" : L[1], "analog" : vsense, "VH" : vinp}.items()

def Module_Battery(pb):
    brd = pb.brd
    x = pb.upper_edge + 5
    pb.upper_edge += 10
    pt = brd.DC((x, 94)).right(180)
    j1 = dip.Screw2(pt)
    j1.s("1").setname("GL2").thermal(1.5).wire(layer = "GBL")
    vin = j1.s("2").wire(width = 0.5)

    return {"5v" : vin}.items()

def Module_7SEG_LARGE(pb):
    brd = pb.brd
    width = cu.inches(0.6) + 1
    conn = dip.SIL(brd.DC((pb.upper_edge + width / 2, 96)).left(90), "6")
    conn.s("1").setname("GL2").thermal(1.3).wire(layer = "GBL")
    for p,nm in zip(conn.pads, ["GND", "LAT", "CLK", "SER", "5V", "12V"]):
        p.copy().right(90).forward(2).text(str(nm))

    pb.upper_edge += width
    return (
            ("digital", conn.s("2")),
            ("digital", conn.s("3")),
            ("digital", conn.s("4")),
            ("5v", conn.s("5")),
            ("VH", conn.s("6")),
           )


class CD40109(cu.TSSOP):
    N = 16
    def escape(self, n):
        names = "VCC ENA A E F B ENB VSS ENC C G NC H D END VDD"
        for p,nm in zip(self.pads, names.split()):
            p.setname(nm)
        enables = set("VCC ENA ENB ENC END".split()[:n])
        for s in "VCC ENA ENB ENC END".split():
            if s in enables | {"VCC"}:
                self.s(s).setname("GL3").w("o f 0.5").wire()
            else:
                self.s(s).w("o -")
        self.s("VSS").w("o -")
        self.s("VDD").w("o f 1.25 /")

        ins = [self.s(c) for c in "ABCD"[:n]]
        outs = [self.s(c) for c in "GHEF"[:n]]

        self.s("A").w("i f 1.5 /")
        self.s("B").w("i f 0.7 /")
        self.s("C").w("i f 0.7 /")
        self.s("D").w("i f 1.5 /")
        self.s("E").w("o f 1 r 90")
        self.s("F").w("o f 2 r 90")
        self.s("H").w("o f 2 l 90")
        self.s("G").w("o f 3 l 90")

        cu.extend2(outs)
        [p.forward(3).wire() for p in outs]
        outs_r = self.board.toriver(outs)
        outs_r.forward(2).wire()

        return {
            'ins': ins,
            'outs': outs_r,
            '5v': self.s("VDD"),
        }

def Module_7SEG_LARGE_LS(pb):
    brd = pb.brd
    width = cu.inches(0.6) + 1
    p = brd.DC((pb.upper_edge + width / 2, 96))
    pb.upper_edge += width
    conn = dip.SIL(p.copy().left(90), "6")

    ls = CD40109(p.w("r 180 f 15  r 90 f 2 l 90   l 180"))
    ls_h = ls.escape(3)

    conn.s("1").setname("GL2").thermal(1.3).wire(layer = "GBL")
    for p,nm in zip(conn.pads, ["GND", "LAT", "CLK", "SER", "5V", "12V"]):
        p.copy().right(90).forward(2).text(str(nm))

    do = [conn.s(c) for c in "234"]
    [p.w("r 90 f 3").wire() for p in do]
    do_r = brd.toriver(do)
    do_r.wire()
    do_r.meet(ls_h["outs"])

    conn.s("5").copy().through().goto(ls_h["5v"]).wire()
    return (
            ("digital", ls_h["ins"][0]),
            ("digital", ls_h["ins"][1]),
            ("digital", ls_h["ins"][2]),
            ("5v", conn.s("5")),
            # ("5v", ls_h["5v"]),
            ("VH", conn.s("6")),
           )

def Module_SwitchInput(pb):
    brd = pb.brd
    width = cu.inches(0.2) + 1
    p = brd.DC((pb.upper_edge + width / 2, 96))
    pb.upper_edge += width
    conn = dip.SIL(p.copy().left(90), "2")
    conn.s("1").setname("GL2").thermal(1.3).wire(layer = "GBL")
    return (
            ("digital", conn.s("2")),
    )

def Module_Serial3(pb):
    # 1 RX
    # 2 TX
    # 3 GND

    brd = pb.brd
    width = cu.inches(0.3) + 2
    p = brd.DC((pb.upper_edge + width / 2, 96))
    pb.upper_edge += width
    conn = dip.SIL_o(p.copy().left(90), "3")
    [c.setname(nm) for (c, nm) in zip(conn.pads, "RX TX GND".split())]
    conn.s("GND").setname("GL2").thermal(1.3).wire(layer = "GBL")
    addlabels(conn)
    return (
            ("rx",      conn.s("RX")),
            ("tx",      conn.s("TX"))
    )

def Module_Serial(pb):
    # 1 DTR
    # 2 RX
    # 3 TX
    # 4 3V3
    # 5 CTS
    # 6 GND

    brd = pb.brd
    width = cu.inches(0.6) + 2
    p = brd.DC((pb.upper_edge + width / 2, 96))
    pb.upper_edge += width
    conn = dip.SIL_o(p.copy().left(90), "6")
    names = ('GND', 'CTS', 'VCC', 'TX', 'RX', 'DTR')
    [c.setname(nm) for (c, nm) in zip(conn.pads, names)]
    addlabels(conn)
    conn.s("GND").mark()
    conn.s("GND").through().thermal(1.3).wire()
    conn.s("VCC").thermal(1.3).wire()
    return (
            ("digital", conn.s("DTR")),
            ("rx",      conn.s("RX")),
            ("tx",      conn.s("TX")),
            ("digital", conn.s("CTS")),
    )

def Module_Serial_Debug(pb):
    # 1 SWCLK
    # 2 RX
    # 3 TX
    # 4 3V3
    # 5 SWDIO
    # 6 GND

    brd = pb.brd
    width = cu.inches(0.6) + 2
    p = brd.DC((pb.upper_edge + width / 2, 96))
    pb.upper_edge += width
    conn = dip.SIL_o(p.copy().left(90), "6")
    names = ['GND', 'SWDIO', 'VCC', 'TX', 'RX', 'SWCLK']
    [c.setname(nm) for (c, nm) in zip(conn.pads, names)]
    addlabels(conn)
    conn.s("GND").through().thermal(1.3).wire()
    conn.s("VCC").thermal(1.3).wire()
    return (
            ("SWCLK",   conn.s("SWCLK")),
            ("rx",      conn.s("RX")),
            ("tx",      conn.s("TX")),
            ("SWDIO",   conn.s("SWDIO")),
    )

def Module_LCD240x240_breakout(pb):
    # 1 GND
    # 2 VCC
    # 3 SDL
    # 4 SDA
    # 5 RES
    # 6 DC
    # 7 BLK

    brd = pb.brd
    width = cu.inches(0.6) + 3
    p = brd.DC((pb.upper_edge + width / 2, 80))
    pb.upper_edge += width
    conn = dip.SIL_o(p.copy().left(90), "7")
    h = 39
    conn.chamfered(p.copy().forward(-(39 / 2 - 1.6)), 28, 39)
    [c.setname(nm) for (c, nm) in zip(conn.pads, "GND 3V3 SDL SDA RES DC BLK".split())]
    conn.s("GND").through().thermal(1.3).wire()
    conn.s("3V3").setname("VCC").thermal(1.3).wire()
    return (
            ("GP14", conn.s("SDL")),
            ("GP15", conn.s("SDA")),
            ("GP11", conn.s("RES")),
            ("GP10", conn.s("DC")),
    )

class ST7789_12(cu.Part):
    family = "U"
    def place(self, dc):
        dc.right(90)
        self.train(dc, 12, lambda: self.rpad(dc, .35, 2), 0.7)

#  1 GND        GND
#  2 LEDK       GND
#  3 LEDA       LEDA
#  4 VDD        VCC
#  5 GND        GND
#  6 GND        GND
#  7 D/C        D/C
#  8 CS         GND
#  9 SCL        SCL
# 10 SDA        SDA
# 11 RESET      RESET
# 12 GND        GND


def Module_LCD240x240(pb):
    brd = pb.brd
    width = 23.4
    p = brd.DC((pb.upper_edge + width / 2 - 7.7 / 2, 70))
    pb.upper_edge += width
    c = ST7789_12(p.copy())
    # https://www.aliexpress.us/item/3256803568692645.html
    #                           12   11  10   9   8   7   6   5   4   3   2     1
    #                               LEDK LEDA                 CS
    for (p, nm) in zip(c.pads, "GND  GND LEDA  VCC GND GND D/C GND SCL SDA RESET GND".split()):
        p.setname(nm)

    c.pads[11].copy().w("f 2").text("1")
    c.pads[ 0].copy().w("f 2").text("12")
    for (i,p) in enumerate(c.pads):
        if p.name == "VCC":
            p.w("f 2").wire()
        elif p.name == "LEDA":
            p.w("r 180 f 6 r 90 f 20").wire()
            dc = p.copy().forward(3).right(90)
            r0 = cu.R0402(dc, '4K7')
            r0.pads[1].goto(p).wire()
            r0.pads[0].w("o f 2").setname("VCC").wire()
        else:
            p.w(f"f {2+i%2} /")
            if p.name == "GND":
                p.forward(1).wire()
    return (
            ("GP14", c.s("SCL")),
            ("GP15", c.s("SDA")),
            ("GP11", c.s("RESET")),
            ("GP10", c.s("D/C")),
    )

# https://www.aliexpress.com/i/2251832118582843.html?gatewayAdapt=4itemAdapt

# https://download.riverdi.com/ZIF0520DH-CF25/DS_ZIF0520DH-CF25.pdf

class RibusHost(cu.Part):
    family = "J"
    def place(self, dc):
        dc.right(90)
        cc = dc.copy()
        self.train(dc, 20, lambda: self.rpad(dc, .3, 1.2), 0.5)
        for (i, dx) in ((0, 1), (19, -1)):
            for dy in (-1, 1):
                p = self.pads[i].copy()
                p.goxy(0, dy * 0.6)           # End of pad
                p.goxy(dx * 0.8, dy * 1.2)    # pad-to-foot gap
                p.goxy(dx * 1, dy * 0.9)      # center of foot
                self.rpad(p, 1.8, 2)
        A = 19 * 0.5
        B = A + 4.6
        cc.left(90).goxy(.5 * 9.5, 3.4)
        self.chamfered(cc, B, 5.8)

def Module_Ribus(pb):
    brd = pb.brd
    width = 30
    p = brd.DC((pb.upper_edge + width / 2, 50))
    pb.upper_edge += width
    c = RibusHost(p.copy().right(0))

    names = (
        'VCC',
        'GND',
        'SCLK',
        'MISO',
        'MOSI',
        'CS',
        'NC',
        'PD',
        'GPIO.0',
        'DISP_AUDIO',
        'GPIO.1',
        'GPIO.2',
        'DTR',
        'RTS',
        'RX',
        'TX',
        'BLVDD1',
        'BLVDD2',
        'GND',
        'GND')

    assert len(names) == 20

    for (p, nm) in zip(c.pads, names):
        p.setname(nm)

    hookups = {
        "PD"     : "GP8",
        "CS"     : "GP9",
        "SCLK"   : "GP10",
        "MOSI"   : "GP11",
        "MISO"   : "GP12",
        "BLVDD2" : "VSYS",
    }

    c.pads[ 0].copy().w("f 2").text("1")
    c.pads[19].copy().w("f 2").text("20")
    for (i,p) in enumerate(c.pads):
        if p.name == "VCC":
            p.w("f 2").wire()
        elif p.name == "GND":
            p.w(f"r 180 f {2+i%2} /")
            p.forward(1).wire()
        elif p.name in hookups:
            p.w(f"f {2+i%2} /")
    c.s("BLVDD1").goto(c.s("BLVDD2")).wire()

    return [(busname, c.s(myname)) for (myname, busname) in hookups.items()]

def gen():
    brd = cu.Board(
        (100, 100),
        trace = 0.127,
        space = 0.127 * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = 0.2,
        silk = cu.mil(6))
    brd.outline()

    for x in (4, 100 - 4):
        for y in (4, 100 - 4):
            brd.hole((x, y), 2.7, 6)

    shield = ArduinoR3(brd.DC((110, 70)).right(180))
    shield.escape()

    (sda0, scl0) = EDS(brd.DC((26, 15)).right(90)).escape()

    mcu = Feather(brd.DC((16, 73)))
    addlabels(mcu)
    mb = mcu.escape()

    du = Distributor(brd.DC((20.6, 38)))
    md = du.escape()

    # mb.w("f 1 r 90 f 1 l 90").wire()
    md.wire()
    md.meet(mb)
    mb.wire()
    
    du.breakout(mb)

    [s.w("o f 1 /") for s in (sda0, scl0)]

    du.via("SDA", sda0)
    du.via("SCL", scl0)

    for (sig, ardsig) in [
        ("SCK", "D13"),
        ("MISO", "D12"),
        ("MOSI", "D11"),
        ("D4", "D8"),
        ("D5", "D9"),
        ("USB", "5V"),
        ]:
        du.via(sig, shield.s(ardsig))

    if 1:
        brd.fill_any("GTL", "GL3")
        brd.fill_any("GBL", "GL2")

    for i,s in enumerate(["(C) 2022", "EXCAMERA LABS", str(__VERSION__)]):
        brd.annotate(81, 60 - 1.5 * i, s)

    name = "ezbake"
    brd.save(name)
    svgout.write(brd, name + ".svg")

def feather_eink():
    pb = Protoboard()
    if 0:
        pb.mcu_feather()
        pb.add_module(Module_i2c_pullups_0402)
    else:
        pb.mcu_pico()
    for i in range(1):
        pb.add_module(Module_EDS)
    # pb.add_module(Module_VIN)
    pb.add_module(Module_einks)
    # pb.add_module(Module_RYLR896)
    pb.finish()
    pb.save("ezbake")

def coop_monitor():
    pb = Protoboard()
    pb.mcu_pico()
    for i in range(1):
        pb.add_module(Module_EDS)
    pb.add_module(Module_VIN)
    pb.add_module(Module_RYLR896)
    pb.finish()
    pb.save("ezbake")

def large_clock():
    pb = Protoboard()
    pb.mcu_pico()
    pb.add_module(Module_VIN, False)
    pb.add_module(Module_GPS_NEO_6M)
    pb.add_module(Module_7SEG_LARGE_LS)
    pb.add_module(Module_SwitchInput)
    pb.finish()
    pb.save("ezbake")

def remote_i2c():
    # https://www.reddit.com/r/raspberrypipico/comments/xalach/measuring_vsys_on_pico_w/
    nm = "remote_i2c"
    pb = Protoboard(nm)
    pb.logo_center = (60, 60)
    pb.mcu_pico()
    pb.add_module(Module_i2c_pullups_0402)
    for i in range(3):
        pb.add_module(Module_EDS)

    pb.add_module(Module_Battery)
    pb.add_module(Module_Serial3)
    pb.add_module(Module_RYLR896)
    pb.finish()
    pb.save(nm)

def td2_a():
    nm = "td2_a"
    pb = Protoboard(nm)
    pb.mcu_pico()
    # pb.add_module(Module_Serial_Debug)
    pb.add_module(Module_LCD240x240_breakout)
    pb.add_module(Module_Serial)
    pb.finish()
    pb.save(nm)

def td2_b():
    nm = "td2_b"
    pb = Protoboard(nm)
    pb.mcu_pico()
    if 1:
        pb.add_module(Module_Serial_Debug)
    if 1:
        pb.add_module(Module_LCD240x240)
        pb.add_module(Module_Serial)
    pb.finish()
    pb.save(nm)

def td2_c():
    nm = "td2_c"
    pb = Protoboard(nm)
    pb.mcu_rp2040()
    if 0:
        pb.add_module(Module_Serial_Debug)
        pb.add_module(Module_LCD240x240)
        pb.add_module(Module_Serial)
    pb.finish()
    pb.save(nm)

def scanalyzer1():
    # https://www.reddit.com/r/raspberrypipico/comments/xalach/measuring_vsys_on_pico_w/
    nm = "scanalyzer1"
    pb = Protoboard(nm)
    pb.logo_center = (60, 70)
    pb.mcu_pico(flush = True)
    pb.add_module(Module_i2c_pullups_0402)
    pb.add_module(Module_EDS)
    pb.add_module(Module_I2C)
    pb.add_module(Module_EDS)

    pb.add_module(Module_Serial_Debug)
    pb.add_module(Module_Ribus)

    pb.finish(mount_holes = False)
    pb.save(nm)


if __name__ == "__main__":
    large_clock()
    # td2_b()
    # remote_i2c()
    # scanalyzer1()
