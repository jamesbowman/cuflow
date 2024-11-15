import sys
import json
from PIL import Image, ImageDraw

from hex import Hex

def circle(dr, x, y, r, c):
    dr.ellipse((x - r, y - r, x + r, y + r), fill=c)

def mark(draw, h, c):
    F = 30
    (x,y) = h.to_plane()
    circle(draw, 256 + F * x, 256 - F * y, F / 8, c)

def hexviz(fn):
    with open(fn) as f:
        obj = json.load(f)
    im = Image.new("RGB", (512, 512))
    draw = ImageDraw.Draw(im)
    for qr in obj["occ"]:
        mark(draw, Hex(*qr), 'gray')
    for nm,qr in obj["sigs"].items():
        print(f"{nm=}")
        mark(draw, Hex(*qr), 'red')
    im.save("out.png")

if __name__ == "__main__":
    hexviz(sys.argv[1])
