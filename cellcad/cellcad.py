import time
import json

from hex import Hex

from browser import document, window, html, ajax, aio

d = (window.innerWidth)
# Create a canvas element and set its size
canvas = html.CANVAS(width=d, height=d)
document <= canvas

ctx = canvas.getContext('2d')

def withidentity(f):
    ctx.save()
    ctx.setTransform()
    f()
    ctx.restore()

async def create_image_bitmap():
    # Draw something on the canvas
    ctx.fillStyle = "green"
    ctx.fillRect(10, 10, 100, 100)

    # Call window.createImageBitmap
    print("promise", window.createImageBitmap(canvas))
    bitmap = await aio.run(window.createImageBitmap(canvas))
    
    # Use the bitmap here, for example, log it to console or draw it on another canvas
    print(bitmap)

class Part:
    def __init__(self, hex):
        self.hex = hex
        # self.prerender()

    def draw(self):
        obj = self.hex
        for qr in obj["occ"]:
            mark(Hex(*qr), 'gray')
        for nm,qr in obj["sigs"].items():
            # print(f"{nm=}")
            mark(Hex(*qr), 'red')

    def prerender(self):
        withidentity(lambda: ctx.clearRect(0, 0, canvas.width, canvas.height))
        self.draw()
        print(aio.run(create_bitmap()))
        assert 0
        return
        d = ctx.getImageData(0, 0, canvas.width, canvas.height)
        self.img = document.ImageData(d, canvas.width, canvas.height)

class Board:
    def __init__(self):
        self.redrawing = False
        self.pending = set()
        self.parts = {}
        self.painted = {(Hex(0, 0), 'yellow')}

    def add_part(self, nm, p):
        self.parts[nm] = p

    def redraw(self):
        ctx.fillStyle = '#333'
        withidentity(lambda: ctx.fillRect(0, 0, canvas.width, canvas.height))

        if 0:
            # Set line width
            ctx.lineWidth = .2

            ctx.strokeStyle = 'yellow'
            ctx.beginPath()
            ctx.moveTo(0, 0)  # Start point (x, y)
            ctx.lineTo(10, 10)  # End point (x, y)
            ctx.stroke()

        # circle(0, 0, 10, 'green')
        if 1:
            for nm,p in self.parts.items():
                p.draw()

        for (h,c) in self.painted:
            mark(h, c)

        ctx.filter = "blur(2px) brightness(50%)"
        self.bg = ctx.getImageData(0, 0, canvas.width, canvas.height)

    def rubberband0(self, x, y):
        ctx.filter = "blur(0px)"
        ctx.putImageData(self.bg, 0, 0)

        ctx.lineWidth = .1
        ctx.strokeStyle = 'yellow'
        ctx.beginPath()
        ctx.moveTo(0, 0)
        ctx.lineTo(x, y)
        ctx.stroke()

    def rubberband(self, x, y):
        ctx.filter = "blur(0px)"
        ctx.putImageData(self.bg, 0, 0)

        ctx.lineWidth = .1
        ctx.strokeStyle = 'yellow'

        ctx.beginPath()

        print("PATH")
        h = Hex.from_xy(x, y)
        ctx.moveTo(0, 0)
        for p in Hex(0, 0).route(h)[1:]:
            print(p)
            ctx.lineTo(*p.to_plane())

        ctx.stroke()

board = Board()

def circle(x, y, r, c):
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 2*3.14159)
    ctx.fillStyle = c
    ctx.fill()

def mark(h, c):
    (x,y) = h.to_plane()
    circle(x, y, 0.2, c)

def redraw():
    ctx.fillStyle = '#333'
    withidentity(lambda: ctx.fillRect(0, 0, canvas.width, canvas.height))

    if 0:
        # Set line width
        ctx.lineWidth = .2

        ctx.strokeStyle = 'yellow'
        ctx.beginPath()
        ctx.moveTo(0, 0)  # Start point (x, y)
        ctx.lineTo(10, 10)  # End point (x, y)
        ctx.stroke()

    # circle(0, 0, 10, 'green')
    if 0:
        for nm,p in board.parts.items():
            print(nm, p)
            p.draw()
    if 0 and board.parts:
        o = board.parts["rp2040"]
        # ctx.putImageData(o.img, 0, 0)
        # ctx.drawImage(o.img, 0, 0)
        # print(o.img)

    for (h,c) in board.painted:
        mark(h, c)

def paint_1(de):
    if not de in board.painted:
        board.painted.add(de)
        mark(*de)

def adjust_canvas_size(*args):
    canvas.focus()
    d = min(window.innerWidth, window.innerHeight) - 10
    canvas.attrs["width"] = d
    canvas.attrs["height"] = d

    (w, h) = (canvas.width, canvas.height)
    ctx.setTransform()
    ctx.translate(w / 2, h / 2)
    ctx.scale(w / 30, h / 30)

    board.redraw()

def on_mouse_move(event):
    rect = canvas.getBoundingClientRect()
    x = event.x - rect.left
    y = event.y - rect.top
    m = ctx.getTransform()
    # Physical coords, in mm
    (tx, ty) = ((x - m.e) / m.a, (y - m.f) / m.d)

    board.rubberband(tx, ty)
    return

    h = Hex.from_xy(tx, ty)
    de = (h, 'orange')

    board.painted.add(de)

    # redraw()

def on_key_press(event):
    print(f"Key pressed: {event.key}")

def app():
    window.bind('resize', adjust_canvas_size)
    canvas.attrs["tabindex"] = "0"
    canvas.bind('mousemove', on_mouse_move)
    canvas.bind('keypress', on_key_press)
    t0 = time.time()
    board.redraw()
    t1 = time.time()
    print(t1 - t0)

def on_complete(req):
    if req.status == 200 or req.status == 0:
        obj = json.loads(req.text)
        board.add_part('rp2040', Part(obj))
        def after(p):
            print("AFTER", p)
            app()
        n = window.foo(canvas, after)
        print("returned", n)
    else:
        print("Error loading file")

adjust_canvas_size()
ajax.get('rp2040-hex.json', oncomplete=on_complete)
