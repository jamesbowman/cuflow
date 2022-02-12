import cuflow as cu
import dip
import sot
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
            "RXD",            # 1
            "RI",             # 2
            "GND",            # 3
            "DSR",            # 4
            "DCD",            # 5
            "CTS",            # 6
            "CBUS2",          # 7
            "USBDP",          # 8
            "USBDM",          # 9
            "VCCOUT",         # 10
            "RESET",          # 11
            "5V",             # 12
            "GND",            # 13
            "CBUS1",          # 14
            "CBUS0",          # 15
            "CBUS3",          # 16
            "TXD",            # 17
            "DTR",            # 18
            "RTS",            # 19
            "VCC",            # 20
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
        self.s("VCC").w("o f 0.7 / r 90 f 3 +").wire()

        self.s("VCCOUT").goto(self.s("RESET")).wire()

        self.s("CTS").w("o f 1 r 90 f 3 r 90")
        self.s("RXD").w("o f 1 r 90")
        self.s("TXD").w("o f 1")
        self.s("DTR").w("o f 1")
        tt = [self.s(n).wire() for n in ["TXD", "DTR", "RXD", "CTS"]]
        cu.extend2(tt)
        # [t.wire().text(t.name) for t in tt]
        r0 = self.board.enriver90(tt, 90).wire()

        tt = [self.s(n).w("o f 0.5") for n in ["USBDP", "USBDM"]]
        r1 = self.board.enriver90(tt, -90).wire()
        return (r0, r1)

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
            if p.name == "VCC":
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

    def escape2(self):
        banks = ([], [], [], [])
        for i,p in enumerate(self.pads[1:]):
            b = i // 5
            if p.name == "GND":
                p.copy().w("i f 1").wire()
                p.w("o -")
            elif p.name != "VCC":
                p.forward(1.5).wire()
                banks[b].append(p)
        self.s("VCC").w("o f 0.8 / r 45 f 2 +").wire()
        [cu.extend2(b) for b in banks]
        [t.wire() for t in self.pads]
        rr = [self.board.enriver(bb, a).wire() for a,bb in zip([-45,-45,45,45], banks)]
        rr[0].forward(0.4).left(90)
        a = rr[0].join(rr[1], 1.0)
        b = rr[2].join(rr[3].right(90)).forward(1)
        cu.extend2(a.tt + b.tt)
        r = a.join(b, 0.5).wire()
        return r

