import sys
from PIL import Image
import math
import cuflow as cu


import xml.etree.ElementTree as ET

def library(lbrfile):
    tree = ET.parse(lbrfile)
    root = tree.getroot()
    packages = root.find("drawing").find("library").find("packages")
    for child in packages:
        print(child.tag, child.attrib)

__VERSION__ = "0.1.0"

if __name__ == "__main__":
    brd = cu.Board(
        (50, 42),
        trace = cu.mil(5),
        space = cu.mil(5) * 2.0,
        via_hole = 0.3,
        via = 0.6,
        via_space = cu.mil(5),
        silk = cu.mil(6))

    library("adafruit.lbr")
    brd.outline()
    brd.save("arduino_dazzler")
