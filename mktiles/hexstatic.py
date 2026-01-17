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
import os
import math
import pickle
import copy
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

    def zoom_abs(self, screen_pos: Tuple[int, int], new_scale: float):
        if new_scale == self.scale: return
        # keep world point under cursor fixed
        sx, sy = screen_pos
        wx, wy = self.screen_to_world((sx, sy))
        self.scale = new_scale
        sx2, sy2 = wx * self.scale, wy * self.scale
        self.offset.update(sx - sx2, sy - sy2)

(W, H) = (30, 30)

def phys_to_world(xy):
    (x, y) = xy
    x -= W / 2
    y -= H / 2
    return (100 * x, 100 * -y)

def world_to_phys(xy):
    (x, y) = xy
    return ((x / 100) + W / 2, (-y / 100) + H / 2)

class LibraryPart:
    def __init__(self, basename):
        self.name = basename
        self.m = pickle.load(open(f"../{basename}.pickle", "rb"))

        src = pg.image.load(f"{basename}.png")
        self.src = [src]
        for i in range(1, 6):
            self.src.append(pg.transform.rotate(src, 60 * i))

class PlacedPart:

    def __init__(self, p, pos, rot = 0):
        self.part = p
        self.pos = pos
        self.rot = rot

        self.owned = {hex.Hex(0, 0)}
        for k, v in self.part.m["padlist"].items():
            self.owned |= set(v['touching'])

    def is_in(self, h0):
        return h0 in {self.pos + h.rot(self.rot) for h in self.owned}

    def touches(self, h0):
        mp = {}
        for k, v in self.part.m["padlist"].items():
            tt = [h1.rot(self.rot) + self.pos for h1 in v['connected']]
            mp.update({t : k for t in tt})
        return mp.get(h0, False)

    def padpos(self, padname):
        pad = self.part.m["padlist"][padname]
        return [self.pos + h.rot(self.rot) for h in pad["connected"]]
    
    def xf(self, h):
        # transform a local hex into global space
        return self.pos + h.rot(self.rot)

class Design:

    def __init__(self, name):
        self.name = name
        self.parts = {}
        self.load(name)
        self.undo_stack = []
        self.redo_stack = []
        self.checkpoint()

    def load(self, name):
        self.add_part(PlacedPart(LibraryPart("USBC"), hex.Hex(12,50)))
        self.add_part(PlacedPart(LibraryPart("SMT6"), hex.Hex(12,50)))
        self.add_part(PlacedPart(LibraryPart("W25Q128"), hex.Hex(12,50)))
        self.add_part(PlacedPart(LibraryPart("Osc12MHz"), hex.Hex(12,50)))
        self.add_part(PlacedPart(LibraryPart("RP2040"), hex.Hex(12,50)))
        self.add_part(PlacedPart(LibraryPart("R0402"), hex.Hex(23, 12)))

        with open(f"{name}.design", "rt") as f:
            self.add_nets(f)

        try:
            d = pickle.load(open(f"{name}.pickle", "rb"))
            print(f"{d=}")
            self.apply(d)
        except FileNotFoundError:
            self.lines = []

    def add_nets(self, cs):
        self.nets = []
        for li in cs:
            li = li.strip()
            if '#' in li:
                li = li[:li.index('#')]
            pads = [x.strip() for x in li.split()]
            if len(pads) > 1:
                pa = []
                print(f"{pads=}")
                for pad in pads:
                    (_p,_d) = pad.split('.')
                    pa.append((self.namedpart(_p), _d))
                self.nets.append(pa)
        # pa.append(self.design.namedpart(_p).part.m["padlist"][_d]["connected"])

    def add_part(self, p):
        fam = p.part.m['family']
        n = len([1 for o in self.parts if o.startswith(fam)])
        self.parts[f"{fam}{n+1}"] = p

    def touches(self, h0):
        for nm,pp in self.parts.items():
            t = pp.touches(h0)
            if t:
                return (nm, t)
        return (None, None)

    def object(self):
        parts = []
        for nm,pp in self.parts.items():
            parts.append((nm, pp.part.name, pp.pos, pp.rot))
        return {
            'lines' : self.lines,
            'parts' : parts,
        }

    def apply(self, o):
        self.lines = o['lines']
        for (nm, pnm, pos, rot) in o['parts']:
            # self.add_part(PlacedPart(LibraryPart(pnm), pos, rot))
            p = self.namedpart(pnm)
            p.pos = pos
            p.rot = rot

    def checkpoint(self):
        o = self.object()
        with open(f"{self.name}.pickle", "wb") as f:
            pickle.dump(o, f)
        self.undo_stack.append(copy.deepcopy(o))
        self.redo_stack = []

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.apply(self.undo_stack[-1])

    def redo(self):
        if self.redo_stack:
            o = self.redo_stack.pop()
            self.undo_stack.append(o)
            self.apply(o)

    def wipe(self):
        self.lines = []
        self.checkpoint()

    def over_part(self, h):
        for nm,pp in self.parts.items():
            if pp.is_in(h):
                return pp
        return None

    def rotate_part(self, h):
        p = self.over_part(h)
        if p:
            p.rot = (p.rot - 1) % 6

    def namedpart(self, nm):
        for (_,pp) in self.parts.items():
            if pp.part.name == nm:
                return pp

    def blockers(self):
        r = []
        for (_,pp) in self.parts.items():
            p = pp.part
            for nm,pad in p.m["padlist"].items():
                ph = pad['touching'] + pad['connected']
                r += [pp.xf(h) for h in ph]
        return r

