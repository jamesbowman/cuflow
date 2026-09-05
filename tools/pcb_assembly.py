#!/usr/bin/env python3
"""Map externally sourced package pads onto reconstructed PCB copper nets."""

from __future__ import annotations

import ast
import csv
import itertools
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import shapely.affinity as sa
import shapely.geometry as sg
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

if __package__:
    from .pcb_topology import BoardTopology
else:
    from pcb_topology import BoardTopology


FOOTPRINT_FORMAT = "cuflow-easyeda-part-2"
PREFLIGHT_PLACEMENT_FORMAT = "cuflow-preflight-placements-1"
JLCPCB_SMD_SPACING_URL = (
    "https://jlcpcb.com/help/article/minimum-spacing-for-smd-components")

# JLCPCB's package-pair recommendations, in millimetres.  The table is
# symmetric; keeping the published category order makes lookup and reporting
# deterministic.
JLCPCB_SMD_CATEGORIES = (
    "0201", "0402", "0603", "0805", "1206",
    "QFN", "QFP", "SOP/SOIC", "SOT", "BGA",
)
_JLCPCB_SMD_SPACING_ROWS = (
    (0.15, 0.15, 0.18, 0.18, 0.25, 1.0, 0.5, 0.4, 0.2, 1.0),
    (0.15, 0.15, 0.18, 0.18, 0.25, 1.0, 0.5, 0.4, 0.2, 1.0),
    (0.18, 0.18, 0.18, 0.18, 0.25, 1.0, 0.5, 0.4, 0.2, 1.0),
    (0.18, 0.18, 0.18, 0.18, 0.25, 1.0, 0.5, 0.4, 0.2, 1.0),
    (0.25, 0.25, 0.25, 0.25, 0.35, 1.0, 0.5, 0.4, 0.2, 1.0),
    (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5),
    (0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.25, 1.25, 1.0, 1.5),
    (0.4, 0.4, 0.4, 0.4, 0.4, 1.0, 1.25, 0.5, 0.4, 1.0),
    (0.2, 0.2, 0.2, 0.2, 0.2, 1.0, 1.0, 0.4, 0.4, 1.0),
    (1.0, 1.0, 1.0, 1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 2.0),
)
_STANDARD_CHIP_BODY_MM = {
    "0201": (0.6, 0.3),
    "0402": (1.0, 0.5),
    "0603": (1.6, 0.8),
    "0805": (2.0, 1.25),
    "1206": (3.2, 1.6),
}
_PACKAGE_BODY_DIMENSIONS = re.compile(
    r"(?:^|_)L(?P<length>[0-9]+(?:\.[0-9]+)?)-"
    r"W(?P<width>[0-9]+(?:\.[0-9]+)?)(?:-|_|$)")


@dataclass(frozen=True)
class FootprintPad:
    number: str
    pad_type: str
    shape: str
    center: tuple[float, float]
    size: tuple[float, float]
    rotation: float
    copper_sides: tuple[str, ...]
    polygon: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class ExternalFootprint:
    lcsc: str
    package: str
    manufacturer: str
    mpn: str
    lcsc_url: str
    source_sha256: str
    device_name: str
    pin_names: Mapping[str, str]
    pads: tuple[FootprintPad, ...]


@dataclass(frozen=True)
class Placement:
    designator: str
    lcsc: str
    xy: tuple[float, float]
    side: str
    rotation: float


@dataclass(frozen=True)
class PlacedBody:
    designator: str
    lcsc: str
    package: str
    category: str
    side: str
    geometry: BaseGeometry


@dataclass(frozen=True)
class BodySpacingViolation:
    first: PlacedBody
    second: PlacedBody
    clearance: float
    required: float


@dataclass(frozen=True)
class DeviceNameAtlas:
    ic_roots_by_lcsc: Mapping[str, str]
    header_pins: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True)
class PlacedPad:
    designator: str
    lcsc: str
    number: str
    pad_index: int
    pad_type: str
    device_name: str
    pin_name: str
    manufacturer: str
    lcsc_url: str
    geometry: BaseGeometry
    layers: tuple[str, ...]

    @property
    def label(self) -> str:
        number = self.number or "<unnumbered>"
        return f"{self.designator}.{number}"

    @property
    def center(self) -> tuple[float, float]:
        point = self.geometry.centroid
        return (point.x, point.y)


