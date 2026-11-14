"""Generate FLASH8's 3 mm IBM Plex Sans SemiBold bit and title bitmaps.

Pass the path to IBMPlexSans-SemiBold.otf. Board generation uses the PNGs,
so the font need not be installed on every machine that builds the board.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path)
    args = parser.parse_args()
    font = ImageFont.truetype(str(args.font), 2048)
    assert font.getname() == ("IBM Plex Sans", "SemiBold"), font.getname()
    destination = Path(__file__).resolve().parents[1] / "assets" / "flash8-labels"
    destination.mkdir(parents=True, exist_ok=True)
    for text in [*(str(digit) for digit in range(8)), "FLASH8"]:
        left, top, right, bottom = font.getbbox(text)
        im = Image.new("L", (right - left, bottom - top))
        ImageDraw.Draw(im).text((-left, -top), text, font=font, fill=255)
        im = im.crop(im.getbbox())
        im = im.resize((round(im.width * 600 / im.height), 600), Image.Resampling.LANCZOS)
        im = im.point(lambda value: 255 if value >= 128 else 0, mode="1")
        im.save(destination / f"{text}.png")


if __name__ == "__main__":
    main()
