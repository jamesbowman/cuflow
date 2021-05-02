import cuflow as cu
import dip
import eagle

class USB(eagle.LibraryPart):
    libraryfile = "10118194-0001LF.lbr"
    partname = "FRAMATOME_10118194-0001LF"
    family = "J"

    def setnames(self):
        [p.setname(nm) for (p,nm) in zip(self.pads, ('5V', 'D-', 'D+', '', 'GND'))]

    def escape(self):
        self.setnames()
        tt = self.pads[1:3]
        [t.w("i f 0.4") for t in tt]
        r0 = self.board.enriver90(tt, 90).wire()
        return (r0, )

class QFN16(cu.Part):
    # FT230X datasheet, figure 9.3 "QFN-16 Package Dimensions"
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 4, 4)

        e = 0.65

        dc.push()
        dc.rect(2.15, 2.15)
        self.pad(dc)
        dc.pop()

        XO = (4.35 - 0.72) / 2
        for i in range(4):
            dc.push()
            dc.goxy(-XO, (3 * e / 2))
            dc.right(180)
            self.train(dc, 4, lambda: self.rpad(dc, 0.3, 0.72), e)
            dc.pop()

            dc.left(90)

class QFN20(cu.Part):
    # https://www.analog.com/media/en/package-pcb-resources/package/pkg_pdf/ltc-legacy-qfn/QFN_20_05-08-1710.pdf
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 4, 4)

        e = 0.5

        dc.push()
        dc.rect(2.45, 2.45)
        self.pad(dc)
        dc.pop()

        XO = (4.50 - 0.70) / 2
        for i in range(4):
            dc.push()
            dc.goxy(-XO, (4 * e / 2))
            dc.right(180)
            self.train(dc, 5, lambda: self.rpad(dc, 0.3, 0.72), e)
            dc.pop()

            dc.left(90)

class FT230X(QFN16):
    def setnames(self):
        names = [
            "GND",
            "VCC",
            "RXD",
            "GND",
            "CTS",
            "CBUS2",
            "USBDP",
            "USBDM",
            "VCC",
            "RESET",
            "5V",
            "CBUS1",
            "CBUS0",
            "GND",
            "CBUS3",
            "TXD",
            "RTS",
        ]
        for (p,nm) in zip(self.pads, names):
            p.setname(nm)

    def escape(self):
        self.setnames()
        pp = self.pads
        for i in (3, 13):
            pp[i].copy().w("i f 1").wire()
        pp[13].w("r 90 f 0.5 -")
        pp[8].goto(pp[9]).wire()
        pp[9].w("o f 0.5").wire()

        self.s("RTS").w("l 90")
        self.s("TXD").w("f 1 l 90")

        sigs = [self.s(nm) for nm in ("TXD", "RTS", "RXD", "CTS")]
        cu.extend2(sigs)
        r0 = self.board.enriver90(sigs, 90).wire()

        sigs = [self.s(nm) for nm in ("USBDP", "USBDM")]
        [t.w("o f 0.3") for t in sigs]
        r1 = self.board.enriver90(sigs, -90).wire()

        return (r0, r1)

class FT231X(QFN20):
    def setnames(self):
        names = [
            "GND",
            "RXD",             # 1
            "RI",             # 2
            "GND",             # 3
            "DSR",             # 4
            "DCD",             # 5
            "CTS",             # 6
            "CBUS2",             # 7
            "USBDP",             # 8
            "USBDM",             # 9
            "VCC",             # 10
            "RESET",             # 11
            "5V",             # 12
            "GND",             # 13
            "CBUS1",             # 14
            "CBUS0",             # 15
            "CBUS3",             # 16
            "TXD",             # 17
            "DTR",             # 18
            "RTS",             # 19
            "VCC",             # 20
        ]
        for (p,nm) in zip(self.pads, names):
            p.setname(nm)

    def escape(self):
        self.setnames()
        pp = self.pads
        for t in pp[1:]:
            if t.name == "GND":
                t.copy().w("i f 1").wire()
                t.w("o -")
        self.s("USBDP").mark()
        return (None, None)

