const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const occtImport = require("occt-import-js")();

function usage() {
  console.error("Usage: node convert-step.js input.step output.mesh.json");
  process.exit(2);
}

function encodeTypedArray(Type, values) {
  const typed = Type.from(values);
  return Buffer.from(typed.buffer, typed.byteOffset, typed.byteLength).toString("base64");
}

function colorKey(color) {
  return color.map((channel) => channel.toFixed(7)).join(",");
}

function materialGroups(mesh) {
  const defaultColor = mesh.color || [0.8, 0.8, 0.8];
  const colors = [];
  const colorIndices = new Map();
  const groups = [];

  function materialIndex(color) {
    const key = colorKey(color);
    if (!colorIndices.has(key)) {
      colorIndices.set(key, colors.length);
      colors.push(color.map((channel) => Math.round(channel * 1e7) / 1e7));
    }
    return colorIndices.get(key);
  }

  function addGroup(firstTriangle, lastTriangle, color) {
    if (lastTriangle <= firstTriangle) return;
    const material = materialIndex(color);
    const start = firstTriangle * 3;
    const count = (lastTriangle - firstTriangle) * 3;
    const previous = groups.at(-1);
    if (previous && previous.material === material && previous.start + previous.count === start) {
      previous.count += count;
    } else {
      groups.push({ start, count, material });
    }
  }

  const faces = (mesh.brep_faces || []).slice().sort((a, b) => a.first - b.first);
  const triangleCount = mesh.index.array.length / 3;
  let triangle = 0;
  for (const face of faces) {
    addGroup(triangle, face.first, defaultColor);
    addGroup(face.first, face.last + 1, face.color || defaultColor);
    triangle = face.last + 1;
  }
  addGroup(triangle, triangleCount, defaultColor);

  if (groups.length === 0) {
    addGroup(0, triangleCount, defaultColor);
  }
  return { colors, groups };
}

function boundsOf(meshes) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const mesh of meshes) {
    const positions = mesh.attributes.position.array;
    for (let offset = 0; offset < positions.length; offset += 3) {
      for (let axis = 0; axis < 3; axis += 1) {
        min[axis] = Math.min(min[axis], positions[offset + axis]);
        max[axis] = Math.max(max[axis], positions[offset + axis]);
      }
    }
  }
  return { min, max };
}

async function convertStep(inputPath, destinationPath) {
  const sourcePath = path.resolve(inputPath);
  const outputPath = path.resolve(destinationPath);
  const source = fs.readFileSync(sourcePath);
  const occt = await occtImport;
  const result = occt.ReadStepFile(source, {
    linearUnit: "millimeter",
    linearDeflectionType: "absolute_value",
    linearDeflection: 0.03,
    angularDeflection: 0.3,
  });
  if (!result.success) {
    throw new Error(`OpenCascade could not import ${sourcePath}`);
  }

  const meshes = result.meshes.map((mesh, index) => {
    const { colors, groups } = materialGroups(mesh);
    return {
      name: mesh.name || `mesh-${index}`,
      positions: encodeTypedArray(Float32Array, mesh.attributes.position.array),
      normals: mesh.attributes.normal
        ? encodeTypedArray(Float32Array, mesh.attributes.normal.array)
        : null,
      indices: encodeTypedArray(Uint32Array, mesh.index.array),
      colors,
      groups,
    };
  });
  const output = {
    format: "cuflow-step-mesh-1",
    source: path.basename(sourcePath),
    sourceSha256: crypto.createHash("sha256").update(source).digest("hex"),
    units: "millimeter",
    bounds: boundsOf(result.meshes),
    meshes,
  };

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(output)}\n`);
  const triangles = result.meshes.reduce(
    (count, mesh) => count + mesh.index.array.length / 3,
    0,
  );
  console.log(
    `Converted ${path.basename(sourcePath)}: ${meshes.length} meshes, ` +
      `${triangles} triangles -> ${path.relative(process.cwd(), outputPath)}`,
  );
  return output;
}

async function main() {
  if (process.argv.length !== 4) usage();
  await convertStep(process.argv[2], process.argv[3]);
}

module.exports = { convertStep };

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
