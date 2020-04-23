import sys
from PIL import Image
import math
import cuflow as cu
import svgout

__VERSION__ = "0.2.0"

class Dazzler(cu.Part):
    family = "M"
    def place(self, dc):
        def local(x, y):
            p = dc.copy()
            return p.goxy(x - 25, y - 21)

        self.chamfered(dc, 50, 42)
        hdmi = local(45, 33.5).right(270)
        hdmi.rect(15, 11.1)
        hdmi.silk()
        self.hdmi_holes(hdmi)

        def padline(dc, n):
            self.train(dc, n, lambda: self.rpad(dc, 1, 1), 2.00)

        padline(local(34, 42).left(90), 15)
        padline(local(0, 36).left(180), 16)
        padline(local(8, 0).right(90), 4)
        padline(local(30, 0).right(90), 3)

        def sr(a,b):
            return [str(i) for i in range(a, b)]
        names = (sr(1, 8) + ["GND1"] +
            sr(8, 23) + ["GND2"] +
            sr(23, 30) +
            ["TMS", "TCK", "TDO", "TDI", "VCC", "GND", "5V"])
        [p.setname(nm) for (p, nm) in zip(self.pads, names)]
        # (p0, p1) = cu.Castellation(brd.DC((34, 42)).left(90), 15).escape()
        # (p2, p3) = cu.Castellation(brd.DC((0, 36)).left(180), 16).escape()
        # p4 = cu.Castellation(brd.DC((8, 0)).right(90), 4).escape1()
        # v5 = cu.Castellation(brd.DC((30, 0)).right(90), 3).escape2()

        brd = self.board
        brd.hole(local(47.2, 2.8).xy, 2.5, 5)
        brd.hole(local(2.8, 42 - 2.8).xy, 2.5, 5)
        brd.hole(local(2.8, 2.8).xy, 2.5, 5)

    def hdmi_holes(self, dc):

        dc.right(90)
        dc.forward(14.5 / 2)
        dc.left(90)
        dc.forward(5.35 + 1.3 - 2.06)
        dc.right(180)
        def holepair():
            dc.push()
            self.board.hole(dc.xy, 2.4)
            dc.forward(5.96)
            self.board.hole(dc.xy, 1.4)
            dc.pop()
        holepair()
        dc.right(90)
        dc.forward(14.5)
        dc.left(90)
        holepair()
        dc.forward(5.96 + 3.6)
        dc.left(90)

    def escapes(self, padnames, a):
        board = self.board
        g = [self.s(nm) for nm in padnames]
        [t.outside().forward(board.c) for t in g]
        return board.enriver90(g, a).wire()

    def escapesM(self, padnames, a):
        board = self.board
        g = [self.s(nm) for nm in padnames]
        [t.inside().forward(1).wire().via('GBL').setlayer('GBL').forward(0.8) for t in g]
        return board.enriver90(g, a).wire()

