from pathlib import Path

import shapely.affinity as sa
import shapely.geometry as sg

import cuflow as cu
import htmlout
import svg_loader
from rp2040 import RP2040

import hex
from hex import Hex
from hexboard import HexBoard, river_ongrid, wire_ongrid

def mean(L):
    return sum(L) / len(L)

ROUTE2 = 1
USE_EDITED_HEADER_ART = True

used_pins = [
# Module_Serial_Debug
"SWCLK",
# "GPIO1",    # Module_Serial_Debug.RX
# "GPIO0",    # Module_Serial_Debug.TX
"SWDIO",

"GPIO0",
"GPIO1",
"GPIO2",
"GPIO3",
"GPIO4",
"GPIO5",
"GPIO6",
"GPIO7",
# "VCC",
"GPIO8",
"GPIO9",
"GPIO10",
"GPIO11",
# "GPIO12",
# "GPIO13",
"GPIO14",
"GPIO15",
# "TESTEN",
"XIN",
# "XOUT",
# "VCC",
# "DVDD",
# "RUN",
# "GPIO16",
# "GPIO17",
# "GPIO18",
# "GPIO19",
"GPIO20",
# "VCC",
# "GPIO21",
# "GPIO22",
# "GPIO23",
# "GPIO24",
# "GPIO25",
# "GPIO26/ADC0",
# "GPIO27/ADC1",
# "GPIO28/ADC2",
# "GPIO29/ADC3",
# "VCC",
# "ADC_AVDD",
# "VREG_VIN",
"VREG_VOUT",
"USB_DM",
"USB_DP",
# "VCC",
# "VCC",
"QSPI_SD3",
"QSPI_SCLK",
"QSPI_SD0",
"QSPI_SD2",
"QSPI_SD1",
"QSPI_SS_N",
]

class HexRP2040(RP2040):
    def hex_escape(self):
        brd = self.board

        banks = self.escape(used_pins)

        by_name = {pad.name: pad for bank in banks for pad in bank}

        def river(names):
            return cu.River(brd, [by_name[name] for name in names])

        river_ongrid(river(tuple(f"GPIO{i}" for i in range(0, 12)))
                     .w("f 0.8 l 60"))
        river_ongrid(river(("GPIO14", "GPIO15")).right(30))
        river_ongrid(river(("SWCLK", "SWDIO")).w("l 30")).wire()
        river_ongrid(river(("USB_DM", "USB_DP")).w("f 0.4 r 30"))
        river_ongrid(river((
            "QSPI_SD3", "QSPI_SCLK", "QSPI_SD0",
            "QSPI_SD2", "QSPI_SD1", "QSPI_SS_N")).left(30))
        for nm in ("XIN", "GPIO20"):
            wire_ongrid(self.s(nm).w("o"))
        wire_ongrid(self.s("GPIO21").w("o f 1"))
        self.pads[0].w("-").wire()

        return

class HexW25Q128(cu.SOIC8):
    source = {'LCSC': 'C131025'}
    mfr = 'W25Q16JVSSIQ'
    footprint = "SOIC-8-208mil"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def hex_escape(self):
        [c.setname(nm) for (c, nm) in zip(self.pads, "CS IO1 IO2 GND IO0 CLK IO3 VCC".split())]

        for p in self.pads:
            if p.name == "GND":
                p.w("i -")
            elif p.name == "VCC":
                p.w("i +")
            else:
                p.w("o f .1")
                wire_ongrid(p)
                p.wire()


class USBC(cu.Part):
    mfr = "USB-TYPE-C-018"
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
            "B8", "A5", "B7", "A6", "A7", "B6", "A8", "B5",
            "A1/B12", "A4/B9", "B4/A9", "B1/A12",
        )
        for pad, name in zip(self.pads, pad_names):
            pad.setname(name)

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

    def hex_escape(self):
        power_width = 2 * self.board.trace
        for name in ("A1/B12", "B1/A12"):
            self.s(name).setwidth(power_width).w("o -")

        via_escape = self.board.via_space + self.board.via / 2
        vbus0 = self.s("A4/B9").copy().setwidth(power_width)
        vbus1 = self.s("B4/A9").copy().setwidth(power_width)
        vbus0.w(f"o f {via_escape} /")
        vbus1.w(f"o f {via_escape} /")
        vbus0.left(90).goto(vbus1).wire()

        self.s("A6").copy().w("i f 0.6 r 90").goto(
            self.s("B6"), twist=True).wire()
        self.s("B7").copy().w("o f 0.4 l 90").goto(
            self.s("A7"), twist=True).wire()

        r8_center = self.s("B5").copy().w(
            "o f 2 l 90 f 0.65 l 90").setname(None)
        r7_center = self.board.DC(
            (r8_center.xy[0] + 1.1, r8_center.xy[1]), r8_center.dir)
        r7 = cu.R0402(
            r7_center, "5K1", source={"LCSC": "C25905"})
        r8 = cu.R0402(
            r8_center, "5K1", source={"LCSC": "C25905"})

        self.s("A5").copy().w("o f 1 l 90 f 2").goto( r7.pads[0], twist=False).wire()
        self.s("B5").copy().w("o").goto(r8.pads[0]).wire()
        for resistor in (r7, r8):
            resistor.pads[1].w("o -")

        return (r7, r8)


