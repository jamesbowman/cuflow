import math
import json

# This uses oddr: shoves odd rows by +½ column
# Which is a pointy-top layout

axial_direction_vectors = [
    (+1, 0), (+1, -1), (0, -1), 
    (-1, 0), (-1, +1), (0, +1), 
]

F = math.sin(math.pi / 3)
if 0:
    height = 0.4
    size = F * height
else:
    size = 0.4
    height = size / F

class Hex:

    def __init__(self, q, r):
        assert isinstance(q, int) and isinstance(r, int)
        self.q = q
        self.r = r

    @property
    def s(self):
        return -self.q - self.r

    def to_grid(self):
        col = self.q + (self.r - (self.r&1)) / 2
        row = self.r
        return (col, row)

    def to_plane(self):
        (x, y) = self.to_grid()
        x += 0.5 * (y & 1)
        return (x * height, y * size)

    def neighbors(self):
        yield(self)
        for (dq, dr) in axial_direction_vectors:
            yield(Hex(self.q + dq, self.r + dr))

    def neighborhood(self, R):
        for q in range(-R, R):
            for r in range(-R, R):
                for s in range(-R, R):
                    if (q + r + s) == 0:
                        yield self + Hex(q, r)

    def __add__(self, other):
        return Hex(self.q + other.q, self.r + other.r)

    def __sub__(self, other):
        return Hex(self.q - other.q, self.r - other.r)

    def __repr__(self):
        return f"<Hex q={self.q}, r={self.r} s={self.s}>"

    @classmethod
    def from_xy(cls, x, y):
        col = int(round((x) / height - 0.25))
        row = int(round(y / size))
        q = col - (row - (row&1)) // 2
        r = row
        return cls(q, r)

    def best_forward(self, p):
        brd = p.board
        candidates = []
        for nb in self.neighbors():
            xy = nb.to_plane()
            o = brd.DC(xy)
            # print(f"{hh=} {xy=}")
            (dx, dy) = p.seek(o)
            if dy >= 0:
                candidates.append((abs(dx), (dx, dy)))
        best = min(candidates)[1]
        return best

    def __iter__(self):
        yield self.q
        yield self.r

    def route(self, goal):
        return [self, goal]
        frontier = [self]
        came_from = {tuple(self): None}
        while tuple(goal) not in came_from:
            current = frontier.pop(0)
            for next in current.neighbors():
                if tuple(next) not in came_from:
                    frontier.append(next)
                    came_from[tuple(next)] = tuple(current)
        c = tuple(goal)
        path = [Hex(*c)]
        while c != tuple(self):
            c = came_from[c]
            path.append(Hex(*c))
        return path[::-1]

    def hop(self, other):
        d = self - other

        p1 = [self, Hex(other.q, self.r), other]
        p2 = [self, Hex(self.q, other.r), other]
        x = other.s - self.s
        p3 = [self, Hex(self.q - x, self.r), other]
        p4 = [self, Hex(self.q, self.r - x), other]
        def seg(a, b):
            q = abs(a.q - b.q)
            r = abs(a.r - b.r)
            s = abs(a.s - b.s)
            return max(q, r, s)
        def ll(hh):
            return sum([seg(a, b) for (a, b) in zip(hh, hh[1:])])
        ranked = {ll(p): p for p in (p1, p2, p3, p4)}
        return ranked[min(ranked)]

    def rot(self, a):
        a %= 6
        if a == 0:
            return self
        elif a == 1:
            return Hex(-self.r, -self.s)
        elif a == 2:
            return Hex(self.s, self.q)
        elif a == 3:
            return Hex(-self.q, -self.r)
        elif a == 4:
            return Hex(self.r, self.s)
        elif a == 5:
            return Hex(-self.s, -self.q)

    def __hash__(self):
        return hash((self.q, self.r))

    def __eq__(self, other):
        return (self.q, self.r) == (other.q, other.r)

