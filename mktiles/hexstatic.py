"""
pcb-cad-starter: grid with zoom (wheel) + pan (MMB)

Run:
  pip install pygame
  python main.py

Notes:
- Mouse wheel zooms centered on cursor
- Middle mouse drag pans the view
- R resets view, F11 fullscreen, Esc quits
"""

import sys
import math
import pickle
from dataclasses import dataclass
from typing import Tuple, Set, Dict

import pygame as pg

sys.path.append("..")

import hex

# ----------------------------
# Config
# ----------------------------
WIDTH, HEIGHT = 1280, 720
BG_COLOR = (18, 18, 22)
GRID_MINOR = (40, 42, 50)
GRID_MAJOR = (65, 70, 82)
CROSSHAIR = (120, 170, 255)
TEXT_COLOR = (210, 210, 220)

# ----------------------------
# Input helper
# ----------------------------
@dataclass
class InputState:
    keys_down: Set[int]
    keys_pressed: Set[int]
    keys_released: Set[int]

    mouse_pos: Tuple[int, int]
    mouse_down: Set[int]
    mouse_pressed: Set[int]
    mouse_released: Set[int]
    mouse_wheel: Tuple[int, int]
    modifiers: Dict[str, bool]

    @staticmethod
    def empty():
        return InputState(
            keys_down=set(),
            keys_pressed=set(),
            keys_released=set(),
            mouse_pos=(0, 0),
            mouse_down=set(),
            mouse_pressed=set(),
            mouse_released=set(),
            mouse_wheel=(0, 0),
            modifiers={"shift": False, "ctrl": False, "alt": False},
        )


class Input:
    def __init__(self):
        self.state = InputState.empty()

    def begin_frame(self):
        # clear edge-triggered flags
        self.state.keys_pressed.clear()
        self.state.keys_released.clear()
        self.state.mouse_pressed.clear()
        self.state.mouse_released.clear()
        self.state.mouse_wheel = (0, 0)

    def handle_event(self, e: pg.event.Event):
        st = self.state
        if e.type == pg.KEYDOWN:
            st.keys_down.add(e.key)
            st.keys_pressed.add(e.key)
        elif e.type == pg.KEYUP:
            st.keys_down.discard(e.key)
            st.keys_released.add(e.key)
        elif e.type == pg.MOUSEMOTION:
            st.mouse_pos = e.pos
        elif e.type == pg.MOUSEBUTTONDOWN:
            st.mouse_down.add(e.button)
            st.mouse_pressed.add(e.button)
        elif e.type == pg.MOUSEBUTTONUP:
            st.mouse_down.discard(e.button)
            st.mouse_released.add(e.button)
        elif e.type == pg.MOUSEWHEEL:
            x, y = st.mouse_wheel
            st.mouse_wheel = (x + e.x, y + e.y)
        elif e.type == pg.WINDOWFOCUSLOST:
            st.keys_down.clear(); st.mouse_down.clear()

        # update modifiers snapshot
        mods = pg.key.get_mods()
        st.modifiers = {
            "shift": bool(mods & (pg.KMOD_LSHIFT | pg.KMOD_RSHIFT)),
            "ctrl": bool(mods & (pg.KMOD_LCTRL | pg.KMOD_RCTRL)),
            "alt": bool(mods & (pg.KMOD_LALT | pg.KMOD_RALT)),
        }

    # convenience
    def is_down(self, key): return key in self.state.keys_down
    def pressed(self, key): return key in self.state.keys_pressed
    def released(self, key): return key in self.state.keys_released
    def mouse_is_down(self, b): return b in self.state.mouse_down
    def mouse_pressed(self, b): return b in self.state.mouse_pressed
    def mouse_released(self, b): return b in self.state.mouse_released