class PZ254RS(cu.Part):
    family = "J"
    footprint = "PZ254RS-11-NP-01"
    lcsc_by_pin_count = {
        6: "C52191418",
        8: "C52191420",
    }
    pitch = 2.54
    body_width = 2.5
    pad_width = 1.02
    pad_length = 2.3

    def pnp_jlc(self):
        return self.center.copy().left(90)

    def place(self, dc):
        self.N = int(self.val)
        assert 2 <= self.N <= 40
        self.mfr = f"PZ254RS-11-{self.N:02d}P-01"
        if self.N in self.lcsc_by_pin_count:
            self.source = {"LCSC": self.lcsc_by_pin_count[self.N]}
        self.val = ""

        self.chamfered(dc, self.body_width, self.N * self.pitch)
        pins = dc.copy().forward((self.N - 1) * self.pitch / 2).left(180)

        def pin():
            self.rpad(pins, self.pad_width, self.pad_length)

        self.train(pins, self.N, pin, self.pitch)
        for i, p in enumerate(self.pads, 1):
            p.setname(str(i))


class Module_SPI_Header(PZ254RS):
    def hex_escape(self):
        for pad in self.pads:
            wire_ongrid(pad.w("o"))


class Module_Serial_Debug(PZ254RS):
    def place(self, dc):
        super().place(dc)
        names = ("GND", "SWDIO", "VCC", "RX", "TX", "SWCLK")
        for pad, name in zip(self.pads, names):
            pad.setname(name)
            pad.copy().forward(4.5).ctext(
                name, scale=0.8, angle=90)

    def hex_escape(self):
        for pad in self.pads:
            route = pad.right(180)
            if pad.name == "GND":
                route.w("o -")
            elif pad.name == "VCC":
                route.w("o +")
            elif pad.name in ("TX", ):
                wire_ongrid(route.w("o"))
            else:
                wire_ongrid(route.w("i"))


class Module_LCD240x240(cu.Part):
    family = "U"
    mfr = "LH133T-IG01"
    footprint = "LCD240x240"
    width = 30
    height = 37.4
    connector_y = -7.8

    def place(self, dc):
        dc.copy().rect(self.width, self.height).silko()
        for x in (-self.width / 2, self.width / 2):
            for y in (-self.height / 2, self.height / 2):
                dc.copy().goxy(x, y).hole(2.5)

        pins = dc.copy().goxy(7.7 / 2, self.connector_y).left(90)
        self.train(pins, 12, lambda: self.rpad(pins, 0.35, 2), 0.7)
        names = "GND GND LEDA VCC GND GND D/C GND SCL SDA RESET GND".split()
        for p, nm in zip(self.pads, names):
            p.setname(nm)

        bar = dc.copy().goxy(-6, self.connector_y)
        bar.newpath()
        bar.right(90).forward(12).silk()
        self.pads[11].copy().w("f 2").text("12")
        self.pads[0].copy().w("f 2").text("1")

    def hex_escape(self):
        for pad in self.pads:
            if pad.name == "GND":
                pad.w("i -").wire()
            elif pad.name == "VCC":
                pad.w("i f 1 +").wire()
            elif pad.name == "LEDA":
                pass
            else:
                wire_ongrid(pad.w("o f 0.2"))


class LDO_1117_3V3(cu.SOT223):
    source = {'LCSC': 'C26537'}
    mfr = "NCP1117ST33T3G"
    idoffset = (0, -4.3)

    def place(self, dc):
        super().place(dc)
        for p, nm in zip(self.pads, ("VCC", "GND", "VCC", "5V")):
            p.setname(nm)

    def hex_escape(self):
        self.pads[2].w("i f 4").wire(width = 0.8)
        self.s("GND").wire(width = 0.8).w("i f 1 l 90 f 4 -")
        return (self.pads[3], self.pads[0])


class SOT23_5(cu.Part):
    family = "U"
    footprint = "SOT-23-5"

    def pnp_jlc(self):
        return self.center.copy().left(270)

    def place(self, dc):
        self.chamfered(dc, 1.5, 2.9)

        dc.push()
        dc.goxy(-2.62 / 2, 0.95).right(180)
        self.train(dc, 3, lambda: self.rpad(dc, 0.62, 1.22), 0.95)
        dc.pop()

        dc.push()
        dc.goxy(2.62 / 2, -0.95)
        self.train(dc, 2, lambda: self.rpad(dc, 0.62, 1.22), 2 * 0.95)
        dc.pop()


