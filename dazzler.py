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

    """
    dc = brd.DC((10, 1.0))

    for i in range(20):
        cu.C0402(dc, '15pF')
        dc.forward(1)
    """

    dc = brd.DC((35.6, 10))
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

    # ldo33 = cu.SOT223(brd.DC((40,6)))
    # ldo33.escape()
    """
    """

    brd.save("dazzler")
