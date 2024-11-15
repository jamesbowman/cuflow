from PIL import Image
import numpy as np
from scipy.signal import convolve2d

EMPTY = 0xffff
COST_H = [5, 1]
COST_V = [1, 5]
COST_VIA = 100
conn4 = [(0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)]

def lees_algorithm(occupied, start, end):
    cost_grid = np.full(occupied.shape, EMPTY).astype(np.uint16)
    cost_grid[start] = 1

    def spreadxy(layer, cg):
        filled = cg != EMPTY
        hb = np.where(filled, cg + COST_H[layer], EMPTY)
        vb = np.where(filled, cg + COST_V[layer], EMPTY)

        r = np.zeros_like(hb)
        r[:, 1:] = hb[:, :-1]
        r[:, 0] = EMPTY

        l = np.zeros_like(hb)
        l[:, :-1] = hb[:, 1:]
        l[:, -1] = EMPTY

        u = np.zeros_like(vb)
        u[:-1, :] = vb[1:, :]
        u[-1, :] = EMPTY

        d = np.zeros_like(vb)
        d[1:, :] = vb[:-1, :]
        d[0, :] = EMPTY

        return np.minimum.reduce((l, r, u, d))

    keepout = np.where(occupied, EMPTY, 0)
    vias = np.full(occupied.shape, 0)
    while cost_grid[end] == EMPTY:
        sp0 = spreadxy(0, cost_grid[0])
        sp1 = spreadxy(1, cost_grid[1])
        sp = np.stack((sp0, sp1))

        filled = cost_grid != EMPTY
        tb0 = np.where(filled[1], cost_grid[1] + COST_VIA, EMPTY)
        tb1 = np.where(filled[0], cost_grid[0] + COST_VIA, EMPTY)
        tb = np.stack((tb0, tb1))

        b = np.minimum(sp, tb)
        via = ((filled == 0) & (tb != EMPTY) & (tb == b))
        vias |= via
        if 1:
            cost_grid = np.minimum(cost_grid, b | keepout)
        else:
            cost_grid = np.where(filled | keepout, cost_grid, b)

    print(vias)
    print(cost_grid)

    (_, w, h) = cost_grid.shape
    used = np.full(occupied.shape, 0).astype(np.uint8)
    cp = end
    used[cp] = 1
    path = [end]
    while cp != start:
        (s, t, u) = cp
        neighbors = [(0, (s, t + j, u + k)) for (j, k) in conn4 if (0 <= (t + j) < w) and (0 <= (u + k) < h)]
        if vias[cp]:
            neighbors += [(COST_VIA, (s ^ 1, t, u))]
        options = [((cost_grid[nb], pref), nb) for (pref,nb) in neighbors]
        print(f"{options=}")
        lowest = min(options)
        (_,cp) = lowest
        path.append(cp)
        used[cp] = 1
    return (path, used)

def save_wires(u):
    (_, h, w) = u.shape
    blu = Image.fromarray(u[0]*255, "L")
    red = Image.fromarray(u[1]*255, "L")
    grn = Image.new("L", (w, h))
    f = 600 // w
    Image.merge("RGB", (red, grn, blu)).resize((w*f, h*f), Image.NEAREST).save("out.png")

def simple_5x5():
    grid = np.array([
                     [[0, 0, 0, 0, 1, 0],
                      [1, 1, 0, 1, 0, 0],
                      [0, 0, 0, 0, 0, 0],
                      [0, 1, 1, 1, 0, 0],
                      [0, 0, 0, 0, 0, 0]],
                     [[0, 0, 0, 0, 1, 0],
                      [1, 1, 0, 1, 0, 0],
                      [0, 0, 0, 0, 0, 0],
                      [0, 1, 1, 1, 0, 0],
                      [0, 0, 0, 0, 0, 0]]
                    ])
    grid = np.zeros((2, 5, 6))
    start = (0, 0, 0)
    end = (1, 4, 5)
    (path, used) = lees_algorithm(grid, start, end)
    save_wires(used)

def random_100():
    grid = np.zeros((2, 100, 100), dtype=np.uint16)
    print(grid)
    start = (0, 0, 0)
    end = (1, 99, 99)
    (path, used) = lees_algorithm(grid, start, end)
    save_wires(used)

simple_5x5()
# random_100()
