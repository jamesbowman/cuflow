import time
import json
import math

from hex import Hex

from browser import document, window, html, ajax, aio

d = (window.innerWidth)
# Create a canvas element and set its size
canvas = html.CANVAS(width=d, height=d)
document <= canvas

gl = canvas.getContext('webgl2')

from browser import document, window

twenty_hex = [
0xe6194B, 0x3cb44b, 0xffe119, 0x4363d8, 0xf58231, 0x911eb4, 0x42d4f4, 0xf032e6, 0xbfef45, 0xfabed4, 0x469990, 0xdcbeff, 0x9A6324, 0xfffac8, 0x800000, 0xaaffc3, 0x808000, 0xffd8b1, 0x000075, 0xa9a9a9, 0xffffff, 0x000000
]

N = 65536
S = 32768
a = window.Int16Array.new(2 * N)

a_color = window.Uint32Array.new(N)

# https://www.desultoryquest.com/blog/drawing-anti-aliased-circular-points-using-opengl-slash-webgl/

vx_shader = """#version 300 es

in vec3 c;
in vec4 vRgbaColor;
out  vec4 color;

void main(void){
    int q = int(c.x);
    int r = int(c.y);
    int col = q + (r - (r&1)) / 2;
    int row = r;
    float x = float(col);
    float y = float(row);
    x += ((r & 1) != 0) ? 0.5 : 0.0;
    
    float size = 0.4;
    float height = size / 0.8660254037844386;

    gl_Position = vec4(x * height / 15.0, y * size / 15.0, 0.0, 1.0);
    gl_PointSize = 6.0;
    color = vRgbaColor;
    color.a = 1.0;
}
"""

frag_shader_dot = """#version 300 es

precision mediump float;
in  vec4 color;
out vec4 fragColor;

void main()
{
    float r = 0.0, delta = 0.0, alpha = 1.0;
    vec2 cxy = 2.0 * gl_PointCoord - 1.0;
    r = dot(cxy, cxy);
    delta = fwidth(r);
    alpha = 1.0 - smoothstep(1.0 - delta, 1.0 + delta, r);

    fragColor = color * alpha;
    fragColor.a = alpha;
}
"""

frag_shader_0 = """#version 300 es

precision mediump float;
in  vec4 color;
out vec4 fragColor;

void main()
{
    fragColor = color;
}
"""

def createShader(type, source):
    shader = gl.createShader(type)
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if not gl.getShaderParameter(shader, gl.COMPILE_STATUS):
        error_log = gl.getShaderInfoLog(shader)
        print("Shader compilation failed:", error_log)
        gl.deleteShader(shader)
        assert 0
    return shader

def createProg(vx, fr):
    prog = gl.createProgram()
    gl.attachShader(prog, vx)
    gl.attachShader(prog, fr)
    gl.linkProgram(prog)
    return prog

vertShader = createShader(gl.VERTEX_SHADER, vx_shader)

prog_0 = createProg(vertShader, createShader(gl.FRAGMENT_SHADER, frag_shader_0))
prog_dot = createProg(vertShader, createShader(gl.FRAGMENT_SHADER, frag_shader_dot))

def update_arrays(prog):
    gl.useProgram(prog)

    vertexBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuf)
    gl.bufferData(gl.ARRAY_BUFFER, a, gl.STATIC_DRAW)

    coord = gl.getAttribLocation(prog, "c")
    gl.vertexAttribPointer(coord, 2, gl.SHORT, False, 0, 0)
    gl.enableVertexAttribArray(coord)

    colorBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, colorBuf)
    gl.bufferData(gl.ARRAY_BUFFER, a_color, gl.STATIC_DRAW)

    color = gl.getAttribLocation(prog, "vRgbaColor")
    gl.vertexAttribPointer(color, 4, gl.UNSIGNED_BYTE, True, 0, 0)
    gl.enableVertexAttribArray(color)

class Part:
    def __init__(self, hex):
        self.nm = hex["name"]
        self.hex = hex
        self.o = Hex(-15, 15)
        self.rot = 0
    def draw(self, mark):
        self.covered = set()
        self.named = {}
        obj = self.hex
        for qr in obj["occ"]:
            h = self.o + Hex(*qr).rot(self.rot)
            mark(h, 0x606060)
            self.covered.add(h)
        for i,(nm,qr) in enumerate(obj["sigs"].items()):
            h = self.o + Hex(*qr).rot(self.rot)
            mark(h, twenty_hex[i])
            self.named[h] = f"{self.nm}.{nm}"

    def tooltip(self, h):
        if h in self.named:
            return self.named[h]
        if h in self.covered:
            return self.nm
        return None

