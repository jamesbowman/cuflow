import cuflow as cu
import svgout
import dip
import sot

__VERSION__ = "1.0.0"

"""
"""

def thermal(t, layer, d = 1.3):
    t.setname(layer).thermal(d).wire(layer = layer)

def straight(src, dst):
    src.path.append(dst.xy)
    src.wire()

class DazzlerPogo(cu.Part):
    family = "J"
    def place(self, dc):
        def pogos():
            for i in range(4):
                yield(8 + 2 * i, 0)
            for i in range(3):
                yield(30 + 2 * i, 0)
            for i in range(2):
                yield(34 - 2 * i, 42 - 0)

        for (x, y) in pogos():
            dc = self.board.DC((x + 2, y + 2))
            self.board.hole(dc.xy, 1.1)
            p = dc.copy()
            p.part = self.id
            p.n_agon(0.8, 60)
            p.contact()
            self.pads.append(dc.copy())

class Teensy40(dip.dip):
    family  = "U"
    width   = cu.inches(.6)
    N       = 28
    def place(self, dc):
        dip.dip.place(self, dc)
        for i in range(24):
            self.pads[i + 1].setname(str(i))
        thermal(self.pads[0], "GBL")
        thermal(self.pads[-2], "GBL")
        thermal(self.pads[-3], "GTL")

class EDS(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 18.0, 18)
        dc.goxy(-8, cu.inches(0.15)).left(180)
        self.train(dc, 4, lambda: self.rpad(dc, 2, 2), cu.inches(0.1))
    def escape(self):
        pp = self.pads
        pp[0].w("i .")
        pp[1].setname("GTL").w("i f 1").wire(layer = "GTL")
        pp[2].w("i f 2").wire().via().setlayer("GBL")
        pp[3].w("i f 2").wire().via().setlayer("GBL")
        return (pp[2], pp[3])

if __name__ == "__main__":
    (xo, yo) = (20, 26)
    # (xo, yo) = (4, 4)
    brd = cu.Board(
        (50 + xo, 42 + yo),
        trace = 0.2,
        space = cu.inches(1 / 20) - 0.2,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    holexy = [
            (47.2, 2.8),
            (2.8, 42 - 2.8),
            (2.8, 2.8),
            (45,33.5)
    ]
    for x,y in holexy:
        brd.hole((x + 2, y + 2), 2.6, 5)

    teensy = Teensy40(brd.DC((42, 57)).right(90))
    if 0:
        daz = DazzlerPogo(brd.DC((25, 21)))
        (sda, scl) = EDS(brd.DC((10, 54))).escape()

        daz.pads[5].setname("GBL").forward(2).wire(layer = "GBL")
        daz.pads[6].setwidth(1).w("r 90 f 6 l 90 f 12 r 90 f 12 l 90").goto(teensy.pads[-1]).wire()
        straight(teensy.s("16"), daz.pads[8])
        straight(teensy.s("17"), daz.pads[7])
        
        sda.w("f 33 r 90").wire().via().setlayer("GTL").goto(teensy.s("18")).wire()
        scl.w("l 90 f 1 r 90 f 35 r 90").wire().via().setlayer("GTL").goto(teensy.s("19")).wire()

        tt = daz.pads[:5][::-1]
        [t.w("f 2") for t in tt]
        jtag1 = brd.enriver(tt, 45)
        jtag1.w("l 45").wire()

        tt = teensy.pads[9:14][::-1]
        [t.w("l 90 f 1") for t in tt]
        jtag2 = brd.enriver(tt, 45).w("f 13 l 45").wire()

        jtag1.meet(jtag2)

    brd.outline()

    if 1:
        brd.space = cu.mil(12)  # XXX hack the 
        brd.fill_any("GTL", "GTL")
        brd.fill_any("GBL", "GBL")

    brd.save("loader")
    svgout.write(brd, "loader.svg")
    brd.postscript("loader.ps")
