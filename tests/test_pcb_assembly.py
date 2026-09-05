import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import shapely.geometry as sg

import cuflow as cu
from tools.pcb_assembly import (
    DeviceNameAtlas,
    ExternalFootprint,
    FootprintPad,
    Placement,
    format_device_pad,
    jlcpcb_body_spacing_violations,
    jlcpcb_smd_category,
    jlcpcb_smd_spacing_mm,
    load_name_atlas,
    map_pads_to_topology,
    package_body_size_mm,
    place_component_body,
    place_footprint,
    read_jlc_bom,
    read_jlc_pnp,
    read_preflight_placements,
)
from tools.pcb_topology import DrillHit, build_topology


def footprint(*pads):
    pin_names = {item.number: f"PIN_{item.number}" for item in pads}
    return ExternalFootprint(
        "C1", "TEST", "Maker", "MPN", "https://example.com/C1", "abc",
        "DEVICE", pin_names, tuple(pads))


def pad(number="1", center=(1, 0), sides=("top",), pad_type="smd"):
    return FootprintPad(
        number, pad_type, "rect", center, (0.4, 0.6), 0, sides)


class PlacementTests(unittest.TestCase):
    def test_top_rotation_270_places_positive_x_south(self):
        placed = place_footprint(
            footprint(pad(center=(1, 0))),
            Placement("R1", "C1", (5, 10), "Top", 270),
            ("GTL", "G2L", "G3L", "GBL"),
        )
        self.assertAlmostEqual(placed[0].center[0], 5)
        self.assertAlmostEqual(placed[0].center[1], 9)
        self.assertEqual(placed[0].layers, ("GTL",))
        atlas = DeviceNameAtlas({"C1": "ROOT"}, {})
        self.assertEqual(format_device_pad(placed[0], atlas), "R1.1")

    def test_common_device_pad_naming(self):
        placed = place_footprint(
            footprint(pad(number="3", center=(0, 0))),
            Placement("R2", "C1", (0, 0), "Top", 0),
            ("GTL", "G2L", "G3L", "GBL"),
        )[0]
        atlas = DeviceNameAtlas(
            {"C1": "ROOT"}, {"J3": {"3": "MISO"}})
        self.assertEqual(format_device_pad(placed, atlas), "R2.3")
        self.assertEqual(
            format_device_pad(
                replace(placed, designator="U1", pin_name="GPIO20"), atlas),
            "ROOT.GPIO20")
        self.assertEqual(
            format_device_pad(replace(placed, designator="J3"), atlas),
            "J3.MISO")

    def test_local_y_is_inverted(self):
        placed = place_footprint(
            footprint(pad(center=(0, 1))),
            Placement("R1", "C1", (5, 10), "Top", 0),
            ("GTL", "G2L", "G3L", "GBL"),
        )
        self.assertAlmostEqual(placed[0].center[0], 5)
        self.assertAlmostEqual(placed[0].center[1], 9)

    def test_through_hole_pad_targets_all_copper_layers(self):
        placed = place_footprint(
            footprint(pad(sides=("all",), pad_type="thru_hole")),
            Placement("J1", "C1", (0, 0), "Top", 0),
            ("GTL", "G2L", "G3L", "GBL"),
        )
        self.assertEqual(
            placed[0].layers, ("GTL", "G2L", "G3L", "GBL"))


class ComponentSpacingTests(unittest.TestCase):
    def placed_body(
            self, designator, package, xy, side="Top", rotation=0):
        source = replace(footprint(pad()), package=package)
        return place_component_body(
            source, Placement(designator, "C1", xy, side, rotation))

    def test_package_categories_cover_jlcpcb_matrix_names(self):
        self.assertEqual(jlcpcb_smd_category("R0402"), "0402")
        self.assertEqual(jlcpcb_smd_category("C0603"), "0603")
        self.assertEqual(
            jlcpcb_smd_category("LQFN-56_L7.0-W7.0-P0.4-EP"), "QFN")
        self.assertEqual(
            jlcpcb_smd_category("MSOP-10_L3.0-W3.0-P0.5"), "SOP/SOIC")
        self.assertEqual(
            jlcpcb_smd_category("SOT-23-5_L3.0-W1.7-P0.95"), "SOT")
        self.assertIsNone(jlcpcb_smd_category("OSC-SMD_4P-L3.2-W2.5"))

    def test_body_sizes_use_chip_standard_or_package_dimensions(self):
        self.assertEqual(package_body_size_mm("C0402"), (1.0, 0.5))
        self.assertEqual(
            package_body_size_mm("SOT-23-5_L3.0-W1.7-P0.95"),
            (3.0, 1.7),
        )

    def test_published_spacing_matrix_is_symmetric(self):
        self.assertEqual(jlcpcb_smd_spacing_mm("0402", "QFN"), 1.0)
        self.assertEqual(jlcpcb_smd_spacing_mm("QFN", "0402"), 1.0)
        self.assertEqual(jlcpcb_smd_spacing_mm("1206", "1206"), 0.35)
        self.assertEqual(jlcpcb_smd_spacing_mm("BGA", "BGA"), 2.0)

    def test_body_rotation_follows_pnp_rotation(self):
        body = self.placed_body(
            "U1", "SOT-23-5_L3.0-W1.7-P0.95", (5, 10), rotation=90)
        minimum_x, minimum_y, maximum_x, maximum_y = body.geometry.bounds
        self.assertAlmostEqual(maximum_x - minimum_x, 1.7)
        self.assertAlmostEqual(maximum_y - minimum_y, 3.0)

    def test_same_side_gap_below_recommendation_is_a_violation(self):
        first = self.placed_body("R1", "R0402", (0, 0))
        second = self.placed_body("R2", "R0402", (1.149, 0))
        violations, pair_count = jlcpcb_body_spacing_violations(
            (first, second))
        self.assertEqual(pair_count, 1)
        self.assertEqual(len(violations), 1)
        self.assertAlmostEqual(violations[0].clearance, 0.149)
        self.assertEqual(violations[0].required, 0.15)

    def test_opposite_side_parts_are_not_compared(self):
        first = self.placed_body("R1", "R0402", (0, 0), side="Top")
        second = self.placed_body("R2", "R0402", (0, 0), side="Bottom")
        violations, pair_count = jlcpcb_body_spacing_violations(
            (first, second))
        self.assertEqual(violations, ())
        self.assertEqual(pair_count, 0)


