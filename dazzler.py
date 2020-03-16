import math
import cuflow as cu

if __name__ == "__main__":
    brd = cu.Board(
        (50, 42),
        trace = cu.mil(3.5),
        space = cu.mil(3.5),
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

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
    (fpga_main, fpga_lvds) = lx9.escape()
    # fpga_main.meet(bt815_main)

    j1 = cu.HDMI(brd.DC((45,34)).right(270))
    hdmi_lvds = j1.escape()

    cu.Castellation(brd.DC((34, 42)).left(90), 15).escape()
    cu.Castellation(brd.DC((0, 36)).left(180), 16).escape()
    cu.Castellation(brd.DC((6, 0)).right(90), 3)

    # p_fl_f = cu.W25Q16J(brd.DC((35, 23)).left(45))
    ldo12 = cu.SOT223(brd.DC((12, 5)).right(90))
    ldo12.escape()
    ldo33 = cu.SOT223(brd.DC((25, 5)).right(90))
    ldo33.escape()

    dc = brd.DC((-6, 0))
    for i in range(20):
        cu.C0402(dc, '0.1 uF')
        dc.forward(1)

    # Connect the LVDS pairs
    [h.meet(f) for (h, f) in zip(hdmi_lvds, fpga_lvds)]

    brd.save("dazzler")
