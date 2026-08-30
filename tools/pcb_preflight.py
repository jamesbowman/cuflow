#!/usr/bin/env python3
"""Deterministic manufacturing-output checks for profiled CuFlow boards."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GERBER_COORD = re.compile(r"^X(-?\d+)Y(-?\d+)D0([123])\*$")
DRILL_HIT = re.compile(r"^X-?\d+Y-?\d+$")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    detail_html: str | None = None


class Audit:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.bom_rows: list[dict[str, str]] = []
        self.topology_rows: list[dict[str, str]] = []
        self.pad_rows: list[dict[str, str]] = []
        self.net_rows: list[dict[str, str]] = []
        self.device_rows: list[dict[str, Any]] = []

    def add(
            self, name: str, passed: bool, detail: str,
            detail_html: str | None = None) -> None:
        self.checks.append(Check(name, passed, detail, detail_html))

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def relative_path(value: str) -> Path:
    return ROOT / value


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        return list(reader.fieldnames or []), list(reader)


def split_designators(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def natural_pad_number_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """Sort official pad numbers naturally, including alphanumeric names."""
    return tuple(
        (0, int(token)) if token.isdigit() else (1, token.upper())
        for token in re.split(r"(\d+)", value)
        if token
    )


def gerber_paths(text: str) -> list[list[tuple[str, str]]]:
    paths: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] | None = None
    for line in text.splitlines():
        match = GERBER_COORD.match(line.strip())
        if match is None:
            continue
        point = (match.group(1), match.group(2))
        operation = match.group(3)
        if operation == "2":
            current = [point]
            paths.append(current)
        elif operation == "1" and current is not None:
            current.append(point)
    return paths


def gerber_has_geometry(text: str) -> bool:
    for line in text.splitlines():
        match = GERBER_COORD.match(line.strip())
        if match is not None and match.group(3) in ("1", "3"):
            return True
    return "G36*" in text


def load_catalog(audit: Audit, path: Path) -> dict[str, dict[str, str]]:
    required = {
        "lcsc",
        "kind",
        "bom_comment",
        "manufacturer_part_number",
        "bom_footprint",
        "manufacturer_footprint",
        "jlcpcb_class",
    }
    try:
        fields, rows = read_csv(path)
    except (OSError, csv.Error) as error:
        audit.add("Part catalog", False, f"Cannot read {path}: {error}")
        return {}

    missing = sorted(required - set(fields))
    audit.add(
        "Part catalog schema",
        not missing,
        "all required fields present" if not missing else
        "missing fields: " + ", ".join(missing),
    )
    if missing:
        return {}

    codes = [row["lcsc"].strip() for row in rows]
    duplicates = duplicate_values(codes)
    malformed: list[str] = []
    catalog: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, 2):
        normalized = {key: (value or "").strip() for key, value in row.items()}
        code = normalized["lcsc"]
        empty = sorted(key for key in required if not normalized[key])
        if normalized["kind"] not in ("discrete", "part"):
            malformed.append(f"line {line_number}: invalid kind {normalized['kind']!r}")
        if empty:
            malformed.append(
                f"line {line_number}: empty " + ", ".join(empty))
        if normalized["kind"] == "part" and (
                normalized["bom_comment"] !=
                normalized["manufacturer_part_number"]):
            malformed.append(
                f"line {line_number}: part comment is not its MPN")
        catalog[code] = normalized

    valid = not duplicates and not malformed
    details: list[str] = []
    if duplicates:
        details.append("duplicate LCSC codes: " + ", ".join(duplicates))
    details.extend(malformed)
    audit.add(
        "Part catalog entries",
        valid,
        f"{len(rows)} reviewed LCSC selections" if valid else "; ".join(details),
    )
    return catalog


def audit_bom_and_pnp(
        audit: Audit, profile: dict[str, Any],
        catalog: dict[str, dict[str, str]]) -> None:
    bom_path = relative_path(profile["bom"])
    pnp_path = relative_path(profile["pnp"])
    bom_fields_required = {
        "Comment", "Designator", "Footprint", "JLCPCB Part #"}
    pnp_fields_required = {
        "Designator", "Mid X", "Mid Y", "Layer", "Rotation"}

    try:
        bom_fields, bom_rows = read_csv(bom_path)
    except (OSError, csv.Error) as error:
        audit.add("JLCPCB BOM", False, f"Cannot read {bom_path}: {error}")
        return
    missing_bom_fields = sorted(bom_fields_required - set(bom_fields))
    audit.add(
        "JLCPCB BOM schema",
        not missing_bom_fields,
        f"{len(bom_rows)} rows" if not missing_bom_fields else
        "missing fields: " + ", ".join(missing_bom_fields),
    )
    if missing_bom_fields:
        return

    bom_designators: list[str] = []
    mismatches: list[str] = []
    for row in bom_rows:
        code = row["JLCPCB Part #"].strip()
        designators = split_designators(row["Designator"])
        bom_designators.extend(designators)
        selected = catalog.get(code)
        issues: list[str] = []
        if not code:
            issues.append("missing LCSC number")
        elif selected is None:
            issues.append("LCSC number absent from reviewed catalog")
        else:
            actual_comment = row["Comment"].strip()
            actual_footprint = row["Footprint"].strip()
            if actual_comment != selected["bom_comment"]:
                rule = "value" if selected["kind"] == "discrete" else "MPN"
                issues.append(
                    f"Comment {actual_comment!r} != expected {rule} "
                    f"{selected['bom_comment']!r}")
            if actual_footprint != selected["bom_footprint"]:
                issues.append(
                    f"Footprint {actual_footprint!r} != expected "
                    f"{selected['bom_footprint']!r}")
        if not designators:
            issues.append("missing designator")
        status = "PASS" if not issues else "FAIL: " + "; ".join(issues)
        if issues:
            mismatches.append(
                f"{row['Designator'] or '<blank>'} ({code or '<blank>'}): "
                + "; ".join(issues))
        audit.bom_rows.append({
            "designator": row["Designator"],
            "lcsc": code,
            "kind": selected["kind"] if selected else "unknown",
            "comment": row["Comment"],
            "footprint": row["Footprint"],
            "mpn": selected["manufacturer_part_number"] if selected else "",
            "manufacturer_footprint": (
                selected["manufacturer_footprint"] if selected else ""),
            "jlcpcb_class": selected["jlcpcb_class"] if selected else "",
            "status": status,
        })

    duplicate_bom_designators = duplicate_values(bom_designators)
    audit.add(
        "BOM designators",
        bool(bom_designators) and not duplicate_bom_designators,
        f"{len(bom_designators)} unique populated designators"
        if bom_designators and not duplicate_bom_designators else
        "duplicates: " + ", ".join(duplicate_bom_designators),
    )
    audit.add(
        "BOM part selections",
        not mismatches,
        f"all {len(bom_rows)} rows match reviewed LCSC/comment/footprint selections"
        if not mismatches else " | ".join(mismatches),
    )

    try:
        pnp_fields, pnp_rows = read_csv(pnp_path)
    except (OSError, csv.Error) as error:
        audit.add("JLCPCB PNP", False, f"Cannot read {pnp_path}: {error}")
        return
    missing_pnp_fields = sorted(pnp_fields_required - set(pnp_fields))
    audit.add(
        "JLCPCB PNP schema",
        not missing_pnp_fields,
        f"{len(pnp_rows)} rows" if not missing_pnp_fields else
        "missing fields: " + ", ".join(missing_pnp_fields),
    )
    if missing_pnp_fields:
        return

    pnp_designators = [row["Designator"].strip() for row in pnp_rows]
    duplicate_pnp_designators = duplicate_values(pnp_designators)
    bom_set = set(bom_designators)
    pnp_set = set(pnp_designators)
    missing_from_pnp = sorted(bom_set - pnp_set)
    missing_from_bom = sorted(pnp_set - bom_set)
    agreement_issues: list[str] = []
    if duplicate_pnp_designators:
        agreement_issues.append(
            "duplicate PNP: " + ", ".join(duplicate_pnp_designators))
    if missing_from_pnp:
        agreement_issues.append(
            "missing from PNP: " + ", ".join(missing_from_pnp))
    if missing_from_bom:
        agreement_issues.append(
            "missing from BOM: " + ", ".join(missing_from_bom))
    audit.add(
        "BOM/PNP designator agreement",
        not agreement_issues,
        f"{len(bom_set)} populated parts agree exactly"
        if not agreement_issues else "; ".join(agreement_issues),
    )

    excluded = set(profile.get("excluded_designators", []))
    present_excluded = sorted(excluded & (bom_set | pnp_set))
    audit.add(
        "Suppressed parts",
        not present_excluded,
        "absent as intended: " + ", ".join(sorted(excluded))
        if excluded and not present_excluded else
        ("unexpectedly populated: " + ", ".join(present_excluded)
         if present_excluded else "no suppressed designators configured"),
    )


def audit_manufacturing_files(
        audit: Audit, profile: dict[str, Any]) -> None:
    for extension, require_geometry in profile["gerber_layers"].items():
        path = ROOT / f"{profile['board']}.{extension}"
        if not path.is_file():
            audit.add(f"Gerber {extension}", False, f"missing {path.name}")
            continue
        text = path.read_text(encoding="ascii")
        has_geometry = gerber_has_geometry(text)
        audit.add(
            f"Gerber {extension}",
            has_geometry or not require_geometry,
            f"{path.stat().st_size} bytes; " +
            ("contains plotted geometry" if has_geometry else
             "intentionally allowed to be empty" if not require_geometry else
             "contains no plotted geometry"),
        )

    drill_path = relative_path(profile["drill_file"])
    if drill_path.is_file():
        drill_text = drill_path.read_text(encoding="ascii")
        drill_hits = sum(
            DRILL_HIT.match(line.strip()) is not None
            for line in drill_text.splitlines())
        audit.add(
            "Drill file",
            drill_hits > 0,
            f"{drill_hits} drill hits in {drill_path.name}",
        )
    else:
        audit.add("Drill file", False, f"missing {drill_path.name}")

    airwire_path = relative_path(profile["airwire_file"])
    if airwire_path.is_file():
        airwire_text = airwire_path.read_text(encoding="ascii")
        has_airwires = gerber_has_geometry(airwire_text)
        audit.add(
            "Airwires",
            not has_airwires,
            "no plotted airwires" if not has_airwires
            else "AIR layer contains unrouted connections",
        )
    else:
        audit.add("Airwires", False, f"missing {airwire_path.name}")

    if "expected_gml_contours" in profile:
        gml_path = ROOT / f"{profile['board']}.GML"
        if gml_path.is_file():
            paths = gerber_paths(gml_path.read_text(encoding="ascii"))
            closed = sum(
                len(path) >= 2 and path[0] == path[-1] for path in paths)
            expected = int(profile["expected_gml_contours"])
            reason = profile.get(
                "expected_gml_contours_reason", "profile requirement")
            audit.add(
                "Board-specific GML contours",
                len(paths) == expected and closed == expected,
                f"found {len(paths)} contours ({closed} closed); expected "
                f"{expected}: {reason}",
            )


def audit_copper_topology(
        audit: Audit, profile: dict[str, Any]) -> None:
    config = profile.get("topology")
    if config is None:
        return
    if __package__:
        from .pcb_topology import (
            InterlayerConnector,
            TopologyFormatError,
            build_topology,
            internal_closed_contours,
            net_clearance_violations,
            parse_cuflow_gerber,
            parse_cuflow_paths_text,
            parse_excellon,
        )
    else:
        from pcb_topology import (
            InterlayerConnector,
            TopologyFormatError,
            build_topology,
            internal_closed_contours,
            net_clearance_violations,
            parse_cuflow_gerber,
            parse_cuflow_paths_text,
            parse_excellon,
        )

    board = profile["board"]
    copper_layers = tuple(config.get(
        "copper_layers", ("GTL", "G2L", "G3L", "GBL")))
    try:
        layer_geometry = {
            layer: parse_cuflow_gerber(ROOT / f"{board}.{layer}")
            for layer in copper_layers
        }
        drill_hits = parse_excellon(relative_path(profile["drill_file"]))
    except (OSError, TopologyFormatError, ValueError) as error:
        audit.add("Copper topology", False, f"cannot parse outputs: {error}")
        return

    interlayer_connectors: list[InterlayerConnector] = []
    expected_slots = config.get("plated_internal_gml_contours")
    if expected_slots is not None:
        gml_path = ROOT / f"{board}.GML"
        try:
            paths = parse_cuflow_paths_text(gml_path.read_text(encoding="ascii"))
            slot_contours = internal_closed_contours(paths)
        except OSError as error:
            audit.add("Topology plated slots", False, str(error))
            slot_contours = ()
        expected_slots = int(expected_slots)
        audit.add(
            "Topology plated slots",
            len(slot_contours) == expected_slots,
            f"found {len(slot_contours)} internal plated contours; "
            f"expected {expected_slots}",
        )
        interlayer_connectors.extend(
            InterlayerConnector(
                f"GML plated slot {index}", contour,
                kind="plated-slot")
            for index, contour in enumerate(slot_contours, 1)
        )

    topology = build_topology(
        layer_geometry, drill_hits, interlayer_connectors)
    component_count = sum(
        len(components)
        for components in topology.components_by_layer.values())
    mapped_drills = len(drill_hits) - len(topology.unmapped_drill_indices)
    audit.add(
        "Copper topology",
        bool(topology.nets),
        f"{component_count} layer components, {mapped_drills}/"
        f"{len(drill_hits)} drills touching copper, "
        f"{len(interlayer_connectors)} plated slots, "
        f"{len(topology.nets)} physical nets",
    )

    clearance = float(config.get("net_clearance_mm", 0.1))
    clearance_violations = net_clearance_violations(topology, clearance)
    clearance_detail = (
        f"all physical nets are separated by at least {clearance:.3f} mm"
        if not clearance_violations else
        f"{len(clearance_violations)} violation(s) at {clearance:.3f} mm: " +
        "; ".join(
            f"{violation.layer} {violation.net_id} intersects buffered "
            f"{'/'.join(violation.conflicting_net_ids)} at "
            f"({violation.centroid[0]:.3f}, {violation.centroid[1]:.3f}) mm"
            for violation in clearance_violations[:20]
        ) + (" ..." if len(clearance_violations) > 20 else "")
    )
    clearance_detail_html = None
    if clearance_violations:
        clearance_detail_html = (
            f"{len(clearance_violations)} violation(s) at "
            f"{clearance:.3f} mm: " +
            "; ".join(
                f"{html_cell(violation.layer)} "
                f"{net_report_link(violation.net_id)} intersects buffered "
                f"{'/'.join(net_report_link(net_id) for net_id in violation.conflicting_net_ids)} "
                f"at ({violation.centroid[0]:.3f}, "
                f"{violation.centroid[1]:.3f}) mm"
                for violation in clearance_violations[:20]
            ) + (" ..." if len(clearance_violations) > 20 else "")
        )
    audit.add(
        "Net-to-net clearance",
        not clearance_violations,
        clearance_detail,
        clearance_detail_html,
    )

    named_nets: dict[str, set[str]] = {}
    seed_errors: list[str] = []
    for name, seeds in config.get("net_seeds", {}).items():
        net_ids: set[str] = set()
        for seed_index, seed in enumerate(seeds, 1):
            layer = seed.get("layer")
            try:
                if seed.get("selector") == "largest":
                    component = topology.largest_component(layer)
                elif "point" in seed:
                    point = tuple(float(value) for value in seed["point"])
                    if len(point) != 2:
                        raise ValueError("point must have two coordinates")
                    component = topology.component_at(layer, point)
                else:
                    raise ValueError("seed needs selector=largest or point")
                net_ids.add(topology.net_for_component(component))
            except (KeyError, LookupError, TypeError, ValueError) as error:
                seed_errors.append(f"{name} seed {seed_index}: {error}")
        named_nets[name] = net_ids

    if named_nets:
        seed_detail = ", ".join(
            f"{name}={len(net_ids)} physical net"
            f"{'s' if len(net_ids) != 1 else ''}"
            for name, net_ids in named_nets.items())
        audit.add(
            "Topology net seeds",
            not seed_errors,
            seed_detail if not seed_errors else "; ".join(seed_errors),
        )

    labels_by_net: dict[str, list[str]] = {}
    for name, net_ids in named_nets.items():
        for net_id in net_ids:
            labels_by_net.setdefault(net_id, []).append(name)

    for pair in config.get("forbidden_connections", []):
        if not isinstance(pair, list) or len(pair) != 2:
            audit.add(
                "Topology forbidden connection", False,
                f"invalid configured pair: {pair!r}")
            continue
        first, second = pair
        if first not in named_nets or second not in named_nets:
            audit.add(
                f"{first}/{second} copper isolation", False,
                "one or both named seed sets are missing")
            continue
        shared = sorted(named_nets[first] & named_nets[second])
        audit.add(
            f"{first}/{second} copper isolation",
            not shared,
            "no shared physical net" if not shared else
            "shared physical net" + ("s " if len(shared) != 1 else " ") +
            ", ".join(shared),
        )

    for net in topology.nets:
        connector_kinds: dict[str, int] = {}
        for connector_index in net.connector_indices:
            kind = topology.connectors[connector_index].kind
            connector_kinds[kind] = connector_kinds.get(kind, 0) + 1
        audit.topology_rows.append({
            "net": net.net_id,
            "labels": ", ".join(sorted(labels_by_net.get(net.net_id, ()))),
            "layers": ", ".join(net.layers),
            "components": str(len(net.components)),
            "connectors": ", ".join(
                f"{kind}={count}"
                for kind, count in sorted(connector_kinds.items())) or "-",
            "area": ", ".join(
                f"{layer}={area:.3f}"
                for layer, area in net.area_by_layer.items()),
        })

    audit_external_footprints(
        audit, profile, topology, labels_by_net)


def audit_external_footprints(
        audit: Audit, profile: dict[str, Any], topology: Any,
        labels_by_net: dict[str, list[str]]) -> None:
    config = profile.get("external_footprints")
    if config is None:
        return
    if __package__:
        from .pcb_assembly import (
            format_device_pad,
            load_footprints,
            load_name_atlas,
            map_pads_to_topology,
            place_footprint,
            read_jlc_bom,
            read_jlc_pnp,
            read_preflight_placements,
        )
    else:
        from pcb_assembly import (
            format_device_pad,
            load_footprints,
            load_name_atlas,
            map_pads_to_topology,
            place_footprint,
            read_jlc_bom,
            read_jlc_pnp,
            read_preflight_placements,
        )

    try:
        lcsc_by_designator = read_jlc_bom(relative_path(profile["bom"]))
        placements = read_jlc_pnp(
            relative_path(profile["pnp"]), lcsc_by_designator)
    except (OSError, ValueError, csv.Error) as error:
        audit.add("External footprint placements", False, str(error))
        return

    supplemental_designators = set(config.get("supplemental_designators", ()))
    if supplemental_designators:
        try:
            manifest_placements = read_preflight_placements(
                relative_path(config["placement_manifest"]))
            manifest_by_designator = {
                placement.designator: placement
                for placement in manifest_placements
            }
            missing = sorted(
                supplemental_designators - manifest_by_designator.keys())
            populated = sorted(
                supplemental_designators & {
                    placement.designator for placement in placements})
            if missing or populated:
                issues = []
                if missing:
                    issues.append("missing: " + ", ".join(missing))
                if populated:
                    issues.append(
                        "already in assembly PNP: " + ", ".join(populated))
                raise ValueError("; ".join(issues))
            supplemental = tuple(
                manifest_by_designator[designator]
                for designator in sorted(supplemental_designators))
            placements += supplemental
            lcsc_by_designator = dict(lcsc_by_designator)
            lcsc_by_designator.update({
                placement.designator: placement.lcsc
                for placement in supplemental
            })
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            audit.add("Supplemental physical placements", False, str(error))
            return
        audit.add(
            "Supplemental physical placements", True,
            f"included {', '.join(sorted(supplemental_designators))} from "
            f"{len(manifest_placements)} generated physical placements",
        )

    footprints, cache_errors = load_footprints(
        relative_path(config["cache_dir"]), lcsc_by_designator.values())
    audit.add(
        "External footprint cache",
        not cache_errors,
        f"{len(footprints)} unique LCSC footprints loaded"
        if not cache_errors else "; ".join(cache_errors),
    )
    if cache_errors:
        return

    try:
        name_atlas = load_name_atlas(
            relative_path(config["name_atlas_source"]),
            config["name_atlas_variable"],
        )
    except (KeyError, OSError, SyntaxError, TypeError, ValueError) as error:
        audit.add("Device name atlas", False, str(error))
        return
    audit.add(
        "Device name atlas", True,
        f"loaded {len(name_atlas.ic_roots_by_lcsc)} IC roots and "
        f"{len(name_atlas.header_pins)} header pin maps",
    )

    placed_pads = []
    placement_errors: list[str] = []
    for placement in placements:
        try:
            placed_pads.extend(place_footprint(
                footprints[placement.lcsc], placement,
                topology.layer_order))
        except (KeyError, ValueError) as error:
            placement_errors.append(f"{placement.designator}: {error}")
    audit.add(
        "External footprint placement",
        not placement_errors,
        f"{len(placements)} parts placed with {len(placed_pads)} copper pads"
        if not placement_errors else "; ".join(placement_errors),
    )
    if placement_errors:
        return

    attachments = map_pads_to_topology(topology, placed_pads)
    display_names: dict[tuple[str, int], str] = {}
    naming_errors: list[str] = []
    for attachment in attachments:
        key = (attachment.pad.designator, attachment.pad.pad_index)
        try:
            display_names[key] = format_device_pad(attachment.pad, name_atlas)
        except ValueError as error:
            naming_errors.append(str(error))
    audit.add(
        "Device pad naming",
        not naming_errors,
        f"all {len(attachments)} pads use the report naming schema"
        if not naming_errors else "; ".join(naming_errors),
    )
    if naming_errors:
        return

    def display_name(attachment: Any) -> str:
        return display_names[
            (attachment.pad.designator, attachment.pad.pad_index)]

    def device_anchor(designator: str) -> str:
        return f"device-{designator.lower()}"

    def pad_anchor(attachment: Any) -> str:
        return (
            f"{device_anchor(attachment.pad.designator)}-"
            f"pad-{attachment.pad.pad_index}"
        )

    bad_attachments = [
        attachment for attachment in attachments
        if len(attachment.net_ids) != 1
    ]
    audit.add(
        "External pad attachment",
        not bad_attachments,
        f"all {len(attachments)} EasyEDA-derived pads touch exactly one "
        "physical copper net"
        if not bad_attachments else
        f"{len(bad_attachments)}/{len(attachments)} pads do not touch exactly "
        "one physical net: " + ", ".join(
            f"{display_name(attachment)}=" +
            ("/".join(attachment.net_ids) or "none")
            for attachment in bad_attachments[:20]) +
        (" ..." if len(bad_attachments) > 20 else ""),
    )
    for attachment in attachments:
        center_x, center_y = attachment.pad.center
        audit.pad_rows.append({
            "status": "PASS" if len(attachment.net_ids) == 1 else "FAIL",
            "pad": attachment.pad.number,
            "device_pad": display_name(attachment),
            "lcsc": attachment.pad.lcsc,
            "layers": ", ".join(attachment.pad.layers),
            "center": f"{center_x:.3f}, {center_y:.3f}",
            "nets": ", ".join(attachment.net_ids) or "-",
            "overlap": f"{attachment.overlap_area:.4f}",
        })

    attachments_by_net: dict[str, list[Any]] = {}
    for attachment in attachments:
        if len(attachment.net_ids) == 1:
            attachments_by_net.setdefault(
                attachment.net_ids[0], []).append(attachment)
    for net in topology.nets:
        net_attachments = sorted(
            attachments_by_net.get(net.net_id, ()),
            key=lambda item: (
                item.pad.designator,
                item.pad.pad_index,
                item.pad.number,
            ),
        )
        common = {
            "net": net.net_id,
            "labels": ", ".join(sorted(labels_by_net.get(net.net_id, ()))) or "-",
            "layers": ", ".join(net.layers),
        }
        if not net_attachments:
            audit.net_rows.append({
                **common,
                "device_pad": "-",
                "footprint_pad": "-",
                "lcsc": "-",
            })
            continue
        for attachment in net_attachments:
            audit.net_rows.append({
                **common,
                "device_pad": display_name(attachment),
                "footprint_pad": attachment.pad.number,
                "lcsc": attachment.pad.lcsc,
            })
    audit.add(
        "Net list",
        len({row["net"] for row in audit.net_rows}) == len(topology.nets),
        f"all {len(topology.nets)} physical nets listed with "
        f"{len(attachments) - len(bad_attachments)} attached named pads",
    )

    family_order = {"J": 0, "U": 1, "Y": 2, "R": 3}

    def designator_key(designator: str) -> tuple[int, str, int, str]:
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", designator)
        family = match.group(1) if match else designator
        return (
            family_order.get(family, len(family_order)),
            family,
            int(match.group(2)) if match else 0,
            designator,
        )

    attachments_by_designator: dict[str, list[Any]] = {}
    for attachment in attachments:
        attachments_by_designator.setdefault(
            attachment.pad.designator, []).append(attachment)
    omitted_power_capacitors = 0
    listed_pad_count = 0
    for designator in sorted(attachments_by_designator, key=designator_key):
        device_attachments = sorted(
            attachments_by_designator[designator],
            key=lambda item: (
                natural_pad_number_key(item.pad.number),
                item.pad.pad_index,
            ))
        first_pad = device_attachments[0].pad
        pad_rows: list[dict[str, Any]] = []
        for attachment in device_attachments:
            if not attachment.net_ids:
                connection_kind = "none"
                connections = ("no physical net",)
            elif len(attachment.net_ids) != 1:
                connection_kind = "error"
                connections = (
                    "multiple physical nets: " +
                    ", ".join(attachment.net_ids),)
            else:
                net_id = attachment.net_ids[0]
                logical_names = set(labels_by_net.get(net_id, ()))
                power_names = tuple(
                    name for name in ("GND", "VCC")
                    if name in logical_names)
                if power_names:
                    connection_kind = "power"
                    connections = power_names
                else:
                    peers_by_name: dict[str, dict[str, str]] = {}
                    for peer in sorted(
                        attachments_by_net.get(net_id, ()),
                        key=lambda item: (
                            display_name(item),
                            item.pad.designator,
                            item.pad.pad_index,
                        ),
                    ):
                        if peer is attachment:
                            continue
                        label = display_name(peer)
                        peers_by_name.setdefault(label, {
                            "label": label,
                            "anchor": pad_anchor(peer),
                        })
                    peers = tuple(peers_by_name.values())
                    if peers:
                        connection_kind = "pads"
                        connections = peers
                    else:
                        connection_kind = "none"
                        connections = ("no other device pads",)
            pad_rows.append({
                "device_pad": display_name(attachment),
                "anchor": pad_anchor(attachment),
                "connection_kind": connection_kind,
                "connections": connections,
            })
        power_connections = {
            connection
            for row in pad_rows
            if row["connection_kind"] == "power"
            for connection in row["connections"]
        }
        if (
            designator.startswith("C")
            and all(row["connection_kind"] == "power" for row in pad_rows)
            and power_connections == {"GND", "VCC"}
        ):
            omitted_power_capacitors += 1
            continue
        audit.device_rows.append({
            "designator": designator,
            "anchor": device_anchor(designator),
            "part_name": name_atlas.ic_roots_by_lcsc.get(first_pad.lcsc, ""),
            "manufacturer": first_pad.manufacturer,
            "lcsc": first_pad.lcsc,
            "lcsc_url": first_pad.lcsc_url,
            "pads": pad_rows,
        })
        listed_pad_count += len(pad_rows)
    audit.add(
        "Device connection list",
        len(audit.device_rows) + omitted_power_capacitors == len(placements),
        f"{len(audit.device_rows)} devices listed with {listed_pad_count} pads; "
        f"{omitted_power_capacitors} VCC-to-GND capacitors omitted",
    )


def html_cell(value: object) -> str:
    return html.escape(str(value), quote=True)


def html_status(value: str) -> str:
    passed = value.startswith("PASS")
    css_class = "pass" if passed else "fail"
    return f'<span class="status {css_class}">{html_cell(value)}</span>'


def net_anchor(net_id: str) -> str:
    return f"net-{net_id.lower()}"


def net_report_link(net_id: str) -> str:
    return (
        f'<a class="net-link" href="#{html_cell(net_anchor(net_id))}">'
        f'<code>{html_cell(net_id)}</code></a>')


def write_report(
        path: Path, profile: dict[str, Any], audit: Audit,
        generation_output: str) -> None:
    result = "PASS" if audit.passed else "FAIL"
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result_class = "pass" if audit.passed else "fail"
    toc_items = [
        ("automated-checks", "Automated Checks"),
        ("nets-by-device", "Nets By Device"),
        ("nets", "Nets"),
        ("copper-topology", "Copper Topology"),
        ("external-pad-attachment", "External Pad Attachment"),
        ("jlcpcb-bom-audit", "JLCPCB BOM Audit"),
        ("manual-checks", "Manual Checks"),
    ]
    if generation_output.strip():
        toc_items.append(("generator-output", "Generator Output"))
    toc_links = "".join(
        f'<li><a href="#{html_cell(anchor)}">{html_cell(label)}</a></li>'
        for anchor, label in toc_items)
    lines = [f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_cell(profile['board'])} manufacturing preflight</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      font-size: 14px;
      letter-spacing: 0;
      color: #182026;
      background: #f4f6f7;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ max-width: 100%; overflow-x: hidden; }}
    body {{ width: 100vw; margin: 0; background: #f4f6f7; }}
    header {{ background: #172126; color: #f7fafb; border-bottom: 4px solid #2f8f62; }}
    .container {{ width: auto; max-width: 1480px; margin: 0 16px; }}
    header .container {{ padding: 24px 0 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; line-height: 1.2; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.3; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; line-height: 1.4; letter-spacing: 0; }}
    p {{ margin: 6px 0; line-height: 1.5; }}
    main {{ padding: 8px 0 40px; }}
    section {{ padding: 22px 0; border-bottom: 1px solid #cbd3d7; }}
    .summary {{ display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }}
    .toc {{ padding: 22px 0; border-bottom: 1px solid #cbd3d7; }}
    .toc h2 {{ margin-bottom: 8px; }}
    .toc ul {{ margin: 0; padding-left: 22px; }}
    .toc li {{ margin: 5px 0; line-height: 1.4; }}
    .toc a {{ color: #16623f; font-weight: 600; text-decoration: underline;
      text-underline-offset: 2px; }}
    .toc a:hover, .toc a:focus {{ color: #0b3d27; }}
    .muted {{ width: calc(100vw - 32px); color: #aebbc1; white-space: normal;
      overflow-wrap: anywhere; }}
    .warning {{ color: #39474e; }}
    .status {{ display: inline-block; min-width: 48px; font-weight: 700; }}
    .status.pass {{ color: #18794e; }}
    .status.fail {{ color: #b42318; }}
    header .status {{ padding: 4px 9px; color: white; border: 1px solid currentColor; }}
    header .status.pass {{ background: #18794e; color: white; }}
    header .status.fail {{ background: #b42318; color: white; }}
    .table-wrap {{ width: 100%; max-width: 100%; overflow-x: auto;
      border: 1px solid #cbd3d7; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ padding: 7px 9px; text-align: left; vertical-align: top;
      border-bottom: 1px solid #e0e5e7; white-space: nowrap; }}
    th {{ position: sticky; top: 0; z-index: 1; background: #e8edef;
      color: #26343b; font-size: 12px; font-weight: 700; }}
    tbody tr:nth-child(even) {{ background: #f8fafb; }}
    td.detail {{ white-space: normal; min-width: 320px; }}
    .device {{ padding: 14px 0; border-top: 1px solid #d9e0e3; }}
    .device:first-of-type {{ border-top: 0; }}
    .device h3 {{ display: flex; align-items: baseline; gap: 9px; margin-bottom: 8px; }}
    .device-identity {{ display: inline-flex; align-items: baseline; gap: 7px; }}
    .device-designator {{ font-size: 16px; font-weight: 800; color: #18252b; }}
    .device-part-name {{ font-size: 14px; font-weight: 650; color: #34434a; }}
    .device-meta {{ color: #68777e; font-size: 12px; font-weight: 400; }}
    .device-meta a {{ color: #3c6b55; text-underline-offset: 2px; }}
    .device-pads {{ margin: 0; padding-left: 32px; }}
    .device-pads li {{ margin: 5px 0; padding: 2px 4px; line-height: 1.45;
      scroll-margin-top: 12px; }}
    .pad-link {{ color: #16623f; text-decoration: underline;
      text-underline-offset: 2px; }}
    .pad-link:hover, .pad-link:focus {{ color: #0b3d27; }}
    .device-pads li.pad-highlight {{ animation: pad-highlight 10s ease-out; }}
    @keyframes pad-highlight {{
      0% {{ background-color: #ffe36e; }}
      12% {{ background-color: #ffe36e; }}
      100% {{ background-color: transparent; }}
    }}
    .connection {{ margin-left: 6px; }}
    code {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 12px; }}
    pre {{ margin: 0; padding: 14px; overflow: auto; background: #11191d;
      color: #e8edef; border: 1px solid #334148; line-height: 1.45; }}
    ul.checklist {{ margin: 0; padding: 0; list-style: none; }}
    ul.checklist li {{ margin: 7px 0; line-height: 1.45; }}
    ul.checklist input {{ margin: 0 8px 0 0; vertical-align: middle; }}
    .mobile-break {{ display: none; }}
    @media (min-width: 1512px) {{
      .container {{ margin-left: auto; margin-right: auto; }}
    }}
    @media (max-width: 700px) {{
      .container {{ margin-left: 10px; margin-right: 10px; }}
      .muted {{ width: calc(100vw - 20px); }}
      .mobile-break {{ display: block; }}
      header .container {{ padding: 18px 0 16px; }}
      h1 {{ font-size: 20px; }}
      th, td {{ padding: 6px 7px; }}
    }}
  </style>
</head>
<body>
<header>
  <div class="container">
    <h1>{html_cell(profile['board'])} manufacturing preflight</h1>
    <div class="summary">
      <span class="status {result_class}">{result}</span>
      <span>Generated {html_cell(generated)}</span>
    </div>
    <p class="muted">A passing automated result does not complete<span
      class="mobile-break"></span> the manual CAM gate.</p>
  </div>
</header>
<main class="container">
<nav class="toc" aria-label="Report contents">
  <h2>Contents</h2>
  <ul>{toc_links}</ul>
</nav>
<section id="automated-checks">
  <h2>Automated Checks</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Result</th><th>Check</th><th>Detail</th></tr></thead>
    <tbody>"""]
    for check in audit.checks:
        status = "PASS" if check.passed else "FAIL"
        detail = (
            check.detail_html
            if check.detail_html is not None else html_cell(check.detail))
        lines.append(
            f"<tr><td>{html_status(status)}</td>"
            f"<td>{html_cell(check.name)}</td>"
            f'<td class="detail">{detail}</td></tr>')
    lines.append("</tbody></table></div></section>")

    if audit.device_rows:
        lines.extend(["""
<section id="nets-by-device">
  <h2>Nets By Device</h2>
  <p class="warning">Each pad lists the other populated device pads on its physical net.
  Identified ground and supply planes are abbreviated as GND and VCC.</p>
"""])
        for device in audit.device_rows:
            part_name = (
                f'<span class="device-part-name">'
                f'{html_cell(device["part_name"])}</span>'
                if device["part_name"] else ""
            )
            lines.append(
                f'<article class="device" id="{html_cell(device["anchor"])}">'
                f'<h3><span class="device-identity"><code class="device-designator">'
                f"{html_cell(device['designator'])}</code>{part_name}</span>"
                f'<span class="device-meta">{html_cell(device["manufacturer"])} · '
                f'<a href="{html_cell(device["lcsc_url"])}" target="_blank" '
                f'rel="noopener noreferrer">{html_cell(device["lcsc"])}</a>'
                '</span></h3><ol class="device-pads">')
            for pad in device["pads"]:
                if pad["connection_kind"] == "power":
                    connections = " / ".join(
                        f"<strong>{html_cell(name)}</strong>"
                        for name in pad["connections"])
                elif pad["connection_kind"] == "pads":
                    connections = ", ".join(
                        f'<a class="pad-link" href="#{html_cell(peer["anchor"])}">'
                        f'<code>{html_cell(peer["label"])}</code></a>'
                        for peer in pad["connections"])
                else:
                    connections = html_cell("; ".join(pad["connections"]))
                lines.append(
                    f'<li id="{html_cell(pad["anchor"])}">'
                    f"<code>{html_cell(pad['device_pad'])}</code>"
                    f'<span class="connection">&rarr; {connections}</span></li>')
            lines.append("</ol></article>")
        lines.append("</section>")

    if audit.net_rows:
        lines.extend(["""
<section id="nets">
  <h2>Nets</h2>
  <p class="warning">Physical nets list every attached populated pad using the
  common report naming schema. Footprint pad number preserves placement provenance.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Physical net</th><th>Logical seed</th><th>Device.pad</th>
      <th>Footprint pad</th><th>LCSC</th><th>Layers</th></tr></thead>
    <tbody>"""])
        previous_net = None
        for row in audit.net_rows:
            repeated = row["net"] == previous_net
            row_id = (
                "" if repeated else
                f' id="{html_cell(net_anchor(row["net"]))}"')
            lines.append(
                f"<tr{row_id}>"
                f"<td><code>{'' if repeated else html_cell(row['net'])}</code></td>"
                f"<td>{'' if repeated else html_cell(row['labels'])}</td>"
                f"<td><code>{html_cell(row['device_pad'])}</code></td>"
                f"<td><code>{html_cell(row['footprint_pad'])}</code></td>"
                f"<td><code>{html_cell(row['lcsc'])}</code></td>"
                f"<td>{'' if repeated else html_cell(row['layers'])}</td>"
                "</tr>")
            previous_net = row["net"]
        lines.append("</tbody></table></div></section>")

    if audit.topology_rows:
        lines.extend(["""
<section id="copper-topology">
  <h2>Copper Topology</h2>
  <p class="warning">Physical nets are reconstructed from connected copper regions,
  drill hits, and configured plated slots before logical seed names are applied.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Net</th><th>Logical seeds</th><th>Layers</th>
      <th>Components</th><th>Connectors</th><th>Copper area (mm²)</th></tr></thead>
    <tbody>"""])
        for row in audit.topology_rows:
            lines.append(
                f"<tr><td><code>{html_cell(row['net'])}</code></td>"
                f"<td>{html_cell(row['labels'] or '-')}</td>"
                f"<td>{html_cell(row['layers'])}</td>"
                f"<td>{html_cell(row['components'])}</td>"
                f"<td>{html_cell(row['connectors'])}</td>"
                f"<td>{html_cell(row['area'])}</td></tr>")
        lines.append("</tbody></table></div></section>")

    if audit.pad_rows:
        lines.extend(["""
<section id="external-pad-attachment">
  <h2>External Pad Attachment</h2>
  <p class="warning">Pad geometry comes from cached EasyEDA footprints selected by
  the JLCPCB BOM, independently placed using the JLCPCB PNP file, and intersected
  with manufacturing copper.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Result</th><th>Device.pad</th><th>Footprint pad</th>
      <th>LCSC</th><th>Copper layers</th><th>Center (mm)</th>
      <th>Physical net</th><th>Overlap (mm²)</th></tr></thead>
    <tbody>"""])
        for row in audit.pad_rows:
            lines.append(
                f"<tr><td>{html_status(row['status'])}</td>"
                f"<td><code>{html_cell(row['device_pad'])}</code></td>"
                f"<td><code>{html_cell(row['pad'])}</code></td>"
                f"<td><code>{html_cell(row['lcsc'])}</code></td>"
                f"<td>{html_cell(row['layers'])}</td>"
                f"<td>{html_cell(row['center'])}</td>"
                f"<td><code>{html_cell(row['nets'])}</code></td>"
                f"<td>{html_cell(row['overlap'])}</td></tr>")
        lines.append("</tbody></table></div></section>")

    lines.extend(["""
<section id="jlcpcb-bom-audit">
  <h2>JLCPCB BOM Audit</h2>
  <p class="warning">For discrete rows, Comment is the electrical value; for part
  rows, it is the manufacturer part number.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Result</th><th>Designator</th><th>LCSC</th><th>Kind</th>
      <th>Comment</th><th>BOM footprint</th><th>Manufacturer part</th>
      <th>Manufacturer package</th><th>JLCPCB class</th></tr></thead>
    <tbody>"""])
    for row in audit.bom_rows:
        lines.append(
            f"<tr><td>{html_status(row['status'])}</td>"
            f"<td>{html_cell(row['designator'])}</td>"
            f"<td><code>{html_cell(row['lcsc'])}</code></td>"
            f"<td>{html_cell(row['kind'])}</td>"
            f"<td>{html_cell(row['comment'])}</td>"
            f"<td>{html_cell(row['footprint'])}</td>"
            f"<td>{html_cell(row['mpn'])}</td>"
            f"<td>{html_cell(row['manufacturer_footprint'])}</td>"
            f"<td>{html_cell(row['jlcpcb_class'])}</td></tr>")
    lines.append("</tbody></table></div></section>")

    lines.extend(['<section id="manual-checks">'
                  "<h2>Board-Specific Manual Checks</h2>",
                  '<ul class="checklist">'])
    manual_checks = profile.get("manual_checks", [])
    if manual_checks:
        lines.extend(
            f'<li><input type="checkbox" disabled>{html_cell(item)}</li>'
            for item in manual_checks)
    else:
        lines.append(
            '<li><input type="checkbox" disabled>No profile-specific items; '
            "complete the skill's general CAM gate.</li>")
    lines.append("</ul></section>")

    if generation_output.strip():
        lines.extend([
            '<section id="generator-output"><h2>Generator Output</h2><pre>',
            html_cell(generation_output.rstrip()),
            "</pre></section>",
        ])
    lines.extend(["""
</main>
<script>
  function highlightPad(anchor) {
    const target = document.getElementById(anchor);
    if (!target || !target.closest('.device-pads')) return;
    target.classList.remove('pad-highlight');
    void target.offsetWidth;
    target.classList.add('pad-highlight');
  }
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a.pad-link');
    if (link) highlightPad(decodeURIComponent(link.hash.slice(1)));
  });
  window.addEventListener('hashchange', () => {
    highlightPad(decodeURIComponent(location.hash.slice(1)));
  });
  if (location.hash) highlightPad(decodeURIComponent(location.hash.slice(1)));
</script>
</body>
</html>"""])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight a profiled CuFlow PCB for manufacturing")
    parser.add_argument("board", help="board/profile name, for example spiq_a")
    parser.add_argument(
        "--profile", type=Path,
        help="profile JSON path (default: preflight/<board>.json)")
    parser.add_argument(
        "--no-generate", action="store_true",
        help="inspect existing outputs without regenerating the board")
    parser.add_argument(
        "--python", dest="python_executable", type=Path,
        help="Python interpreter for the board generator (overrides profile)")
    parser.add_argument(
        "--report", type=Path,
        help="report path (default: <board>-preflight.html)")
    return parser.parse_args()