class LCD(cu.Part):
    family = "U"
    def place(self, dc):
        self.train(dc, 12, lambda: self.rpad(dc, 0.35, 2.0), 0.7)
        self.pads[0].text("12")
        self.pads[-1].text("1")

    def escape(self):
        tt = [p.copy().w("o") for p in self.pads]
        r = cu.R0402(tt[10].copy().forward(1.5).left(90))
        r.pads[0].goto(tt[10]).wire()
        tt[10] = r.pads[1].w("o f 1")
        cu.extend2(tt)
        return self.board.toriver(tt)

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
        (99, 99),
        trace = cu.mil(5),
        space = cu.mil(5) * 1.6,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    tu = brd.DC((1.4, 80))
    usb = USB(tu.copy().right(90))
    (aUSB, ) = usb.escape()
    usb.pads[4].w("o -")

    ft230x = FT231X(tu.goxy(3.5, 9).copy().right(90))
    (aSER, bUSB) = ft230x.escape()
    cc = [cu.C0402(tu.copy().goxy(2 + 1.0 * i, -4.6).right(90), "0.1") for i in range(4)]
    cc[0].pads[0].copy().goto(cc[1].pads[0]).wire()
    for c in cc[2:]:
        c.pads[0].setname('VCC').w("o f 1").wire()
    for c in cc:
        c.pads[1].w("o -").wire()
    c = cu.C0402(tu.copy().goxy(0.2, -4.6).right(90), "0.1")
    c.pads[0].goto(ft230x.s("RESET")).wire()
    c.pads[1].w("r 90 f 1 -")

    ldo = sot.SOT23(brd.DC((10, 80)).left(90))
    ldo.pads[0].w("i -")
    ldo.pads[1].setname("VCC").w("i f 1").wire()
    ldo.pads[2].setwidth(0.2).goto(usb.pads[0]).wire()

    lcd = LCD(brd.DC((50, 72)).right(90))
    lcd0 = lcd.escape().wire()

    dc = brd.DC((19, 68))
    efm8 = EFM8BB2(dc.right(45))
    efm8.setnames()
    bus0 = efm8.escape2()
    bus0.w("f 1").wire()
    c4 = cu.C0402(brd.DC((19, 72)))
    c4.pads[0].setname('VCC').w("o f 1").wire()
    c4.pads[1].setname('GND').w("o -")

    print([t.name for t in bus0.tt])

    def grid(t):
        t.w(".").setlayer('GTL')
        t.w("r 90 f 0.5").wire()
        if t.name == "VCC":
            t.copy().w("r 90 f 1").wire()
        t.setname("")
        def p(t):
            t.copy().rect(0.5, 0.5).pad()
        p(t)
        t = t.forward(0.5 + 0.125).copy()
        p(t)
        t.w("l 90 f 0.5 r 90").wire()
        return t

    busdip = dip.SIL(brd.DC((97, 28)), "19")
    names = [p.name for p in bus0.tt[::-1]] + ["VCC", "GND"]
    for (a, nm) in zip(busdip.pads, names):
        a.copy().w("r 90 f 2").text(nm)
    tt = [t.copy().setlayer('GBL').right(90) for t in busdip.pads]
    tt[17].setname("VCC")
    tt[18].setname("GND")

    [t.w("f 10").wire() for t in tt]
    struts = []
    [t.newpath() for t in tt]
    for i in range(22):
        [t.w("f 2.54").copy().wire() for t in tt]
        [t.silk() for t in tt]
        s = [grid(t.copy()) for t in tt][-1].w("f 48").wire()
        struts.append(s)
    for (a, nm) in zip(tt, names):
        a.copy().w("f 2").text(nm)
    [t.w("f 10").wire() for t in tt]
    bus1 = brd.enriver90(tt[:17], 90).w("/")
    bus0.meet(bus1)
    # tt[17].w("f 3 +").setname("GL1").thermal(1.3).wire(layer = "GTL")

    ext = dip.SIL(brd.DC((77, 92)).left(90), "6")
    uart_names = ('DTR', 'RXI', 'TXO', '3V3', 'CTS', 'GND')
    for p,nm in zip(ext.pads, uart_names):
        p.copy().w("r 90 f 2").text(nm)

    brk = dip.SIL(struts[11].copy().right(90), "23")
    [t.forward(2.54) for t in struts]
    brk = dip.SIL(struts[11].copy().right(90), "23")
    [t.forward(2.54) for t in struts]

    fps0 = brd.toriver(struts[:6])
    fps0.forward(0).wire()

    fps1 = brd.toriver([p.w("r 90 f 10") for p in ext.pads]).w("f 10").wire()
    fps0.meet(fps1)

    lcd1 = brd.toriver(struts[6:18]).wire()
    lcd0.meet(lcd1)

    # Routing
    aUSB.w("f 4").meet(bUSB)
    # bUSB.w("f 1 r 90 f 1").wire()
    (ft230x.s("5V").setwidth(.2).w("o f 0.9").
     goto(cc[0].pads[0]).
     goto(usb.s("5V").setwidth(.2).w("o f 1.4").wire()).
     wire()
    ).wire()

    bSER = brd.toriver(struts[18:]).wire()
    aSER.w("l 90 f 20 r 90").meet(bSER)

    brd.outline()
    if 0:
        brd.fill_any("GTL", ["GL3", "VCC"])
        brd.fill_any("GBL", ["GL2", "GND"])

    brd.save("udriver")

if __name__ == "__main__":
    # bb2_breakout()
    proto1()

