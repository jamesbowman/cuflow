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

a = window.Int16Array.new(2 * 500)
for i in range(a.length // 2):
    t = i / (a.length // 2)
    th = math.pi * 3 * t
    r = 0.3 + 0.7 * t
    a[2*i+0] = 32767 * (math.cos(th) * r)
    a[2*i+1] = 32767 * (math.sin(th) * r)

a_color = window.Uint32Array.new(10000)
for i in range(0, a_color.length, 1):
    a_color[i] = int(0x1000000 * window.Math.random())

for i,h in enumerate(Hex(0, 0).neighbors()):
    a[2*i+0] = h.q
    a[2*i+1] = h.r

a_color[0] = 0x00eeff
a_color[1] = 0x440eff

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
    gl_PointSize = 10.0;
    color = vRgbaColor;
    color.a = 1.0;
}
"""

frag_shader = """#version 300 es
precision mediump float;
in  vec4 color;
out vec4 fragColor;

void
main()
{
    float r = 0.0, delta = 0.0, alpha = 1.0;
    vec2 cxy = 2.0 * gl_PointCoord - 1.0;
    r = dot(cxy, cxy);
    if (r > 1.0) {
        discard;
    }
    fragColor = color * (alpha);
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

    fragShader = gl.createShader(gl.FRAGMENT_SHADER)
    gl.shaderSource(fragShader, frag_shader)
    gl.compileShader(fragShader)

    prog = gl.createProgram()
    gl.attachShader(prog, vertShader)
    gl.attachShader(prog, fragShader)
    gl.linkProgram(prog)
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


def redraw():
    gl.viewport(0,0,canvas.width,canvas.height)

    gl.clearColor(0, 0.1, 0, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.drawArrays(gl.POINTS, 0, 7)

def on_mouse_move(event):
    redraw()

redraw()
canvas.bind('mousemove', on_mouse_move)
