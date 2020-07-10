import cuflow as cu

T = cu.inches(0.1)    # tenth on an inch, used throughout

class dip(cu.Part):
    def place(self, dc):
        height = T * ((self.N // 2) - 1)
        for _ in range(2):
            dc.push()
            dc.goxy(-self.width / 2, height / 2).left(180)
            def gh():
                dc.board.hole(dc.xy, .8)
                p = dc.copy()
                p.part = self.id
                p.n_agon(0.8, 60)
                p.contact()
                self.pads.append(dc.copy())
            self.train(dc, self.N // 2, gh, cu.inches(.1))
            dc.pop()
            dc.right(180)

class PTH(cu.Part):
    r = .8
    def gh(self, dc):
        dc.board.hole(dc.xy, self.r)
        p = dc.copy()
        p.n_agon(self.r, 30)
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