# ----------------------------
# App
# ----------------------------
class App:
    def __init__(self, name):
        pg.init()
        pg.display.set_caption("silly.png")
        self.screen = pg.display.set_mode((WIDTH, HEIGHT), pg.RESIZABLE | pg.SCALED)
        self.clock = pg.time.Clock()
        self.font = pg.font.SysFont("consolas", 16)
        pg.mouse.set_cursor(pg.SYSTEM_CURSOR_CROSSHAIR)

        self.input = Input()
        self.cam = Camera(self.screen)
        self.running = True
        self.fullscreen = False

        self._last_mouse = pg.Vector2(self.input.state.mouse_pos)
        self.rubber = None
        self.moving = None

        self.design = Design(name)

        fns = [fn[1:-4] for fn in os.listdir() if fn[0] == "_" and fn.endswith(".png")]
        self.tiles = {n:pg.image.load(f"_{n}.png") for n in fns}

        hex.setsize(0.3)
        self.hgrid = list(hex.inrect((0, 0), (W, H)))
        if 0:
            print(hex.Hex(0, 0).to_plane())
            print((hex.Hex(0, 0) + hex.Hex(0, 1)).to_plane())
            h0 = hex.Hex(0, 0)
            h1 = hex.Hex(10, 10)
            print(h0.line(h1))
        

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
        if False and inp.pressed(pg.K_r):
            w, h = self.screen.get_size()
            self.cam.scale = 1.0
            self.cam.offset.update(w/2, h/2)
        if inp.pressed(ord('q')):
            self.running = False
        if inp.pressed(pg.K_F11):
            self.toggle_fullscreen()

    def hex_to_screen(self, h):
        (x, y) = self.cam.world_to_screen(phys_to_world(h.to_plane()))
        return (x, y)

    def linewidth(self):
        s = self.cam.scale
        return int(round(9 * s))

    def hexline(self, surface, color, a, b):
        hp = a.line(b)
        pts = [self.hex_to_screen(h) for h in hp]
        if len(pts) > 1:
            pg.draw.lines(surface, color, False, pts, width=self.linewidth())

    def draw(self, surface: pg.Surface, dt: float):
        surface.fill(BG_COLOR)
        ti = self.tiles["blank"]
        (w, h) = ti.get_size()

        ppmm = self.cam.scale * 100

        for hx in self.hgrid:
            (x, y) = self.cam.world_to_screen(phys_to_world(hx.to_plane()))
            self.centered(surface, x, y, ti)
        for nm,pp in self.design.parts.items():
            (x, y) = self.cam.world_to_screen(phys_to_world(pp.pos.to_plane()))
            self.centered(surface, x, y, pp.part.src[0], pp.rot * 60)

        hx = self.mouse_hex()

        if self.moving:
            self.moving.pos = hx

        (x, y) = self.cam.world_to_screen(phys_to_world(hx.to_plane()))
        self.centered(surface, x, y, self.tiles["solid"])

        for hx in self.design.blockers():
            (x, y) = self.cam.world_to_screen(phys_to_world(hx.to_plane()))
            self.centered(surface, x, y, self.tiles["solid"])

        color = (200, 60, 0)
        for l in self.design.lines:
            if len(l) > 1:
                pts = [self.hex_to_screen(p) for p in l]
                pg.draw.lines(surface, color, False, pts, width=self.linewidth())
                if 0:
                    for (x, y) in pts:
                        self.centered(surface, x, y, self.tiles["circle"])

        color = (255, 0, 255)
        for net in self.design.nets:
            pts = [self.hex_to_screen(p.padpos(nn)[0]) for (p,nn) in net]
            pg.draw.lines(surface, color, False, pts, width=3)
            
        if self.rubber:
            self.hexline(surface, (255, 100, 0), hx, self.rubber)

        self.status_line = f"q={hx.q:3d} r={hx.r:3d} s={hx.s:3d}"

        (nm, t) = self.design.touches(hx)
        if t:
            self.status_line += f" {nm}.{t}"

        self._draw_hud(surface, dt)

    def mouse_hex(self):
        mx, my = self.input.state.mouse_pos
        wx, wy = self.cam.screen_to_world((mx, my))
        (px, py) = world_to_phys((wx, wy))
        return hex.Hex.from_xy_fine(px, py)

    bmcache = {}

    def centered(self, dst, x, y, src, rot = 0):
        (w, h) = src.get_size()
        s = self.cam.scale
        k = (src, rot, s)
        if k in self.bmcache:
            scaled = self.bmcache[k]
        else:
            scaled = pg.transform.rotozoom(src, rot, s)
            self.bmcache[k] = scaled
        (w, h) = scaled.get_size()
        dst.blit(scaled, (x - w / 2, y - h / 2))

    def _draw_hud(self, surface: pg.Surface, dt: float):
        mx, my = self.input.state.mouse_pos
        wx, wy = self.cam.screen_to_world((mx, my))
        lines = [
            # "Wheel: zoom at cursor  •  MMB: pan  •  R: reset  •  F11: fullscreen  •  Esc: quit",
            # f"Zoom: {self.cam.scale:0.4f} px/unit  Offset: ({self.cam.offset.x:0.1f}, {self.cam.offset.y:0.1f})",
            # f"Mouse(screen): ({mx:4}, {my:4})  Mouse(world): ({wx:8.3f}, {wy:8.3f})  FPS: {self.clock.get_fps():5.1f}",
            self.status_line,
            f"FPS: {self.clock.get_fps():5.1f}",
        ]
        y = 8
        for s in lines:
            surf = self.font.render(s, True, TEXT_COLOR)
            surface.blit(surf, (10, y))
            y += 20

    def mouse1(self):
        p = self.mouse_hex()
        if self.moving:
            self.moving = None
            self.design.checkpoint()
            return

        if self.rubber is None:
            self.rubber = p
            self.design.lines.append([p])
        else:
            if (self.rubber != p):
                self.design.lines[-1] += self.rubber.line(p)
                # If reaches a terminal cell, end the line
                (nm, t) = self.design.touches(p)
                if nm:
                    self.rubber = None
                else:
                    self.rubber = p
                self.design.checkpoint()

    # -------------- main loop --------------
    def run(self):
        while self.running:
            dt = self.clock.tick(120) / 1000.0  # seconds
            self.input.begin_frame()
            for e in pg.event.get():
                if e.type == pg.KEYDOWN:
                    if e.key == pg.K_ESCAPE:
                        self.rubber = None
                    elif e.key == ord('m'):
                        self.moving = self.design.over_part(self.mouse_hex())
                    elif e.key == ord('o'):
                        self.design.redo()
                    elif e.key == ord('r'):
                        self.design.rotate_part(self.mouse_hex())
                    elif e.key == ord('u'):
                        self.rubber = None
                        self.design.undo()
                    elif e.key == ord('0'):
                        self.design.wipe()
                    elif e.key == ord('1'):
                        self.cam.zoom_abs(self.input.state.mouse_pos, 1.0)
                    else:
                        print("Unhandled", e.key)

                if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
                    self.mouse1()
                if e.type == pg.QUIT:
                    self.running = False
                else:
                    self.input.handle_event(e)
            self.update(dt)
            self.draw(self.screen, dt)
            pg.display.flip()
        pg.quit(); sys.exit(0)

if __name__ == "__main__":
    App("efmtoy").run()
