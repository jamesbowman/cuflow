#!/usr/bin/env python3
"""Reconstruct anonymous physical nets from CuFlow manufacturing outputs."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import shapely.geometry as sg
import shapely.ops as so
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree


GERBER_COORD = re.compile(r"^X(-?\d+)Y(-?\d+)D0?([123])\*$")
EXCELLON_TOOL = re.compile(r"^T(\d+)C(\d+(?:\.\d+)?)$")
EXCELLON_SELECT = re.compile(r"^T(\d+)$")
EXCELLON_HIT = re.compile(r"^X(-?\d+)Y(-?\d+)$")


class TopologyFormatError(ValueError):
    """Manufacturing output is outside the CuFlow subset understood here."""


@dataclass(frozen=True, order=True)
class ComponentRef:
    layer: str
    index: int


@dataclass(frozen=True)
class CopperComponent:
    ref: ComponentRef
    geometry: BaseGeometry

    @property
    def area(self) -> float:
        return self.geometry.area

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.geometry.bounds


@dataclass(frozen=True)
class DrillHit:
    tool: int
    diameter: float
    xy: tuple[float, float]


@dataclass(frozen=True)
class InterlayerConnector:
    label: str
    geometry: BaseGeometry
    layers: tuple[str, ...] | None = None
    kind: str = "connector"


@dataclass(frozen=True)
class ConnectorMapping:
    label: str
    kind: str
    components: tuple[ComponentRef, ...]
    xy: tuple[float, float] | None = None

    @property
    def layers(self) -> tuple[str, ...]:
        return tuple(sorted({component.layer for component in self.components}))


@dataclass(frozen=True)
class PhysicalNet:
    net_id: str
    components: tuple[ComponentRef, ...]
    connector_indices: tuple[int, ...]
    area_by_layer: Mapping[str, float]

    @property
    def layers(self) -> tuple[str, ...]:
        return tuple(self.area_by_layer)

    @property
    def area(self) -> float:
        return sum(self.area_by_layer.values())


@dataclass(frozen=True)
class ClearanceViolation:
    layer: str
    net_id: str
    conflicting_net_ids: tuple[str, ...]
    centroid: tuple[float, float]


@dataclass
class BoardTopology:
    layer_order: tuple[str, ...]
    components_by_layer: Mapping[str, tuple[CopperComponent, ...]]
    drill_hits: tuple[DrillHit, ...]
    connectors: tuple[ConnectorMapping, ...]
    unmapped_drill_indices: tuple[int, ...]
    nets: tuple[PhysicalNet, ...]
    component_to_net: Mapping[ComponentRef, str]

    def component(self, ref: ComponentRef) -> CopperComponent:
        return self.components_by_layer[ref.layer][ref.index]

    def largest_component(self, layer: str) -> CopperComponent:
        components = self.components_by_layer.get(layer, ())
        if not components:
            raise LookupError(f"No copper components on {layer}")
        return max(components, key=lambda component: component.area)

    def component_at(
            self, layer: str,
            xy: tuple[float, float]) -> CopperComponent:
        point = sg.Point(xy)
        matches = [
            component
            for component in self.components_by_layer.get(layer, ())
            if component.geometry.covers(point)
        ]
        if len(matches) != 1:
            raise LookupError(
                f"Expected one {layer} copper component at {xy}, "
                f"found {len(matches)}")
        return matches[0]

    def net_for_component(self, component: CopperComponent) -> str:
        return self.component_to_net[component.ref]

    def net(self, net_id: str) -> PhysicalNet:
        return next(net for net in self.nets if net.net_id == net_id)

    def geometry_for_net(self, net_id: str, layer: str) -> BaseGeometry:
        net = self.net(net_id)
        geometries = [
            self.component(ref).geometry
            for ref in net.components
            if ref.layer == layer
        ]
        return so.unary_union(geometries) if geometries else sg.Polygon()


class _UnionFind:
    def __init__(self, values: Iterable[ComponentRef]):
        values = tuple(values)
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: ComponentRef) -> ComponentRef:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first: ComponentRef, second: ComponentRef) -> None:
        a = self.find(first)
        b = self.find(second)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def _polygon_parts(geometry: BaseGeometry) -> list[sg.Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, sg.Polygon):
        return [geometry]
    if isinstance(geometry, (sg.MultiPolygon, sg.GeometryCollection)):
        parts: list[sg.Polygon] = []
        for item in geometry.geoms:
            parts.extend(_polygon_parts(item))
        return parts
    return []


def _gerber_xy(match: re.Match[str]) -> tuple[float, float]:
    return (int(match.group(1)) / 10000, int(match.group(2)) / 10000)


def parse_cuflow_gerber_text(text: str) -> BaseGeometry:
    """Parse CuFlow's positive, metric, polygon-region Gerber subset."""
    if "%MOMM*%" not in text or "%FSLAX34Y34*%" not in text:
        raise TopologyFormatError("Expected CuFlow metric 3.4 Gerber format")

    polygons: list[sg.Polygon] = []
    in_region = False
    current: list[tuple[float, float]] | None = None
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if line == "G36*":
            if in_region:
                raise TopologyFormatError(
                    f"Nested Gerber region at line {line_number}")
            in_region = True
            current = None
            continue
        if line == "G37*":
            if not in_region or current is None or len(current) < 3:
                raise TopologyFormatError(
                    f"Incomplete Gerber region at line {line_number}")
            polygon = sg.Polygon(current)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            parts = _polygon_parts(polygon)
            if not parts:
                raise TopologyFormatError(
                    f"Invalid Gerber polygon ending at line {line_number}")
            polygons.extend(parts)
            in_region = False
            current = None
            continue

        match = GERBER_COORD.match(line)
        if match is None:
            continue
        operation = match.group(3)
        if not in_region:
            if operation in ("1", "3"):
                raise TopologyFormatError(
                    f"Copper operation outside a region at line {line_number}")
            continue
        if operation == "3":
            raise TopologyFormatError(
                f"Gerber flash inside a region at line {line_number}")
        point = _gerber_xy(match)
        if operation == "2":
            if current is not None:
                raise TopologyFormatError(
                    f"Multiple contours in one region at line {line_number}")
            current = [point]
        elif current is None:
            raise TopologyFormatError(
                f"Gerber draw before move at line {line_number}")
        else:
            current.append(point)

    if in_region:
        raise TopologyFormatError("Unterminated Gerber region")
    return so.unary_union(polygons) if polygons else sg.Polygon()


