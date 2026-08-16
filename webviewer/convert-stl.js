const crypto = require("crypto");
const fs = require("fs");
const path = require("path");


function usage() {
  console.error(
    "Usage: node convert-stl.js input.stl output.mesh.json [RRGGBB]",
  );
  process.exit(2);
}


function encodeTypedArray(Type, values) {
  const typed = Type.from(values);
  return Buffer.from(
    typed.buffer,
    typed.byteOffset,
    typed.byteLength,
  ).toString("base64");
}


function parseColor(value = "808080") {
  const match = value.match(/^#?([0-9a-f]{6})$/i);
  if (!match) {
    throw new Error(`Invalid STL color '${value}'; expected RRGGBB`);
  }
  const packed = Number.parseInt(match[1], 16);
  return [
    (packed >> 16) / 255,
    ((packed >> 8) & 0xff) / 255,
    (packed & 0xff) / 255,
  ];
}


function triangleNormal(vertices) {
  const [a, b, c] = vertices;
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  return [
    ab[1] * ac[2] - ab[2] * ac[1],
    ab[2] * ac[0] - ab[0] * ac[2],
    ab[0] * ac[1] - ab[1] * ac[0],
  ];
}


function normalized(normal, vertices) {
  let candidate = normal;
  let length = Math.hypot(...candidate);
  if (!Number.isFinite(length) || length < 1e-12) {
    candidate = triangleNormal(vertices);
    length = Math.hypot(...candidate);
  }
  if (!Number.isFinite(length) || length < 1e-12) {
    return [0, 0, 1];
  }
  return candidate.map((coordinate) => coordinate / length);
}


function meshBuilder() {
  const positions = [];
  const normals = [];
  const indices = [];
  const bounds = {
    min: [Infinity, Infinity, Infinity],
    max: [-Infinity, -Infinity, -Infinity],
  };

  function addTriangle(normal, vertices) {
    if (vertices.length !== 3) {
      throw new Error("STL facet does not contain exactly three vertices");
    }
    const faceNormal = normalized(normal, vertices);
    for (const vertex of vertices) {
      if (vertex.length !== 3 || vertex.some((value) => !Number.isFinite(value))) {
        throw new Error("STL contains an invalid vertex");
      }
      const index = positions.length / 3;
      indices.push(index);
      positions.push(...vertex);
      normals.push(...faceNormal);
      for (let axis = 0; axis < 3; axis += 1) {
        bounds.min[axis] = Math.min(bounds.min[axis], vertex[axis]);
        bounds.max[axis] = Math.max(bounds.max[axis], vertex[axis]);
      }
    }
  }

  return { positions, normals, indices, bounds, addTriangle };
}


function isBinaryStl(source) {
  if (source.length < 84) return false;
  const triangleCount = source.readUInt32LE(80);
  return 84 + 50 * triangleCount === source.length;
}


function parseBinaryStl(source) {
  const mesh = meshBuilder();
  const triangleCount = source.readUInt32LE(80);
  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    const offset = 84 + 50 * triangle;
    const vector = (start) => [
      source.readFloatLE(start),
      source.readFloatLE(start + 4),
      source.readFloatLE(start + 8),
    ];
    mesh.addTriangle(
      vector(offset),
      [vector(offset + 12), vector(offset + 24), vector(offset + 36)],
    );
  }
  return mesh;
}


function parseAsciiStl(source) {
  const mesh = meshBuilder();
  let normal = [0, 0, 0];
  let vertices = [];
  for (const sourceLine of source.toString("utf8").split(/\r?\n/)) {
    const line = sourceLine.trim();
    let match = line.match(
      /^facet\s+normal\s+(\S+)\s+(\S+)\s+(\S+)$/i,
    );
    if (match) {
      normal = match.slice(1).map(Number);
      vertices = [];
      continue;
    }
    match = line.match(/^vertex\s+(\S+)\s+(\S+)\s+(\S+)$/i);
    if (match) {
      vertices.push(match.slice(1).map(Number));
      continue;
    }
    if (/^endfacet$/i.test(line)) {
      mesh.addTriangle(normal, vertices);
      vertices = [];
    }
  }
  return mesh;
}


function convertStl(inputPath, outputPath, colorValue) {
  const sourcePath = path.resolve(inputPath);
  const destinationPath = path.resolve(outputPath);
  const source = fs.readFileSync(sourcePath);
  const mesh = isBinaryStl(source)
    ? parseBinaryStl(source)
    : parseAsciiStl(source);
  if (mesh.indices.length === 0) {
    throw new Error(`No triangles found in ${sourcePath}`);
  }

  const color = parseColor(colorValue);
  const output = {
    format: "cuflow-stl-mesh-1",
    source: path.basename(sourcePath),
    sourceSha256: crypto.createHash("sha256").update(source).digest("hex"),
    units: "millimeter",
    bounds: mesh.bounds,
    meshes: [{
      name: path.basename(sourcePath),
      positions: encodeTypedArray(Float32Array, mesh.positions),
      normals: encodeTypedArray(Float32Array, mesh.normals),
      indices: encodeTypedArray(Uint32Array, mesh.indices),
      colors: [color],
      groups: [{ start: 0, count: mesh.indices.length, material: 0 }],
    }],
  };

  fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
  fs.writeFileSync(destinationPath, `${JSON.stringify(output)}\n`);
  console.log(
    `Converted ${path.basename(sourcePath)}: ${mesh.indices.length / 3} ` +
    `triangles -> ${path.relative(process.cwd(), destinationPath)}`,
  );
  return output;
}


function main() {
  if (process.argv.length < 4 || process.argv.length > 5) usage();
  convertStl(process.argv[2], process.argv[3], process.argv[4]);
}


module.exports = { convertStl };

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error);
    process.exit(1);
  }
}
