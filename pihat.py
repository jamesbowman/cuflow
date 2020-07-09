import cuflow as cu
import dip
import sot

__VERSION__ = "1.0.0"

"""
RPi dimensions:
  https://www.raspberrypi.org/documentation/hardware/raspberrypi/mechanical/rpi_MECH_4b_4p0.pdf

| GPIO | pin | color  | function            |
| ---- | --- | ------ | ------------------- |
| 14   |  8  | yellow | C2C: RESET          |
| 17   | 11  | green  | C2D: C2D            |
| 18   | 12  | yellow | VS:  VCC sense      |
| 12   | 32  | blue   | 1K:  1khz reference |
|  6   | 31  |        |      relay control  |

1   3v3 Power
2   5v Power
3   BCM 2 (SDA)
4   5v Power
5   BCM 3 (SCL)
6   Ground
7   BCM 4 (GPCLK0)
8   BCM 14 (TXD)
9   Ground
10  BCM 15 (RXD)
11  BCM 17
12  BCM 18 (PWM0)
13  BCM 27
14  Ground
15  BCM 22
16  BCM 23
17  3v3 Power
18  BCM 24
19  BCM 10 (MOSI)
20  Ground
21  BCM 9 (MISO)
22  BCM 25
23  BCM 11 (SCLK)
24  BCM 8 (CE0)
25  Ground
26  BCM 7 (CE1)
27  BCM 0 (ID_SD)
28  BCM 1 (ID_SC)
29  BCM 5
30  Ground
31  BCM 6
32  BCM 12 (PWM0)
33  BCM 13 (PWM1)
34  Ground
35  BCM 19 (MISO)
36  BCM 16
37  BCM 26
38  BCM 20 (MOSI)
39  Ground
40  BCM 21 (SCLK)

"""
def thermal(t, layer, d = 1.3):
    t.setname(layer).thermal(d).wire(layer = layer)

if __name__ == "__main__":
    brd = cu.Board(
        (85, 56),
        trace = 0.2,
        space = cu.inches(1 / 20) - 0.2,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    WW = 0.6 # wide wire width

    dc = brd.DC((3.5 + 29, 56 - 3.5)).left(90)

    j1 = dip.HDR40(dc)
    for pin in "6 9 14 20 25 30 34 39".split():
        thermal(j1.s(pin), "GBL")
    for pin in "2 4".split():
        thermal(j1.s(pin), "GTL")

    route = (8, 12, 11, 32)
    tt = [j1.s(str(i)) for i in route]
    for t in tt:
        pn = int(t.name)
        if (pn % 2) == 0:
            t.left(45).forward(cu.inches(.0707)).left(45)
        else:
            t.left(90)
        t.forward(2)
    cu.extend2(tt)
    rv1 = brd.enriver90(tt, 90)
    rv1.w("l 90")
    rv1.wire()

    j2 = dip.Screw2(brd.DC((80, 50)).left(90))
    thermal(j2.s("1"), "GBL", 2)
    thermal(j2.s("2"), "GTL", 2)

    k1 = dip.ReedRelay(brd.DC((40, 36)).left(90))
    thermal(k1.pads[1], "GTL")

    r1 = dip.Res10W(brd.DC((34, 25)))
    k1.pads[0].left(90).setwidth(WW).setlayer("GBL").goto(r1.pads[0]).wire()

    rv = rv1
    rv.w("f 3 l 90")

    p = k1.pads[2].copy()
    p.w("l 90 f 4.5 l 180")
    t1 = sot.SOT23(p)
    t1.s("2").w("r 90 f 1 .")
    t1.s("3").goto(k1.pads[2]).wire()

    p.w("l 90 f 4 l 90")
    r = cu.R0402(p, "2K3")
    r.pads[0].goto(t1.s("1")).wire()
    p = r.pads[1]
    p.w("o")
    j1.s("31").left(90).goto(p).wire()
    for x in (0, 58):
        for y in (0, 49):
            brd.hole((3.5 + x, 3.5 + y), 2.7, 6)

    j3 = dip.Hdr_1_7(brd.DC((46, 5)).left(90))
    for p,lbl in zip(j3.pads, ('GND', 'C2C', 'C2D', 'VS', '1K', 'L-', 'L+')):
        for a in (-90, 90):
            p.copy().right(a).forward(3.5).text(lbl)
    thermal(j3.pads[0], "GBL")
    [p.w("l 90 f 5") for p in j3.pads[1:]]
    [p.setwidth(WW).forward(6) for p in j3.pads[-2:]]
    rv3 = brd.enriver90(j3.pads[4:0:-1], -90)
    rv.meet(rv3.wire())

    j3.pads[5].goto(k1.pads[3]).wire()
    j3.pads[6].goto(r1.pads[1]).wire()

    brd.outline()

    if 1:
        brd.space = cu.mil(12)  # XXX hack the 
        brd.fill_any("GTL", "GTL")
        brd.fill_any("GBL", "GBL")

    brd.save("pihat")
