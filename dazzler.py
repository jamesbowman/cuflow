import math
import cuflow as cu

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
    brd.hole((8, 35), 2.5, 5)

    dc = brd.DC((40, 10))
    dc.push()
    dc.right(270)
    u1 = cu.BT815(dc)
    dc.left(225)
    (bt815_qspi, bt815_main) = u1.escape()

    dc.w("f 9.7 l 90 f 3.0 r 90")
    u2 = cu.W25Q16J(dc)
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
    p4 = cu.Castellation(brd.DC((6, 0)).right(90), 4).escape1()
    v5 = cu.Castellation(brd.DC((30, 0)).right(90), 3).escape2()

    p_fl_f = cu.W25Q16J(brd.DC((35, 23)).left(45))
    fl2_qspi = p_fl_f.escape1()
    ldo12 = cu.SOT223(brd.DC((12, 6)).right(90))
    ldo12.escape()
    ldo33 = cu.SOT223(brd.DC((25, 6)).right(90))
    vcc = ldo33.escape()
    vcc.left(45)
    for i in range(3):
        vcc.copy().right(45 * i).forward(1.5).wire(width = 0.8).via('GL3')

    dc = brd.DC((-6, 0))
    for i in range(20):
        cu.C0402(dc, '0.1 uF')
        dc.forward(1)

    # Connect the LVDS pairs
    for b in range(4):
        fpga_lvds[b].w("f 0.5 l 45").forward(b + 1).w("l 45 f 3").wire()
        hdmi_lvds[b].w("f 0.5").wire()
    # [h.meet(f) for (h, f) in zip(hdmi_lvds, fpga_lvds)]
    [f.meet2(h) for (h, f) in zip(hdmi_lvds, fpga_lvds)]

    fpga_p0.meet(p0)
    fpga_p1.meet(p1)

    fpga_p23.right(90).wire()
    (fpga_p2,fpga_p3) = fpga_p23.split(8)
    # fpga_p2.w("r 45 f 1 l 45").wire()
    fpga_p3.w("f 2").wire()

    fpga_p2.meet(p2)
    fpga_p3.meet(p3)

    fpga_main.meet(bt815_main)

    # Bottom-layer hookups

    fpga_fl.meet(fl2_qspi)
    fpga_jtag.meet(p4)

    # 5V to the LDOs
    v5.w("i f 2.4 l 90 f 25").wire(width = 0.8)

    # FPGA 1.2 V supply
    t = fpga_v12
    t.w("f 1 r 45 f 7.0").wire(width = 0.8)
    t.via()
    t.w("l 45 f 2").wire('GTL', width = 0.8)

    # HDMI detect
    t = hdmi_detect
    t.w("o f 1").wire()
    r = cu.R0402(t.copy().w("f 2 r 45"), "10K")
    t.goto(r.pads[0]).wire()
    r.pads[1].w("o -").wire()

    brd.save("dazzler")
    lx9.dump_ucf("dazzler")
