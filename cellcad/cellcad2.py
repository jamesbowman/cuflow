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

frag_shader = """#version 300 es

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

if 1:
    if 0:
        vertShader = gl.createShader(gl.VERTEX_SHADER)
        gl.shaderSource(vertShader, vx_shader)
        gl.compileShader(vertShader)
    else:
        vertShader = createShader(gl.VERTEX_SHADER, vx_shader)

    fragShader = createShader(gl.FRAGMENT_SHADER, frag_shader)

    prog = gl.createProgram()
    gl.attachShader(prog, vertShader)
    gl.attachShader(prog, fragShader)
    gl.linkProgram(prog)
    gl.useProgram(prog)

def update_arrays():
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
    def __init__(self, nm, hex):
        self.nm = nm
        self.hex = hex
        self.o = Hex(-15, 15)
    def draw(self, mark):
        self.covered = set()
        self.named = {}
        obj = self.hex
        for qr in obj["occ"]:
            h = self.o + Hex(*qr)
            mark(h, 0x606060)
            self.covered.add(h)
        for i,(nm,qr) in enumerate(obj["sigs"].items()):
            h = self.o + Hex(*qr)
            mark(h, twenty_hex[i])
            self.named[h] = f"{self.nm}.{nm}"
            print(i, nm, twenty_hex[i])

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
        a = self.alloc
        self.alloc = p.a0
        p.draw(self.mark)
        self.alloc = a

    def redraw(self):
        gl.viewport(0,0,canvas.width,canvas.height)
        update_arrays()

        gl.clearColor(0, .1, 0, 1)
        gl.clear(gl.COLOR_BUFFER_BIT)
        gl.disable(gl.DEPTH_TEST);
        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        gl.enable(gl.BLEND);
        gl.drawArrays(gl.POINTS, 0, self.alloc)

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
        
    def on_mouse_move(self, event):
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
                print("DRAG START")
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

        return
        # self.mark(h, 0x008080)
        p = self.parts['rp2040']
        p.o = h
        self.move_part(p, o)
        self.redraw()

board = Board()

canvas.bind('mousemove', board.on_mouse_move)

def on_complete(req):
    if req.status == 200 or req.status == 0:
        obj = json.loads(req.text)
        p = Part('rp2040', obj)
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

window.bind('resize', adjust_canvas_size)
ajax.get('c0402-hex.json', oncomplete=on_complete)