if __name__ == "__main__":
    brd = cu.Board(
        (50, 42),
        trace = cu.mil(3.5),
        space = cu.mil(3.5) * 1.0,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    brd.hole((47.2, 2.8), 2.5, 5)
    brd.hole((2.8, 42 - 2.8), 2.5, 5)
    brd.hole((2.8, 2.8), 2.5, 5)

    dc = brd.DC((40, 10))
    dc.push()
    dc.right(270)
    u1 = cu.BT815(dc)
    dc.left(225)
    (bt815_qspi, bt815_main) = u1.escape()

    dc.w("f 9.7 l 90 f 3.0 r 90")
    u2 = cu.W25Q64J(dc)
    fl1_qspi = u2.escape()

    bt815_qspi.left(45)
    bt815_qspi.wire()
    bt815_qspi.meet(fl1_qspi)
    dc.pop()
    # dc.w("l 90 f 19.3 r 90 f 13.94 l 90")
    dc.w("l 45 f 24.3 l 90 f 2.95 r 45")

    lx9 = cu.XC6LX9(dc)
    (fpga_main, fpga_lvds, fpga_p0, fpga_p1, fpga_p23, fpga_fl, fpga_jtag, fpga_v12) = lx9.escape()

    j1 = cu.HDMI(brd.DC((45,33.5)).right(270))
    (hdmi_lvds, hdmi_detect) = j1.escape()

    (p0, p1) = cu.Castellation(brd.DC((34, 42)).left(90), 15).escape()
    (p2, p3) = cu.Castellation(brd.DC((0, 36)).left(180), 16).escape()
    p4 = cu.Castellation(brd.DC((8, 0)).right(90), 4).escape1()
    v5 = cu.Castellation(brd.DC((30, 0)).right(90), 3).escape2()

    p_fl_f = cu.W25Q64J(brd.DC((35, 23)).left(45))
    fl2_qspi = p_fl_f.escape1()

    def ldo(p):
        r = cu.SOT223(p)
        p.goxy(-2.3/2, -5.2).w("r 180")
        cu.C0603(p, val = '4.7uF', source = {'LCSC' : 'C19666'})
        p.forward(2)
        pa = cu.C0603(p, val = '22uF', source = {'LCSC': 'C159801'}).pads
        pa[0].w("l 90 f 3").wire(width = 0.4)
        pa[1].w("r 90 f 3").wire(width = 0.4)
        return (r, r.escape())

    (ldo12, (t, _)) = ldo(brd.DC((12, 6)).right(90))
    t.outside().fan(1.0, 'GL3')
    ldo12.mfr = 'LM1117S-1.2'
    ldo12.source = {'LCSC': 'C126025'}

    p = brd.DC((25, 6)).right(90)
    (ldo33, (_, vcc)) = ldo(p)
    ldo33.mfr = 'ZLDO1117QG33TA'
    ldo33.source = {'LCSC': 'C326523'}

    vcc.fan(1.5, 'GL3')

    # Connect the LVDS pairs
    for b in range(4):
        fpga_lvds[b].w("f 0.5 l 45").forward(b + 1).w("l 45 f 3").wire()
        hdmi_lvds[b].w("f 0.5").wire()
    # [h.meet(f) for (h, f) in zip(hdmi_lvds, fpga_lvds)]
    [f.meet2(h) for (h, f) in zip(hdmi_lvds, fpga_lvds)]

    fpga_p0.w("f 2.5").meet(p0)
    fpga_p1.w("f 2.5").meet(p1)

    fpga_p23.right(90).wire()
    (fpga_p2,fpga_p3) = fpga_p23.split(8)
    # fpga_p2.w("r 45 f 1 l 45").wire()
    fpga_p3.w("f 2").wire()

    fpga_p2.forward(1).meet(p2)
    fpga_p3.meet(p3)

    fpga_main.meet(bt815_main)

    # Bottom-layer hookups

    fpga_fl.meet(fl2_qspi)
    p4.w("r 45 f 1 l 45 f 4 l 45 f 1 r 45").wire()
    fpga_jtag.meet(p4)

    # 5V to the LDO
    v5.w("i f 1.4 l 90 f 12 r 90 f 1").wire(width = 0.8)

    # FPGA 1.2 V supply
    t = fpga_v12
    t.w("f 4 r 90 f 5 l 90").wire(width = 0.8)
    t.via()
    t.w("f 2").wire('GTL')

    # HDMI detect
    t = hdmi_detect
    t.w("o f 1").wire()
    r = cu.R0402(t.copy().w("f 2 r 45"), "10K")
    t.goto(r.pads[0]).wire()
    r.pads[1].w("o -").wire()

    def caps(dc, l0, l1, n = 1):
        for i in range(n):
            cu.C0402(dc, '0.1 uF').escape(l0, l1)
            dc.forward(1)

    caps(brd.DC((18.4, 34.5)), 'GL2', 'GBL', 3)
    caps(brd.DC((27.6, 34.5)), 'GL2', 'GL3', 3)
    caps(brd.DC((11.0, 31.0)).left(90), 'GL2', 'GL3')
    caps(brd.DC((30.3, 20.0)).right(90), 'GL2', 'GL3')
    caps(brd.DC((13.0, 14.7)).right(90), 'GL3', 'GL2')
    caps(brd.DC((18.8, 11.0)), 'GL2', 'GBL')

    caps(brd.DC((46.6, 8.2)), 'GBL', 'GL2', 2)
    caps(brd.DC((43.7, 2.8)).left(90), 'GL2', 'GBL', 2)
    caps(brd.DC((32.9, 4.2)).left(180), 'GBL', 'GL2')

    caps(brd.DC((37.0, 1.0)), 'GL2', 'GL3', 3)
    caps(brd.DC((47.7, 14.2)).right(90), 'GL2', 'GL3', 2)

    brd.outline()
    # brd.oversize(2)
    brd.fill()
    brd.check()

    if 1:
        im = Image.open("img/dazzler-logo.png").transpose(Image.ROTATE_270)
        brd.logo(6.9, 28.8, im)
        im = Image.open("img/gd3x-logo.png")
        brd.logo(9.5, 36, im, 0.8)
        im = Image.open("img/oshw-logo-outline.png")
        brd.logo(6.9, 13.6, im, 0.5)

        x = j1.center.xy[0] + 0.5
        for i,s in enumerate(["(C) 2020", "EXCAMERA LABS", str(__VERSION__)]):
            brd.annotate(x, 35.3 - 1.5 * i, s)

    brd.save("dazzler")
    svgout.write(brd, "dazzler.svg")
    lx9.dump_ucf("dazzler")

    for f,pp in brd.parts.items():
        print(f)
        for p in pp:
            if p.inBOM:
                if len(p.source) > 0:
                    vendor = list(p.source.keys())[0]
                    vendor_c = p.source[vendor]
                else:
                    (vendor, vendor_c) = ('', '')
                print("    %3s  %20s %20s %10s  %10s %20s" % (p.id, p.mfr, p.footprint, p.val, vendor, vendor_c))
