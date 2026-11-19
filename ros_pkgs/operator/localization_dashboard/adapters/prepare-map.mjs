// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Deterministic spatial preview. --activate changes the dashboard's local preview only.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const args = process.argv.slice(2);
const flags = ["--activate", "--require-manifest"];
const activate = args.includes("--activate");
const requireManifest = args.includes("--require-manifest");
const [source, requested] = args.filter((arg) => !flags.includes(arg));
if (!source)
  throw Error("Usage: node adapters/prepare-map.mjs source.pcd [preview.pcd] [--activate] [--require-manifest]");
const raw = fs.readFileSync(source);
const digest = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const hash = digest(raw);
// The release manifest next to the source is trusted only when it names this exact PCD.
const sourceManifestPath = path.join(path.dirname(path.resolve(source)), "manifest.json");
const manifestBytes = fs.existsSync(sourceManifestPath) ? fs.readFileSync(sourceManifestPath) : undefined;
const sourceManifest = manifestBytes && JSON.parse(manifestBytes.toString("utf8"));
const manifestMatches = sourceManifest?.reference_sha256 === hash;
if (requireManifest && !manifestMatches)
  throw Error(`manifest.json does not describe ${path.basename(source)} (sha256 ${hash.slice(0, 12)}); release may be in progress`);
const target = requested ?? (activate ? `public/map-${hash.slice(0, 12)}.pcd` : "public/prior-preview.pcd");
const absoluteTarget = path.resolve(target);
if (absoluteTarget === path.resolve(source)) throw Error("Input and output must differ");
if (activate && (path.dirname(absoluteTarget) !== path.resolve("public") ||
    !/^[a-zA-Z0-9._-]+\.pcd$/.test(path.basename(target)))) throw Error("Activation requires a PCD filename in public/");

const header = raw.subarray(0, 65536).toString("latin1").match(/^([\s\S]*?^DATA binary\r?\n)/m)?.[1];
if (!header) throw Error("Expected uncompressed binary PCD");
const rows = Object.fromEntries(header.trim().split(/\r?\n/).filter((line) => !line.startsWith("#")).map((line) => {
  const [key, ...values] = line.trim().split(/\s+/);
  return [key, values];
}));
let stride = 0;
const fields = new Map();
rows.FIELDS.forEach((name, i) => {
  const width = Number(rows.SIZE[i]);
  const count = Number(rows.COUNT?.[i] ?? 1);
  fields.set(name, { type: rows.TYPE[i], width, count, offset: stride });
  stride += width * count;
});
const n = Number(rows.POINTS[0]);
if (!Number.isSafeInteger(n) || n <= 0 || header.length + n * stride !== raw.length)
  throw Error("PCD payload length differs from header");
const xyz = ["x", "y", "z"].map((name) => {
  const f = fields.get(name);
  if (!f || f.width !== 4 || f.count !== 1 || f.type !== "F") throw Error("Expected scalar float32 XYZ");
  return f.offset;
});
const label = fields.get("label");
if (label && (label.count !== 1 || label.width !== 4 || !["I", "U"].includes(label.type)))
  throw Error("Expected scalar int32/uint32 label");

const budget = 80000;
let voxel = 0.1;
let selected;
for (;;) {
  selected = new Map();
  for (let i = 0, offset = header.length; i < n; i++, offset += stride) {
    const x = raw.readFloatLE(offset + xyz[0]);
    const y = raw.readFloatLE(offset + xyz[1]);
    const z = raw.readFloatLE(offset + xyz[2]);
    if (![x, y, z].every(Number.isFinite)) continue;
    const id = label ? raw.readUInt32LE(offset + label.offset) : 0;
    const key = `${Math.floor(x / voxel)},${Math.floor(y / voxel)},${Math.floor(z / voxel)},${id}`;
    if (!selected.has(key)) selected.set(key, offset);
    if (selected.size > budget) break;
  }
  if (selected.size <= budget) break;
  voxel *= 1.4;
}
if (!selected.size) throw Error("No finite XYZ points");
const size = selected.size;
const outputHeader = [
  "VERSION 0.7", label ? "FIELDS x y z label" : "FIELDS x y z",
  label ? "SIZE 4 4 4 4" : "SIZE 4 4 4", label ? "TYPE F F F U" : "TYPE F F F",
  label ? "COUNT 1 1 1 1" : "COUNT 1 1 1", `WIDTH ${size}`, "HEIGHT 1",
  "VIEWPOINT 0 0 0 1 0 0 0", `POINTS ${size}`, "DATA binary", "",
].join("\n");
const output = Buffer.alloc(Buffer.byteLength(outputHeader) + size * (label ? 16 : 12));
let offset = output.write(outputHeader);
const counts = {};
for (const index of selected.values()) {
  for (const field of xyz) offset = output.writeFloatLE(raw.readFloatLE(index + field), offset);
  if (label) {
    const id = raw.readUInt32LE(index + label.offset);
    offset = output.writeUInt32LE(id, offset);
    counts[id] = (counts[id] ?? 0) + 1;
  }
}
const reviewCandidate = manifestMatches && sourceManifest?.status === "review_candidate";
const meta = {
  version: hash.slice(0, 12) + (reviewCandidate ? " · 분류 검토본" : ""), file: path.basename(target), source: path.basename(source),
  source_sha256: hash, preview_sha256: digest(output), source_points: n, preview_points: size,
  method: "one measured point per occupied 3D voxel and label", voxel_m: voxel,
  ...(label && { class_counts: counts }),
  // Release review state is copied verbatim; the dashboard never upgrades it.
  ...(manifestMatches && {
    review_status: String(sourceManifest.status ?? "unknown"),
    ...(sourceManifest.reason && { review_reason: String(sourceManifest.reason) }),
    ...(sourceManifest.frame && { declared_frame: String(sourceManifest.frame) }),
    manifest_sha256: digest(manifestBytes),
  }),
};
fs.mkdirSync(path.dirname(absoluteTarget), { recursive: true });
if (fs.existsSync(absoluteTarget)) {
  if (!fs.readFileSync(absoluteTarget).equals(output)) throw Error("Output exists with different contents: " + target);
} else fs.writeFileSync(absoluteTarget, output, { flag: "wx" });
const json = JSON.stringify(meta, null, 2) + "\n";
fs.writeFileSync(absoluteTarget + ".json", json);
if (activate) {
  const manifest = path.resolve("public/reference-map.json");
  const temp = manifest + "." + process.pid;
  fs.writeFileSync(temp, json, { flag: "wx" });
  fs.renameSync(temp, manifest);
}
console.log(json);
