import cuflow as cu

BT815pins = [
    'GND',
    'R0',
    '+1V2',
    'E.SCK',
    'E.MISO',
    'E.MOSI',
    'E.CS',
    '',
    '',
    '3V3',
    '',
    'E.INT',
    'E.PD',
    '',
    'M_SCK',
    'M_CS',
    'M_MOSI',
    '3V3',
    'M_MISO',
    'M_IO2',
    'M_IO3',
    '',
    '',
    'GND',
    '3V3',
    '+1V2',
    'AUDIO',
    '3V3',
    '3V3',
    '',
    '',
    '',
    '',
    'GND',
    '',
    'DE',
    'VSYNC',
    'HSYNC',
    'DISP',
    'PCLK',
    'B7',
    'B6',
    'B5',
    'B4',
    'B3',
    'B2',
    'B1',
    'B0',
    'GND',
    'G7',
    'G6',
    'G5',
    'G4',
    'G3',
    'G2',
    'G1',
    'G0',
    '+1V2',
    'R7',
    'R6',
    'R5',
    'R4',
    'R3',
    'R2',
    'R1',
]

def bt815_escape(u1):
    dc = u1.pads[23]
    dc.right(180)
    dc.forward(2)
    dc.wire()

    dc = u1.pads[33]
    dc.right(180)
    dc.forward(.65)
    dc.right(45)
    dc.forward(1)
    dc.wire()

    dc = u1.pads[48]
    dc.right(180)
    dc.forward(.65)
    dc.left(45)
    dc.forward(1)
    dc.wire()

    def via(dc, l):
        dc.forward(.35)
        dc.forward(brd.via_space + brd.via / 2)
        dc.wire()
        dc.via(l)
    # VCC
    for i in (9, 24, 27):
        dc = u1.pads[i]
        via(dc, 'GL3')
    dc = u1.pads[28]
    dc.right(90)
    dc.forward(0.5)
    dc.wire()

    for i,sig in enumerate(BT815pins):
        if sig == "+1V2":
            print(i, sig)
            via(u1.pads[i], 'GBL')
        if sig not in ('3V3', 'GND', '', '+1V2'):
            u1.pads[i].forward(1)
            u1.pads[i].wire()

if __name__ == "__main__":
    brd = cu.Board(
        (80, 80),
        trace = cu.mil(3.5),
        space = cu.mil(3.5),
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))
    dc = brd.DC((30, 30))
    for i in range(1, 32):
        cu.C0402('C' + str(i), '15pF').place(dc)
        dc.forward(1)
    u1 = cu.QFN64('U1')
    u1.place(brd.DC((50, 50)))
    bt815_escape(u1)
    brd.save("dazzler")

