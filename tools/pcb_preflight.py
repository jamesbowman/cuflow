#!/usr/bin/env python3
"""Deterministic manufacturing-output checks for profiled CuFlow boards."""

from __future__ import annotations

import argparse
import csv
import json
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


class Audit:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.bom_rows: list[dict[str, str]] = []

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name, passed, detail))

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


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_report(
        path: Path, profile: dict[str, Any], audit: Audit,
        generation_output: str) -> None:
    result = "PASS" if audit.passed else "FAIL"
    lines = [
        f"# {profile['board']} manufacturing preflight",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"Automated result: **{result}**",
        "",
        "A passing automated result does not complete the manual CAM gate.",
        "",
        "## Automated checks",
        "",
        "| Result | Check | Detail |",
        "| --- | --- | --- |",
    ]
    for check in audit.checks:
        lines.append(
            f"| {'PASS' if check.passed else 'FAIL'} | "
            f"{markdown_cell(check.name)} | {markdown_cell(check.detail)} |")

    lines.extend([
        "",
        "## JLCPCB BOM audit",
        "",
        "For `discrete` rows, Comment is the electrical value; for `part` rows, "
        "it is the manufacturer part number.",
        "",
        "| Result | Designator | LCSC | Kind | Comment | BOM footprint | "
        "Manufacturer part | Manufacturer package | JLCPCB class |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in audit.bom_rows:
        cells = {key: markdown_cell(value) for key, value in row.items()}
        lines.append(
            "| {status} | {designator} | {lcsc} | {kind} | {comment} | "
            "{footprint} | {mpn} | {manufacturer_footprint} | "
            "{jlcpcb_class} |".format(
                **cells))

    lines.extend([
        "",
        "## Board-specific manual checks",
        "",
    ])
    manual_checks = profile.get("manual_checks", [])
    if manual_checks:
        lines.extend(f"- [ ] {item}" for item in manual_checks)
    else:
        lines.append(
            "- [ ] No profile-specific items; complete the skill's general CAM gate.")

    if generation_output.strip():
        lines.extend([
            "",
            "## Generator output",
            "",
            "```text",
            generation_output.rstrip(),
            "```",
        ])
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
        help="report path (default: <board>-preflight.md)")
    return parser.parse_args()


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

    audit = Audit()
    generation_output = ""
    if args.no_generate:
        audit.add("Board generation", True, "skipped by explicit --no-generate")
    else:
        source = relative_path(profile["source"])
        configured_python = (
            args.python_executable or Path(profile.get("python", sys.executable)))
        python_executable = configured_python.expanduser()
        if not python_executable.is_absolute():
            python_executable = ROOT / python_executable
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

    report_path = args.report or ROOT / f"{args.board}-preflight.md"
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
