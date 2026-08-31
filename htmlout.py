"""Write a self-contained, interactive 3D board preview."""

import hashlib
import json
from pathlib import Path

import shapely.geometry as sg


_MODEL_MANIFEST = Path("assets/step/models.json")
_MODEL_MESH_DIRECTORY = Path("webviewer/generated")
_LCD_DESIGNATOR = "U3"
_LCD_STEP_MODEL = Path("assets/misc-step/LH133T-IG01.stp")
_LCD_MESH_MODEL = Path("webviewer/generated/LH133T-IG01.mesh.json")
_BEZEL_STL_MODEL = Path("assets/misc-stl/bezel.stl")
_BEZEL_MESH_MODEL = Path("webviewer/generated/bezel.mesh.json")
_BEZEL_CONTACT_Z = 2.1


def _ring(coords):
    points = list(coords)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return [[round(x, 5), round(y, 5)] for x, y in points]


def _polygons(geometry):
    if isinstance(geometry, sg.Polygon):
        geometries = [geometry]
    elif isinstance(geometry, (sg.MultiPolygon, sg.GeometryCollection)):
        geometries = [g for g in geometry.geoms if isinstance(g, sg.Polygon)]
    else:
        raise TypeError(f"Unsupported board geometry: {geometry.geom_type}")
    return [
        {
            "outer": _ring(polygon.exterior.coords),
            "holes": [_ring(hole.coords) for hole in polygon.interiors],
        }
        for polygon in geometries
        if not polygon.is_empty
    ]


def _expand_designators(compact):
    designators = []
    for item in compact.split(","):
        item = item.strip()
        if "-" not in item:
            designators.append(item)
            continue
        first, last = item.split("-", 1)
        prefix = first.rstrip("0123456789")
        start = int(first[len(prefix) :])
        if last.startswith(prefix):
            last = last[len(prefix) :]
        finish = int(last)
        designators.extend(f"{prefix}{number}" for number in range(start, finish + 1))
    return designators


def _step_library(board, generated_records):
    root = Path(__file__).parent
    manifest_path = root / _MODEL_MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Missing {manifest_path}; run fetch_bom_models.py first"
        )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != "cuflow-easyeda-models-1":
        raise ValueError(f"Unsupported model manifest format in {manifest_path}")

    code_by_designator = {}
    for record in generated_records["bom"]["bom"]:
        if record["vendor"].upper() != "LCSC":
            continue
        designators = _expand_designators(record["parts"])
        if len(designators) != int(record["qty"]):
            raise ValueError(f"BOM quantity mismatch in {record}")
        for designator in designators:
            code_by_designator[designator] = record["code"]

    jlcpcb_pnp = {
        record["Designator"]: record
        for record in generated_records["pnp"]["jlcpcb"]
    }
    parts_by_designator = {
        part.id: part
        for parts in board.parts.values()
        for part in parts
        if part.inBOM
    }
    components = []
    used_codes = set()
    skipped = set()
    for record in generated_records["pnp"]["pnp"]:
        designator = record["Designator"]
        code = code_by_designator.get(designator)
        metadata = manifest["models"].get(code) if code else None
        step_path = (
            manifest_path.parent / metadata["step"]
            if metadata is not None
            else None
        )
        if step_path is None or not step_path.exists():
            skipped.add(designator)
            continue
        components.append({
            "designator": designator,
            "lcsc": code,
            "pnp": record,
            "jlcpcbPnp": jlcpcb_pnp[designator],
            "stepAdjust": parts_by_designator[designator].step_adjust(),
        })
        used_codes.add(code)

    models = {}
    for code in sorted(used_codes):
        metadata = manifest["models"][code]
        step_path = manifest_path.parent / metadata["step"]
        mesh_path = root / _MODEL_MESH_DIRECTORY / f"{code}.mesh.json"
        if not mesh_path.exists():
            raise FileNotFoundError(
                f"Missing {mesh_path}; run 'npm run convert:models' in webviewer/"
            )
        mesh = json.loads(mesh_path.read_text())
        source_hash = hashlib.sha256(step_path.read_bytes()).hexdigest()
        if mesh.get("sourceSha256") != source_hash:
            raise RuntimeError(
                f"{mesh_path} is stale; run 'npm run convert:models' in webviewer/"
            )
        models[code] = {"metadata": metadata, "mesh": mesh}
    return models, components, skipped


