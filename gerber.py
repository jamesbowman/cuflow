preamble = """\
G04 Excamera Labs Gerber RS-274X export*
G75*
%MOMM*%
%FSLAX34Y34*%
%LPD*%
%IN{0}*%
%IPPOS*%
%AMOC8*
5,1,8,0,0,1.08239X$1,22.5*%
G01*
%ADD10C,0.254000*%

"""

class Gerber:
    def __init__(self, f, desc):
        self.f = f
        self.f.write(preamble.format(desc))

    def number(self, n):
        i = int(round(n * 10000))
        return "%07d" % i
        
    def points(self, pp):
        d = "D02"
        for (x, y) in pp:
            self.f.write("X" + self.number(x) + "Y" + self.number(y) + d + "*\n")
            d = "D01"

    def rect(self, x0, y0, x1, y1):
        self.f.write("D10*\n")
        self.points([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])

    def linestring(self, pp):
        self.f.write("D10*\n")
        self.points(pp)

    def poly(self, pp):
        self.f.write("G36*\n")
        self.points(pp)
        self.f.write("G37*\n")
        self.f.write("\n")

    def finish(self):
        self.f.write("M02*\n")
