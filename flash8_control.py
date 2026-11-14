"""Select and identify FLASH8 devices through the SPIDriver Python API.

Selection programming never asserts CS. transaction() gates the selected
output only while the caller is transferring bytes. No erase/write commands
are issued by the CLI.
"""

import argparse
from contextlib import contextmanager
import operator
import time


# Footprints U2..U9 -> shift-register bits QA=0 through QH=7.
# Public slot numbers and silkscreen labels are the bit numbers themselves.
FLASH_OUTPUT_BITS = (0, 2, 4, 6, 1, 3, 5, 7)


class Flash8:
    def __init__(self, driver):
        self.driver = driver
        self.active = False
        self.slot = None
        self.program(None)

    def program(self, slot):
        """Select printed label 0..7 (QA..QH), or None to deselect all."""
        if self.active:
            raise RuntimeError("Cannot change slots during a transaction")
        if slot is not None:
            slot = operator.index(slot)
            if not 0 <= slot < 8:
                raise ValueError("Slot must be 0 through 7, or None")
        self.slot = None
        driver = self.driver
        driver.unsel()
        driver.setb(0)
        pattern = 0xFF if slot is None else 0xFF ^ (1 << slot)
        # First eight edges fill the shift register, MSB first (QH to QA).
        # The ninth edge latches that value and shifts an unused one into QA.
        bits = [(pattern >> bit) & 1 for bit in range(7, -1, -1)] + [1]
        for bit in bits:
            driver.seta(bit)
            driver.setb(1)
            driver.setb(0)
        self.slot = slot

    @contextmanager
    def transaction(self, slot):
        if self.active:
            raise RuntimeError("Transactions cannot be nested")
        self.program(slot)
        if slot is None:
            raise ValueError("A transaction needs a slot")
        self.active = True
        try:
            self.driver.sel()
            yield self.driver
        finally:
            self.driver.unsel()
            self.active = False

    def jedec_id(self, slot):
        with self.transaction(slot) as driver:
            driver.write(b"\x9f")
            return bytes(driver.read(3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="SPIDriver serial port")
    args = parser.parse_args()
    from spidriver import SPIDriver
    driver = SPIDriver(args.port)
    fixture = Flash8(driver)
    try:
        if driver.product == "spidriverq":
            driver.set_width(1)
            driver.set_speed(1_000_000)
            driver.set2(1)
            driver.set3(1)
        driver.setmode(0)
        # Allow power-up and output-disable settling before the first query.
        time.sleep(0.01)
        for slot in range(8):
            identity = fixture.jedec_id(slot)
            note = " (empty or unresponsive)" if identity in (b"\xff" * 3, b"\0" * 3) else ""
            ref = FLASH_OUTPUT_BITS.index(slot) + 2
            print(f"{slot} / U{ref}: {identity.hex(' ')}{note}")
    finally:
        driver.unsel()
        fixture.program(None)


if __name__ == "__main__":
    main()
