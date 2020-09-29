import math
import cuflow as cu

if __name__ == "__main__":
    D = 0.4
    brd = cu.Board(
        (10, 10),
        trace = D,
        space = D,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    c = brd.trace + brd.space * 1
    rr = [0]
    rr = [7,6,5,4,3,2,1,0]
    r = cu.River(brd, [brd.DC((3.6 + c * i, 1)) for i in rr])
    r.tt[-1].setlayer('GBL')

    def label(s):
        if len(rr) == 1:
            d = r.tt[0].copy()
            d.dir = 90
            d.forward(0.8).ltext(s)
    label("fwd 3")
    r.w("f 3")
    label("left 45")
    r.w("l 45 f 3")
    label("fwd 4")
    r.w("f 1")

    r.wire()

    brd.outline()
    brd.save("demo")