class QFN20(cu.Part):
    # EFM8BB2 datasheet, figure 9.2 "QFN20 Land Pattern"
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 3, 3)

        C1 = 3.1
        C3 = 2.5
        X1 = 0.3
        Y1 = 0.9
        Y3 = 1.8

        dc.push()
        dc.rect(Y3, Y3)
        self.pad(dc)
        dc.pop()

        for i in range(4):
            dc.push()
            dc.goxy(-C3 / 2, C3 / 2).left(90)
            dc.rect(.3, .3)
            self.pad(dc)
            dc.pop()

            dc.push()
            dc.goxy(-C1 / 2, (Y3 - 0.3) / 2)
            dc.right(180)
            self.train(dc, 4, lambda: self.rpad(dc, X1, Y1), 0.5)
            dc.pop()

            dc.left(90)

class EFM8BB2(QFN20):
    def setnames(self):
        names = [
            "GND",
            "P0.1",
            "P0.0",
            "GND",
            "VCC",
            "RST",
            "P2.0",
            "P1.6",
            "P1.5",
            "P1.4",
            "P1.3",
            "P1.2",
            "GND",
            "P1.1",
            "P1.0",
            "P0.7",
            "P0.6",
            "P0.5",
            "P0.4",
            "P0.3",
            "P0.2",
        ]
        for (p,nm) in zip(self.pads, names):
            p.setname(nm)

    def escape1(self):
        self.setnames()

        banks = ([], [], [], [])
        for i,p in enumerate(self.pads[1:]):
            b = i // 5
            if p.name == "xVCC":
                p.forward(0.5).wire()
            elif p.name != "GND":
                p.forward(0.5).wire()
                banks[b].append(p)
        [cu.extend2(b) for b in banks]
        [t.wire() for t in self.pads]
        r0 = brd.enriver90(banks[0], -90).right(90).wire()
        r1 = brd.enriver90(banks[1], 90).wire()
        r0.join(r1).wire()

        return (r0, )

def bb2_breakout():
    brd = cu.Board(
        (30, 30),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    dc = brd.DC((15, 15))
    efm8 = EFM8BB2(dc)
    efm8.setnames()
    outers = []
    for i in range(4):
        dc.left(90)
        d = dc.copy()
        d.forward(9).right(90)
        bar = dip.SIL(d, "5")
        outers += bar.pads

    for a,b in zip(efm8.pads[1:], outers):
        a.forward(1).meet(b)
        nm = a.name.replace("P", "")
        b.copy().w("l 90 f 2").text(nm)

    brd.outline()
    brd.save("bb2_breakout")

def proto1():
    brd = cu.Board(
        (80, 50),
        trace = cu.mil(6),
        space = cu.mil(5) * 2.0,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    tu = brd.DC((1.4, 15))
    usb = USB(tu.copy().right(90))
    (aUSB, ) = usb.escape()

    ft230x = FT231X(tu.goxy(3.5, 8).copy().right(90))
    (aSER, bUSB) = ft230x.escape()
    # cc = [cu.C0402(tu.copy().goxy(-1 + 1.0 * i, -3.6).right(90), "0.1") for i in range(3)]
    # cc[0].pads[1].copy().goto(cc[2].pads[1]).wire()
    # cc[0].pads[1].w("o f 1").wire()

    dc = brd.DC((15, 15))
    efm8 = EFM8BB2(dc)
    efm8.setnames()

    ext = dip.SIL(brd.DC((72, 25)), "6")

    # Routing
    """
    aUSB.w("f 4").meet(bUSB)
    (ft230x.s("5V").setwidth(.2).w("o f .2").
     goto(cc[1].pads[0]).
     goto(cc[2].pads[0]).
     w("l 90 f 1.0 r 90 f 3").
     goto(usb.s("5V").w("f 1").wire())
    ).wire()
    # .wire()
    """

    brd.outline()
    brd.save("udriver")

if __name__ == "__main__":
    # bb2_breakout()
    proto1()
