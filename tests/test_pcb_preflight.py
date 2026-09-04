import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import shapely.geometry as sg

from tools.pcb_preflight import (
    Audit,
    audit_intended_netlist,
    natural_pad_number_key,
    stable_json_hash,
    write_report,
)
from tools.pcb_topology import build_topology


def terminal(designator, pad_index, pad, x, y):
    return {
        "designator": designator,
        "pad_index": pad_index,
        "pad": pad,
        "layer": "GTL",
        "x_mm": x,
        "y_mm": y,
    }


def check(audit, name):
    return next(item for item in audit.checks if item.name == name)


class IntendedNetTests(unittest.TestCase):
    def audit_document(self, document, topology, expected_hash=None):
        audit = Audit()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.net.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            audit_intended_netlist(
                audit, path, "board", topology,
                expected_hash=expected_hash)
        return audit

    def connectivity_document(self):
        return {
            "format": "cuflow-netlist-1",
            "board": "board",
            "nets": [
                {"id": "L001", "name": None, "terminals": [
                    terminal("J1", 1, "A", 0.5, 0.5),
                    terminal("U1", 1, "B", 0.5, 2.5),
                ]},
                {"id": "L002", "name": None, "terminals": [
                    terminal("J2", 1, "C", 2.5, 0.5),
                    terminal("U2", 1, "D", 2.5, 2.5),
                ]},
            ],
        }

    def discovered_hash(self, document, topology):
        result = check(
            self.audit_document(document, topology),
            "Discovered netlist connectivity hash",
        )
        match = re.search(r"SHA-256 ([0-9a-f]{64})", result.detail)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_connectivity_hash_is_sequence_order_independent(self):
        document = {
            "format": "cuflow-discovered-netlist-1",
            "board": "board",
            "nets": [
                {"terminals": [
                    {"designator": "J1", "pad_index": 1, "pad": "A"},
                    {"designator": "U1", "pad_index": 1, "pad": "B"},
                ]},
                {"terminals": [
                    {"designator": "J2", "pad_index": 1, "pad": "C"},
                    {"designator": "U2", "pad_index": 1, "pad": "D"},
                ]},
            ],
            "unattached": [],
        }
        reordered = copy.deepcopy(document)
        reordered["nets"].reverse()
        for net in reordered["nets"]:
            net["terminals"].reverse()

        self.assertEqual(
            stable_json_hash(document),
            stable_json_hash(reordered),
        )

    def test_connectivity_hash_ignores_geometry_and_generated_net_ids(self):
        document = self.connectivity_document()
        topology = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 1, 3),
                sg.box(2, 0, 3, 3),
            )),
        }, ())
        moved = copy.deepcopy(document)
        for index, net in enumerate(moved["nets"], 20):
            net["id"] = f"L{index:03d}"
            for item in net["terminals"]:
                item["layer"] = "GBL"
                item["x_mm"] += 10
                item["y_mm"] += 10
        moved_topology = build_topology({
            "GBL": sg.MultiPolygon((
                sg.box(10, 10, 11, 13),
                sg.box(12, 10, 13, 13),
            )),
        }, ())

        self.assertEqual(
            self.discovered_hash(document, topology),
            self.discovered_hash(moved, moved_topology),
        )

    def test_connectivity_hash_changes_when_terminal_groups_change(self):
        document = self.connectivity_document()
        vertical = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 1, 3),
                sg.box(2, 0, 3, 3),
            )),
        }, ())
        horizontal = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 3, 1),
                sg.box(0, 2, 3, 3),
            )),
        }, ())

        self.assertNotEqual(
            self.discovered_hash(document, vertical),
            self.discovered_hash(document, horizontal),
        )

    def test_configured_connectivity_hash_is_a_gate(self):
        document = self.connectivity_document()
        topology = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 1, 3),
                sg.box(2, 0, 3, 3),
            )),
        }, ())
        actual_hash = self.discovered_hash(document, topology)

        matching = self.audit_document(
            document, topology, actual_hash)
        mismatch = self.audit_document(document, topology, "0" * 64)

        self.assertTrue(check(
            matching, "Discovered netlist connectivity hash").passed)
        mismatch_check = check(
            mismatch, "Discovered netlist connectivity hash")
        self.assertFalse(mismatch_check.passed)
        self.assertIn("expected " + "0" * 64, mismatch_check.detail)

    def test_distinct_logical_nets_on_one_physical_net_are_a_short(self):
        topology = build_topology({"GTL": sg.box(0, 0, 4, 1)}, ())
        audit = self.audit_document({
            "format": "cuflow-netlist-1",
            "board": "board",
            "nets": [
                {"id": "L001", "name": None, "terminals": [
                    terminal("J1", 1, "DTR", 0.5, 0.5),
                    terminal("U1", 1, "GPIO12", 1.5, 0.5),
                ]},
                {"id": "L002", "name": None, "terminals": [
                    terminal("J1", 2, "RTS", 2.5, 0.5),
                    terminal("U1", 2, "GPIO13", 3.5, 0.5),
                ]},
            ],
        }, topology)

        self.assertTrue(check(audit, "Intended net manifest").passed)
        self.assertTrue(
            check(audit, "Intended net terminal attachment").passed)
        self.assertTrue(check(audit, "Intended net continuity").passed)
        isolation = check(audit, "Intended net isolation")
        self.assertFalse(isolation.passed)
        self.assertIn("N001 joins L001", isolation.detail)
        self.assertIn("and L002", isolation.detail)
        self.assertIn("U1.GPIO12", isolation.detail)
        self.assertIn("U1.GPIO13", isolation.detail)

    def test_one_logical_net_on_two_physical_nets_is_an_open(self):
        topology = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 1, 1),
                sg.box(2, 0, 3, 1),
            )),
        }, ())
        audit = self.audit_document({
            "format": "cuflow-netlist-1",
            "board": "board",
            "nets": [{
                "id": "L001",
                "name": None,
                "terminals": [
                    terminal("U1", 1, "A", 0.5, 0.5),
                    terminal("U2", 1, "B", 2.5, 0.5),
                ],
            }],
        }, topology)

        continuity = check(audit, "Intended net continuity")
        self.assertFalse(continuity.passed)
        self.assertIn("L001 spans N001/N002", continuity.detail)
        self.assertTrue(check(audit, "Intended net isolation").passed)

    def test_unattached_terminal_fails_attachment_and_continuity(self):
        topology = build_topology({"GTL": sg.box(0, 0, 1, 1)}, ())
        audit = self.audit_document({
            "format": "cuflow-netlist-1",
            "board": "board",
            "nets": [{
                "id": "L001",
                "name": None,
                "terminals": [
                    terminal("U1", 1, "A", 0.5, 0.5),
                    terminal("U2", 1, "B", 2.5, 0.5),
                ],
            }],
        }, topology)

        attachment = check(audit, "Intended net terminal attachment")
        self.assertFalse(attachment.passed)
        self.assertIn("U2.B", attachment.detail)
        continuity = check(audit, "Intended net continuity")
        self.assertFalse(continuity.passed)
        self.assertIn("L001 has unattached U2.B", continuity.detail)

    def test_terminal_cannot_belong_to_two_logical_nets(self):
        topology = build_topology({"GTL": sg.box(0, 0, 1, 1)}, ())
        shared = terminal("U1", 1, "A", 0.5, 0.5)
        audit = self.audit_document({
            "format": "cuflow-netlist-1",
            "board": "board",
            "nets": [
                {"id": "L001", "name": None,
                 "terminals": [shared, terminal("U2", 1, "B", .5, .5)]},
                {"id": "L002", "name": None,
                 "terminals": [shared, terminal("U3", 1, "C", .5, .5)]},
            ],
        }, topology)

        manifest = check(audit, "Intended net manifest")
        self.assertFalse(manifest.passed)
        self.assertIn(
            "U1 pad 1 belongs to both L001 and L002", manifest.detail)


class HtmlReportTests(unittest.TestCase):
    def test_pad_numbers_sort_naturally(self):
        values = ["B1", "A12", "10", "A2", "2", "A1", "P5.10", "P5.2"]

        self.assertEqual(
            sorted(values, key=natural_pad_number_key),
            ["2", "10", "A1", "A2", "A12", "B1", "P5.2", "P5.10"],
        )

    def test_report_is_html_and_escapes_external_values(self):
        audit = Audit()
        audit.netlist_hash = "a" * 64
        audit.add("Example <check>", True, "safe & complete")
        audit.add(
            "Clearance", False, "N001 intersects N002",
            '<a class="net-link" href="#net-n001"><code>N001</code></a> '
            'intersects <a class="net-link" href="#net-n002"><code>N002</code></a>',
        )
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
        self.assertIn(
            "Discovered netlist SHA-256:\n      <code>" + "a" * 64,
            output,
        )
        self.assertNotIn("manual CAM gate", output)
        self.assertIn("Example &lt;check&gt;", output)
        self.assertIn("safe &amp; complete", output)
        self.assertIn('id="net-n001"', output)
        self.assertIn('href="#net-n001"', output)
        self.assertIn('<code>N001</code></a> intersects', output)
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
