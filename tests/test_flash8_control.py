import unittest

from flash8_control import Flash8


class ShiftRegisterModel:
    """Model independent shift and latch registers sharing one rising edge."""
    def __init__(self, initial):
        self.shift = initial
        self.latch = initial ^ 0xFF
        self.a = self.b = 0
        self.disabled = True
        self.rising_edges = 0

    def unsel(self):
        self.disabled = True

    def sel(self):
        self.disabled = False

    def seta(self, value):
        self.a = value

    def setb(self, value):
        if value and not self.b:
            assert self.disabled, "Selection changed while outputs enabled"
            self.latch, self.shift = self.shift, ((self.shift << 1) | self.a) & 0xFF
            self.rising_edges += 1
        self.b = value


class Flash8ControlTests(unittest.TestCase):
    def test_every_initial_state_and_slot(self):
        for initial in range(256):
            model = ShiftRegisterModel(initial)
            fixture = Flash8(model)
            self.assertEqual(model.latch, 0xFF)
            for slot in range(8):
                before = model.rising_edges
                fixture.program(slot)
                self.assertEqual(model.rising_edges - before, 9)
                self.assertTrue(model.disabled)
                # Printed labels 0..7 correspond directly to QA..QH.
                self.assertEqual(model.latch,
                                 (0xFE, 0xFD, 0xFB, 0xF7,
                                  0xEF, 0xDF, 0xBF, 0x7F)[slot])

    def test_transaction_deselects_after_exception(self):
        model = ShiftRegisterModel(0)
        fixture = Flash8(model)
        with self.assertRaisesRegex(RuntimeError, "transfer failed"):
            with fixture.transaction(5):
                self.assertFalse(model.disabled)
                self.assertEqual(model.latch, 0xDF)
                raise RuntimeError("transfer failed")
        self.assertTrue(model.disabled)
        self.assertFalse(fixture.active)

    def test_invalid_or_nested_selection(self):
        model = ShiftRegisterModel(0)
        fixture = Flash8(model)
        for slot in (-1, 8):
            with self.assertRaises(ValueError):
                fixture.program(slot)
        with fixture.transaction(0):
            with self.assertRaises(RuntimeError):
                fixture.program(1)
            with self.assertRaises(RuntimeError):
                with fixture.transaction(1):
                    pass


if __name__ == "__main__":
    unittest.main()
