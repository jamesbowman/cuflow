import math
import unittest
from types import SimpleNamespace

from tools.fetch_easyeda_footprints import pad_drill, silkscreen


class PadDrillTests(unittest.TestCase):
    # Strings as easyeda2kicad's drill_to_ki() writes them.
    def test_round_drill_has_equal_width_and_length(self):
        self.assertEqual(pad_drill("(drill 1.0)"), [1.0, 1.0])

    def test_oval_drill_keeps_both_dimensions(self):
        self.assertEqual(pad_drill("(drill oval 0.6000000000000001 1.7)"),
                         [0.6000000000000001, 1.7])

    def test_surface_pad_has_no_drill(self):
        self.assertIsNone(pad_drill(""))

    def test_unrecognised_drill_is_an_error(self):
        with self.assertRaises(ValueError):
            pad_drill("(drill offset 1 2)")


def exported(tracks=(), rectangles=(), circles=(), arcs=()):
    return SimpleNamespace(
        tracks=list(tracks), rectangles=list(rectangles),
        circles=list(circles), arcs=list(arcs))


def polyline(layers, points, width=0.15):
    return SimpleNamespace(
        layers=layers,
        points_start_x=[p[0] for p in points[:-1]],
        points_start_y=[p[1] for p in points[:-1]],
        points_end_x=[p[0] for p in points[1:]],
        points_end_y=[p[1] for p in points[1:]],
        stroke_width=width)


class SilkscreenTests(unittest.TestCase):
    def test_only_top_silkscreen_is_kept(self):
        strokes = silkscreen(exported(tracks=[
            polyline("F.SilkS", [(0, 0), (1, 0), (1, 1)]),
            polyline("F.Fab", [(0, 0), (2, 0)]),
        ]))
        self.assertEqual(strokes, [
            {"line": [[0, 0], [1, 0]], "width": 0.15},
            {"line": [[1, 0], [1, 1]], "width": 0.15},
        ])

    def test_circle_radius_comes_from_its_end_point(self):
        circle = SimpleNamespace(
            layers="F.SilkS", cx=1, cy=2, end_x=4, end_y=6, stroke_width=0.2)
        self.assertEqual(silkscreen(exported(circles=[circle])),
                         [{"circle": [1, 2, 5.0], "width": 0.2}])

    def test_arc_is_sampled_from_first_point_through_its_sweep(self):
        # KiCad 5 fp_arc: start is the centre, end the first point.
        arc = SimpleNamespace(
            layers="F.SilkS", start_x=0, start_y=0, end_x=2, end_y=0,
            angle=90, stroke_width=0.1)
        (stroke,) = silkscreen(exported(arcs=[arc]))
        points = stroke["line"]
        self.assertEqual(len(points), 10)
        for actual, expected in ((points[0], (2, 0)), (points[-1], (0, 2))):
            self.assertAlmostEqual(actual[0], expected[0])
            self.assertAlmostEqual(actual[1], expected[1])
        for x, y in points:
            self.assertAlmostEqual(math.hypot(x, y), 2)


if __name__ == "__main__":
    unittest.main()
