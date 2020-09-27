import sys
from PIL import Image, ImageDraw, ImageFont
import math
import cuflow as cu
from dip import DIP8

__VERSION__ = "0.1.0"

class WSON8L(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 8, 6)
        self.chamfered(dc, 6, 5, False)
        e = 1.27
        for _ in range(2):
            dc.push()
            dc.goxy(-6.75 / 2, e * 1.5).left(180)
            self.train(dc, 4, lambda: self.rpad(dc, 0.5, 2.00), e)
            dc.pop()
            dc.right(180)
    def escape(self):
        ii = 1.27 / 2
        q = math.sqrt((ii ** 2) + (ii ** 2))
        for p in self.pads[4:]:
            p.w("i r 45").forward(q).left(45).forward(1)
        for p in self.pads[:4]:
            p.w("o f .2")
        oo = list(sum(zip(self.pads[4:], self.pads[:4]), ()))
        cu.extend2(oo)
        [p.wire() for p in oo]
        return oo

if __name__ == "__main__":
    brd = cu.Board(
        (24, 12),
        trace = cu.mil(6),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    dc = brd.DC((6, 6)).left(37)
    u1 = DIP8(dc).escape()

    dc = brd.DC((18, 6))
    u2 = WSON8L(dc).escape()

    for src,dst in zip(u1, u2):
        src.meet(dst)

    brd.outline()
    brd.check()
    brd.save("adapter")
