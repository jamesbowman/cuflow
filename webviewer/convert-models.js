const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { convertStep } = require("./convert-step.js");

function sourceHash(sourcePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(sourcePath)).digest("hex");
}

async function main() {
  if (process.argv.length !== 4) {
    console.error("Usage: node convert-models.js models.json output-directory");
    process.exit(2);
  }
  const manifestPath = path.resolve(process.argv[2]);
  const sourceDirectory = path.dirname(manifestPath);
  const outputDirectory = path.resolve(process.argv[3]);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  if (manifest.format !== "cuflow-easyeda-models-1") {
    throw new Error(`Unsupported model manifest format in ${manifestPath}`);
  }

  let converted = 0;
  let current = 0;
  const entries = Object.entries(manifest.models).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  for (const [lcscCode, metadata] of entries) {
    const sourcePath = path.join(sourceDirectory, metadata.step);
    const outputPath = path.join(outputDirectory, `${lcscCode}.mesh.json`);
    const hash = sourceHash(sourcePath);
    if (fs.existsSync(outputPath)) {
      const cached = JSON.parse(fs.readFileSync(outputPath, "utf8"));
      if (cached.sourceSha256 === hash) {
        current += 1;
        continue;
      }
    }
    await convertStep(sourcePath, outputPath);
    converted += 1;
  }
  console.log(
    `Model mesh cache ready: ${converted} converted, ${current} current, ` +
      `${entries.length} total`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