def _anchored_model(
        board, scene_name, source_model, mesh_model, rebuild_command,
        flip = False, rotation_adjust = 0, flip_offset = None):
    root = Path(__file__).parent
    source_path = root / source_model
    mesh_path = root / mesh_model
    if not source_path.exists():
        raise FileNotFoundError(f"Missing model {source_path}")
    if not mesh_path.exists():
        raise FileNotFoundError(
            f"Missing {mesh_path}; run '{rebuild_command}'"
        )

    anchor = next(
        (
            part
            for parts in board.parts.values()
            for part in parts
            if part.id == _LCD_DESIGNATOR
        ),
        None,
    )
    if anchor is None:
        raise ValueError(f"Missing model anchor {_LCD_DESIGNATOR}")

    mesh = json.loads(mesh_path.read_text())
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if mesh.get("sourceSha256") != source_hash:
        raise RuntimeError(
            f"{mesh_path} is stale; run '{rebuild_command}'"
        )

    x, y = anchor.center.xy
    return {
        "designator": scene_name,
        "position": [x, y],
        "rotation": (
            anchor.center.dir + anchor.step_adjust() + rotation_adjust
        ),
        "flip": flip,
        "flipOffset": flip_offset,
        "mesh": mesh,
    }


def _lcd_model(board):
    return _anchored_model(
        board,
        _LCD_DESIGNATOR,
        _LCD_STEP_MODEL,
        _LCD_MESH_MODEL,
        f"node webviewer/convert-step.js {_LCD_STEP_MODEL} {_LCD_MESH_MODEL}",
    )


def _bezel_model(board):
    return _anchored_model(
        board,
        "LCD bezel",
        _BEZEL_STL_MODEL,
        _BEZEL_MESH_MODEL,
        "npm --prefix webviewer run convert:bezel",
        flip = True,
        rotation_adjust = 180,
        flip_offset = _BEZEL_CONTACT_Z,
    )


def write(board, filename, generated_records, thickness=1.6):
    """Write ``filename`` without changing any manufacturing layers."""
    part_name = Path(filename).stem
    runtime_path = Path(__file__).with_name("webviewer") / "viewer-runtime.min.js"
    if not runtime_path.exists():
        raise FileNotFoundError(
            f"Missing {runtime_path}; run 'npm install && npm run build' "
            "in webviewer/"
        )

    body = board.body()
    top_solder_mask_openings = board.layers["GTS"].preview().intersection(body)
    bottom_solder_mask_openings = board.layers["GBS"].preview().intersection(body)
    top_silkscreen = (
        board.layers["GTO"]
        .preview()
        .intersection(body)
        .difference(top_solder_mask_openings)
    )
    bottom_silkscreen = (
        board.layers["GBO"]
        .preview()
        .intersection(body)
        .difference(bottom_solder_mask_openings)
    )
    top_solder_paste = board.layers["GTP"].preview().intersection(body)
    bottom_solder_paste = board.layers["GBP"].preview().intersection(body)
    top_copper = board.layers["GTL"].preview().intersection(body)
    bottom_copper = board.layers["GBL"].preview().intersection(body)
    exposed_top_copper = top_copper.intersection(top_solder_mask_openings)
    exposed_bottom_copper = bottom_copper.intersection(bottom_solder_mask_openings)
    masked_top_copper = top_copper.difference(exposed_top_copper)
    masked_bottom_copper = bottom_copper.difference(exposed_bottom_copper)
    step_models, components, skipped = _step_library(board, generated_records)
    lcd_model = _lcd_model(board) if part_name == "spiq_a" else None
    bezel_model = _bezel_model(board) if part_name == "spiq_a" else None
    min_x, min_y, max_x, max_y = body.bounds
    model = {
        "name": part_name,
        "thickness": thickness,
        "center": [(min_x + max_x) / 2, (min_y + max_y) / 2],
        "size": [max_x - min_x, max_y - min_y],
        "polygons": _polygons(body),
        "topCopper": _polygons(top_copper),
        "bottomCopper": _polygons(bottom_copper),
        "maskedTopCopper": _polygons(masked_top_copper),
        "maskedBottomCopper": _polygons(masked_bottom_copper),
        "exposedTopCopper": _polygons(exposed_top_copper),
        "exposedBottomCopper": _polygons(exposed_bottom_copper),
        "topSilkscreen": _polygons(top_silkscreen),
        "bottomSilkscreen": _polygons(bottom_silkscreen),
        "topSolderPaste": _polygons(top_solder_paste),
        "bottomSolderPaste": _polygons(bottom_solder_paste),
        "stepModels": step_models,
        "lcdModel": lcd_model,
        "bezelModel": bezel_model,
        "components": components,
        "unpopulated": sorted(skipped),
    }
    runtime = runtime_path.read_text()
    model_json = json.dumps(model, separators=(",", ":"))
    Path(filename).write_text(_document(runtime, model_json))