class LDO_23_5(SOT23_5):
    source = {'LCSC': 'C81233'}
    mfr = "ME6212C33M5G"

    def step_adjust(self):
        return 180

    def hex_escape(self):
        names = ("5V", "GND", "CE", "", "VCC")
        for p, nm in zip(self.pads, names):
            p.setname(nm)
        self.s("GND").w("i -")
        self.s("VCC").w("i +")
        self.s("CE").w("o f 0.4").goto(self.s("5V")).wire()


class VSSOP10(cu.Part):
    family = "U"
    footprint = "VSSOP-10"
    N = 10

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def place(self, dc):
        self.chamfered(dc, 3, 3)
        pins_per_side = self.N // 2
        pitch = 0.5
        for _ in range(2):
            dc.push()
            dc.forward(pitch * (pins_per_side - 1) / 2)
            dc.left(90)
            dc.forward(4.4 / 2)
            dc.left(90)
            self.train(
                dc, pins_per_side,
                lambda: self.rpad(dc, 0.3, 1.45), pitch)
            dc.pop()
            dc.right(180)


class INA226(VSSOP10):
    mfr = "INA226AIDGSR"
    source = {"LCSC": "C49851"}

    def place(self, dc):
        super().place(dc)
        names = "A1 A0 Alert SDA SCL VCC GND VBUS IN- IN+".split()
        for pad, name in zip(self.pads, names):
            pad.setname(name)

    def hex_escape(self):
        self.s("A0").goto(self.s("A1")).wire()
        self.s("A1").w("o -")
        self.s("VBUS").goto(self.s("IN-")).wire()
        self.s("GND").w("i -")
        self.s("VCC").w("o r 90 f .5 +")
        wire_ongrid(self.s("SDA").w("i f 0.2"))
        wire_ongrid(self.s("SCL").w("o f 0.2"))

class R1206(cu.Part):
    family = "R"
    footprint = "1206"
    source = {"LCSC": "C22464903"}

    def place(self, dc):
        for direction in (-90, 90):
            dc.push()
            dc.right(direction)
            dc.forward(3.2 / 2)
            dc.rect(1.6, 1)
            self.pad(dc)
            dc.pop()

        dc.rect(3.2, 1.6)
        dc.silko()
        dc.push()
        dc.right(90)
        dc.forward(2.65)
        self.label(dc)
        dc.pop()


class SMD_3225_4P(cu.Part):
    family = "Y"
    def place(self, dc):
        self.chamfered(dc, 2.8, 3.5, idoffset = (1.4, .2))

        for _ in range(2):
            dc.push()
            dc.goxy(-1.75 / 2, 2.20 / 2).right(180)
            self.train(dc, 2, lambda: self.rpad(dc, 1.2, 0.95), 2.20)
            dc.pop()
            dc.right(180)
        [p.setname(nm) for p,nm in zip(self.pads, ["", "GND", "CLK", "VDD"])]

class Osc_12MHz(SMD_3225_4P):
    source = {'LCSC': 'C454611'}
    mfr = "TFOM12M4RHKCNT2T"
    footprint = "SMD3225-4P"

    def pnp_jlc(self):
        return self.center.copy().right(90)

    def hex_escape(self):
        self.s("GND").w("o -")
        self.s("VDD").w("o +")
        wire_ongrid(self.s("CLK").w("o"))

def hexgrid(b):
    width, height = b.size
    bounds = sg.box(0, 0, width, height)
    margin_x = 2 * hex.height
    margin_y = 2 * hex.size
    for h in hex.inrect(
            (-margin_x, -margin_y),
            (width + margin_x, height + margin_y)):
        clipped = sg.LineString(h.hexagon()).intersection(bounds)
        lines = clipped.geoms if hasattr(clipped, "geoms") else (clipped,)
        for line in lines:
            if isinstance(line, sg.LineString) and not line.is_empty:
                b.layers["HEX"].add(line)

