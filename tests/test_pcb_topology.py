import unittest

import shapely.geometry as sg

from tools.pcb_topology import (
    DrillHit,
    InterlayerConnector,
    build_topology,
    internal_closed_contours,
    net_clearance_violations,
    parse_cuflow_gerber_text,
    parse_cuflow_paths_text,
    parse_excellon_text,
)


def gerber_text(*polygons):
    def number(value):
        return f"{round(value * 10000):07d}"

    lines = [
        "G04 test*",
        "%MOMM*%",
        "%FSLAX34Y34*%",
        "%LPD*%",
    ]
    for polygon in polygons:
        lines.append("G36*")
        for index, (x, y) in enumerate(polygon.exterior.coords):
            operation = "D02" if index == 0 else "D01"
            lines.append(f"X{number(x)}Y{number(y)}{operation}*")
        lines.append("G37*")
    lines.append("M02*")
    return "\n".join(lines) + "\n"


class GerberParsingTests(unittest.TestCase):
    def test_touching_regions_form_one_component(self):
        geometry = parse_cuflow_gerber_text(gerber_text(
            sg.box(0, 0, 1, 1),
            sg.box(1, 0, 2, 1),
            sg.box(4, 0, 5, 1),
        ))
        self.assertEqual(len(geometry.geoms), 2)
        self.assertAlmostEqual(geometry.area, 3)

    def test_internal_contours_exclude_largest_outline(self):
        text = "\n".join((
            "X0000000Y0000000D02*",
            "X0100000Y0000000D01*",
            "X0100000Y0100000D01*",
            "X0000000Y0100000D01*",
            "X0000000Y0000000D01*",
            "X0020000Y0020000D02*",
            "X0030000Y0020000D01*",
            "X0030000Y0030000D01*",
            "X0020000Y0030000D01*",
            "X0020000Y0020000D01*",
        ))
        contours = internal_closed_contours(parse_cuflow_paths_text(text))
        self.assertEqual(len(contours), 1)
        self.assertEqual(contours[0].bounds, (2, 2, 3, 3))


class ExcellonParsingTests(unittest.TestCase):
    def test_tools_and_hits(self):
        hits = parse_excellon_text("""\
M48
METRIC,TZ,000.000
T2C0.300
T3C0.650
%
T2
X1250Y-250
T3
X2000Y3000
M30
""")
        self.assertEqual(hits, (
            DrillHit(2, 0.3, (1.25, -0.25)),
            DrillHit(3, 0.65, (2, 3)),
        ))


class TopologyTests(unittest.TestCase):
    def test_net_clearance_accepts_gap_larger_than_threshold(self):
        topology = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 1, 1),
                sg.box(1.11, 0, 2.11, 1),
            )),
        }, ())

        self.assertEqual(net_clearance_violations(topology, 0.1), ())

    def test_net_clearance_reports_buffer_intersection(self):
        topology = build_topology({
            "GTL": sg.MultiPolygon((
                sg.box(0, 0, 1, 1),
                sg.box(1.09, 0, 2.09, 1),
            )),
        }, ())

        violations = net_clearance_violations(topology, 0.1)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].layer, "GTL")
        self.assertEqual(violations[0].net_id, "N002")
        self.assertEqual(violations[0].conflicting_net_ids, ("N001",))

    def test_overlapping_layers_are_separate_without_a_drill(self):
        copper = sg.box(0, 0, 1, 1)
        topology = build_topology({"GTL": copper, "GBL": copper}, ())
        self.assertEqual(len(topology.nets), 2)

    def test_drill_joins_every_layer_with_copper_at_its_center(self):
        copper = sg.box(0, 0, 1, 1)
        layers = {layer: copper for layer in ("GTL", "G2L", "G3L", "GBL")}
        topology = build_topology(
            layers, (DrillHit(2, 0.3, (0.5, 0.5)),))
        self.assertEqual(len(topology.nets), 1)
        self.assertEqual(topology.nets[0].layers, tuple(layers))
        self.assertEqual(topology.connectors[0].layers, tuple(sorted(layers)))

    def test_antipad_plane_is_not_joined(self):
        pad = sg.box(0, 0, 1, 1)
        topology = build_topology({
            "GTL": pad,
            "G2L": sg.box(2, 2, 3, 3),
            "GBL": pad,
        }, (DrillHit(2, 0.3, (0.5, 0.5)),))
        self.assertEqual(len(topology.nets), 2)
        self.assertEqual(topology.connectors[0].layers, ("GBL", "GTL"))

    def test_plated_slot_joins_intersected_outer_copper(self):
        top = sg.box(0, 0, 3, 1)
        bottom = sg.box(0, 0, 3, 1)
        slot = sg.LineString(((1, 0.5), (2, 0.5)))
        topology = build_topology(
            {"GTL": top, "GBL": bottom}, (),
            (InterlayerConnector("slot", slot, kind="plated-slot"),),
        )
        self.assertEqual(len(topology.nets), 1)
        self.assertEqual(topology.connectors[0].kind, "plated-slot")

    def test_component_point_lookup_and_dominant_component(self):
        topology = build_topology({
            "G2L": sg.MultiPolygon((
                sg.box(0, 0, 10, 10),
                sg.box(20, 20, 21, 21),
            )),
        }, ())
        dominant = topology.largest_component("G2L")
        self.assertEqual(dominant.area, 100)
        self.assertEqual(topology.component_at("G2L", (20.5, 20.5)).area, 1)


if __name__ == "__main__":
    unittest.main()