@dataclass(frozen=True)
class PadAttachment:
    pad: PlacedPad
    net_ids: tuple[str, ...]
    overlap_area: float


def jlcpcb_smd_category(package: str) -> str | None:
    """Map an EasyEDA package name to a category in JLCPCB's SMD table."""
    normalized = package.upper()
    chip = re.search(
        r"(?:^|[-_])(?:R|C)?(0201|0402|0603|0805|1206)(?:$|[-_])",
        normalized,
    )
    if chip:
        return chip.group(1)
    if "QFN" in normalized:
        return "QFN"
    if "QFP" in normalized:
        return "QFP"
    if any(name in normalized for name in (
            "SOIC", "SOP", "MSOP", "SSOP", "TSSOP")):
        return "SOP/SOIC"
    if "SOT" in normalized:
        return "SOT"
    if "BGA" in normalized:
        return "BGA"
    return None


def package_body_size_mm(
        package: str, category: str | None = None
        ) -> tuple[float, float] | None:
    """Return nominal body length/width derivable from a package name."""
    category = category or jlcpcb_smd_category(package)
    if category in _STANDARD_CHIP_BODY_MM:
        return _STANDARD_CHIP_BODY_MM[category]
    match = _PACKAGE_BODY_DIMENSIONS.search(package.upper())
    if match:
        return (float(match.group("length")), float(match.group("width")))
    return None


def jlcpcb_smd_spacing_mm(first_category: str, second_category: str) -> float:
    """Return JLCPCB's recommended minimum for a package-category pair."""
    first = JLCPCB_SMD_CATEGORIES.index(first_category)
    second = JLCPCB_SMD_CATEGORIES.index(second_category)
    return _JLCPCB_SMD_SPACING_ROWS[first][second]


def place_component_body(
        footprint: ExternalFootprint, placement: Placement) -> PlacedBody:
    """Place a nominal package body at its JLCPCB PNP location."""
    category = jlcpcb_smd_category(footprint.package)
    if category is None:
        raise ValueError(
            f"package {footprint.package!r} is outside JLCPCB's spacing table")
    size = package_body_size_mm(footprint.package, category)
    if size is None:
        raise ValueError(
            f"cannot derive body dimensions from package {footprint.package!r}")
    length, width = size
    geometry = sg.box(-length / 2, -width / 2, length / 2, width / 2)
    geometry = sa.rotate(geometry, placement.rotation, origin=(0, 0))
    geometry = sa.translate(geometry, *placement.xy)
    return PlacedBody(
        placement.designator,
        placement.lcsc,
        footprint.package,
        category,
        placement.side,
        geometry,
    )


def jlcpcb_body_spacing_violations(
        bodies: Iterable[PlacedBody], tolerance: float = 1e-9
        ) -> tuple[tuple[BodySpacingViolation, ...], int]:
    """Check same-side body gaps against JLCPCB's package-pair table."""
    ordered = sorted(bodies, key=lambda body: body.designator)
    violations: list[BodySpacingViolation] = []
    pair_count = 0
    for first, second in itertools.combinations(ordered, 2):
        if first.side != second.side:
            continue
        pair_count += 1
        required = jlcpcb_smd_spacing_mm(first.category, second.category)
        clearance = first.geometry.distance(second.geometry)
        if clearance + tolerance < required:
            violations.append(BodySpacingViolation(
                first, second, clearance, required))
    violations.sort(key=lambda item: (
        item.clearance - item.required,
        item.first.designator,
        item.second.designator,
    ))
    return tuple(violations), pair_count


def load_name_atlas(path: Path, variable: str) -> DeviceNameAtlas:
    """Read a literal naming atlas from board source without importing it."""
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    value = None
    for statement in module.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = (
                statement.targets if isinstance(statement, ast.Assign)
                else (statement.target,))
            if any(isinstance(target, ast.Name) and target.id == variable
                   for target in targets):
                value = ast.literal_eval(statement.value)
                break
    if not isinstance(value, dict):
        raise ValueError(f"{path}: literal {variable} atlas not found")
    roots = value.get("ic_roots_by_lcsc")
    headers = value.get("header_pins")
    if not isinstance(roots, dict) or not isinstance(headers, dict):
        raise ValueError(
            f"{path}: {variable} needs ic_roots_by_lcsc and header_pins")
    normalized_roots = {
        str(lcsc): str(name) for lcsc, name in roots.items()
    }
    normalized_headers: dict[str, dict[str, str]] = {}
    for designator, header in headers.items():
        if not isinstance(header, dict):
            raise ValueError(
                f"{path}: header atlas {designator} must be an object")
        names = header.get("names")
        external_numbers = header.get("external_pad_numbers")
        if (not isinstance(names, (list, tuple)) or
                not isinstance(external_numbers, (list, tuple)) or
                len(names) != len(external_numbers)):
            raise ValueError(
                f"{path}: header atlas {designator} needs equal-length "
                "names and external_pad_numbers")
        normalized_headers[str(designator)] = {
            str(number): str(name)
            for number, name in zip(external_numbers, names)
        }
    return DeviceNameAtlas(normalized_roots, normalized_headers)


