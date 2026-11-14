FLASH8 bit labels 0–7 and board title

Typeface: IBM Plex Sans SemiBold, from IBMPlexSans-SemiBold.otf.
Rasterized with Pillow at high resolution, downsampled with Lanczos, then
thresholded to monochrome without dithering. White pixels become silkscreen.
Each bitmap is 600 pixels high and prints at 3.000 mm: 0.005 mm per pixel.
The original glyph proportions are preserved to the nearest pixel.
FLASH8 is rotated 90 degrees counterclockwise on the board to read south
to north, centered at (15.5, 24.5) mm.

Regenerate with the project Python:
  python tools/generate_flash8_labels.py /path/to/IBMPlexSans-SemiBold.otf

These bitmaps are checked in so ordinary board generation needs no system font.
IBM Plex is distributed under the SIL Open Font License; these files are
rendered text artwork, not redistributed font software.
