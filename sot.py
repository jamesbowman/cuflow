import cuflow as cu

class SOT23(cu.Part):
    family = "T"
    def place(self, dc):
        self.chamfered(dc, 3.0, 1.4)
        (w, h) = (1.0, 1.4)
        self.pad(dc.copy().goxy(-0.95, -1.1).rect(w, h))
        self.pad(dc.copy().goxy( 0.95, -1.1).rect(w, h))
        self.pad(dc.copy().goxy( 0.00,  1.1).rect(w, h))
        [p.setname(nm) for p,nm in zip(self.pads, ('1', '2', '3'))]
