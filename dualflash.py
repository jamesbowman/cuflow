import cuflow as cu
import dip
import shapely.geometry as sg
from hexboard import HexBoard


BOARD_SIZE = (49, 49)
CORNER_RADIUS = 2

# Match the routing geometry used by spiq_a.py.
TRACE_WIDTH = 0.127
TRACE_SPACE = 0.4 - TRACE_WIDTH
VIA_HOLE = 0.3
VIA_DIAMETER = 0.6
VIA_SPACE = cu.mil(5)
SILK_WIDTH = cu.mil(5)

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
SPI_RIVER_SIGNALS = ("SCK", "MOSI", "MISO", "IO2", "IO3", "CS", "A")
SPI_RIVER_PITCH = HEADER_PITCH
DIP_X = 24
NORTH_DIP_Y = BOARD_SIZE[1] - 7
SOUTH_DIP_Y = 19
EAST_HEADER_X = 42.6
FLASH_PIN_NAMES = ("CS", "MISO", "IO2", "GND", "MOSI", "SCK", "IO3", "VCC")
FLASH_SIGNAL_PINS = (1, 2, 3, 5, 6, 7)


class FlashHeader(dip.HDR8):
    def place(self, dc):
        super().place(dc)
        self.pads = self.pads[::2] + self.pads[1::2][::-1]
        for i, pad in enumerate(self.pads, 1):
            pad.setname(str(i))


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


def connect_flash_signals(brd, flash, river, signal_overrides = None):
    signal_overrides = signal_overrides or {}
    for pad, name in zip(flash.pads, FLASH_PIN_NAMES):
        pad.setname(name)

    river_by_name = {trace.name: trace for trace in river.tt}
    for pin in FLASH_SIGNAL_PINS:
        pad = flash.pads[pin - 1]
        trace = pad.copy().setlayer("GBL")

        if pin <= 3:
            # Pass midway between the pins on the opposite side of the DIP.
            trace.forward(HEADER_PITCH / 2).left(90)
        else:
            trace.right(90)

        river_trace = river_by_name[signal_overrides.get(pad.name, pad.name)]
        assert river_trace.dir == 0
        trace.forward(river_trace.xy[0] - trace.xy[0]).wire()
        trace.via()
        brd.addnet(pad, river_trace)


def make_board():
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

    # These rows mate with spiq_a J2 and J3 respectively. Their nominal
    # 2.54 mm bodies sit 1 mm inboard from dualflash's west edge. The default
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


    SPI_RIVER_PITCH = 1.0
    for i in range(7):
        p = spi_header.pads[i]
        p.left(90)
    r = brd.enriver(spi_header.pads[:7][::-1], 45, pitch = SPI_RIVER_PITCH)
    r.w("f 6 l 45 f 17 l 90 f 37").wire()

    north_flash = dip.DIP8(brd.DC((DIP_X, NORTH_DIP_Y)))
    south_flash = dip.DIP8(brd.DC((DIP_X, SOUTH_DIP_Y)))
    north_header = FlashHeader(brd.DC((EAST_HEADER_X, NORTH_DIP_Y)))
    south_header = FlashHeader(brd.DC((EAST_HEADER_X, SOUTH_DIP_Y)))
    connect_flash_signals(brd, north_flash, r)
    connect_flash_signals(brd, south_flash, r, {"CS": "A"})

    # CuFlow vias touch every allocated copper layer. Discard the framework's
    # two inner layers so the fabrication output remains a two-layer board.
    for layer in ("GL2", "GL3"):
        del brd.layers[layer]
        brd.layer_extensions.pop(layer, None)

    return brd


def dualflash():
    brd = make_board()
    brd.save("dualflash")
    print("Saved")
    return brd


if __name__ == "__main__":
    dualflash()