class AttachmentTests(unittest.TestCase):
    def test_pad_maps_to_physical_net(self):
        topology = build_topology({
            "GTL": sg.box(4, 8, 6, 10),
            "GBL": sg.box(20, 20, 21, 21),
        }, ())
        placed = place_footprint(
            footprint(pad(center=(1, 0))),
            Placement("R1", "C1", (5, 10), "Top", 270),
            topology.layer_order,
        )
        attachment = map_pads_to_topology(topology, placed)[0]
        self.assertEqual(attachment.net_ids, ("N001",))
        self.assertGreater(attachment.overlap_area, 0)

    def test_through_hole_uses_actual_connector_not_nominal_land(self):
        top_and_bottom = sg.box(-0.2, -0.2, 0.2, 0.2)
        topology = build_topology({
            "GTL": top_and_bottom,
            "G2L": sg.box(0.3, -0.5, 0.5, 0.5),
            "GBL": top_and_bottom,
        }, (DrillHit(1, 0.3, (0, 0)),))
        large_tht = FootprintPad(
            "1", "thru_hole", "rect", (0, 0), (1, 1), 0, ("all",))
        placed = place_footprint(
            footprint(large_tht),
            Placement("J1", "C1", (0, 0), "Top", 0),
            topology.layer_order,
        )
        attachment = map_pads_to_topology(topology, placed)[0]
        self.assertEqual(attachment.net_ids, ("N001",))


class CsvTests(unittest.TestCase):
    def test_cuflow_manifest_includes_part_excluded_from_assembly(self):
        board = cu.Board((10, 10), 0.1, 0.1, 0.3, 0.6, 0.1, 0.1)

        class PhysicalPart:
            id = "J4"
            inBOM = False
            source = {"LCSC": "C46061679"}

            def pnp_jlc(self):
                return board.DC((3, 4)).setlayer("GBL").right(90)

        board.parts["J"].append(PhysicalPart())
        with tempfile.TemporaryDirectory() as directory:
            basename = str(Path(directory) / "board")
            board.pnp(basename)
            placements = read_preflight_placements(
                Path(basename + "-preflight-placements.json"))
            assembly_pnp = Path(
                basename + "-jlcpcb-pnp.csv").read_text(encoding="utf-8")

        self.assertEqual(placements, (
            Placement("J4", "C46061679", (3, 4), "Bottom", 270),))
        self.assertNotIn("J4", assembly_pnp)

    def test_literal_name_atlas_maps_external_header_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "board.py"
            source.write_text(
                "ATLAS = {\n"
                "  'ic_roots_by_lcsc': {'C1': 'ROOT'},\n"
                "  'header_pins': {'J1': {\n"
                "    'names': ('A', 'B'),\n"
                "    'external_pad_numbers': (2, 1),\n"
                "  }},\n"
                "}\n",
                encoding="utf-8")
            atlas = load_name_atlas(source, "ATLAS")

        self.assertEqual(atlas.ic_roots_by_lcsc["C1"], "ROOT")
        self.assertEqual(atlas.header_pins["J1"], {"2": "A", "1": "B"})

    def test_grouped_bom_designators_join_pnp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bom = root / "bom.csv"
            pnp = root / "pnp.csv"
            bom.write_text(
                'Designator,JLCPCB Part #\n"R1,R2",C123\n',
                encoding="utf-8")
            pnp.write_text(
                "Designator,Mid X,Mid Y,Layer,Rotation\n"
                "R1,1.2mm,3.4mm,Top,90\n"
                "R2,5mm,6mm,Bottom,180\n",
                encoding="utf-8")
            mapping = read_jlc_bom(bom)
            placements = read_jlc_pnp(pnp, mapping)
        self.assertEqual(mapping, {"R1": "C123", "R2": "C123"})
        self.assertEqual(placements[0].xy, (1.2, 3.4))
        self.assertEqual(placements[1].side, "Bottom")

    def test_preflight_manifest_includes_unpopulated_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "placements.json"
            manifest.write_text(
                '{"format": "cuflow-preflight-placements-1", '
                '"placements": [{"designator": "J4", "lcsc": "C46061679", '
                '"x": 30.5, "y": 29.5, "side": "Bottom", '
                '"rotation": 0}]}',
                encoding="utf-8",
            )
            placements = read_preflight_placements(manifest)

        self.assertEqual(placements, (
            Placement("J4", "C46061679", (30.5, 29.5), "Bottom", 0),))


if __name__ == "__main__":
    unittest.main()
