import cuflow as cu
from hexboard import wire_ongrid


class USBC(cu.Part):
    mfr = "USB-TYPE-C-018"
    footprint = "USB-C_SMD-TYPE-C-31-M-12"
    source = {'LCSC': 'C2927038'}   # Also C2765186 (better datasheet)
    family = "J"
    body_width = 8.94
    body_depth = 7.35

    def pnp_jlc(self):
        return self.center.copy().forward(5)

    def place(self, dc):
        self.chamfered(
            dc.copy().forward(self.body_depth / 2),
            self.body_width,
            self.body_depth,
        )
        dc.copy().forward(self.body_depth).silk()

        holes = dc.copy().forward(6.28)
        for d in (-1, 1):
            holes.copy().goxy(d * 5.78 / 2, 0).hole(0.65, ko = 0.22)

        p = holes.copy().goxy(0, 1.07)
        a = p.copy().goxy(3.50 / 2, 0)
        self.train(a.left(90), 8, lambda: self.rpad(a, 0.3, 1.1), 0.5)
        a = p.copy().goxy(6.4 / 2, 0)
        self.train(a.left(90), 2, lambda: self.rpad(a, 0.6, 1.1), 0.8)
        a = p.copy().goxy(-4.8 / 2, 0)
        self.train(a.left(90), 2, lambda: self.rpad(a, 0.6, 1.1), 0.8)

        pad_names = (
            "B5", "A8", "B6", "A7", "A6", "B7", "A5", "B8",
            "A1/B12", "A4/B9", "B4/A9", "B1/A12",
        )
        for pad, name in zip(self.pads, pad_names):
            pad.setname(name)

        self.s("A6").mark()

        baseline = dc.copy().goxy(0, 2.6)

        def plated_slot(slot, land_length):
            # C2765186 specifies a 0.6 mm routed slot surrounded by a
            # 0.2 mm land: 1.4/1.7 mm slots in 1.8/2.1 mm lands.
            slot_length = land_length - 0.4
            slot.left(90).stadium(0.3, 60, slot_length - 0.6)
            self.board.layers["GML"].route(slot.boundary)
            land = slot.boundary.buffer(0.2)
            for layer in ("GTL", "GTS", "GTP", "GBL", "GBS"):
                self.board.layers[layer].add(land, "SHIELD")
            self.board.keepouts.append(land)

        for d in (-1, 1):
            p = baseline.copy().goxy(d * 8.65 / 2, 0)
            plated_slot(p, 1.8)
            p = baseline.copy().goxy(d * 8.65 / 2, 4.2)
            plated_slot(p, 2.1)

    def hex_escape(self, cc_positions=None, bridge_dplus=True):
        power_width = 2 * self.board.trace
        for name in ("A1/B12", "B1/A12"):
            self.s(name).setwidth(power_width).w("o -")

        via_escape = self.board.via_space + self.board.via / 2
        vbus0 = self.s("A4/B9").copy().setwidth(power_width)
        vbus1 = self.s("B4/A9").copy().setwidth(power_width)
        vbus0.w(f"o f {via_escape} /")
        vbus1.w(f"o f {via_escape} /")
        vbus0.left(90).goto(vbus1).wire()

        a7 = self.s("A7").copy()
        b7 = self.s("B7").copy()
        a7.w("i f 0.6 r 90").goto(b7, twist=True).wire()

        if bridge_dplus:
            self.s("B6").copy().w("o f 0.4 l 90").goto(
                self.s("A6"), twist=True).wire()
        else:
            for name in ("A6", "B6"):
                wire_ongrid(self.s(name).w("o"))
            wire_ongrid(self.s("B7").w("o"))

        def cc_pulldown(pin, north=0, position=None):
            if position is None:
                center = self.s(pin).copy().w(
                    "o f 2 l 90 f 0.65 l 90").setname(None)
                center = self.board.DC(
                    (center.xy[0], center.xy[1] + north), center.dir)
            else:
                center = self.board.DC(position)
            resistor = cu.R0402(
                center, "5K1", source={"LCSC": "C25905"})
            self.s(pin).copy().w("o").goto(
                resistor.pads[0], twist=True).wire()
            resistor.pads[1].w("o -")
            return resistor

        positions = cc_positions or (None, None)
        r5 = cc_pulldown("A5", north=0.4, position=positions[0])
        r6 = cc_pulldown("B5", north=0.2, position=positions[1])

        return (r5, r6)