def spiq_a():
    w = .4/3   # .127 is JLCPCB minimum
    w = 0.127
    brd = HexBoard(
        (61, 49),
        trace = w,
        space = .4 - w,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(5))

    def spiq_logo():
        x0, y0 = (0.9, 0.9)
        x1, y1 = (13.6, 10)

        svg_path = Path(__file__).with_name("spiq-path.svg")
        try:
            artwork = svg_loader.load(
                svg_path, fill="#f6d410", tolerance=0.05)
        except FileNotFoundError:
            return
        assert not artwork.is_empty, "No gold artwork found in spiq-path.svg"

        source_x0, source_y0, source_x1, source_y1 = artwork.bounds
        scale_x = (x1 - x0) / (source_x1 - source_x0)
        scale_y = -(y1 - y0) / (source_y1 - source_y0)
        artwork = sa.affine_transform(artwork, (
            scale_x, 0, 0, scale_y,
            x0 - scale_x * source_x0,
            y1 - scale_y * source_y0,
        ))
        brd.layers["GTL"].add(artwork)
        brd.layers["GTS"].add(artwork.buffer(0.05))
        if 0:
            r = 0.100 / 2
            bd = artwork.buffer(r).boundary
            brd.layers["GTO"].add(bd.buffer(r))

    spiq_logo()

    def oshw_logo():
        artwork = svg_loader.load(
            Path(__file__).with_name("assets") / "oshw-logo-filled-white.svg",
            fill="#fff")
        assert not artwork.is_empty, "No artwork found in OSHW logo SVG"
        artwork = max(artwork.geoms, key=lambda geometry: geometry.area)

        x0, y0, x1, y1 = artwork.bounds
        source_center = ((x0 + x1) / 2, (y0 + y1) / 2)
        scale = 5.5 / (y1 - y0)
        center = (40, 45.75)
        artwork = sa.affine_transform(artwork, (
            scale, 0, 0, -scale,
            center[0] - scale * source_center[0],
            center[1] + scale * source_center[1],
        ))
        brd.layers["GTO"].add(artwork)

    oshw_logo()

    layout_offset = Hex(-12, 24)
    layout_dx, layout_dy = layout_offset.to_plane()

    def layout_xy(xy):
        x, y = xy
        return (x + layout_dx, y + layout_dy)

    def layout_dc(xy):
        return brd.DC(layout_xy(xy))

    xy = Hex.from_xy(7, 27).to_plane()
    dc = brd.DC((xy[0], xy[1]))
    u1 = HexRP2040(dc.left(120))

    # Program Flash
    h = Hex.from_xy(6, 17)
    u2_xy = h.to_plane()
    u2 = HexW25Q128(
        brd.DC((u2_xy[0], u2_xy[1])).right(180).left(120))

    # Match the legacy SPIDriver's 6.25 mm top-edge offset.
    j1 = USBC(brd.DC((0, brd.size[1] - 6.25)).right(90))

    j2 = PZ254RS(brd.DC((50.0, 38.65)), 6)
    for p, nm in zip(j2.pads, ("GND", "GND", "VCC", "VCC", "5V", "5V")):
        p.setname(nm)
    for i in (0,1):
        j2.pads[i].w("o -")
    if not USE_EDITED_HEADER_ART:
        label_x = j2.center.xy[0] + 7.1
        label_text_x = label_x + 3.4
        label_font_size = 1.452
        # IBM Plex Sans Bold gives MISO an advance width of 2.589 em.
        label_text_width = 2.589 * label_font_size
        label_box_width = label_text_width + 1.0
        # SVG's "middle" baseline uses half the x-height. Shift the rectangle
        # to the centre of Plex Sans Bold's 0.698-em capital height instead.
        label_box_y_offset = (0.698 - 0.525) / 2 * label_font_size
        label_gap = 0.8

        def svg_header_label(xy, label, box_height):
            x, y = xy
            brd.svg_layers["art"].rectangle(
                (x - label_text_width / 2, y + label_box_y_offset),
                (label_box_width, box_height), fill="green")
            brd.svg_layers["art"].text(
                xy, label, label_font_size,
                anchor="end", font_family="IBM Plex Sans",
                font_weight="bold", fill="black")

        j2_label_box_height = 2 * j2.pitch - label_gap
        pair_centers = []
        for pair, label in zip(
                (j2.pads[0:2], j2.pads[2:4], j2.pads[4:6]),
                ("GND", "3.3V", "5V")):
            y = sum(p.xy[1] for p in pair) / 2
            pair_centers.append(y)
            brd.DC((label_text_x, y)).rtext(label, scale = 1.452)
            svg_header_label((label_text_x, y), label, j2_label_box_height)
        bar_ys = [pair_centers[0] + j2.pitch]
        bar_ys += [
            (a + b) / 2 for a, b in zip(pair_centers, pair_centers[1:])]
        bar_ys.append(pair_centers[-1] - j2.pitch)
        bar_width = 0.4
        bar_length = 6.3
        half_line = (bar_length - bar_width) / 2
        for y in bar_ys:
            line = sg.LineString(((label_x - half_line, y),
                                  (label_x + half_line, y)))
            brd.layers["GTO"].add(line.buffer(bar_width / 2))

    j2_top = j2.center.xy[1] + j2.N * j2.pitch / 2
    edge_clearance = brd.size[1] - j2_top
    j3_pins = 8
    j3_y = edge_clearance + j3_pins * j2.pitch / 2
    j3 = Module_SPI_Header(brd.DC((j2.center.xy[0], j3_y)), j3_pins)
    j3_names = ["SCK", "MOSI", "MISO", "IO2", "IO3", "CS", "A", "B"]
    for p, nm in zip(j3.pads, j3_names):
        p.setname(nm)
        if not USE_EDITED_HEADER_ART:
            brd.DC((label_text_x, p.xy[1])).rtext(nm, scale = 1.452)
            svg_header_label(
                (label_text_x, p.xy[1]), nm, j2.pitch - label_gap)

    if USE_EDITED_HEADER_ART:
        header_art = svg_loader.load(
            Path(__file__).parent / "assets" / "spiq" /
            "spiq_a.art-edit.svg",
            fill="#000000", tolerance=0.002, ppi=25.4)
        assert not header_art.is_empty, "No header art found in SVG"
        header_art = sa.scale(header_art, 1, -1, origin=(0, 0))
        header_art = sa.translate(header_art, yoff=brd.size[1])
        brd.layers["GTO"].add(header_art)

    u3 = Module_LCD240x240(
        brd.DC((brd.size[0] / 2, brd.size[1] / 2 - 2)))
    u3.inBOM = False
    leda = u3.s("LEDA")
    r1 = cu.R0603(
        brd.DC((12.5, 14)).right(90), "6R2",
        source={"LCSC": "C23210"})
    r1.pads[0].setname("VCC").w("o +").wire()
    r1.pads[1].setname("LEDA")
    leda.copy().w("i f 3").goto(r1.s("LEDA")).wire()

    j4 = Module_Serial_Debug(
        brd.DC((brd.size[0] / 2, brd.size[1] / 2 + 5))
        .setlayer("GBL").right(90), 6)
    j4.inBOM = False

    j2_bottom = j2.center.xy[1] - j2.N * j2.pitch / 2
    j3_top = j3.center.xy[1] + j3.N * j3.pitch / 2

    # External 3V3 supply
    ldo_y = (j2_bottom + j3_top) / 2
    u4 = LDO_1117_3V3(
        brd.DC((j2.center.xy[0] + 4, ldo_y)).right(90))
    u4_heatsink = u4.center.copy().setlayer("GBL").rect(10, 10).poly()
    brd.layers["GBL"].add(u4_heatsink, "VCC")
    tab_x0, tab_y0, tab_x1, tab_y1 = u4.pads[0].boundary.bounds
    tab_center = ((tab_x0 + tab_x1) / 2, (tab_y0 + tab_y1) / 2)
    top_heatsink = brd.DC(tab_center).rect(tab_x1 - tab_x0, 8).poly()
    brd.layers["GTL"].add(top_heatsink, "VCC")
    via_radius = brd.via / 2
    via_overlap = 0.1
    thermal_vias = (
        (tab_x0 + 0.2, tab_y1 + via_radius - via_overlap),
        ((tab_x0 + tab_x1) / 2, tab_y1 + via_radius - via_overlap),
        (tab_x1 - 0.2, tab_y1 + via_radius - via_overlap),
        (tab_x0 - via_radius + via_overlap, tab_y1 - 0.4),
        (tab_x0 - via_radius + via_overlap, (tab_y0 + tab_y1) / 2),
        (tab_x0 - via_radius + via_overlap, tab_y0 + 0.4),
        (tab_x0 + 0.2, tab_y0 - via_radius + via_overlap),
        ((tab_x0 + tab_x1) / 2, tab_y0 - via_radius + via_overlap),
        (tab_x1 - 0.2, tab_y0 - via_radius + via_overlap),
    )
    for xy in thermal_vias:
        via_copper = sg.Point(xy).buffer(via_radius)
        assert via_copper.intersects(u4.pads[0].boundary)
        assert not any(
            via_copper.intersects(pad.boundary) for pad in u4.pads[1:])
        brd.DC(xy).via()
    center_via_copper = sg.Point(u4.center.xy).buffer(via_radius)
    assert not any(
        center_via_copper.intersects(pad.boundary) for pad in u4.pads)
    brd.DC(u4.center.xy).via()

    # Internal 3V3 supply
    u5 = LDO_23_5(layout_dc((12.0, 31.6)).left(90))
    ldo_5v = u5.pads[0]

    nearest_usb_5v = min(
        (j1.s("A4/B9"), j1.s("B4/A9")), key=ldo_5v.distance)
    ldo_5v.copy().setlayer("GTL").setwidth(
        2 * brd.trace).goto(nearest_usb_5v, twist = True).wire()

    u6 = INA226(brd.DC((29.5, 44.1)))

    midpoint = mean([u6.s(nm).xy[1] for nm in ("IN+", "IN-")])
    r2 = R1206(brd.DC((34.0, midpoint)).right(90), "0R27")
    (p0, p1) = r2.pads
    u6.s("IN+").copy().goto(p0, twist = True).wire()
    u6.s("IN-").copy().goto(p1, twist = True).wire()

    def hex_near(x, y):
        xy = Hex.from_xy(x, y).to_plane()
        return brd.DC(xy)

    def setup_i2c_pullup(resistor, signal):
        resistor.pads[0].w("o +").wire()
        resistor.pads[1].setname(signal)
        wire_ongrid(resistor.pads[1].w("o ")).wire()

    r3 = cu.R0402(
        hex_near(23, 43).right(0), "5K1",
        source={"LCSC": "C25905"})
    setup_i2c_pullup(r3, "SDA")
    r4 = cu.R0402(
        hex_near(23, 45).right(180), "5K1",
        source={"LCSC": "C25905"})
    setup_i2c_pullup(r4, "SCL")

    p = hex_near(16, 46)
    r5 = cu.R0402(p, "5K1", source={"LCSC": "C25905"})
    r6 = cu.R0402(
        p.forward(-1.1), "5K1", source={"LCSC": "C25905"})
    r5.pads[1].w("l 90 f 1.7").wire()
    r6.pads[1].w("o -")
    r5.pads[0].goto(r6.pads[0]).wire()
    analog_vin = wire_ongrid(r6.pads[0].w("o")).hex("/ f").wire()

    # Construct the USB-C CC pull-downs before the USB data resistors so
    # all six 5.1 kOhm resistors receive contiguous designators R3-R8.
    r7, r8 = j1.hex_escape()

    def ucap(p, val = '100nF'):
        cn = cu.C0402_nolabel(
            p, val, source={"LCSC": "C1525"})
        cn.pads[0].setname("GND")
        return cn
    def cap(p, val = '100nF'):
        cn = ucap(p, val)
        cn.pads[1].setname("VCC")
        if val == '100nF':
            cn.pads[0].w("o -")
            cn.pads[1].w("o +")
        return cn
    def ldo_cap(
            package, center, value, supply, ldo_pad, twist = False,
            lcsc = None):
        source = {"LCSC": lcsc} if lcsc else None
        capacitor = package(center, value, source=source)
        capacitor.pads[0].setname("GND").setwidth(
            2 * brd.trace).w("o -")
        capacitor.pads[1].setname(supply).setwidth(2 * brd.trace)
        capacitor.pads[1].copy().goto(ldo_pad, twist).wire()
        brd.addnet(capacitor.pads[1], ldo_pad)
        return capacitor

    # U4: the 1117 regulator needs bulk capacitance on both sides.
    c1 = ldo_cap(
        cu.C0805, brd.DC((47.7, u4.center.xy[1])).right(90),
        "10uF", "5V", u4.s("5V"), True, "C15850")
    c2 = ldo_cap(
        cu.C0805_nolabel, brd.DC((59.3, u4.pads[2].xy[1])).right(90),
        "10uF", "VCC", u4.pads[0], lcsc="C15850")

    # U5: use 1 uF input capacitance and a little extra output
    # capacitance for transient response.
    c3 = ldo_cap(
        cu.C0603, brd.DC((10.3, 38)).right(180),
        "1uF", "5V", u5.pads[0], lcsc="C15849")
    c4 = ldo_cap(
        cu.C0603, brd.DC((12.2, 45)).right(90),
        "4.7uF", "VCC", u5.pads[4], True, "C19666")

    # Add all 100 nF 0402 capacitors after the LDO capacitors.
    c5 = cap(u2.center.copy().forward(3.6))
    c6 = cap(u6.center.copy().forward(2.3))
    c7 = cap(brd.DC((13.0, 26.0)).right(150))
    c8 = cap(brd.DC((12.7, 30.5)).right(150))
    c9 = cap(brd.DC((3.3, 31.5)).right(150))
    c10 = cu.C0402_nolabel(
        brd.DC((1.3, 23.7)).right(90), '100nF',
        source={"LCSC": "C1525"})
    u1.s("DVDD2").copy().w("o f 2").goto(c10.pads[0], True).wire()
    c10.pads[1].w("o -")

    y1 = Osc_12MHz(brd.DC((12, 34)).right(60))
    y1_body = y1.center.copy().rect(2.8, 3.5).poly()
    for layer in ("GTL", "GBL"):
        brd.route_keepouts[layer].append(y1_body)

    usb_body_south = j1.center.xy[1] - 8.94 / 2
    series_resistor_y = usb_body_south - 1.0 - 1.1
    r9 = cu.R0402(
        brd.DC((5.2, series_resistor_y)).right(90), "27",
        source={"LCSC": "C25100"})
    r10 = cu.R0402(
        brd.DC((4.1, series_resistor_y)).right(90), "27",
        source={"LCSC": "C25100"})
    j1.s("B7").copy().w("i").goto(
        r9.pads[0], twist=True).wire()
    j1.s("A6").copy().w("i").goto(
        r10.pads[0], twist=True).wire()
    if ROUTE2:
        for r in (r9, r10):
            wire_ongrid(r.pads[1].w("o f 0"))

    for parts in brd.parts.values():
        for part in parts:
            if part is not j1:
                part.hex_escape()

    power_width = 2 * brd.trace
    j1.s("B4/A9").setwidth(power_width).w("o f 1.1 l 90 f 2.5 r 90").goto(r2.pads[0], twist = True).wire()

    for (a,b) in ((2,3), (4,5)):
        j2.pads[a].copy().setwidth(power_width).goto(j2.pads[b]).wire()

    r2.pads[1].setwidth(power_width).goto(j2.pads[4], twist = True).wire()
    j2.pads[5].setwidth(power_width).w("o f 0 l 90").goto(u4.s("5V"), twist = True).wire()
    j2.pads[3].setwidth(power_width).w("i").goto(u4.s("VCC"), twist = True).wire()

    if ROUTE2:
        # Debug port signals on bottom

        u1.s("SWDIO").hex("lr/!3f").wire()
        u1.s("SWCLK").hex("ff/!3f").wire()
        u1.s("GPIO0").hex("r/f").wire()
        u1.s("GPIO1").hex("2frf/f").wire()

        wire_ongrid(u1.s("GPIO26/ADC0").w("o f .4 ")).hex("/ f").wire()

        bus = [u1.s(f"GPIO{i}") for i in range(2, 10)]
        aligner = [
            "f",
            "2f",
            "2f",
            "3f",
            "3f",
            "4f",
            "rl3f",
            "rl3f",
        ]
        for p, a in zip(bus, aligner):
            p.hex(a).wire()
        for (i, p) in enumerate(bus):
            p.hex(f"{i+2}f r / {i + 35}f / >>")
            p.hex(f"{8 - i}f rfff").wire()

        # reorder the LCD signals
        u3.s("D/C").hex("/>6f/>13f").wire()
        u3.s("RESET").hex("/>10f/>6f").wire()
        u3.s("SCL").hex("f/>14f/>9f").wire()
        u3.s("SDA").hex("/>18f/>3f").wire()


    if ROUTE2:
        brd.hex_setup()
        print("Starting route")

    if ROUTE2:

        brd.hex_route(u2.s("CS"), u1.s("QSPI_SS_N"))
        brd.hex_route(u2.s("IO1"), u1.s("QSPI_SD1"))
        brd.hex_route(u2.s("IO2"), u1.s("QSPI_SD2"))
        brd.hex_route(u2.s("IO0"), u1.s("QSPI_SD0"))
        brd.hex_route(u2.s("CLK"), u1.s("QSPI_SCLK"))
        brd.hex_route(u2.s("IO3"), u1.s("QSPI_SD3"))

        brd.hex_route(u1.s("USB_DM"), r9.pads[1])
        brd.hex_route(u1.s("USB_DP"), r10.pads[1])
        brd.hex_route(u1.s("XIN"), y1.s("CLK"))

        brd.hex_route(j4.s("SWCLK"), u1.s("SWCLK"))
        brd.hex_route(u1.s("GPIO0"), j4.s("TX"))
        brd.hex_route(u1.s("GPIO1"), j4.s("RX"))
        brd.hex_route(j4.s("SWDIO"), u1.s("SWDIO"))

        for (a, b) in zip(bus, j3.pads):
            brd.hex_route(a, b)

        brd.hex_route(u3.s("D/C"), u1.s("GPIO10"))
        brd.hex_route(u3.s("RESET"), u1.s("GPIO11"))
        brd.hex_route(u3.s("SCL"), u1.s("GPIO14"))
        brd.hex_route(u3.s("SDA"), u1.s("GPIO15"))

        brd.hex_route_net((
            u1.s("GPIO20"),
            u6.s("SDA"),
            r3.s("SDA"),
        ))
        brd.hex_route_net((
            u1.s("GPIO21"),
            u6.s("SCL"),
            r4.s("SCL"),
        ))
        brd.hex_route(analog_vin, u1.s("GPIO26/ADC0"))


    if ROUTE2:
        brd.hex_render()
        brd.wire_routes()

    pinout_modules = {
        "Module_LCD240x240": u3,
        "Module_spiq_pwr": u6,
        "Module_spiq_ios": j3,
    }
    airwires = []
    current_measurement_bus_sources = {}

    pinout_path = Path(__file__).with_name("spiq_a.pinout")
    for line in pinout_path.read_text().splitlines():
        source_name, target_name = line.split()
        module_name, target_pin = target_name.rsplit(".", 1)
        if target_pin == "None":
            continue
        source_pin = "GPIO" + source_name.removeprefix("GP")
        source = u1.s(source_pin)
        target = pinout_modules[module_name].s(target_pin)
        if (module_name == "Module_spiq_pwr" and
                target_pin in ("SDA", "SCL")):
            current_measurement_bus_sources[target_pin] = source
        else:
            airwires.append((source, target))

    qspi_airwires = (
        ("QSPI_SS_N", "CS"),
        ("QSPI_SD1", "IO1"),
        ("QSPI_SD2", "IO2"),
        ("QSPI_SD0", "IO0"),
        ("QSPI_SCLK", "CLK"),
        ("QSPI_SD3", "IO3"),
    )
    for rp2040_pin, flash_pin in qspi_airwires:
        airwires.append((u1.s(rp2040_pin), u2.s(flash_pin)))
    airwires.append((u1.s("XIN"), y1.s("CLK")))

    usb_airwires = (
        (r9.pads[1], u1.s("USB_DM")),
        (r10.pads[1], u1.s("USB_DP")),
    )
    airwires.extend(usb_airwires)

    current_measurement_airwires = (
        (current_measurement_bus_sources["SDA"],
         u6.s("SDA"), r3.s("SDA")),
        (current_measurement_bus_sources["SCL"],
         u6.s("SCL"), r4.s("SCL")),
    )
    airwires.extend(current_measurement_airwires)

    airwire_rows = []
    total_airwire_distance = 0.0

    completed_connections = {
        frozenset(connection)
        for connection in brd.nets
    }

    def minimum_spanning_tree(net):
        assert len(net) >= 2
        parent = list(range(len(net)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(a, b):
            a = find(a)
            b = find(b)
            if a != b:
                parent[b] = a

        endpoint = lambda pad: (pad.part, pad.name)
        for source_index in range(len(net)):
            for target_index in range(source_index + 1, len(net)):
                connection = frozenset((
                    endpoint(net[source_index]),
                    endpoint(net[target_index]),
                ))
                if connection in completed_connections:
                    union(source_index, target_index)

        tree = []
        edges = sorted(
            (net[source_index].distance(net[target_index]),
             source_index, target_index)
            for source_index in range(len(net))
            for target_index in range(source_index + 1, len(net))
        )
        for distance, source_index, target_index in edges:
            if find(source_index) != find(target_index):
                union(source_index, target_index)
                tree.append((
                    net[source_index], net[target_index], distance))
        return tree

    for net in airwires:
        for source, target, distance in minimum_spanning_tree(net):
            brd.layers["AIR"].add(sg.LineString((source.xy, target.xy)))
            airwire_rows.append((
                f"{source.part}.{source.name}",
                f"{target.part}.{target.name}",
                f"{distance:.3f}" if distance else "",
            ))
            total_airwire_distance += distance

    if airwire_rows:
        airwire_headers = ("src", "dest", "distance (mm)")
        airwire_widths = [
            max(len(header), *(len(row[column]) for row in airwire_rows))
            for column, header in enumerate(airwire_headers)
        ]
        print("  ".join(
            header.ljust(airwire_widths[column])
            for column, header in enumerate(airwire_headers)))
        print("  ".join("-" * width for width in airwire_widths))
        for row in airwire_rows:
            print("  ".join(
                value.rjust(airwire_widths[column]) if column == 2 else
                value.ljust(airwire_widths[column])
                for column, value in enumerate(row)))
        print("  ".join("-" * width for width in airwire_widths))
        total_row = ("total", "", f"{total_airwire_distance:.3f}")
        print("  ".join(
            value.rjust(airwire_widths[column]) if column == 2 else
            value.ljust(airwire_widths[column])
            for column, value in enumerate(total_row)))

    brd.outline(corner_radius = 2)
    gml_contour_count = (
        len(brd.layers["GML"].lines) + len(brd.layers["GML"].routed))
    assert gml_contour_count == 5, (
        f"Expected 5 GML contours, found {gml_contour_count}")
    brd.fill(edge_clearance = 0.4)

    if 0:
        brd.DC((30.5, 1.2)).ctext("(C) EXCAMERA LABS 2026", scale = 1.1)

    hexgrid(brd)

    missing_hex_escape = [
        part.id
        for parts in brd.parts.values()
        for part in parts
        if not callable(getattr(part, "hex_escape", None))
    ]
    assert not missing_hex_escape, (
        "Parts missing hex_escape(): " + ", ".join(missing_hex_escape))

    # Keep Python part names synchronized with the generated designators.
    # C5-C10 are intentionally excluded because they are decoupling caps.
    expected_part_names = """
        j1 j2 j3 j4
        u1 u2 u3 u4 u5 u6
        r1 r2 r3 r4 r5 r6 r7 r8 r9 r10
        c1 c2 c3 c4
        y1
    """.split()
    part_locals = locals()
    named_parts = {
        source_name: part_locals[source_name]
        for source_name in expected_part_names
    }
    for source_name, part in named_parts.items():
        assert part.id == source_name.upper(), (
            f"Source name {source_name} refers to {part.id}")

    decoupling_caps = {c5, c6, c7, c8, c9, c10}
    constructed_parts = {
        part
        for parts in brd.parts.values()
        for part in parts
    }
    covered_parts = set(named_parts.values()) | decoupling_caps
    assert constructed_parts == covered_parts, (
        "Part designator assertions are incomplete; uncovered: " +
        ", ".join(sorted(
            part.id for part in constructed_parts - covered_parts)))

    generated_records = brd.save("spiq_a")
    htmlout.write(brd, "spiq_a.html", generated_records)
    print("Saved")

if __name__ == "__main__":
    spiq_a()
