"""Eight-device SPI/QSPI fixture with power, control, CS and shared buses routed.

U1 is SN74LVC595APWR. Flash labels 0..7 correspond directly to QA..QH.
With SRCLK and RCLK tied together, send eight bits MSB first followed by
one extra rising edge, always while the host CS/OE signal is high.
"""

from collections import defaultdict
from functools import lru_cache
from itertools import groupby
from pathlib import Path

from PIL import Image
import cuflow as cu
import dip
import hex
import svg_loader
import shapely.geometry as sg
import shapely.affinity as sa
import shapely.ops as so
from hexboard import HexBoard
from flash8_control import FLASH_OUTPUT_BITS


BOARD_SIZE = (49, 49)
CORNER_RADIUS = 2

# All dimensions are in mm. Vias must not occupy adjacent hex cells.
TRACE_WIDTH = 0.100
TRACE_SPACE = 0.100
HEX_GRID_SIZE = 0.3750
VIA_HOLE = 0.200
VIA_DIAMETER = 0.450
VIA_SPACE = 0.100
SILK_WIDTH = 0.127
LABEL_HEIGHT = 3.0
LABEL_ASSETS = Path(__file__).resolve().parent / "assets" / "flash8-labels"


@lru_cache(maxsize=9)
def label_bitmap(label):
    """Convert the checked-in Plex Sans bitmap to fine-pitch silk geometry."""
    with Image.open(LABEL_ASSETS / f"{label}.png") as source:
        im = source.convert("L")
    width, height = im.size
    pixel = LABEL_HEIGHT / height
    runs = []
    pixels = im.tobytes()
    for row in range(height):
        x = 0
        for value, run in groupby(pixels[row * width:(row + 1) * width]):
            length = sum(1 for _ in run)
            if value > 127:
                runs.append(sg.box(x * pixel, (height - row - 1) * pixel,
                                   (x + length) * pixel, (height - row) * pixel))
            x += length
    return sa.translate(so.unary_union(runs),
                        -width * pixel / 2, -LABEL_HEIGHT / 2)


def board_branding(brd):
    """Reuse SPIQ's Excamera wordmark and read FLASH8 from south to north."""
    logo = svg_loader.load(
        Path(__file__).resolve().parent / "assets" / "excamera-logo.svg",
        fill="#000000", tolerance=0.002, ppi=25.4)
    x0, y0, x1, y1 = logo.bounds
    scale = 11.5 / (x1 - x0)
    # SVG Y points down; board Y points north. Anchor at (0.9, 0.8) mm.
    logo = sa.affine_transform(logo, (
        scale, 0, 0, -scale, 0.9 - scale * x0, 0.8 + scale * y1))
    brd.layers["GTO"].add(logo)
    title = sa.rotate(label_bitmap("FLASH8"), 90, origin=(0, 0))
    brd.layers["GTO"].add(sa.translate(title, 15.5, BOARD_SIZE[1] / 2))

# J2 and J3 on spiq_a share these vertical datum dimensions. Keeping the
# mating rows 4 mm from the north/south edges makes both 49 mm-tall boards
# line up without an additional Y offset.
HEADER_PITCH = dip.T
HEADER_X = HEADER_PITCH / 2 + 1.0
HEADER_END_CLEARANCE = 4.0
HEADER_LABEL_BAR_X = HEADER_X + 7.1
HEADER_LABEL_X = HEADER_X + 7.5
HEADER_LABEL_SCALE = 1.452
POWER_HEADER_PINS = 6
SPI_HEADER_PINS = 8


class ShiftRegister(cu.Part):
    family = "U"
    footprint = "TSSOP-16_4.4x5mm_P0.65mm"
    mfr = "SN74LVC595APWR"

    def place(self, dc):
        # TI PW0016A land pattern: 1.5 x 0.45 pads, 5.8 row centers.
        self.chamfered(dc, 4.4, 5.0)
        for _ in range(2):
            dc.push().forward(2.275).left(90).forward(2.9).left(90)
            self.train(dc, 8, lambda: self.rpad(dc, 0.45, 1.5), 0.65)
            dc.pop().right(180)
        for pad, name in zip(self.pads, (
                "QB", "QC", "QD", "QE", "QF", "QG", "QH", "GND",
                "QH_PRIME", "SRCLR", "SRCLK", "RCLK", "OE", "SER",
                "QA", "VCC")):
            pad.setname(name)


