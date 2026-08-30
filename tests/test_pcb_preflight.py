import tempfile
import unittest
from pathlib import Path

from tools.pcb_preflight import Audit, natural_pad_number_key, write_report


class HtmlReportTests(unittest.TestCase):
    def test_pad_numbers_sort_naturally(self):
        values = ["B1", "A12", "10", "A2", "2", "A1", "P5.10", "P5.2"]

        self.assertEqual(
            sorted(values, key=natural_pad_number_key),
            ["2", "10", "A1", "A2", "A12", "B1", "P5.2", "P5.10"],
        )

    def test_report_is_html_and_escapes_external_values(self):
        audit = Audit()
        audit.add("Example <check>", True, "safe & complete")
        audit.net_rows.append({
            "net": "N001",
            "labels": "GND",
            "device_pad": "RP2040.GPIO20",
            "footprint_pad": "31",
            "lcsc": "C2040",
            "layers": "GTL",
        })
        audit.device_rows.append({
            "designator": "U6",
            "anchor": "device-u6",
            "part_name": "INA226",
            "manufacturer": "Texas Instruments",
            "lcsc": "C49851",
            "lcsc_url": "https://www.lcsc.com/search?q=C49851",
            "pads": [{
                "device_pad": "INA226.SDA",
                "anchor": "device-u6-pad-4",
                "connection_kind": "pads",
                "connections": ({
                    "label": "R3.2",
                    "anchor": "device-r3-pad-2",
                },),
            }],
        })
        audit.device_rows.append({
            "designator": "R3",
            "anchor": "device-r3",
            "part_name": "",
            "manufacturer": "UNI-ROYAL",
            "lcsc": "C25804",
            "lcsc_url": "https://www.lcsc.com/search?q=C25804",
            "pads": [{
                "device_pad": "R3.2",
                "anchor": "device-r3-pad-2",
                "connection_kind": "pads",
                "connections": ({
                    "label": "INA226.SDA",
                    "anchor": "device-u6-pad-4",
                },),
            }],
        })
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "board-preflight.html"
            write_report(report, {"board": "board"}, audit, "")
            output = report.read_text(encoding="utf-8")

        self.assertTrue(output.startswith("<!doctype html>"))
        self.assertIn("Example &lt;check&gt;", output)
        self.assertIn("safe &amp; complete", output)
        self.assertIn("RP2040.GPIO20", output)
        self.assertIn("U6</code><span class=\"device-part-name\">INA226", output)
        self.assertIn('id="device-r3-pad-2"', output)
        self.assertIn('href="#device-r3-pad-2"', output)
        self.assertIn('class="pad-link"', output)
        self.assertIn("animation: pad-highlight 10s ease-out", output)
        self.assertIn("function highlightPad(anchor)", output)
        self.assertIn("Footprint pad", output)
        self.assertNotIn("U1.31", output)
        self.assertIn('href="#automated-checks"', output)
        self.assertIn('id="automated-checks"', output)
        self.assertIn('href="#nets-by-device"', output)
        self.assertIn('id="nets-by-device"', output)
        self.assertIn('href="#nets"', output)
        self.assertIn('id="nets"', output)
        self.assertIn('<nav class="toc" aria-label="Report contents">', output)
        self.assertIn("<h2>Contents</h2>", output)
        self.assertIn('<ul><li><a href="#automated-checks">', output)
        self.assertNotIn('href="#generator-output"', output)

    def test_generator_output_is_included_in_toc_when_present(self):
        audit = Audit()
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "board-preflight.html"
            write_report(report, {"board": "board"}, audit, "generated")
            output = report.read_text(encoding="utf-8")

        self.assertIn('href="#generator-output"', output)
        self.assertIn('id="generator-output"', output)


if __name__ == "__main__":
    unittest.main()