def _document(runtime, model_json):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CuFlow board viewer</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
  body {{
    background: radial-gradient(
      circle at 50% 38%,
      #27354b 0%,
      #151d2b 38%,
      #090d15 72%,
      #05070b 100%
    );
    color: #e8edf5;
    font: 13px/1.3 system-ui, sans-serif;
  }}
  #viewer {{ position: fixed; inset: 0; }}
  canvas {{ display: block; width: 100%; height: 100%; touch-action: none; }}
  .toolbar {{
    position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
    display: flex; gap: 6px; padding: 6px; z-index: 2;
    background: rgba(15,19,28,.78); border: 1px solid rgba(255,255,255,.13);
    border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,.3);
    backdrop-filter: blur(12px);
  }}
  button {{
    border: 0; border-radius: 6px; padding: 7px 11px; color: inherit;
    background: rgba(255,255,255,.08); font: inherit; cursor: pointer;
  }}
  button:hover {{ background: rgba(255,255,255,.16); }}
  .layer-control {{
    position: fixed; left: 16px; top: 50%; transform: translateY(-50%);
    display: flex; gap: 8px; align-items: center; z-index: 2;
    padding: 12px 11px;
    background: rgba(15,19,28,.78); border: 1px solid rgba(255,255,255,.13);
    border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,.3);
    backdrop-filter: blur(12px);
  }}
  .layer-slider-track {{ position: relative; width: 22px; height: 240px; }}
  #layer-slider {{
    position: absolute; top: 0; left: 22px; width: 240px; height: 22px;
    margin: 0; transform: rotate(90deg); transform-origin: 0 0;
    accent-color: #d8e4f7; cursor: pointer;
  }}
  .layer-labels {{
    display: grid; grid-template-rows: repeat(6, 1fr); height: 240px;
  }}
  .layer-step {{
    align-self: center; padding: 3px 5px; color: rgba(232,237,245,.58);
    background: transparent; text-align: left; white-space: nowrap;
  }}
  .layer-step:hover {{ color: #e8edf5; background: rgba(255,255,255,.08); }}
  .layer-step.active {{ color: #fff; }}
  .help {{
    position: fixed; left: 16px; bottom: 14px; z-index: 2;
    color: rgba(232,237,245,.62); pointer-events: none;
  }}
  .capture-status {{
    position: fixed; right: 16px; bottom: 14px; z-index: 2;
    padding: 7px 10px; border-radius: 7px;
    color: #e8edf5; background: rgba(15,19,28,.82);
    border: 1px solid rgba(255,255,255,.13);
    opacity: 0; transform: translateY(4px); pointer-events: none;
    transition: opacity .15s ease, transform .15s ease;
  }}
  .capture-status.visible {{ opacity: 1; transform: translateY(0); }}
</style>
</head>
<body>
<main id="viewer" aria-label="Interactive 3D PCB viewer"></main>
<nav class="toolbar" aria-label="Camera views">
  <button id="view-reset" type="button">reset</button>
  <button id="view-top" type="button">top</button>
</nav>
<aside class="layer-control" aria-label="Layer visibility">
  <div class="layer-slider-track">
    <input id="layer-slider" type="range" min="0" max="5" step="1" value="0"
      aria-label="Layer visibility depth">
  </div>
  <div class="layer-labels">
    <button class="layer-step active" type="button" data-layer-level="0">Bezel</button>
    <button class="layer-step" type="button" data-layer-level="1">Components</button>
    <button class="layer-step" type="button" data-layer-level="2">Paste</button>
    <button class="layer-step" type="button" data-layer-level="3">Silkscreen</button>
    <button class="layer-step" type="button" data-layer-level="4">Solder Mask</button>
    <button class="layer-step" type="button" data-layer-level="5">Gold</button>
  </div>
</aside>
<div class="help">Drag or flick to spin board · right-drag to pan · scroll to zoom · S copies screenshot</div>
<div id="capture-status" class="capture-status" role="status" aria-live="polite"></div>
<script>{runtime}</script>
<script>
(() => {{
  const MODEL = {model_json};
  const {{ THREE, OrbitControls, RoomEnvironment }} = window.CuflowViewerRuntime;
  const host = document.getElementById("viewer");
  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(34, 1, 0.5, 1000);
  const renderer = new THREE.WebGLRenderer({{
    antialias: true,
    alpha: true,
    logarithmicDepthBuffer: true,
    preserveDrawingBuffer: true
  }});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  host.appendChild(renderer.domElement);

  const studioEnvironment = new RoomEnvironment();
  const pmremGenerator = new THREE.PMREMGenerator(renderer);
  const environmentTarget = pmremGenerator.fromScene(
    studioEnvironment,
    0,
    0.1,
    100,
    {{ size: 512 }}
  );
  scene.environment = environmentTarget.texture;
  scene.environmentIntensity = 0.25;
  studioEnvironment.dispose();
  pmremGenerator.dispose();

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.screenSpacePanning = true;
  controls.zoomToCursor = true;
  controls.enableRotate = false;
  controls.mouseButtons.LEFT = -1;

  const group = new THREE.Group();
  const [cx, cy] = MODEL.center;
  const visibilityLayers = {{
    traceRelief: new THREE.Group(),
    exposedCopper: new THREE.Group(),
    copper: new THREE.Group(),
    paste: new THREE.Group(),
    silks: new THREE.Group(),
    components: new THREE.Group(),
    bezel: new THREE.Group()
  }};
  Object.entries(visibilityLayers).forEach(([name, layer]) => {{
    layer.name = name;
    group.add(layer);
  }});
  const material = new THREE.MeshPhysicalMaterial({{
    color: 0x050608,
    roughness: 0.08,
    metalness: 0,
    envMapIntensity: 0.8,
    clearcoat: 1,
    clearcoatRoughness: 0.003,
    side: THREE.DoubleSide
  }});
  const silkscreenMaterial = new THREE.MeshPhysicalMaterial({{
    color: 0xf4f3ec,
    roughness: 0.52,
    metalness: 0,
    envMapIntensity: 1.6,
    clearcoat: 0.08,
    side: THREE.DoubleSide
  }});
  const exposedGoldMaterial = new THREE.MeshPhysicalMaterial({{
    color: 0xe0a11a,
    metalness: 0.96,
    roughness: 0.18,
    envMapIntensity: 4,
    clearcoat: 0.2,
    clearcoatRoughness: 0.12,
    side: THREE.DoubleSide
  }});
  const solderPasteMaterial = new THREE.MeshPhysicalMaterial({{
    color: 0xb8bec5,
    metalness: 0.96,
    roughness: 0.14,
    envMapIntensity: 4,
    clearcoat: 0.3,
    clearcoatRoughness: 0.07,
    side: THREE.DoubleSide
  }});
  const copperThickness = 0.050;
  const surfaceGap = 0.002;
  const topCopperBase = MODEL.thickness / 2 + surfaceGap;
  const bottomCopperBase = -MODEL.thickness / 2 - surfaceGap - copperThickness;
  const topSurfaceBase = topCopperBase + copperThickness + surfaceGap;
  const silkscreenThickness = 0.018;
  const pasteThickness = 0.05;
  const topSilkscreenBase = topSurfaceBase;
  const bottomSilkscreenBase = (
    bottomCopperBase - surfaceGap - silkscreenThickness
  );
  const topPasteBase = topSurfaceBase;
  const bottomPasteBase = bottomCopperBase - surfaceGap - pasteThickness;

  function pathFrom(points, PathType) {{
    const path = new PathType();
    points.forEach(([x, y], index) => {{
      const px = x - cx;
      const py = y - cy;
      if (index === 0) path.moveTo(px, py);
      else path.lineTo(px, py);
    }});
    path.closePath();
    return path;
  }}

  function shapesFrom(polygons) {{
    return polygons.map((polygon) => {{
      const shape = pathFrom(polygon.outer, THREE.Shape);
      polygon.holes.forEach((hole) => shape.holes.push(pathFrom(hole, THREE.Path)));
      return shape;
    }});
  }}

  function extrudedLayer(polygons, depth, y, layerMaterial, parent = group) {{
    if (polygons.length === 0) return;
    const geometry = new THREE.ExtrudeGeometry(shapesFrom(polygons), {{
      depth,
      bevelEnabled: false,
      curveSegments: 1
    }});
    geometry.rotateX(-Math.PI / 2);
    geometry.translate(0, y, 0);
    geometry.computeVertexNormals();
    parent.add(new THREE.Mesh(geometry, layerMaterial));
  }}

  function decodeTypedArray(encoded, Type) {{
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {{
      bytes[index] = binary.charCodeAt(index);
    }}
    return new Type(bytes.buffer);
  }}

  const stepMaterialCache = new Map();
  function stepMaterial(rgb) {{
    const key = rgb.join(",");
    if (stepMaterialCache.has(key)) return stepMaterialCache.get(key);
    const high = Math.max(...rgb);
    const low = Math.min(...rgb);
    const looksMetallic = high > 0.3 && high < 0.9 && high - low < 0.14;
    const color = new THREE.Color().setRGB(...rgb, THREE.SRGBColorSpace);
    const surface = new THREE.MeshPhysicalMaterial({{
      color,
      metalness: looksMetallic ? 0.72 : 0,
      roughness: looksMetallic ? 0.3 : (high < 0.2 ? 0.34 : 0.46),
      envMapIntensity: looksMetallic ? 3.2 : (high < 0.2 ? 0.8 : 2.2),
      clearcoat: looksMetallic ? 0.08 : (high < 0.2 ? 0.18 : 0.03),
      clearcoatRoughness: 0.35,
      side: THREE.DoubleSide
    }});
    stepMaterialCache.set(key, surface);
    return surface;
  }}

  function buildStepTemplate(definition) {{
    const modelData = definition.mesh;
    const component = new THREE.Group();
    component.name = modelData.source;
    const modelCenterX = (modelData.bounds.min[0] + modelData.bounds.max[0]) / 2;
    const modelCenterY = (modelData.bounds.min[1] + modelData.bounds.max[1]) / 2;
    const modelFloorZ = modelData.bounds.min[2];
    modelData.meshes.forEach((sourceMesh) => {{
      const geometry = new THREE.BufferGeometry();
      geometry.name = sourceMesh.name;
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(decodeTypedArray(sourceMesh.positions, Float32Array), 3)
      );
      if (sourceMesh.normals) {{
        geometry.setAttribute(
          "normal",
          new THREE.BufferAttribute(decodeTypedArray(sourceMesh.normals, Float32Array), 3)
        );
      }} else {{
        geometry.computeVertexNormals();
      }}
      geometry.setIndex(
        new THREE.BufferAttribute(decodeTypedArray(sourceMesh.indices, Uint32Array), 1)
      );
      // Match easyeda2kicad's WRL normalization: center the raw model in XY
      // and place its lowest Z point on the footprint plane. Then bake the
      // STEP Z-up to viewer Y-up conversion into the mesh.
      geometry.translate(-modelCenterX, -modelCenterY, -modelFloorZ);
      geometry.rotateX(-Math.PI / 2);
      sourceMesh.groups.forEach((entry) => {{
        geometry.addGroup(entry.start, entry.count, entry.material);
      }});
      const materials = sourceMesh.colors.map(stepMaterial);
      const mesh = new THREE.Mesh(
        geometry,
        materials.length === 1 ? materials[0] : materials
      );
      mesh.name = sourceMesh.name;
      component.add(mesh);
    }});
    return component;
  }}

  const stepTemplates = new Map(
    Object.entries(MODEL.stepModels).map(([code, definition]) => [
      code,
      buildStepTemplate(definition)
    ])
  );

  function placeComponent(componentData) {{
    const record = componentData.pnp;
    if (record.Layer !== "Top" || componentData.jlcpcbPnp.Layer !== "Top") {{
      throw new Error(`Unsupported component side for ${{componentData.designator}}`);
    }}
    const x = Number.parseFloat(componentData.jlcpcbPnp["Mid X"]);
    const y = Number.parseFloat(componentData.jlcpcbPnp["Mid Y"]);
    const definition = MODEL.stepModels[componentData.lcsc];
    const metadata = definition.metadata;
    const [rotationX, rotationY, rotationZ] = metadata.rotation;
    if (Math.abs(rotationX) > 1e-6 || Math.abs(rotationY) > 1e-6) {{
      throw new Error(`Unsupported tilted EasyEDA model: ${{componentData.lcsc}}`);
    }}

    const model = stepTemplates.get(componentData.lcsc).clone(true);
    const [translateX, translateY, translateZ] = metadata.translation;
    model.rotation.y = -THREE.MathUtils.degToRad(rotationZ);
    model.position.set(translateX, translateZ, -translateY);

    const component = new THREE.Group();
    component.name = componentData.designator;
    component.add(model);
    const assemblyRotation = (
      360 - Number(componentData.jlcpcbPnp.Rotation)
    ) % 360;
    component.rotation.y = -THREE.MathUtils.degToRad(
      assemblyRotation + componentData.stepAdjust
    );
    component.position.set(
      x - cx,
      topSurfaceBase,
      -(y - cy)
    );
    component.userData = componentData;
    visibilityLayers.components.add(component);
  }}

  function placeAccessory(accessoryData, parent) {{
    const model = buildStepTemplate(accessoryData);
    if (accessoryData.flip) {{
      model.rotation.x = Math.PI;
      model.position.y = accessoryData.flipOffset ?? (
        accessoryData.mesh.bounds.max[2] - accessoryData.mesh.bounds.min[2]
      );
    }}
    const accessory = new THREE.Group();
    accessory.name = accessoryData.designator;
    accessory.add(model);
    accessory.rotation.y = -THREE.MathUtils.degToRad(accessoryData.rotation);
    accessory.position.set(
      accessoryData.position[0] - cx,
      topSurfaceBase,
      -(accessoryData.position[1] - cy)
    );
    accessory.userData = accessoryData;
    parent.add(accessory);
  }}

  extrudedLayer(
    MODEL.polygons,
    MODEL.thickness,
    -MODEL.thickness / 2,
    material
  );
  extrudedLayer(
    MODEL.maskedTopCopper ?? MODEL.topCopper ?? [],
    copperThickness,
    topCopperBase,
    material,
    visibilityLayers.traceRelief
  );
  extrudedLayer(
    MODEL.maskedBottomCopper ?? MODEL.bottomCopper ?? [],
    copperThickness,
    bottomCopperBase,
    material,
    visibilityLayers.traceRelief
  );
  extrudedLayer(
    MODEL.exposedTopCopper,
    copperThickness,
    topCopperBase,
    exposedGoldMaterial,
    visibilityLayers.exposedCopper
  );
  extrudedLayer(
    MODEL.exposedBottomCopper,
    copperThickness,
    bottomCopperBase,
    exposedGoldMaterial,
    visibilityLayers.exposedCopper
  );
  extrudedLayer(
    MODEL.topCopper ?? MODEL.exposedTopCopper,
    copperThickness,
    topCopperBase,
    exposedGoldMaterial,
    visibilityLayers.copper
  );
  extrudedLayer(
    MODEL.bottomCopper ?? MODEL.exposedBottomCopper,
    copperThickness,
    bottomCopperBase,
    exposedGoldMaterial,
    visibilityLayers.copper
  );
  extrudedLayer(
    MODEL.topSilkscreen,
    silkscreenThickness,
    topSilkscreenBase,
    silkscreenMaterial,
    visibilityLayers.silks
  );
  extrudedLayer(
    MODEL.bottomSilkscreen,
    silkscreenThickness,
    bottomSilkscreenBase,
    silkscreenMaterial,
    visibilityLayers.silks
  );
  extrudedLayer(
    MODEL.topSolderPaste,
    pasteThickness,
    topPasteBase,
    solderPasteMaterial,
    visibilityLayers.paste
  );
  extrudedLayer(
    MODEL.bottomSolderPaste ?? [],
    pasteThickness,
    bottomPasteBase,
    solderPasteMaterial,
    visibilityLayers.paste
  );
  if (MODEL.lcdModel) {{
    placeAccessory(MODEL.lcdModel, visibilityLayers.components);
  }}
  if (MODEL.bezelModel) {{
    placeAccessory(MODEL.bezelModel, visibilityLayers.bezel);
  }}
  MODEL.components.forEach(placeComponent);
  scene.add(group);

  scene.add(new THREE.HemisphereLight(0xdce8ff, 0x17120c, 1.7));
  const key = new THREE.DirectionalLight(0xffffff, 2.6);
  key.position.set(-45, 75, -35);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x77aaff, 1.2);
  rim.position.set(55, 25, 45);
  scene.add(rim);
  const cameraFill = new THREE.DirectionalLight(0xdfe9ff, 2.2);
  cameraFill.position.set(18, 85, 88);
  scene.add(cameraFill);

  const span = Math.max(...MODEL.size);
  const dramaticPosition = new THREE.Vector3(
    span * 0.72,
    span * 0.82,
    span * 0.92
  );
  let spinYaw = 0;
  let spinPitch = 0;

  function stopSpin() {{
    spinYaw = 0;
    spinPitch = 0;
  }}

  function resetView() {{
    stopSpin();
    group.quaternion.identity();
    camera.up.set(0, 1, 0);
    camera.position.copy(dramaticPosition);
    controls.target.set(0, 0, 0);
    controls.update();
  }}

  function topView() {{
    stopSpin();
    group.quaternion.identity();
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const horizontalFov = 2 * Math.atan(
      Math.tan(verticalFov / 2) * camera.aspect
    );
    const heightDistance = MODEL.size[1] / (2 * Math.tan(verticalFov / 2));
    const widthDistance = MODEL.size[0] / (2 * Math.tan(horizontalFov / 2));
    const distance = Math.max(heightDistance, widthDistance) * 1.12;
    camera.up.set(0, 0, -1);
    camera.position.set(0, distance, 0);
    controls.target.set(0, 0, 0);
    controls.update();
  }}

  document.getElementById("view-reset").onclick = resetView;
  document.getElementById("view-top").onclick = topView;
  resetView();

  const layerSlider = document.getElementById("layer-slider");
  const layerSteps = [...document.querySelectorAll(".layer-step")];
  const layerNames = [
    "Bezel",
    "Components",
    "Paste",
    "Silkscreen",
    "Solder Mask",
    "Gold"
  ];

  function setLayerLevel(requestedLevel) {{
    const level = THREE.MathUtils.clamp(Number(requestedLevel), 0, 5);
    visibilityLayers.bezel.visible = level <= 0;
    visibilityLayers.components.visible = level <= 1;
    visibilityLayers.paste.visible = level <= 2;
    visibilityLayers.silks.visible = level <= 3;
    visibilityLayers.traceRelief.visible = level < 5;
    visibilityLayers.exposedCopper.visible = level < 5;
    visibilityLayers.copper.visible = level === 5;
    layerSlider.value = String(level);
    layerSlider.setAttribute(
      "aria-valuetext",
      layerNames[level] + (level === 0 ? ": all layers visible" : "")
    );
    layerSteps.forEach((step, index) => {{
      step.classList.toggle("active", index === level);
    }});
  }}

  layerSlider.addEventListener("input", () => setLayerLevel(layerSlider.value));
  layerSteps.forEach((step) => {{
    step.addEventListener("click", () => setLayerLevel(step.dataset.layerLevel));
  }});
  setLayerLevel(0);

  let rotatingBoard = false;
  let pointerX = 0;
  let pointerY = 0;
  let lastPointerTime = 0;
  let lastFrameTime = performance.now();
  const yaw = new THREE.Quaternion();
  const pitch = new THREE.Quaternion();
  const worldUp = new THREE.Vector3(0, 1, 0);
  const cameraRight = new THREE.Vector3();
  const rotationPerPixel = 0.008;
  const maximumSpinSpeed = 6;
  const spinDamping = 0.22;

  function rotateBoard(yawAngle, pitchAngle) {{
    cameraRight.set(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
    yaw.setFromAxisAngle(worldUp, yawAngle);
    pitch.setFromAxisAngle(cameraRight, pitchAngle);
    group.quaternion.premultiply(yaw).premultiply(pitch).normalize();
  }}

  renderer.domElement.addEventListener("pointerdown", (event) => {{
    if (event.button !== 0 || !event.isPrimary) return;
    stopSpin();
    rotatingBoard = true;
    pointerX = event.clientX;
    pointerY = event.clientY;
    lastPointerTime = event.timeStamp;
    renderer.domElement.setPointerCapture(event.pointerId);
  }});
  renderer.domElement.addEventListener("pointermove", (event) => {{
    if (!rotatingBoard || !event.isPrimary) return;
    const dx = event.clientX - pointerX;
    const dy = event.clientY - pointerY;
    const elapsed = Math.max((event.timeStamp - lastPointerTime) / 1000, 1 / 240);
    pointerX = event.clientX;
    pointerY = event.clientY;
    lastPointerTime = event.timeStamp;

    const yawAngle = dx * rotationPerPixel;
    const pitchAngle = dy * rotationPerPixel;
    const blend = Math.min(1, elapsed * 24);
    spinYaw = THREE.MathUtils.lerp(
      spinYaw,
      THREE.MathUtils.clamp(yawAngle / elapsed, -maximumSpinSpeed, maximumSpinSpeed),
      blend
    );
    spinPitch = THREE.MathUtils.lerp(
      spinPitch,
      THREE.MathUtils.clamp(pitchAngle / elapsed, -maximumSpinSpeed, maximumSpinSpeed),
      blend
    );
    rotateBoard(yawAngle, pitchAngle);
  }});
  function stopBoardRotation(event, keepSpinning) {{
    if (!rotatingBoard || !event.isPrimary) return;
    rotatingBoard = false;
    if (!keepSpinning || event.timeStamp - lastPointerTime > 100) stopSpin();
    if (renderer.domElement.hasPointerCapture(event.pointerId)) {{
      renderer.domElement.releasePointerCapture(event.pointerId);
    }}
  }}
  renderer.domElement.addEventListener(
    "pointerup", (event) => stopBoardRotation(event, true)
  );
  renderer.domElement.addEventListener(
    "pointercancel", (event) => stopBoardRotation(event, false)
  );

  function resize() {{
    const width = host.clientWidth;
    const height = host.clientHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
  }}
  window.addEventListener("resize", resize);
  resize();

  const captureStatus = document.getElementById("capture-status");
  let captureStatusTimer;
  function showCaptureStatus(message) {{
    captureStatus.textContent = message;
    captureStatus.classList.add("visible");
    clearTimeout(captureStatusTimer);
    captureStatusTimer = setTimeout(() => {{
      captureStatus.classList.remove("visible");
    }}, 1800);
  }}

  function screenshotBlob() {{
    renderer.render(scene, camera);
    const source = renderer.domElement;
    const output = document.createElement("canvas");
    output.width = source.width;
    output.height = source.height;
    const context = output.getContext("2d");
    const centerX = output.width * 0.5;
    const centerY = output.height * 0.38;
    const radius = Math.max(
      Math.hypot(centerX, centerY),
      Math.hypot(output.width - centerX, centerY),
      Math.hypot(centerX, output.height - centerY),
      Math.hypot(output.width - centerX, output.height - centerY)
    );
    const background = context.createRadialGradient(
      centerX, centerY, 0, centerX, centerY, radius
    );
    background.addColorStop(0, "#27354b");
    background.addColorStop(0.38, "#151d2b");
    background.addColorStop(0.72, "#090d15");
    background.addColorStop(1, "#05070b");
    context.fillStyle = background;
    context.fillRect(0, 0, output.width, output.height);
    context.drawImage(source, 0, 0);
    return new Promise((resolve, reject) => {{
      output.toBlob((blob) => {{
        if (blob) resolve(blob);
        else reject(new Error("PNG capture failed"));
      }}, "image/png");
    }});
  }}

  async function copyScreenshot() {{
    if (!navigator.clipboard?.write || !window.ClipboardItem) {{
      showCaptureStatus("Image clipboard is unavailable");
      return;
    }}
    try {{
      const blob = screenshotBlob();
      await navigator.clipboard.write([
        new ClipboardItem({{ "image/png": blob }})
      ]);
      showCaptureStatus("Screenshot copied");
    }} catch (error) {{
      console.error("Screenshot copy failed", error);
      showCaptureStatus("Could not copy screenshot");
    }}
  }}

  window.addEventListener("keydown", (event) => {{
    const target = event.target;
    const isTextInput = target instanceof HTMLInputElement &&
      !["button", "checkbox", "radio", "range"].includes(target.type);
    const isEditing = isTextInput || target instanceof HTMLTextAreaElement ||
      target?.isContentEditable;
    if (isEditing || event.metaKey || event.ctrlKey || event.altKey ||
        event.key.toLowerCase() !== "s") return;
    event.preventDefault();
    copyScreenshot();
  }});

  renderer.setAnimationLoop((frameTime) => {{
    const elapsed = Math.min((frameTime - lastFrameTime) / 1000, 0.05);
    lastFrameTime = frameTime;
    if (!rotatingBoard &&
        (Math.abs(spinYaw) > 0.001 || Math.abs(spinPitch) > 0.001)) {{
      rotateBoard(spinYaw * elapsed, spinPitch * elapsed);
      const decay = Math.exp(-spinDamping * elapsed);
      spinYaw *= decay;
      spinPitch *= decay;
    }}
    controls.update();
    renderer.render(scene, camera);
  }});
}})();
</script>
</body>
</html>
"""