def parse_cuflow_gerber(path: Path) -> BaseGeometry:
    return parse_cuflow_gerber_text(path.read_text(encoding="ascii"))


def parse_cuflow_paths_text(text: str) -> tuple[sg.LineString, ...]:
    """Parse D02/D01 paths, used for CuFlow GML contours."""
    paths: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    for raw_line in text.splitlines():
        match = GERBER_COORD.match(raw_line.strip())
        if match is None:
            continue
        point = _gerber_xy(match)
        operation = match.group(3)
        if operation == "2":
            current = [point]
            paths.append(current)
        elif operation == "1" and current is not None:
            current.append(point)
    return tuple(sg.LineString(path) for path in paths if len(path) >= 2)


def internal_closed_contours(
        paths: Iterable[sg.LineString]) -> tuple[sg.LineString, ...]:
    closed = [path for path in paths if path.is_ring]
    if not closed:
        return ()
    outline = max(closed, key=lambda path: abs(sg.Polygon(path).area))
    return tuple(path for path in closed if path is not outline)


def parse_excellon_text(text: str) -> tuple[DrillHit, ...]:
    """Parse CuFlow's metric, trailing-zero-suppressed Excellon subset."""
    if "METRIC,TZ,000.000" not in text:
        raise TopologyFormatError("Expected CuFlow metric Excellon format")
    tools: dict[int, float] = {}
    selected: int | None = None
    hits: list[DrillHit] = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        match = EXCELLON_TOOL.match(line)
        if match is not None:
            tools[int(match.group(1))] = float(match.group(2))
            continue
        match = EXCELLON_SELECT.match(line)
        if match is not None:
            selected = int(match.group(1))
            if selected not in tools:
                raise TopologyFormatError(
                    f"Undefined Excellon tool T{selected} at line {line_number}")
            continue
        match = EXCELLON_HIT.match(line)
        if match is not None:
            if selected is None:
                raise TopologyFormatError(
                    f"Excellon hit before tool selection at line {line_number}")
            hits.append(DrillHit(
                selected,
                tools[selected],
                (int(match.group(1)) / 1000,
                 int(match.group(2)) / 1000),
            ))
    return tuple(hits)


def parse_excellon(path: Path) -> tuple[DrillHit, ...]:
    return parse_excellon_text(path.read_text(encoding="ascii"))


def _components_for_layer(
        layer: str, geometry: BaseGeometry) -> tuple[CopperComponent, ...]:
    polygons = _polygon_parts(so.unary_union(geometry))
    polygons.sort(key=lambda polygon: (
        polygon.bounds[0], polygon.bounds[1],
        polygon.bounds[2], polygon.bounds[3], -polygon.area))
    return tuple(
        CopperComponent(ComponentRef(layer, index), polygon)
        for index, polygon in enumerate(polygons)
    )