def format_device_pad(pad: PlacedPad, atlas: DeviceNameAtlas) -> str:
    """Format device.pad using the board's report naming convention."""
    family = pad.designator[:1].upper()
    if family in ("R", "C"):
        return f"{pad.designator}.{pad.number}"
    if family == "U":
        try:
            device = atlas.ic_roots_by_lcsc[pad.lcsc]
        except KeyError as error:
            raise ValueError(
                f"no IC root name for {pad.designator} ({pad.lcsc})") from error
        return f"{device}.{pad.pin_name}"
    if family == "J":
        header_names = atlas.header_pins.get(pad.designator)
        if header_names is not None:
            try:
                pin_name = header_names[pad.number]
            except KeyError as error:
                raise ValueError(
                    f"no header name for {pad.designator}.{pad.number}") from error
            return f"{pad.designator}.{pin_name}"
        return f"{pad.designator}.{pad.pin_name}"
    return f"{pad.designator}.{pad.pin_name}"


def _parse_mm(value: str) -> float:
    value = value.strip()
    if value.lower().endswith("mm"):
        value = value[:-2]
    return float(value)


def split_designators(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def read_jlc_bom(path: Path) -> dict[str, str]:
    """Return designator -> LCSC code from a JLCPCB assembly BOM."""
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"Designator", "JLCPCB Part #"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"{path} is missing column(s): {', '.join(sorted(missing))}")
        result: dict[str, str] = {}
        for line_number, row in enumerate(reader, 2):
            lcsc = (row.get("JLCPCB Part #") or "").strip().upper()
            for designator in split_designators(row.get("Designator") or ""):
                if designator in result:
                    raise ValueError(
                        f"{path}:{line_number}: duplicate {designator}")
                result[designator] = lcsc
    return result


def read_jlc_pnp(path: Path, lcsc_by_designator: Mapping[str, str]
                 ) -> tuple[Placement, ...]:
    """Read JLCPCB placements and associate each with its BOM LCSC code."""
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"Designator", "Mid X", "Mid Y", "Layer", "Rotation"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"{path} is missing column(s): {', '.join(sorted(missing))}")
        placements: list[Placement] = []
        seen: set[str] = set()
        for line_number, row in enumerate(reader, 2):
            designator = (row.get("Designator") or "").strip()
            if designator in seen:
                raise ValueError(
                    f"{path}:{line_number}: duplicate {designator}")
            seen.add(designator)
            if designator not in lcsc_by_designator:
                raise ValueError(
                    f"{path}:{line_number}: {designator} is absent from BOM")
            side = (row.get("Layer") or "").strip().title()
            if side not in ("Top", "Bottom"):
                raise ValueError(
                    f"{path}:{line_number}: invalid layer {side!r}")
            placements.append(Placement(
                designator,
                lcsc_by_designator[designator],
                (_parse_mm(row["Mid X"]), _parse_mm(row["Mid Y"])),
                side,
                float(row["Rotation"]),
            ))
    return tuple(placements)


