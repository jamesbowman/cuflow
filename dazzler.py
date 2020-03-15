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
    dc.w("l 90 f 19.6 r 90 f 13.84")

    lx9 = cu.XC6LX9(dc)
    fpga_se = lx9.escape()
    # fpga_se.meet(bt815_main)

    j1 = cu.HDMI(brd.DC((45,34)).right(270))

    cu.Castellation(brd.DC((34, 42)).left(90), 15)
    cu.Castellation(brd.DC((0, 36)).left(180), 16)
    cu.Castellation(brd.DC((6, 0)).right(90), 3)

    # unplaced

    p_fl_f = cu.W25Q16J(brd.DC((60,30)))
    ldo12 = cu.SOT223(brd.DC((60,16)))
    ldo12.escape()
    ldo33 = cu.SOT223(brd.DC((60,4)))
    ldo33.escape()

    dc = brd.DC((-6, 0))
    for i in range(20):
        cu.C0402(dc, '0.1 uF')
        dc.forward(1)

    brd.save("dazzler")
