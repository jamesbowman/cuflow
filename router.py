import numpy as np
from scipy.signal import convolve2d

hkernel = np.array([[0, 0, 0], [1, 0, 1], [0, 0, 0]])
vkernel = np.array([[0, 1, 0], [0, 0, 0], [0, 1, 0]])
EMPTY = 0xffff
COST_H = [2, 1]
COST_V = [1, 2]
conn4 = [(0,1), (0,-1), (1,0), (-1,0)]

def lees_algorithm(occupied, start, end):
    # Define the convolution kernel

    # Initialize the grid

    cost_grid = np.full(grid.shape, EMPTY).astype(np.uint16)
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
    while cost_grid[end] == EMPTY:
        sp = spreadxy(0, cost_grid)
        cost_grid = np.minimum(cost_grid, sp | keepout)

    # print(cost_grid)

    (w, h) = cost_grid.shape
    cost_grid = np.full(grid.shape, EMPTY).astype(np.uint16)
    cp = end
    occupied[cp] = 1
    path = [end]
    used = np.full(grid.shape, 0).astype(np.uint8)
    while cp != start:
        neighbors = [(cp[0] + i, cp[1] + j) for (i,j) in conn4 if (0 <= (cp[0]+i) < w) and (0 <= (cp[1]+j) < h)]
        lowest = min([(cost_grid[nb], nb) for nb in neighbors])
        (_,cp) = lowest
        path.append(cp)
        occupied[cp] = 1
        used[cp] = 1

    return (path, used)

# Example usage
grid = np.array([[0, 0, 0, 0, 1, 0],
                 [1, 1, 0, 1, 0, 0],
                 [0, 0, 0, 0, 0, 0],
                 [0, 1, 1, 1, 0, 0],
                 [0, 0, 0, 0, 0, 0]])

start = (0, 0)
end = (4, 5)

result = lees_algorithm(grid, start, end)