# ----------------------------
# Camera / transforms
# ----------------------------
class Camera:
    def __init__(self, screen: pg.Surface):
        w, h = screen.get_size()
        self.scale = 1.0  # pixels per world unit
        self.offset = pg.Vector2(w/2, h/2)  # where world (0,0) lands on screen

    def world_to_screen(self, p: Tuple[float, float]) -> Tuple[int, int]:
        v = pg.Vector2(p) * self.scale + self.offset
        return int(round(v.x)), int(round(v.y))

    def screen_to_world(self, p: Tuple[int, int]) -> Tuple[float, float]:
        v = (pg.Vector2(p) - self.offset) / self.scale
        return float(v.x), float(v.y)

    def zoom_at(self, screen_pos: Tuple[int, int], dy: int):
        if dy == 0: return
        # zoom factor per wheel notch
        factor = 1.2 ** dy
        # clamp scale
        new_scale = max(0.05, min(200.0, self.scale * factor))
        if new_scale == self.scale: return
        # keep world point under cursor fixed
        sx, sy = screen_pos
        wx, wy = self.screen_to_world((sx, sy))
        self.scale = new_scale
        sx2, sy2 = wx * self.scale, wy * self.scale
        self.offset.update(sx - sx2, sy - sy2)

def phys_to_world(xy):
    (x, y) = xy
    x -= 12.8 / 2
    y -= 7.2 / 2
    return (100 * x, 100 * y)

# ----------------------------
# Grid renderer (adaptive spacing)
# ----------------------------
class Grid:
    def __init__(self):
        self.base_screen_spacing = 32  # target px between minor lines
        self.major_every = 10          # 10 minor -> 1 major

    @staticmethod
    def _nice_step(x: float) -> float:
        # choose 1-2-5 decade steps
        if x <= 0: return 1.0
        exp = math.floor(math.log10(x))
        f = x / (10 ** exp)
        if f < 1.5: nice = 1.0
        elif f < 3.5: nice = 2.0
        elif f < 7.5: nice = 5.0
        else: nice = 10.0
        return nice * (10 ** exp)

    def draw(self, surface: pg.Surface, cam: Camera):
        w, h = surface.get_size()
        # compute visible world rect
        tl = cam.screen_to_world((0, 0))
        br = cam.screen_to_world((w, h))
        xmin, ymin = min(tl[0], br[0]), min(tl[1], br[1])
        xmax, ymax = max(tl[0], br[0]), max(tl[1], br[1])

        # step in world units so that on screen it's near base_screen_spacing
        target_world = self.base_screen_spacing / cam.scale
        step = self._nice_step(target_world)
        major_step = step * self.major_every

        # start from multiples of step
        x0 = math.floor(xmin / step) * step
        y0 = math.floor(ymin / step) * step

        # minor grid
        x = x0
        while x <= xmax:
            sx, _ = cam.world_to_screen((x, 0))
            pg.draw.line(surface, GRID_MINOR, (sx, 0), (sx, h))
            x += step
        y = y0
        while y <= ymax:
            _, sy = cam.world_to_screen((0, y))
            pg.draw.line(surface, GRID_MINOR, (0, sy), (w, sy))
            y += step

        # major grid
        x = math.floor(xmin / major_step) * major_step
        while x <= xmax:
            sx, _ = cam.world_to_screen((x, 0))
            pg.draw.line(surface, GRID_MAJOR, (sx, 0), (sx, h), 2)
            x += major_step
        y = math.floor(ymin / major_step) * major_step
        while y <= ymax:
            _, sy = cam.world_to_screen((0, y))
            pg.draw.line(surface, GRID_MAJOR, (0, sy), (w, sy), 2)
            y += major_step

        # axes crosshair at world origin
        ox, oy = cam.world_to_screen((0, 0))
        pg.draw.line(surface, CROSSHAIR, (ox - 12, oy), (ox + 12, oy), 2)
        pg.draw.line(surface, CROSSHAIR, (ox, oy - 12), (ox, oy + 12), 2)


class Part:
    def __init__(self, basename):
        self.src = pg.image.load(f"{basename}.png")
        self.m = pickle.load(open(f"../{basename}.pickle", "rb"))
        
