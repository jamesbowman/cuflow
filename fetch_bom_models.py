#!/usr/bin/env python3
"""Fetch EasyEDA 3D models for every LCSC part in a CuFlow BOM."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from pathlib import Path
import re
import tempfile


LCSC_RE = re.compile(r"C[0-9]+")


class ModelFetchError(RuntimeError):
    pass


def lcsc_codes(bom_path: Path) -> list[str]:
    """Return unique LCSC codes in BOM order."""
    with bom_path.open(newline="", encoding="utf-8-sig") as bom_file:
        reader = csv.DictReader(bom_file)
        required = {"vendor", "code"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"{bom_path} is missing BOM column(s): {', '.join(sorted(missing))}"
            )

        codes = []
        seen = set()
        for line_number, row in enumerate(reader, start=2):
            if (row.get("vendor") or "").strip().upper() != "LCSC":
                continue
            code = (row.get("code") or "").strip().upper()
            if not LCSC_RE.fullmatch(code):
                raise ValueError(
                    f"{bom_path}:{line_number}: invalid LCSC part number {code!r}"
                )
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def atomic_write(path: Path, data: bytes) -> None:
    """Replace a model file only after its complete contents are available."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(data)
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def import_model(api, lcsc_code: str, download: bool):
    from easyeda2kicad.easyeda.easyeda_importer import Easyeda3dModelImporter

    cad_data = api.get_cad_data_of_component(lcsc_id=lcsc_code)
    if not cad_data:
        raise ModelFetchError("component data was not returned by EasyEDA")

    imported = Easyeda3dModelImporter(
        easyeda_cp_cad_data=cad_data,
        download_raw_3d_model=download,
        api=api,
    ).output
    if imported is None:
        raise ModelFetchError("no EasyEDA 3D model is assigned")
    return imported


def model_metadata(lcsc_code: str, imported) -> dict:
    return {
        "step": f"{lcsc_code}.step",
        "wrl": f"{lcsc_code}.wrl",
        "easyedaName": imported.name,
        "translation": [
            imported.translation.x,
            imported.translation.y,
            imported.translation.z,
        ],
        "rotation": [
            imported.rotation.x,
            imported.rotation.y,
            imported.rotation.z,
        ],
    }


def fetch_model(api, lcsc_code: str) -> tuple[bytes, bytes, dict]:
    from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad

    imported = import_model(api, lcsc_code, download=True)

    exported = Exporter3dModelKicad(model_3d=imported)
    if exported.output_step is None:
        raise ModelFetchError("the EasyEDA model has no STEP data")
    if exported.output is None or not exported.output.raw_wrl:
        raise ModelFetchError("the EasyEDA model could not be converted to WRL")

    return (
        exported.output_step,
        exported.output.raw_wrl.encode("utf-8"),
        model_metadata(lcsc_code, imported),
    )


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"format": "cuflow-easyeda-models-1", "models": {}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format") != "cuflow-easyeda-models-1":
        raise ValueError(f"Unsupported model manifest format in {path}")
    if not isinstance(manifest.get("models"), dict):
        raise ValueError(f"Invalid model manifest in {path}")
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Fetch STEP and WRL models for the unique LCSC codes in a CuFlow BOM."
        )
    )
    result.add_argument("bom", type=Path, help="CuFlow BOM CSV, e.g. spiq_a-bom.csv")
    result.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("assets/step"),
        help="model destination (default: assets/step)",
    )
    result.add_argument(
        "--overwrite",
        action="store_true",
        help="replace model files that already exist",
    )
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="list model paths without accessing EasyEDA",
    )
    result.add_argument(
        "--no-cache",
        action="store_true",
        help="disable easyeda2kicad's local API cache",
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        codes = lcsc_codes(arguments.bom)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2

    if not codes:
        print(f"No LCSC parts found in {arguments.bom}")
        return 0

    if arguments.dry_run:
        for code in codes:
            print(arguments.output_dir / f"{code}.step")
            print(arguments.output_dir / f"{code}.wrl")
        print(f"{len(codes)} unique LCSC part(s)")
        return 0

    try:
        from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
    except ModuleNotFoundError:
        print(
            "error: easyeda2kicad is not installed; run "
            "'python -m pip install -r requirements.txt'"
        )
        return 2

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    api = EasyedaApi(use_cache=not arguments.no_cache)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = arguments.output_dir / "models.json"
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}")
        return 2

    fetched = 0
    skipped = 0
    failures = []
    for index, code in enumerate(codes, start=1):
        step_path = arguments.output_dir / f"{code}.step"
        wrl_path = arguments.output_dir / f"{code}.wrl"
        step_complete = step_path.is_file() and step_path.stat().st_size > 0
        wrl_complete = wrl_path.is_file() and wrl_path.stat().st_size > 0
        if step_complete and wrl_complete and not arguments.overwrite:
            try:
                if code not in manifest["models"]:
                    imported = import_model(api, code, download=False)
                    manifest["models"][code] = model_metadata(code, imported)
                print(f"[{index}/{len(codes)}] {code}: already present")
                skipped += 1
                continue
            except (ModelFetchError, OSError, ValueError) as error:
                failures.append((code, str(error)))
                print(f"[{index}/{len(codes)}] {code}: metadata unavailable: {error}")
                continue

        print(f"[{index}/{len(codes)}] {code}: fetching")
        try:
            step_data, wrl_data, metadata = fetch_model(api, code)
            if arguments.overwrite or not step_complete:
                atomic_write(step_path, step_data)
            if arguments.overwrite or not wrl_complete:
                atomic_write(wrl_path, wrl_data)
            manifest["models"][code] = metadata
            fetched += 1
            print(
                f"           wrote {step_path.name} ({len(step_data):,} bytes), "
                f"{wrl_path.name} ({len(wrl_data):,} bytes)"
            )
        except (ModelFetchError, OSError, ValueError) as error:
            failures.append((code, str(error)))
            print(f"           unavailable: {error}")

    atomic_write(
        manifest_path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )

    print(
        f"Finished: {fetched} fetched, {skipped} already present, "
        f"{len(failures)} unavailable"
    )
    if failures:
        print("Unavailable models:")
        for code, reason in failures:
            print(f"  {code}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
