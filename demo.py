import math
import cuflow as cu

if __name__ == "__main__":
    brd = cu.Board(
        (8, 6),
        trace = cu.mil(3.5),
        space = cu.mil(3.5) * 1.0,
        via_hole = 0.2,
        via = 0.45,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    c = brd.trace + brd.space * 2
    r = cu.River(brd, [brd.DC((0.5, 0.5 + c * i)).right(90) for i in range(10)])

    r.forward(.001).wire('GBL')
    if 1:
        r.forward(3).wire()
    if 1:
        r.left(90).wire()
    if 1:
        r.forward(0.5).wire()
    if 1:
        r.left(30).wire()
    if 1:
        r.right(30).wire('GTL')
    
    brd.save("demo")
