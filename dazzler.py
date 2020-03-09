import math
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

    def backside(dc, d):
        dc.newpath()
        dc.push()
        dc.right(180)
        dc.forward(0.35 + .2)
        dc.right(90)
        dc.forward(d * 0.5)
        dc.right(90)
        dc.forward(0.35 + .2)
        dc.wire()
        dc.pop()

    def via(dc, l):
        dc.push()
        dc.forward(.35)
        dc.forward(brd.via_space + brd.via / 2)
        dc.wire()
        dc.via(l)
        dc.pop()
    # VCC
    backside(u1.pads[24], 3)
    backside(u1.pads[24], 4)

    for i in (9, 17, 27):
        print('vcc', BT815pins[i])
        dc = u1.pads[i]
        via(dc, 'GL3')

    for i,sig in enumerate(BT815pins):
        if sig == "+1V2":
            print(i, sig)
            via(u1.pads[i], 'GBL')

    power = {'3V3', 'GND', '', '+1V2'}
    spim = {'M_SCK', 'M_CS', 'M_MOSI', 'M_MISO', 'M_IO2', 'M_IO3'}

    ext = [i for i,sig in enumerate(BT815pins) if sig not in (power | spim)]
    for i in ext:
        u1.pads[i].forward(1)
        u1.pads[i].wire()

    def bank(n):
        return [u1.pads[i] for i in ext if (i - 1) // 16 == n]
    brd.enriver(bank(0), 45)
    brd.enriver(bank(2), -45)
    brd.enriver(bank(3), 45)

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
    dc = brd.DC((50, 50))
    dc.right(225)
    u1.place(dc)
    bt815_escape(u1)
    brd.save("dazzler")