def configured_python(
        args: argparse.Namespace, profile: dict[str, Any]) -> Path:
    configured = (
        args.python_executable or Path(profile.get("python", sys.executable)))
    executable = configured.expanduser()
    return executable if executable.is_absolute() else ROOT / executable


def main() -> int:
    args = parse_args()
    profile_path = (
        args.profile if args.profile is not None
        else ROOT / "preflight" / f"{args.board}.json")
    if not profile_path.is_absolute():
        profile_path = ROOT / profile_path
    try:
        profile = load_json(profile_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"preflight: cannot load profile: {error}", file=sys.stderr)
        return 2
    if profile.get("board") != args.board:
        print(
            f"preflight: profile board {profile.get('board')!r} does not match "
            f"{args.board!r}", file=sys.stderr)
        return 2

    python_executable = configured_python(args, profile)
    if profile.get("topology") is not None:
        try:
            __import__("shapely")
        except ModuleNotFoundError:
            if Path(sys.executable).absolute() == python_executable.absolute():
                print(
                    "preflight: topology checks require Shapely in "
                    f"{python_executable}", file=sys.stderr)
                return 2
            try:
                os.execv(
                    str(python_executable),
                    [str(python_executable), str(Path(__file__).resolve()),
                     *sys.argv[1:]])
            except OSError as error:
                print(
                    f"preflight: cannot restart with {python_executable}: "
                    f"{error}", file=sys.stderr)
                return 2

    audit = Audit()
    generation_output = ""
    if args.no_generate:
        audit.add("Board generation", True, "skipped by explicit --no-generate")
    else:
        source = relative_path(profile["source"])
        try:
            result = subprocess.run(
                [str(python_executable), str(source)], cwd=ROOT, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            generation_output = result.stdout
            return_code: int | None = result.returncode
        except OSError as error:
            generation_output = str(error)
            return_code = None
        audit.add(
            "Board generation",
            return_code == 0,
            f"{source.name} via {python_executable} exited {return_code}"
            if return_code is not None else
            f"could not run {python_executable}: {generation_output}",
        )

    catalog = load_catalog(audit, relative_path(profile["part_catalog"]))
    audit_bom_and_pnp(audit, profile, catalog)
    audit_manufacturing_files(audit, profile)
    audit_copper_topology(audit, profile)

    report_path = args.report or ROOT / f"{args.board}-preflight.html"
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    write_report(report_path, profile, audit, generation_output)

    failures = [check for check in audit.checks if not check.passed]
    print(
        f"{args.board}: {'PASS' if audit.passed else 'FAIL'} "
        f"({len(audit.checks) - len(failures)}/{len(audit.checks)} checks passed)")
    for failure in failures:
        print(f"FAIL: {failure.name}: {failure.detail}")
    print(f"Report: {report_path}")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
