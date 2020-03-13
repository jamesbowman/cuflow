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
    spi = [i for i,sig in enumerate(BT815pins) if sig in spim]
    for i in ext:
        u1.pads[i].forward(1)
        u1.pads[i].wire()
    [u1.pads[i].outside() for i in spi]

    def bank(n, pool):
        return [u1.pads[i] for i in pool if (i - 1) // 16 == n]
    rv0 = brd.enriver(bank(0, ext), 45)
    rv2 = brd.enriver(bank(2, ext), -45)
    rv3 = brd.enriver(bank(3, ext), 45)
    rv0.forward(brd.c)
    rv0.right(90)
    rv0.forward(1)
    rv0.wire()

    rv2.forward(0.6)

    rv23 = rv2.join(rv3, 1.0)
    rv23.wire()
    rv230 = rv23.join(rv0)
    rv230.w("f 1 r 31 f 1")
    rv230.wire()

    rv4 = brd.enriver(bank(0, spi), -45)
    rv4.w("f 0.7 l 90 f 2.3 l 45 f 1 r 45")
    rv5 = brd.enriver(bank(1, spi), -45)
    rv5.forward(1)
    rvspi = rv4.join(rv5)

    rvspi.wire()
    return (rvspi, )

def u2_escape(u2):
    nms = "CS MISO IO2 GND MOSI SCK IO3 VCC".split()
    sigs = {nm: p for (nm, p) in zip(nms, u2.pads)}
    
    sigs['SCK' ].w("f 1.1 f .1")
    sigs['CS'  ].w("i f 1.5 r 90 f 1.27 f 1.27 f .63 l 90 f .1")
    sigs['MISO'].w("i f 1.0 r 90 f 1.27 f 1.27 f .63 l 90 f .1")
    sigs['MOSI'].w("o f .1")
    sigs['IO2' ].w("i f 0.5 r 90 f 1.27 f 1.27 l 90 f .1")
    sigs['IO3' ].w("i f 0.5 r 90 f 1.27 f .63 l 90 f 5.5 l 90 f 6 l 90 f .1")
    sigs['GND' ].w("o -")
    sigs['VCC' ].w("o +")

    proper = (
        sigs['IO3' ],
        sigs['IO2' ],
        sigs['MISO'],
        sigs['MOSI'],
        sigs['CS'  ],
        sigs['SCK' ],
    )
    cu.extend(sigs['SCK'], proper)
    rv = brd.enriver(proper, 45)
    rv.right(45)
    rv.wire()
    return rv

if __name__ == "__main__":
    brd = cu.Board(
        (50, 42),
        trace = cu.mil(3.5),
        space = cu.mil(3.5),
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    dc = brd.DC((10, 1.0))

    for i in range(20):
        cu.C0402(dc, '15pF')
        dc.forward(1)

    dc = brd.DC((40, 24))
    dc.right(225)
    u1 = cu.QFN64(dc)
    dc.left(225)
    (bt815_qspi, ) = bt815_escape(u1)

    dc.w("f 11 r 90 f 0.78 l 90")
    u2 = cu.SOIC8(dc)
    fl1_qspi = u2_escape(u2)

    bt815_qspi.meet(fl1_qspi)

    j1 = cu.HDMI(brd.DC((5,33)).right(90))

    ldo33 = cu.SOT223(brd.DC((40,6)))
    ldo33.escape()

    brd.save("dazzler")
