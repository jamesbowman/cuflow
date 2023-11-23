from browser import document, window, html

d = (window.innerWidth)
# Create a canvas element and set its size
canvas = html.CANVAS(width=d, height=d)
document <= canvas

import hex

def redraw():
    context = canvas.getContext('2d')

    context.fillStyle = 'lightblue'
    context.fillRect(0, 0, canvas.width, canvas.height)

    (w, h) = (canvas.width, canvas.height)

    # Set line width
    context.lineWidth = 4

    context.strokeStyle = 'blue'
    context.beginPath()
    context.moveTo(50, 50)  # Start point (x, y)
    context.lineTo(100, 100)  # End point (x, y)
    context.stroke()

    context.strokeStyle = 'red'
    context.beginPath()
    context.moveTo(.9*w, .9*h)  # Start point (x, y)
    context.lineTo(w, h)  # End point (x, y)
    context.stroke()

def adjust_canvas_size(*args):
    context = canvas.getContext('2d')
    d = min(window.innerWidth, window.innerHeight) - 10
    canvas.attrs["width"] = d
    canvas.attrs["height"] = d
    redraw()

def on_mouse_move(event):
    print(f"Mouse position: {event.x}, {event.y}")
    canvas.focus()

def on_key_press(event):
    print(f"Key pressed: {event.key}")

window.bind('resize', adjust_canvas_size)  # Adjust canvas size on window resize
canvas.attrs["tabindex"] = "0"
canvas.style.borderColor = 'red'
canvas.style.borderWidth = '1px'
print(canvas.style)
canvas.bind('mousemove', on_mouse_move)
canvas.bind('keypress', on_key_press)

adjust_canvas_size()
