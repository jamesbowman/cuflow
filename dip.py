import math
import cuflow as cu

T = cu.inches(0.1)    # tenth on an inch, used throughout

class dip(cu.Part):
    N2 = None
    def place(self, dc):
        self.dc = dc
        self.chamfered(dc, self.width - T, T * (self.N / 2) + 2)
        height = T * ((self.N // 2) - 1)
        self.height = height
        if self.N2 is None:
            nps = [self.N // 2, self.N // 2]
        else:
            nps = self.N2
        print(f"{nps=}")
        for np in nps:
            dc.push()
            dc.goxy(-self.width / 2, height / 2).left(180)
            self.train(dc, np, self.gh, cu.inches(.1))
            dc.pop()
            dc.right(180)

    def gh(self):
        dc = self.dc
        dc.board.hole(dc.xy, .8)
        p = dc.copy()
        p.part = self.id
        self.padfoot(p)
        p.contact()
        self.pads.append(dc.copy())

    def padfoot(self, p):
        p.n_agon(0.8, 60)

class PTH(cu.Part):
    r = .8
    def gh(self, dc, plate = 1.0):
        dc.board.hole(dc.xy, self.r)
        p = dc.copy()
        p.n_agon(plate * self.r, 30)
        p.contact()

        p = dc.copy()
        p.part = self.id
        self.pads.append(p)

class hdr(PTH):
    def place(self, dc):
        height = T * ((self.N // 2) - 1)
        for i in range(self.N // 2):
            dc.push()
            dc.goxy(-self.width / 2, height / 2 - T * i)
            self.gh(dc)
            dc.right(90).forward(self.width).left(90)
            self.gh(dc)
            dc.pop()
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]
        for i in range(1, self.N + 1, 10):
            nm = str(i)
            pin = self.s(str(i)).copy().left(90).forward(2)
            self.text(pin, nm)

class HDR40(hdr):
    family  = "J"
    inBOM   = False
    width   = cu.inches(0.1)
    N       = 40

    def escape(self):
        return

class HDR14(hdr):
    family  = "J"
    inBOM   = False
    width   = cu.inches(0.1)
    N       = 14

    def escape(self):
        return

class Screw2(hdr):
    family  = "J"
    width   = 5
    N       = 2
    r       = 1.2

    def place(self, dc):
        self.chamfered(dc, 10, 10)
        hdr.place(self, dc)

    def escape(self):
        return


class Res10W(hdr):
    family  = "R"
    width   = 55
    N       = 2
    r       = 1.2

    def place(self, dc):
        self.chamfered(dc, 49, 13)
        hdr.place(self, dc)

class ReedRelay(PTH):
    family  = "K"
    def place(self, dc):
        self.chamfered(dc, 5.08, 19.3)
        dc.forward(3 * T).left(180)
        self.train(dc, 4, lambda: self.gh(dc), 2 * T)

class Hdr_1_7(PTH):
    family  = "J"
    N = 7
    def place(self, dc):
        self.chamfered(dc, T + 2, T * self.N + 2)
        dc.forward(((self.N - 1) / 2) * T).left(180)
        self.train(dc, self.N, lambda: self.gh(dc), T)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

class SIL(PTH):
    family  = "J"
    def place(self, dc):
        self.N = int(self.val)
        # self.chamfered(dc, T + 2, T * self.N + 2)
        dc.forward(((self.N - 1) / 2) * T).left(180)
        self.train(dc, self.N, lambda: self.gh(dc), T)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

class SIL_o(PTH):
    family  = "J"
    def place(self, dc):
        self.N = int(self.val)
        self.chamfered(dc, T, T * self.N)
        dc.forward(((self.N - 1) / 2) * T).left(180)
        self.train(dc, self.N, lambda: self.gh(dc), T)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

class Screw1(SIL_o):
    family  = "J"
    width   = 5
    r       = 2.0
    N       = 1

    def place(self, dc):
        dc.forward(((self.N - 1) / 2) * T).left(180)
        self.train(dc, self.N, lambda: self.gh(dc, 0.8), T)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

    def escape(self):
        return


class Screw16(PTH):
    family  = "J"
    source = {'Digikey' : '277-1591-ND'}
    r = 1.3
    def place(self, dc):
        self.N = 16
        G = 5   # gap
        self.chamfered(dc, 9, G * self.N)
        dc.forward(((self.N - 1) / 2) * G).left(180)
        self.train(dc, self.N, lambda: self.gh(dc), G)
        [p.setname(str(i + 1)) for (i, p) in enumerate(self.pads)]

class DIP(PTH):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 6.2, 9.2)
        for _ in range(2):
            dc.push()
            dc.goxy(-1.5 * T, 1.5 * T).left(180)
            self.train(dc, self.N // 2, lambda: self.gh(dc), cu.inches(.1))
            dc.pop()
            dc.right(180)
    def escape(self):
        ii = cu.inches(.1) / 2
        q = math.sqrt((ii ** 2) + (ii ** 2))
        for p in self.pads[:4]:
            p.w("l 45").forward(q).left(45).forward(1)
        for p in self.pads[4:]:
            p.w("r 90 f 1")
        oo = list(sum(zip(self.pads[4:], self.pads[:4]), ()))
        cu.extend2(oo)
        return oo

class DIP8(DIP):
    N = 8
