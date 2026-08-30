---
name: pcb-manufacturing-preflight
description: Preflight CuFlow PCB outputs before manufacture, including Gerbers, drills and routed slots, airwires, JLCPCB BOM/PNP consistency, footprint selection, and CAM inspection. Use when a user asks whether a board is ready to submit or requests a manufacturing/pre-flight review.
---

# PCB manufacturing preflight

Run the repository's deterministic checks, then perform the checks that require
engineering judgment in a CAM view. A passing script is necessary but is not by
itself approval to manufacture.

Boards with `external_footprints` in their profile also map package pads to
physical copper nets using cached EasyEDA footprints selected by the JLCPCB BOM
and placed by the JLCPCB PNP file. Normal preflight is cache-only. Refresh that
independent source explicitly when a BOM selection changes:

```sh
python3 tools/fetch_easyeda_footprints.py <board>-jlcpcb-bom.csv
```

The cache includes official EasyEDA symbol pin names. The report joins those
names to the package pads and physical nets while retaining reference designator
and pad number as provenance.

## Automated gate

From the repository root, run:

```sh
python3 tools/pcb_preflight.py <board-name>
```

This regenerates the board unless `--no-generate` is explicitly appropriate.
Read the generated `<board-name>-preflight.html` report and resolve every failure.
Use the selected board's profile in `preflight/`; do not generalize profile-only
requirements to other boards. For example, `spiq_a` requires five GML contours
because it has one perimeter and four routed USB-C mounting slots.

The pinned part catalog distinguishes two BOM comment rules:

- For resistors, capacitors, and other entries marked `discrete`, JLCPCB's
  `Comment` is the electrical value. It is not the manufacturer part number.
- For entries marked `part`, `Comment` is the manufacturer part number.

In both cases the LCSC number, emitted comment, emitted footprint, actual
manufacturer part number, and manufacturer package are kept together in the
catalog. Treat a change to any member of that selection as a part change that
needs review. Current stock and Basic/Extended status are not guaranteed by the
pinned catalog; verify them live when the user asks for current procurement
status.

## Manual CAM gate

Inspect the generated manufacturing files themselves, not only a PCB rendering:

- Confirm the board outline, routed slots, plated lands, and drill hits exist in
  the submitted files and have the intended locations and sizes.
- Compare mechanically critical and polarized footprints against their selected
  manufacturer datasheets, especially connectors and fine-pitch packages.
- Inspect top and bottom copper for unintended crossings, shorts, via collisions,
  copper outside the substrate, and suspicious neck-downs or clearances.
- Inspect solder mask, paste, and silkscreen alignment. Confirm paste is absent
  where intended and silkscreen does not obscure pads or leave the board edge.
- Check edge clearances and slot clearances using the intended fabrication and
  assembly rules, including any V-score constraints.
- Check PNP side, position, and rotation for representative asymmetric parts and
  confirm every populated BOM designator has exactly one placement.
- Complete every board-specific manual item printed in the report.

## Result

Report automated failures separately from manual findings. Say the board is
ready only when both gates pass. Include the report path and identify any check
that could not be completed; do not silently convert an unperformed check into a
pass.