class Board:
    def __init__(self):
        self.parts = set()
        self.wires = {}
        self.alloc = 0
        self.str_alloc = S
        self.drag_start = None

    def mark(self, h, c):
        a_color[self.alloc] = c
        a[2*self.alloc+0] = h.q
        a[2*self.alloc+1] = h.r
        self.alloc += 1

    def add_part(self, p):
        self.parts.add(p)
        p.a0 = self.alloc
        p.draw(self.mark)
        p.a1 = self.alloc

    def move_part(self, p, o):
        p.o = o
        self.redraw_part(p)

    def redraw_part(self, p):
        a = self.alloc
        self.alloc = p.a0
        p.draw(self.mark)
        self.alloc = a

    def add_string(self, hh, c):
        self.str_alloc = S
        for (h0,h1) in zip(hh, hh[1:]):
            i = self.str_alloc
            a[2*i+0] = h0.q
            a[2*i+1] = h0.r
            a[2*i+2] = h1.q
            a[2*i+3] = h1.r
            a_color[i+0] = c
            a_color[i+1] = c
            self.str_alloc += 2

    def redraw(self):
        gl.viewport(0,0,canvas.width,canvas.height)

        gl.clearColor(0, .1, 0, 1)
        gl.clear(gl.COLOR_BUFFER_BIT)
        gl.disable(gl.DEPTH_TEST);

        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        gl.enable(gl.BLEND);
        update_arrays(prog_dot)
        gl.drawArrays(gl.POINTS, 0, self.alloc)

        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(prog_0)
        gl.drawArrays(gl.LINES, S, self.str_alloc - S)

    def under(self, h):
        for p in self.parts:
            if h in p.covered:
                return p
        return None

    def tooltip(self, h):
        for p in self.parts:
            tt = p.tooltip(h)
            if tt is not None:
                return tt
        return None
        
    def on_keypress(self, event):
        event.preventDefault()
        p = self.under(self.cursor)
        if p is not None:
            if event.key == "r":
                p.rot += 1
                self.redraw_part(p)
                self.redraw()

    def on_mouse_move(self, event):
        canvas.focus()
        event.preventDefault()
        rect = canvas.getBoundingClientRect()
        x = event.x - rect.left
        y = event.y - rect.top

        cx = canvas.width / 2
        cy = canvas.height / 2
        f = canvas.width / 30
        # Physical coords, in mm
        (tx, ty) = ((x - cx) / f, -(y - cy) / f)

        h = Hex.from_xy(tx, ty)
        self.cursor = h

        tooltip = document['tooltip']

        tt = self.tooltip(h)
        if (self.drag_start is not None) or (tt is None):
            tooltip.style.display = 'none'
        else:
            tooltip.style.display = 'block'
            tooltip.style.left = str(event.clientX + 10) + 'px'
            tooltip.style.top = str(event.clientY + 10) + 'px'
            tooltip.innerHTML = tt

        if event.buttons:
            if self.drag_start is None:
                p = self.under(h)
                if p is not None:
                    self.drag_start = (h,p)
            else:
                (h0, p) = self.drag_start
                d = h - h0
                self.move_part(p, p.o + d)
                self.drag_start = (h, p)
                self.redraw()
        else:
            self.drag_start = None
            path = Hex(0,0).hop(h)
            self.add_string(path, 0x0000ff)
            self.redraw()

board = Board()

def on_complete(req):
    if req.status == 200 or req.status == 0:
        obj = json.loads(req.text)
        p = Part(obj)
        board.add_part(p)
        board.redraw()
    else:
        print("Error loading file")

def adjust_canvas_size(*args):
    canvas.focus()
    d = min(window.innerWidth, window.innerHeight) - 10
    canvas.attrs["width"] = d
    canvas.attrs["height"] = d

    board.redraw()

canvas.attrs["tabindex"] = "0"
canvas.bind('mousemove', board.on_mouse_move)
canvas.bind('keypress', board.on_keypress)
window.bind('resize', adjust_canvas_size)
ajax.get('rp2040-hex.json', oncomplete=on_complete)
