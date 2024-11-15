import cuflow as cu

class EDS(cu.Part):
    family = "U"
    def place(self, dc):
        self.chamfered(dc, 18.0, 18)
        dc.goxy(-8.5, cu.inches(0.15)).left(180)
        self.train(dc, 4, lambda: self.rpad(dc, 2, 2), cu.inches(0.1))
    def escape(self):
        pp = self.pads
        if 0:
            pp[0].setname("GL2").w("o f 1 -")
            pp[1].setname("GL3").w("o f 1").wire()
        else:
            pp[0].setname("GND").w("o f 1 / f 1").wire()
            pp[1].setname("VCC").w("o f 1").wire()
            

        # pp[1].setname("GTL").w("i f 1").wire(layer = "GTL")
        # pp[2].w("i f 2").wire().via().setlayer("GBL")
        # pp[3].w("i f 2").wire().via().setlayer("GBL")
        return (pp[2], pp[3])