class Flash(cu.SOIC8b):
    A = 5.3
    B = 5.3
    footprint = "SOIC-8_Dual_3.9-5.3mm_P1.27mm"
    val = "3.3V SPI NOR (user populated)"

    def rpad(self, dc, w, h):
        # Union of the existing wide lands (2.405..4.655 mm from center)
        # and the narrow SOIC reference lands (1.500..3.450 mm).
        # Extend only inward: 3.155 x 0.630 mm copper/mask/paste pads.
        # Keep the routing anchor at the original 3.530 mm row offset.
        extension = 0.905
        dc.right(90)
        dc.push().forward(-extension / 2).rect(w, h + extension).pop()
        self.pad(dc)
        dc.left(90)

    def chamfered(self, dc, w, h):
        super().chamfered(dc, w, h, drawid=False)

    def place(self, dc):
        super().place(dc)
        for pad, name in zip(self.pads, (
                "CS", "MISO", "IO2", "GND", "MOSI", "SCK", "IO3", "VCC")):
            pad.setname(name)


class Resistor(cu.R0402):
    def label(self, dc):
        pass


class Capacitor(cu.C0402):
    def label(self, dc):
        pass


class Indicator(cu.D0603):
    family = "D"
    val = "Red LED"

    def label(self, dc):
        pass

    def place(self, dc):
        super().place(dc)
        # Pad 1 is anode; pad 2 is cathode. Rotate the cathode bar
        # with the footprint (cathode is right at zero degrees).
        line = sg.LineString((dc.copy().goxy(1.65, -0.5).xy,
                              dc.copy().goxy(1.65, 0.5).xy))
        self.board.layers["GTO"].add(line.buffer(0.15 / 2))


def bind(brd, name, *pads):
    """Keep intended connectivity separate from routed copper."""
    for pad in pads:
        assert not hasattr(pad, "net_name"), (pad.part, pad.name)
        pad.net_name = name
        brd.fixture_nets[name].append(pad)


def tag_copper(brd):
    pads = [p for group in brd.parts.values() for part in group for p in part.pads]
    for layer in ("GTL", "GBL"):
        tagged = []
        for _, geometry in brd.layers[layer].polys:
            matches = [p for p in pads if geometry.covers(sg.Point(p.xy))]
            assert len(matches) == 1, (layer, len(matches))
            tagged.append((matches[0].net_name, geometry))
        brd.layers[layer].polys = tagged
        brd.layers[layer].p = None


def connect_planes(brd):
    parts = {part.id: part for group in brd.parts.values() for part in group}
    for name, plane in (("GND", "GL2"), ("VCC", "GL3")):
        for pad in brd.fixture_nets[name]:
            if getattr(pad, "through_hole", False):
                # Connect plated header pins with inner-layer thermal reliefs.
                brd.layers[plane].add(pad.boundary, plane)
                pad.copy().setname(plane).thermal(1.3).wire(
                    layer=plane, width=brd.trace)
                continue

            trace = pad.copy().setname(name)
            if parts[pad.part].family == "U":
                trace.dir = 270 if pad.xy[0] < parts[pad.part].center.xy[0] else 90
                trace.forward(1.5 if pad.part == "U1" else 1.6)
            else:
                trace.outside().forward(0.5)
            trace.wire(width=brd.trace)
            via = sg.Point(trace.xy).buffer(brd.via / 2)
            for layer in ("GTL", "GL2", "GL3", "GBL"):
                brd.layers[layer].add(via, plane if layer == plane else name)
            brd.drill(trace.xy, brd.via_hole)