def build_topology(
        layer_geometry: Mapping[str, BaseGeometry],
        drill_hits: Iterable[DrillHit],
        interlayer_connectors: Iterable[InterlayerConnector] = (),
        ) -> BoardTopology:
    """Build physical copper nets by joining layer components at z-connectors."""
    layer_order = tuple(layer_geometry)
    components_by_layer = {
        layer: _components_for_layer(layer, geometry)
        for layer, geometry in layer_geometry.items()
    }
    all_components = [
        component
        for layer in layer_order
        for component in components_by_layer[layer]
    ]
    union_find = _UnionFind(component.ref for component in all_components)
    indexes = {
        layer: STRtree([component.geometry for component in components])
        if components else None
        for layer, components in components_by_layer.items()
    }

    def touching_components(
            geometry: BaseGeometry,
            layers: Iterable[str]) -> tuple[ComponentRef, ...]:
        touched: list[ComponentRef] = []
        for layer in layers:
            components = components_by_layer.get(layer, ())
            index = indexes.get(layer)
            if index is None:
                continue
            for candidate in index.query(geometry, predicate="intersects"):
                component = components[int(candidate)]
                if component.geometry.intersects(geometry):
                    touched.append(component.ref)
        return tuple(touched)

    mappings: list[ConnectorMapping] = []
    unmapped_drills: list[int] = []
    drill_hits = tuple(drill_hits)
    for drill_index, hit in enumerate(drill_hits):
        point = sg.Point(hit.xy)
        touched = touching_components(point, layer_order)
        if not touched:
            unmapped_drills.append(drill_index)
            continue
        mapping = ConnectorMapping(
            f"T{hit.tool}@{hit.xy[0]:.3f},{hit.xy[1]:.3f}",
            "drill", touched, hit.xy)
        mappings.append(mapping)
        for component in touched[1:]:
            union_find.union(touched[0], component)

    for connector in interlayer_connectors:
        layers = connector.layers or layer_order
        touched = touching_components(connector.geometry, layers)
        if not touched:
            continue
        mapping = ConnectorMapping(
            connector.label, connector.kind, touched,
            tuple(connector.geometry.centroid.coords[0]))
        mappings.append(mapping)
        for component in touched[1:]:
            union_find.union(touched[0], component)

    groups: dict[ComponentRef, list[ComponentRef]] = defaultdict(list)
    for component in all_components:
        groups[union_find.find(component.ref)].append(component.ref)

    layer_rank = {layer: index for index, layer in enumerate(layer_order)}

    def ref_key(ref: ComponentRef) -> tuple[int, int]:
        return (layer_rank[ref.layer], ref.index)

    grouped_refs = [tuple(sorted(group, key=ref_key)) for group in groups.values()]
    grouped_refs.sort(key=lambda group: min(ref_key(ref) for ref in group))

    component_to_net: dict[ComponentRef, str] = {}
    nets: list[PhysicalNet] = []
    for net_number, refs in enumerate(grouped_refs, 1):
        net_id = f"N{net_number:03d}"
        for ref in refs:
            component_to_net[ref] = net_id
        connection_indices = tuple(
            index for index, mapping in enumerate(mappings)
            if any(ref in refs for ref in mapping.components))
        area_by_layer = {
            layer: sum(
                components_by_layer[ref.layer][ref.index].area
                for ref in refs if ref.layer == layer)
            for layer in layer_order
            if any(ref.layer == layer for ref in refs)
        }
        nets.append(PhysicalNet(
            net_id, refs, connection_indices, area_by_layer))

    return BoardTopology(
        layer_order,
        components_by_layer,
        drill_hits,
        tuple(mappings),
        tuple(unmapped_drills),
        tuple(nets),
        component_to_net,
    )


def net_clearance_violations(
        topology: BoardTopology,
        clearance: float) -> tuple[ClearanceViolation, ...]:
    """Find different-net copper closer than the requested clearance."""
    if clearance < 0:
        raise ValueError("clearance must not be negative")
    violations: list[ClearanceViolation] = []
    radius = clearance / 2
    for layer in topology.layer_order:
        running_sum: BaseGeometry = sg.Polygon()
        accepted: list[tuple[str, BaseGeometry]] = []
        for net in topology.nets:
            geometry = topology.geometry_for_net(net.net_id, layer)
            if geometry.is_empty:
                continue
            buffered = geometry.buffer(radius)
            if buffered.intersects(running_sum):
                intersection = buffered.intersection(running_sum)
                conflicts = tuple(
                    net_id
                    for net_id, previous in accepted
                    if buffered.intersects(previous)
                )
                violations.append(ClearanceViolation(
                    layer, net.net_id, conflicts,
                    tuple(intersection.centroid.coords[0])))
                continue
            running_sum = running_sum.union(buffered)
            accepted.append((net.net_id, buffered))
    return tuple(violations)
