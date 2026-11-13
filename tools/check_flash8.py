"""Check FLASH8 connectivity and clearances from its generated Gerbers.

Run from the repository root with: python -m tools.check_flash8
This is an electrical/layout check, not a completed manufacturing preflight.
"""

import csv
from dataclasses import replace
import json
from pathlib import Path

import shapely.geometry as sg

from tools.pcb_preflight import Audit, audit_intended_netlist
from tools.pcb_topology import (
    build_topology, net_clearance_violations, parse_cuflow_gerber,
    parse_cuflow_paths_text, parse_excellon,
)


def check():
    layers = {name: parse_cuflow_gerber(Path(f"flash8.{name}"))
              for name in ("GTL", "G2L", "G3L", "GBL")}
    drills = parse_excellon(Path("flash8.TXT"))
    topology = build_topology(layers, drills)
    audit = Audit()
    audit_intended_netlist(audit, Path("flash8.net.json"), "flash8", topology)

    document = json.loads(Path("flash8.net.json").read_text())
    nets = {
        (t["designator"], t["pad_index"]): net["id"]
        for net in document["nets"] for t in net["terminals"]}
    expected = {
        "GND": [("J1", 1), ("J1", 2), ("U1", 8)],
        "VCC": [("J1", 3), ("J1", 4), ("U1", 10), ("U1", 16)],
        "5V": [("J1", 5), ("J1", 6)],
        "SCK": [("J2", 1)], "MOSI": [("J2", 2)],
        "MISO": [("J2", 3)], "IO2": [("J2", 4)], "IO3": [("J2", 5)],
        "OE": [("J2", 6), ("U1", 13), ("R1", 2)],
        "A": [("J2", 7), ("U1", 14)],
        "B": [("J2", 8), ("U1", 11), ("U1", 12)],
    }
    expected["VCC"] += [("C1", 1), ("C2", 1), ("R1", 1), ("R2", 1), ("R4", 1), ("R5", 1)]
    expected["GND"] += [("C1", 2), ("C2", 2), ("R3", 1)]
    for name, ref in (("A", "R2"), ("B", "R3"), ("IO2", "R4"), ("IO3", "R5")):
        expected[name].append((ref, 2))
    for slot, qpin in enumerate((15, 1, 2, 3, 4, 5, 6, 7)):
        ref = f"U{slot + 2}"
        expected[f"CS{slot}"] = [
            ("U1", qpin), (ref, 1), (f"R{6 + 2 * slot}", 2),
            (f"D{slot + 1}", 2)]
        expected[f"LED{slot}_A"] = [
            (f"R{7 + 2 * slot}", 2), (f"D{slot + 1}", 1)]
        for name, pin in (("MISO", 2), ("IO2", 3), ("GND", 4),
                          ("MOSI", 5), ("SCK", 6), ("IO3", 7), ("VCC", 8)):
            expected[name].append((ref, pin))
        expected["VCC"].extend([
            (f"R{6 + 2 * slot}", 1), (f"R{7 + 2 * slot}", 1),
            (f"C{slot + 3}", 1)])
        expected["GND"].append((f"C{slot + 3}", 2))
    identities = {}
    for name, pins in expected.items():
        connected = {nets.get(pin) for pin in pins}
        audit.add(f"Pin mapping: {name}", len(connected) == 1 and None not in connected,
                  ", ".join(f"{ref}.{pin}" for ref, pin in pins))
        identities[name] = next(iter(connected))
    audit.add("Independent functional nets", len(set(identities.values())) == len(identities),
              "Power, shared signals, chip selects and LED anodes stay distinct")

    violations = net_clearance_violations(topology, 0.12)
    audit.add("Copper clearance >= 0.12 mm", not violations,
              str(violations[:12]) if violations else "All four copper layers checked")
    outer_violations = net_clearance_violations(
        replace(topology, layer_order=("GTL", "GBL")), 0.15)
    audit.add("Outer-layer copper clearance >= 0.15 mm", not outer_violations,
              str(outer_violations[:12]) if outer_violations else "Top and bottom checked")
    bom = {ref: row for row in csv.DictReader(Path("flash8-jlcpcb-bom.csv").open())
           for ref in row["Designator"].split(",")}
    for slot in range(8):
        correct = (bom[f"R{6 + 2 * slot}"]["Comment"] == "470" and
                   bom[f"R{7 + 2 * slot}"]["Comment"] == "1.5k" and
                   bom[f"D{slot + 1}"]["Comment"] == "Red LED" and
                   bom[f"U{slot + 2}"]["Footprint"] == "SOIC-8-208mil" and
                   bom[f"C{slot + 3}"]["Comment"] == "100nF")
        audit.add(f"Slot {slot} component values", correct,
                  "470 ohm pull-up, 1.5 kohm LED resistor, red LED, wide SOIC-8, 100 nF")
    audit.add("Shift register selection", bom["U1"]["Comment"] == "SN74LVC595APWR",
              bom["U1"]["Comment"])
    outline = sg.Polygon(parse_cuflow_paths_text(Path("flash8.GML").read_text())[0])
    for layer, copper in layers.items():
        clearance = 0.19 if layer in ("G2L", "G3L") else 0.39
        outside = copper.difference(outline.buffer(-clearance))
        audit.add(f"Copper edge clearance: {layer}", outside.area < 1e-6,
                  f">= {clearance:.2f} mm")
    audit.add("Every drill touches copper", not topology.unmapped_drill_indices,
              f"{len(drills)} plated drills")
    points = [sg.Point(hit.xy).buffer(hit.diameter / 2) for hit in drills]
    collisions = [(i, j) for i, a in enumerate(points) for j, b in enumerate(points[:i])
                  if a.distance(b) < 0.19]
    audit.add("Drill separation >= 0.19 mm", not collisions, str(collisions[:12]))
    report = {"passed": audit.passed, "scope": "Electrical/layout checks; not manufacturing release",
              "checks": [vars(item) for item in audit.checks]}
    Path("flash8-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    for item in audit.checks:
        print(f"{'PASS' if item.passed else 'FAIL'} {item.name}: {item.detail}")
    return audit.passed


if __name__ == "__main__":
    raise SystemExit(0 if check() else 1)