def flash_bus_trunks(brd, flashes):
    """Straight bottom trunks through alternate-row hex centers.

    Top branches reach the nearest center on their trunk, with a via at
    that center. The columns and J2 are joined later at the south edge.
    """
    brd.bus_trunks = []
    brd.bus_taps = []
    y0, y1 = 4.5, 42.0
    # Freeze existing bottom copper before adding the new signal vias.
    obstacles = [geometry for _, geometry in brd.layers["GBL"].polys]
    for column in range(2):
        devices = flashes[column * 4:column * 4 + 4]
        for side, names in ((-1, ("MISO", "IO2")),
                            (1, ("SCK", "MOSI", "IO3"))):
            # Preserve the established trunk positions when U1 or its
            # power vias move. Indices identify even-row hex centers.
            column_index = ((46, 73), (81, 108))[column][side > 0]
            for name in names:
                trunk_x = column_index * hex.height
                line = sg.LineString(((trunk_x, y0), (trunk_x, y1)))
                assert 0.4 < trunk_x < BOARD_SIZE[0] - 0.4
                assert all(line.distance(g) >= brd.trace / 2 + brd.space
                           for g in obstacles), (column, name)
                brd.layers["GBL"].add(line.buffer(brd.trace / 2), name)
                brd.bus_trunks.append((column, name, line))
                for flash in devices:
                    pad = flash.s(name)
                    row = 2 * round(pad.xy[1] / (2 * hex.size))
                    cell = hex.Hex(column_index - row // 2, row)
                    via = brd.DC(cell.to_plane()).setname(name)
                    via.boundary = sg.Point(via.xy).buffer(brd.via / 2)
                    for layer in ("GTL", "GL2", "GL3", "GBL"):
                        brd.layers[layer].add(via.boundary, name)
                    brd.drill(via.xy, brd.via_hole)
                    brd.bus_taps.append((pad, via))
                column_index += side


def connect_host_controls(brd, shift, header):
    """Bottom-layer host controls with short pad-area branches at U1."""
    parts = {part.id: part for group in brd.parts.values() for part in group}
    brd.control_vias = {}
    # Three nonadjacent hex centers just inside U1's west pad row.
    # These vias are outside the pads and carry no soldermask openings.
    for name, dy in (("A", -0.875), ("OE", -0.125), ("B", 0.625)):
        cell = hex.Hex.from_xy(shift.center.xy[0] - 1.2,
                               shift.center.xy[1] + dy)
        via = brd.DC(cell.to_plane()).setname(name)
        via.boundary = sg.Point(via.xy).buffer(brd.via / 2)
        for layer in ("GTL", "GL2", "GL3", "GBL"):
            brd.layers[layer].add(via.boundary, name)
        brd.drill(via.xy, brd.via_hole)
        brd.control_vias[name] = via

    def route(*pads):
        # A plated terminal's own hole keepout must not block entry into
        # its annulus. Other header pins retain their keepouts.
        terminal_points = [sg.Point(pad.xy) for pad in pads
                           if pad.part == header.id]
        keepouts = brd.keepouts
        try:
            brd.keepouts = [g for g in keepouts
                            if not any(g.covers(p) for p in terminal_points)]
            return brd.hex_route_net(
                [brd.pad_endpoint(pad) for pad in pads], width=TRACE_WIDTH)
        finally:
            brd.keepouts = keepouts

    route(shift.s("SER"), brd.control_vias["A"])
    route(shift.s("OE"), parts["R1"].pads[1], brd.control_vias["OE"])
    route(shift.s("SRCLK"), shift.s("RCLK"), brd.control_vias["B"])
    # The plated header pads provide the layer transition for R2 and R3.
    route(header.s("A"), parts["R2"].pads[1])
    route(header.s("B"), parts["R3"].pads[1])
    for name, pin in (("A", "A"), ("OE", "CS"), ("B", "B")):
        route(header.s(pin).copy().setlayer("GBL"),
              brd.control_vias[name].copy().setlayer("GBL"))


def connect_shared_buses(brd, header):
    """Join the fixed column trunks across the clear south edge."""
    parts = {part.id: part for group in brd.parts.values() for part in group}
    brd.shared_bus_vias = {}
    # Separate top-layer crosslinks by two hex rows. Extend the existing
    # bottom trunks straight south to the new, nonadjacent tap vias.
    for name, y in (("SCK", 3.75), ("MOSI", 3.0), ("MISO", 2.25),
                    ("IO2", 1.5), ("IO3", 0.75)):
        taps = []
        for column, net, trunk in brd.bus_trunks:
            if net != name:
                continue
            x = trunk.bounds[0]
            # Lift the southeast tap clear of the rounded board corner.
            tap_y = 1.5 if name == "IO3" and column == 1 else y
            via = brd.DC(hex.Hex.from_xy(x, tap_y).to_plane()).setname(name)
            via.boundary = sg.Point(via.xy).buffer(brd.via / 2)
            for layer in ("GTL", "GL2", "GL3", "GBL"):
                brd.layers[layer].add(via.boundary, name)
            brd.drill(via.xy, brd.via_hole)
            extension = sg.LineString(((x, trunk.bounds[1]), via.xy))
            brd.layers["GBL"].add(extension.buffer(brd.trace / 2), name)
            taps.append(via)
        brd.shared_bus_vias[name] = taps

    for name in ("SCK", "MOSI", "MISO", "IO2", "IO3"):
        pad = header.s(name)
        terminals = [pad, *brd.shared_bus_vias[name]]
        if name in ("IO2", "IO3"):
            terminals.append(parts["R4" if name == "IO2" else "R5"].pads[1])
        keepouts = brd.keepouts
        try:
            brd.keepouts = [g for g in keepouts if not g.covers(sg.Point(pad.xy))]
            brd.hex_route_net(
                [brd.pad_endpoint(p) for p in terminals], width=TRACE_WIDTH)
        finally:
            brd.keepouts = keepouts


def header_center_y(pin_count, edge):
    half_span = (pin_count - 1) * HEADER_PITCH / 2
    if edge == "north":
        return BOARD_SIZE[1] - HEADER_END_CLEARANCE - half_span
    if edge == "south":
        return HEADER_END_CLEARANCE + half_span
    raise ValueError(f"Unknown edge: {edge}")


def label_pins(brd, header, names):
    for pad, name in zip(header.pads, names):
        pad.setname(name)
        brd.DC((HEADER_LABEL_X, pad.xy[1])).rtext(
            name, scale=HEADER_LABEL_SCALE)


def label_power_pairs(brd, header):
    for pad, name in zip(
            header.pads, ("GND", "GND", "VCC", "VCC", "5V", "5V")):
        pad.setname(name)

    pair_centers = []
    for pair, label in zip(
            (header.pads[0:2], header.pads[2:4], header.pads[4:6]),
            ("GND", "3.3V", "5V")):
        y = sum(pad.xy[1] for pad in pair) / 2
        pair_centers.append(y)
        brd.DC((HEADER_LABEL_X, y)).rtext(
            label, scale=HEADER_LABEL_SCALE)

    bar_ys = [pair_centers[0] + HEADER_PITCH]
    bar_ys += [
        (a + b) / 2 for a, b in zip(pair_centers, pair_centers[1:])]
    bar_ys.append(pair_centers[-1] - HEADER_PITCH)
    bar_width = 0.4
    bar_length = 6.3
    half_line = (bar_length - bar_width) / 2
    for y in bar_ys:
        line = sg.LineString((
            (HEADER_LABEL_BAR_X - half_line, y),
            (HEADER_LABEL_BAR_X + half_line, y),
        ))
        brd.layers["GTO"].add(line.buffer(bar_width / 2))


def make_board():
    hex.set_grid_size(HEX_GRID_SIZE)
    brd = HexBoard(
        BOARD_SIZE,
        trace=TRACE_WIDTH,
        space=TRACE_SPACE,
        via_hole=VIA_HOLE,
        via=VIA_DIAMETER,
        via_space=VIA_SPACE,
        silk=SILK_WIDTH,
    )
    brd.outline(corner_radius=CORNER_RADIUS)
    brd.add_hex_grid()
    brd.fixture_nets = defaultdict(list)
    local_connections = []
    flashes = []

    # These rows mate with spiq_a J2 and J3 respectively. Their nominal
    # 2.54 mm bodies sit 1 mm inboard from flash8's west edge. The default
    # SIL direction preserves spiq_a's north-to-south pin numbering.
    power_header = dip.SIL(
        brd.DC((HEADER_X, header_center_y(POWER_HEADER_PINS, "north"))),
        str(POWER_HEADER_PINS),
    )
    label_power_pairs(brd, power_header)

    spi_header = dip.SIL(
        brd.DC((HEADER_X, header_center_y(SPI_HEADER_PINS, "south"))),
        str(SPI_HEADER_PINS),
    )
    label_pins(
        brd, spi_header,
        ("SCK", "MOSI", "MISO", "IO2", "IO3", "CS", "A", "B"))

    for header in (power_header, spi_header):
        header.inBOM = True
        header.footprint = f"PinSocket_1x{len(header.pads):02d}_P2.54mm"
        for pad in header.pads:
            pad.through_hole = True
            bind(brd, "OE" if pad.name == "CS" else pad.name, pad)

    shift = ShiftRegister(brd.DC((8.8, 26)).right(180))
    for name, pin in (("A", "SER"), ("B", "SRCLK"), ("B", "RCLK"),
                      ("OE", "OE"), ("VCC", "SRCLR"), ("VCC", "VCC"),
                      ("GND", "GND"), ("NC_QH_PRIME", "QH_PRIME")):
        bind(brd, name, shift.s(pin))
    for i, bit in enumerate(FLASH_OUTPUT_BITS):
        bind(brd, f"CS{i}", shift.s("Q" + "ABCDEFGH"[bit]))

    def decouple(xy, value="100nF", direction=0, reference=None):
        cap = Capacitor(brd.DC(xy).right(direction), value)
        if reference is not None:
            # Preserve C3-C10 identities after removing the former bulk C2.
            cap.id = reference
            for pad in cap.pads:
                pad.part = reference
        bind(brd, "VCC", cap.pads[0])
        bind(brd, "GND", cap.pads[1])
        return cap

    # C1 follows U1's rotation, with its supply pad just south of VCC.
    vcc_pin = shift.s("VCC")
    c1_xy = (vcc_pin.xy[0] - 0.65, vcc_pin.xy[1] - 1.1)
    decouple(c1_xy, direction=180)
    # Defined, disabled startup state even when the host is disconnected.
    for name, rail in (("OE", "VCC"), ("A", "VCC"), ("B", "GND"),
                       ("IO2", "VCC"), ("IO3", "VCC")):
        if name == "OE":
            # R1's signal pad faces U1 OE; its supply via faces west.
            oe_pin = shift.s("OE")
            xy, direction = (oe_pin.xy[0] - 2.3, oe_pin.xy[1]), 0
        else:
            # R2-R5 sit beside their J2 pins, with signal pads facing west.
            xy, direction = (5.0, spi_header.s(name).xy[1]), 180
        resistor = Resistor(brd.DC(xy).right(direction), "10k")
        bind(brd, rail, resistor.pads[0])
        bind(brd, name, resistor.pads[1])
        label_xy = (xy[0], xy[1] - 0.8)
        brd.DC(label_xy).ctext(resistor.id, scale=0.6)

    for i in range(8):
        x, y = (26 + 15 * (i // 4), 7 + 11 * (i % 4))
        flash = Flash(brd.DC((x, y)))
        flashes.append(flash)
        for pad in flash.pads:
            bind(brd, f"CS{i}" if pad.name == "CS" else pad.name, pad)
        decouple((x + 3, y + 4.3), reference=f"C{i + 3}")
        pullup = Resistor(brd.DC((x - 3, y + 4.3)), "470")
        bind(brd, "VCC", pullup.pads[0])
        bind(brd, f"CS{i}", pullup.pads[1])
        # Rotate the pair as a group: cathode west near the CS pull-up,
        # series resistor east, still north of the pull-up/capacitor row.
        led_y = y + 6.5
        led_r = Resistor(brd.DC((x + 2, led_y)).right(180), "1.5k")
        led = Indicator(brd.DC((x - 2, led_y)).right(180))
        bind(brd, "VCC", led_r.pads[0])
        bind(brd, f"LED{i}_A", led_r.pads[1], led.pads[0])
        bind(brd, f"CS{i}", led.pads[1])
        local_connections.extend((
            (flash.s("CS"), pullup.pads[1], led.pads[1]),
            (led_r.pads[1], led.pads[0]),
        ))
        label = FLASH_OUTPUT_BITS[i]
        # Keep the lowered digits clear of the pull-up resistor pads.
        brd.layers["GTO"].add(sa.translate(
            label_bitmap(label), x - 5.45, led_y - 1.5))
        brd.DC((x - 2, led_y - 0.95)).ctext(led.id, scale=0.6)
        brd.DC((x + 2, led_y - 0.9)).ctext(led_r.id, scale=0.6)
        brd.DC((x - 3, y + 3.4)).ctext(pullup.id, scale=0.6)
        # Pin-1 mark just above the pad, near the package's chamfer.
        brd.layers["GTO"].add(sg.Point((x - 3.15, y + 2.65)).buffer(0.18))
        # Lowered labels allow a shorter frame and 0.65 mm clear row gaps.
        # Widen slightly so the 2 mm corner arcs clear all flash pads.
        x0, y0, x1, y1 = x - 7.3, y - 2.9, x + 5.5, y + 7.3
        radius = 2.0
        frame = sg.box(x0 + radius, y0 + radius,
                       x1 - radius, y1 - radius).buffer(radius, resolution=64)
        brd.layers["GTO"].add(frame.boundary.buffer(0.075))

    board_branding(brd)
    # Preserve the established local, column and CS routing first; add
    # host controls and shared-bus joins afterward using pad-area endpoints.
    tag_copper(brd)
    connect_planes(brd)
    flash_bus_trunks(brd, flashes)
    brd.hex_clearance = TRACE_SPACE
    brd.hex_edge_clearance = 0.4
    brd.hex_setup()
    for pads in local_connections:
        brd.hex_route_net(
            [brd.pad_endpoint(pad) for pad in pads], width=TRACE_WIDTH)
    for pad, via in brd.bus_taps:
        brd.hex_route_net(
            [brd.pad_endpoint(pad), brd.pad_endpoint(via)], width=TRACE_WIDTH)
    # Route in output-bit order with pad-area endpoints. The printed rows
    # read 0/1, 2/3, 4/5, 6/7 from south to north, west to east.
    brd.cs_routes = {}
    for slot in sorted(range(8), key=FLASH_OUTPUT_BITS.__getitem__):
        output = shift.s("Q" + "ABCDEFGH"[FLASH_OUTPUT_BITS[slot]])
        brd.cs_routes[slot] = brd.hex_route(
            brd.pad_endpoint(output), brd.pad_endpoint(flashes[slot].s("CS")))
    connect_host_controls(brd, shift, spi_header)
    connect_shared_buses(brd, spi_header)
    brd.wire_routes()
    brd.fill()
    # Break body outlines at exposed pads, leaving a printable silk clearance.
    mask = brd.layers["GTS"].preview().buffer(0.15)
    brd.layers["GTO"].polys = [
        (name, geometry.difference(mask))
        for name, geometry in brd.layers["GTO"].polys]
    brd.layers["GTO"].p = None
    return brd


def flash8():
    brd = make_board()
    brd.save("flash8")
    brd.save_netlist("flash8", [
        pads for pads in brd.fixture_nets.values() if len(pads) > 1])
    brd.postscript("flash8.ps")
    print("Saved")
    return brd


if __name__ == "__main__":
    flash8()
