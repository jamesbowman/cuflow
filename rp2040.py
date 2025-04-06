import cuflow as cu

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
                # dc.setname("GND")
                self.pad(dc)
                # dc.via('GBL')
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

RP2040pins = [
    (0, "GND"),             
    (1, "IOVDD"),
    (2, "GPIO0"),
    (3, "GPIO1"),
    (4, "GPIO2"),
    (5, "GPIO3"),
    (6, "GPIO4"),
    (7, "GPIO5"),
    (8, "GPIO6"),
    (9, "GPIO7"),
    (10, "IOVDD"),
    (11, "GPIO8"),
    (12, "GPIO9"),
    (13, "GPIO10"),
    (14, "GPIO11"),
    (15, "GPIO12"),
    (16, "GPIO13"),
    (17, "GPIO14"),
    (18, "GPIO15"),
    (19, "TESTEN"),
    (20, "XIN"),
    (21, "XOUT"),
    (22, "IOVDD"),
    (23, "DVDD1"),
    (24, "SWCLK"),
    (25, "SWD"),
    (26, "RUN"),
    (27, "GPIO16"),
    (28, "GPIO17"),
    (29, "GPIO18"),
    (30, "GPIO19"),
    (31, "GPIO20"),
    (32, "GPIO21"),
    (33, "IOVDD"),
    (34, "GPIO22"),
    (35, "GPIO23"),
    (36, "GPIO24"),
    (37, "GPIO25"),
    (38, "GPIO26/ADC0"),
    (39, "GPIO27/ADC1"),
    (40, "GPIO28/ADC2"),
    (41, "GPIO29/ADC3"),
    (42, "IOVDD"),
    (43, "ADC_AVDD"),
    (44, "VREG_VIN"),
    (45, "VREG_VOUT"),
    (46, "USB_DM"),
    (47, "USB_DP"),
    (48, "USB_VDD"),
    (49, "IOVDD"),
    (50, "DVDD2"),
    (51, "QSPI_SD3"),
    (52, "QSPI_SCLK"),
    (53, "QSPI_SD0"),
    (54, "QSPI_SD2"),
    (55, "QSPI_SD1"),
    (56, "QSPI_SS_N")
]

class RP2040(QFN56):
    source = {'LCSC': 'C2040'}
    mfr = 'RP2040'
    footprint = "LQFN-56(7x7)"
    def escape(self, used_pins):
        brd = self.board
        for i,nm in RP2040pins:
            self.pads[i].setname(nm)
        for p in self.pads:
            nm = p.name
            if nm in ("IOVDD", "VREG_VIN", "USB_VDD", "RUN", "ADC_AVDD"):
                if False and nm in ("IOVDD", ):
                    r = cu.C0402(p.copy().w("f 3 l 90"), '.1nF')
                    p.goto(r.pads[0])
                    r.pads[1].w("o -")
                else:
                    p.w("o f .3 ")
                p.setname("VCC").wire()

        vreg_vout = self.s("VREG_VOUT").copy()
        vreg_vout.w("i f .3").wire()
        vreg_vout.copy().goto(self.s("DVDD2"), False).wire()
        vreg_vout.w("f 0.6 l 90 f 0.2 r 90 f 4.4").goto(self.s("DVDD1")).wire()

        self.s("TESTEN").w("i f 2")

        banks = ([], [], [], [])
        for i,p in enumerate(self.pads[1:]):
            b = i // 14
            if p.name in used_pins:
                p.w("o").wire()
                banks[b].append(p)
        [cu.extend2(b) for b in banks if b]
        [t.wire() for t in self.pads]
        return banks

        rr = [self.board.enriver(bb, a).wire() for a,bb in zip([-45,-45,45,45], banks)]
        rr[0].forward(0.4).left(90)
        a = rr[0].join(rr[1], 1.0)
        b = rr[2].join(rr[3].right(90)).forward(1)
        cu.extend2(a.tt + b.tt)
        r = a.join(b, 0.5).right(45).wire()
        print(r)
        return []
        return r
