import cuflow as cu
import dip

class QFN20(cu.Part):
    # EFM8BB2 datasheet, figure 9.2 "QFN20 Land Pattern"
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 3, 3)

        def p():
            dc.rect(.240, .950)
            self.pad(dc)

        C1 = 3.1
        C3 = 2.5
        X1 = 0.3
        Y1 = 0.9
        Y3 = 1.8
        for i in range(4):
            dc.push()
            dc.goxy(-C3 / 2, C3 / 2)
            dc.rect(.3, .3)
            self.pad(dc)
            dc.pop()

            dc.push()
            dc.goxy(-C1 / 2, Y3 / 2)
            dc.right(180)
            self.train(dc, 4, lambda: self.rpad(dc, X1, Y1), 0.35)
            dc.pop()

            dc.left(90)


if __name__ == "__main__":
    D = 0.4
    brd = cu.Board(
        (80, 50),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    conn = dip.SIL(brd.DC((66.5, 38)).left(180), "16")
    efm8 = QFN20(brd.DC((40, 25)))

    brd.outline()
    brd.save("udriver")
