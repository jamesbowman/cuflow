import time
import json

from hex import Hex

from browser import document, window, html, ajax, aio

d = (window.innerWidth)
# Create a canvas element and set its size
canvas = html.CANVAS(width=d, height=d)
document <= canvas

gl = canvas.getContext('webgl')

from browser import document, window

a = window.Float32Array.new(10000)
for i in range(0, a.length, 5):
    a[i+0] = window.Math.random() * 2 - 1
    a[i+1] = window.Math.random() * 2 - 1

    a[i+2] = window.Math.random()
    a[i+3] = window.Math.random()
    a[i+4] = window.Math.random()

# https://www.desultoryquest.com/blog/drawing-anti-aliased-circular-points-using-opengl-slash-webgl/

vx_shader = """
attribute vec3 c;
attribute vec4 vRgbaColor;
varying  vec4 color;

void main(void){
    gl_Position = vec4(c, 1.0);
    gl_PointSize = 10.0;
    color = vRgbaColor;
}
"""

frag_shader = """
precision mediump float;
varying  vec4 color;

void
main()
{
    float r = 0.0, delta = 0.0, alpha = 1.0;
    vec2 cxy = 2.0 * gl_PointCoord - 1.0;
    r = dot(cxy, cxy);
    if (r > 1.0) {
        discard;
    }
    gl_FragColor = color * (alpha);
}
"""

if 1:
    vertShader = gl.createShader(gl.VERTEX_SHADER)
    gl.shaderSource(vertShader, vx_shader)
    gl.compileShader(vertShader)
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
    gl.vertexAttribPointer(coord, 2, gl.FLOAT, False, 5*4, 0)
    gl.enableVertexAttribArray(coord)

    color = gl.getAttribLocation(prog, "vRgbaColor")
    gl.vertexAttribPointer(color, 3, gl.FLOAT, False, 5*4, 2*4)
    gl.enableVertexAttribArray(color)


def redraw():
    gl.viewport(0,0,canvas.width,canvas.height)

    gl.clearColor(0, 0.1, 0, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    p = int(window.Math.random() * 2000)
    gl.drawArrays(gl.POINTS, p, 500)

def on_mouse_move(event):
    redraw()

redraw()
canvas.bind('mousemove', on_mouse_move)
