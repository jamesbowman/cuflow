#!/usr/bin/env python3
"""Fetch and normalize EasyEDA footprints used by a JLCPCB BOM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

if __package__:
    from .pcb_assembly import FOOTPRINT_FORMAT, read_jlc_bom
else:
    from pcb_assembly import FOOTPRINT_FORMAT, read_jlc_bom


POLYGON_POINT = re.compile(
    r"\(xy\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def copper_sides(layers: str) -> list[str]:
    values = set(layers.split())
    if "*.Cu" in values:
        return ["all"]
    result = []
    if "F.Cu" in values:
        result.append("top")
    if "B.Cu" in values:
        result.append("bottom")
    return result


def normalize_footprint(lcsc: str, cad_data: dict) -> dict:
    from easyeda2kicad.easyeda.easyeda_importer import (
        EasyedaFootprintImporter,
        EasyedaSymbolImporter,
    )
    from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad

    imported = EasyedaFootprintImporter(cad_data).output
    exported = ExporterFootprintKicad(imported).output
    symbol = EasyedaSymbolImporter(cad_data).output
    symbol_units = [symbol]
    for unit in symbol_units:
        symbol_units.extend(unit.sub_symbols)
    pin_names: dict[str, str] = {}
    for unit in symbol_units:
        for pin in unit.pins:
            number = pin.settings.spice_pin_number.strip()
            name = pin.name.text.strip()
            if not number or not name:
                continue
            previous = pin_names.get(number)
            if previous is not None and previous != name:
                raise ValueError(
                    f"symbol pin {number} has conflicting names "
                    f"{previous!r} and {name!r}")
            pin_names[number] = name
    pads = []
    for pad in exported.pads:
        sides = copper_sides(pad.layers)
        if not sides:
            continue
        polygon = [
            [float(x), float(y)]
            for x, y in POLYGON_POINT.findall(pad.polygon)
        ]
        pads.append({
            "center": [pad.pos_x, pad.pos_y],
            "copper_sides": sides,
            "number": pad.number,
            "polygon": polygon,
            "rotation": pad.orientation,
            "shape": pad.shape,
            "size": [pad.width, pad.height],
            "type": pad.type,
        })
    canonical_source = json.dumps(
        cad_data, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")
    return {
        "format": FOOTPRINT_FORMAT,
        "device_name": symbol.info.name,
        "lcsc": lcsc,
        "lcsc_url": cad_data.get("lcsc", {}).get("url") or
        f"https://www.lcsc.com/search?q={lcsc}",
        "manufacturer": symbol.info.manufacturer,
        "mpn": symbol.info.mpn,
        "package": exported.info.name,
        "pads": pads,
        "pin_names": pin_names,
        "source_sha256": hashlib.sha256(canonical_source).hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cache normalized EasyEDA footprints for a JLCPCB BOM")
    parser.add_argument("bom", type=Path, help="JLCPCB BOM CSV")
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("preflight/easyeda-footprints"),
        help="cache directory (default: preflight/easyeda-footprints)")
    parser.add_argument(
        "--refresh", action="store_true",
        help="replace existing normalized cache entries")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        lcsc_by_designator = read_jlc_bom(args.bom)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    lcsc_codes = sorted(set(lcsc_by_designator.values()))
    try:
        from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
    except ModuleNotFoundError:
        print("error: easyeda2kicad is not installed")
        return 2

    api = EasyedaApi(use_cache=True)
    failures: list[str] = []
    for index, lcsc in enumerate(lcsc_codes, 1):
        destination = args.output_dir / f"{lcsc}.json"
        if destination.is_file() and not args.refresh:
            print(f"[{index}/{len(lcsc_codes)}] {lcsc}: already cached")
            continue
        try:
            cad_data = api.get_cad_data_of_component(lcsc_id=lcsc)
            if not cad_data or "packageDetail" not in cad_data:
                raise ValueError("component footprint data was not returned")
            atomic_json(destination, normalize_footprint(lcsc, cad_data))
            print(f"[{index}/{len(lcsc_codes)}] {lcsc}: {destination}")
        except (KeyError, OSError, TypeError, ValueError) as error:
            failures.append(f"{lcsc}: {error}")
            print(f"[{index}/{len(lcsc_codes)}] {lcsc}: FAILED: {error}")
    if failures:
        print(f"{len(failures)} footprint(s) failed")
        return 1
    print(f"{len(lcsc_codes)} normalized footprint(s) available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