def read_preflight_placements(path: Path) -> tuple[Placement, ...]:
    """Read all physical LCSC-backed placements emitted by CuFlow."""
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    if value.get("format") != PREFLIGHT_PLACEMENT_FORMAT:
        raise ValueError(f"{path}: unsupported placement manifest format")
    records = value.get("placements")
    if not isinstance(records, list):
        raise ValueError(f"{path}: placements must be a list")

    placements: list[Placement] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise ValueError(f"{path}: placement {index} must be an object")
        try:
            designator = str(record["designator"]).strip()
            lcsc = str(record["lcsc"]).strip().upper()
            side = str(record["side"]).strip().title()
            xy = (float(record["x"]), float(record["y"]))
            rotation = float(record["rotation"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"{path}: invalid placement {index}: {error}") from error
        if not designator or not lcsc:
            raise ValueError(
                f"{path}: placement {index} needs designator and LCSC code")
        if designator in seen:
            raise ValueError(f"{path}: duplicate {designator}")
        if side not in ("Top", "Bottom"):
            raise ValueError(f"{path}: invalid layer {side!r} for {designator}")
        seen.add(designator)
        placements.append(Placement(designator, lcsc, xy, side, rotation))
    return tuple(placements)


def _pair(value: object, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"footprint {field} must contain two values")
    return (float(value[0]), float(value[1]))


def load_footprint(path: Path) -> ExternalFootprint:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != FOOTPRINT_FORMAT:
        raise ValueError(f"unsupported footprint cache format in {path}")
    pads: list[FootprintPad] = []
    for index, pad in enumerate(value.get("pads", ())):
        if not isinstance(pad, dict):
            raise ValueError(f"{path}: pad {index + 1} is not an object")
        polygon = tuple(
            _pair(point, f"pad {index + 1} polygon point")
            for point in pad.get("polygon", ()))
        sides = tuple(str(side) for side in pad.get("copper_sides", ()))
        if not sides or not set(sides).issubset({"top", "bottom", "all"}):
            raise ValueError(f"{path}: pad {index + 1} has invalid copper sides")
        pads.append(FootprintPad(
            str(pad.get("number", "")),
            str(pad["type"]),
            str(pad["shape"]),
            _pair(pad["center"], f"pad {index + 1} center"),
            _pair(pad["size"], f"pad {index + 1} size"),
            float(pad.get("rotation", 0)),
            sides,
            polygon,
        ))
    if not pads:
        raise ValueError(f"{path}: footprint has no copper pads")
    device_name = str(value.get("device_name", "")).strip()
    raw_pin_names = value.get("pin_names")
    if not device_name:
        raise ValueError(f"{path}: missing official device name")
    if not isinstance(raw_pin_names, dict):
        raise ValueError(f"{path}: missing official pin names")
    pin_names = {
        str(number): str(name).strip()
        for number, name in raw_pin_names.items()
    }
    missing_names = sorted({
        pad.number for pad in pads
        if not pad.number or not pin_names.get(pad.number)
    })
    if missing_names:
        raise ValueError(
            f"{path}: pads without official names: " +
            ", ".join(repr(number) for number in missing_names))
    manufacturer = str(value.get("manufacturer", "")).strip()
    lcsc_url = str(value.get("lcsc_url", "")).strip()
    if not manufacturer:
        raise ValueError(f"{path}: missing manufacturer")
    if not lcsc_url.startswith(("https://lcsc.com/", "https://www.lcsc.com/")):
        raise ValueError(f"{path}: invalid LCSC link {lcsc_url!r}")
    return ExternalFootprint(
        str(value["lcsc"]),
        str(value.get("package", "")),
        manufacturer,
        str(value.get("mpn", "")),
        lcsc_url,
        str(value.get("source_sha256", "")),
        device_name,
        pin_names,
        tuple(pads),
    )


def load_footprints(cache_dir: Path, lcsc_codes: Iterable[str]
                    ) -> tuple[dict[str, ExternalFootprint], list[str]]:
    footprints: dict[str, ExternalFootprint] = {}
    errors: list[str] = []
    for lcsc in sorted(set(lcsc_codes)):
        path = cache_dir / f"{lcsc}.json"
        try:
            footprint = load_footprint(path)
            if footprint.lcsc != lcsc:
                raise ValueError(
                    f"cached LCSC {footprint.lcsc!r} does not match {lcsc!r}")
            footprints[lcsc] = footprint
        except (OSError, ValueError, KeyError, TypeError,
                json.JSONDecodeError) as error:
            errors.append(f"{lcsc}: {error}")
    return footprints, errors


def _ellipse(width: float, height: float) -> BaseGeometry:
    circle = sg.Point(0, 0).buffer(0.5, resolution=32)
    return sa.scale(circle, xfact=width, yfact=height, origin=(0, 0))


def _oval(width: float, height: float) -> BaseGeometry:
    if math.isclose(width, height):
        return _ellipse(width, height)
    if width > height:
        half_line = (width - height) / 2
        return sg.LineString(((-half_line, 0), (half_line, 0))).buffer(
            height / 2, resolution=32)
    half_line = (height - width) / 2
    return sg.LineString(((0, -half_line), (0, half_line))).buffer(
        width / 2, resolution=32)


def local_pad_geometry(pad: FootprintPad) -> BaseGeometry:
    """Build pad copper in EasyEDA/KiCad footprint-local coordinates."""
    width, height = pad.size
    if pad.shape == "custom":
        if len(pad.polygon) < 3:
            raise ValueError(f"custom pad {pad.number!r} has no polygon")
        geometry: BaseGeometry = sg.Polygon(pad.polygon)
    elif pad.shape == "oval":
        geometry = _oval(width, height)
    elif pad.shape == "circle":
        geometry = _ellipse(width, height)
    elif pad.shape in ("rect", "roundrect"):
        geometry = sg.box(-width / 2, -height / 2, width / 2, height / 2)
    else:
        raise ValueError(f"unsupported pad shape {pad.shape!r}")
    if pad.shape != "custom" and pad.rotation:
        geometry = sa.rotate(geometry, pad.rotation, origin=(0, 0))
    return sa.translate(geometry, pad.center[0], pad.center[1])


def _placed_layers(
        copper_sides: tuple[str, ...], placement_side: str,
        layer_order: tuple[str, ...]) -> tuple[str, ...]:
    if "all" in copper_sides:
        return layer_order
    result: list[str] = []
    for side in copper_sides:
        physical_side = side
        if placement_side == "Bottom":
            physical_side = "bottom" if side == "top" else "top"
        layer = "GTL" if physical_side == "top" else "GBL"
        if layer in layer_order and layer not in result:
            result.append(layer)
    return tuple(result)


def place_footprint(
        footprint: ExternalFootprint, placement: Placement,
        layer_order: tuple[str, ...]) -> tuple[PlacedPad, ...]:
    """Place package-local pads using JLCPCB PNP coordinates and rotation.

    EasyEDA/KiCad package Y coordinates point down. CuFlow board Y points up,
    so local Y is reflected before applying JLCPCB's counterclockwise rotation.
    Bottom-side placement additionally reflects local X.
    """
    result: list[PlacedPad] = []
    for pad_index, pad in enumerate(footprint.pads, 1):
        geometry = local_pad_geometry(pad)
        geometry = sa.scale(
            geometry,
            xfact=-1 if placement.side == "Bottom" else 1,
            yfact=-1,
            origin=(0, 0),
        )
        geometry = sa.rotate(
            geometry, placement.rotation, origin=(0, 0))
        geometry = sa.translate(geometry, *placement.xy)
        result.append(PlacedPad(
            placement.designator,
            placement.lcsc,
            pad.number,
            pad_index,
            pad.pad_type,
            footprint.device_name,
            footprint.pin_names[pad.number],
            footprint.manufacturer,
            footprint.lcsc_url,
            geometry,
            _placed_layers(pad.copper_sides, placement.side, layer_order),
        ))
    return tuple(result)


def map_pads_to_topology(
        topology: BoardTopology,
        pads: Iterable[PlacedPad]) -> tuple[PadAttachment, ...]:
    indexes = {
        layer: STRtree([component.geometry for component in components])
        if components else None
        for layer, components in topology.components_by_layer.items()
    }
    result: list[PadAttachment] = []
    for pad in pads:
        net_ids: set[str] = set()
        overlap_area = 0.0
        if pad.pad_type == "thru_hole":
            matched_connectors = [
                connector for connector in topology.connectors
                if connector.xy is not None
                and pad.geometry.covers(sg.Point(connector.xy))
            ]
            for connector in matched_connectors:
                net_ids.update(
                    topology.component_to_net[ref]
                    for ref in connector.components)
                overlap_area += sum(
                    topology.component(ref).geometry.intersection(
                        pad.geometry).area
                    for ref in connector.components)
            result.append(PadAttachment(
                pad, tuple(sorted(net_ids)), overlap_area))
            continue
        for layer in pad.layers:
            components = topology.components_by_layer.get(layer, ())
            index = indexes.get(layer)
            if index is None:
                continue
            for candidate in index.query(pad.geometry, predicate="intersects"):
                component = components[int(candidate)]
                overlap = component.geometry.intersection(pad.geometry).area
                if overlap > 1e-8:
                    net_ids.add(topology.component_to_net[component.ref])
                    overlap_area += overlap
        result.append(PadAttachment(
            pad, tuple(sorted(net_ids)), overlap_area))
    return tuple(result)