# ----------------------------
# App
# ----------------------------
class App:
    def __init__(self):
        pg.init()
        pg.display.set_caption("silly.png")
        self.screen = pg.display.set_mode((WIDTH, HEIGHT), pg.RESIZABLE | pg.SCALED)
        self.clock = pg.time.Clock()
        self.font = pg.font.SysFont("consolas", 16)

        self.input = Input()
        self.grid = Grid()
        self.cam = Camera(self.screen)
        self.running = True
        self.fullscreen = False

        self._last_mouse = pg.Vector2(self.input.state.mouse_pos)

        self.klak = Part("EFM8BB2")
        self.tiles = {n:pg.image.load(f"_{n}.png") for n in ("blank", )}

        hex.setsize(0.3)
        self.hgrid = list(hex.inrect((0, 0), (12, 7)))
        if 1:
            print(hex.Hex(0, 0).to_plane())
            print((hex.Hex(0, 0) + hex.Hex(0, 1)).to_plane())

    # -------------- helpers --------------
    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            pg.display.set_mode((0, 0), pg.FULLSCREEN | pg.SCALED)
        else:
            pg.display.set_mode((WIDTH, HEIGHT), pg.RESIZABLE | pg.SCALED)

    # -------------- update/draw --------------
    def update(self, dt: float):
        inp = self.input

        # zoom via wheel (y), centered at cursor
        wx, wy = inp.state.mouse_wheel
        if wy:
            self.cam.zoom_at(inp.state.mouse_pos, wy)

        # pan with MMB drag
        cur = pg.Vector2(inp.state.mouse_pos)
        if inp.mouse_is_down(2):  # MMB
            delta = cur - self._last_mouse
            self.cam.offset += delta
        self._last_mouse = cur

        # quick actions
        if inp.pressed(pg.K_r):
            w, h = self.screen.get_size()
            self.cam.scale = 1.0
            self.cam.offset.update(w/2, h/2)
        if inp.pressed(pg.K_ESCAPE):
            self.running = False
        if inp.pressed(pg.K_F11):
            self.toggle_fullscreen()

    def draw(self, surface: pg.Surface, dt: float):
        surface.fill(BG_COLOR)
        ti = self.tiles["blank"]
        (w, h) = ti.get_size()

        ppmm = self.cam.scale * 100

        for hx in self.hgrid:
            (x, y) = self.cam.world_to_screen(phys_to_world(hx.to_plane()))
            self.centered(surface, x, y, ti)
        (x, y) = self.cam.world_to_screen(phys_to_world(hex.Hex(10, 10).to_plane()))
        self.centered(surface, x, y, self.klak.src)
        self._draw_hud(surface, dt)

    def centered(self, dst, x, y, src):
        (w, h) = src.get_size()
        s = self.cam.scale
        scaled = pg.transform.scale(src, (s * w, s * h))
        (w, h) = scaled.get_size()
        dst.blit(scaled, (x - w / 2, y - h / 2))

    def _draw_hud(self, surface: pg.Surface, dt: float):
        mx, my = self.input.state.mouse_pos
        wx, wy = self.cam.screen_to_world((mx, my))
        lines = [
            "Wheel: zoom at cursor  •  MMB: pan  •  R: reset  •  F11: fullscreen  •  Esc: quit",
            f"Zoom: {self.cam.scale:0.4f} px/unit  Offset: ({self.cam.offset.x:0.1f}, {self.cam.offset.y:0.1f})",
            f"Mouse(screen): ({mx:4}, {my:4})  Mouse(world): ({wx:8.3f}, {wy:8.3f})  FPS: {self.clock.get_fps():5.1f}",
        ]
        y = 8
        for s in lines:
            surf = self.font.render(s, True, TEXT_COLOR)
            surface.blit(surf, (10, y))
            y += 20

    # -------------- main loop --------------
    def run(self):
        while self.running:
            dt = self.clock.tick(120) / 1000.0  # seconds
            self.input.begin_frame()
            for e in pg.event.get():
                if e.type == pg.QUIT:
                    self.running = False
                else:
                    self.input.handle_event(e)
            self.update(dt)
            self.draw(self.screen, dt)
            pg.display.flip()
        pg.quit(); sys.exit(0)


if __name__ == "__main__":
    App().run()
