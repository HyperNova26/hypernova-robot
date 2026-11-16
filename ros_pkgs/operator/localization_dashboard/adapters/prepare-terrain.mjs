// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Decimated display mesh of the MuJoCo terrain heightfields. Reads the terrain package only.
// Usage: node adapters/prepare-terrain.mjs path/to/terrain/scene [--stride 4]
// Output: public/terrain-<scene sha12>.bin (float32 xyz, then uint32 triangle indices)
//         public/terrain-mesh.json (active mesh metadata)
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const args = process.argv.slice(2);
const at = args.indexOf("--stride");
const stride = at >= 0 ? Number(args[at + 1]) : 4;
const sceneDir = args.find((arg, i) => !arg.startsWith("--") && args[i - 1] !== "--stride");
if (!sceneDir || !Number.isInteger(stride) || stride < 1)
  throw Error("Usage: node adapters/prepare-terrain.mjs scene_dir [--stride N]");
const digest = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const xml = fs.readFileSync(path.join(sceneDir, "scene.xml"));
const manifestBytes = fs.readFileSync(path.join(sceneDir, "manifest.json"));
const manifest = JSON.parse(manifestBytes.toString("utf8"));
const text = xml.toString("utf8");
const attrs = (tag) => Object.fromEntries([...tag.matchAll(/(\w+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
const nums = (value) => value.trim().split(/\s+/).map(Number);
const fields = new Map(
  [...text.matchAll(/<hfield\b[^>]*>/g)].map((m) => {
    const a = attrs(m[0]);
    return [a.name, { file: a.file, size: nums(a.size) }];
  }),
);
const geoms = [...text.matchAll(/<geom\b[^>]*type="hfield"[^>]*>/g)].map((m) => attrs(m[0]));
if (!geoms.length) throw Error("No hfield geoms in scene.xml");

const positions = [];
const indices = [];
// MuJoCo hfield: header int32 nrow, ncol; float32 elevation in [0, 1], row-major.
// Rows run along +Y, columns along +X; z = pos.z + value * size[2].
for (const geom of geoms) {
  const field = fields.get(geom.hfield);
  if (!field) throw Error("Missing hfield asset: " + geom.hfield);
  const raw = fs.readFileSync(path.join(sceneDir, field.file));
  const nrow = raw.readInt32LE(0), ncol = raw.readInt32LE(4);
  if (raw.length !== 8 + nrow * ncol * 4) throw Error("Bad hfield length: " + field.file);
  const [rx, ry, rz] = field.size;
  const [px, py, pz] = nums(geom.pos);
  const pick = (n) => {
    const out = [];
    for (let i = 0; i < n - 1; i += stride) out.push(i);
    out.push(n - 1);
    return out;
  };
  const rows = pick(nrow), cols = pick(ncol);
  const base = positions.length / 3;
  for (const r of rows)
    for (const c of cols) {
      const v = raw.readFloatLE(8 + (r * ncol + c) * 4);
      positions.push(
        px - rx + (2 * rx * c) / Math.max(1, ncol - 1),
        py - ry + (2 * ry * r) / Math.max(1, nrow - 1),
        pz + v * rz,
      );
    }
  for (let r = 0; r < rows.length - 1; r++)
    for (let c = 0; c < cols.length - 1; c++) {
      const a = base + r * cols.length + c, b = a + 1, d = a + cols.length, e = d + 1;
      indices.push(a, b, e, a, e, d);
    }
}
const body = Buffer.concat([
  Buffer.from(new Float32Array(positions).buffer),
  Buffer.from(new Uint32Array(indices).buffer),
]);
const sceneHash = digest(xml);
const file = `terrain-${sceneHash.slice(0, 12)}.bin`;
const meta = {
  file, scene_sha256: sceneHash, scene_manifest_sha256: digest(manifestBytes), mesh_sha256: digest(body),
  reference_map_sha256: manifest.reference_map_sha256 ?? null, declared_frame: manifest.frame ?? null,
  status: manifest.status ?? null, hfields: geoms.length, stride,
  vertices: positions.length / 3, triangles: indices.length / 3,
  method: `every ${stride}th heightfield sample plus edges; display only, not the collision surface`,
};
const target = path.resolve("public", file);
if (fs.existsSync(target)) {
  if (!fs.readFileSync(target).equals(body)) throw Error("Output exists with different contents: " + file);
} else fs.writeFileSync(target, body, { flag: "wx" });
const json = JSON.stringify(meta, null, 2) + "\n";
const active = path.resolve("public/terrain-mesh.json");
const temp = active + "." + process.pid;
fs.writeFileSync(temp, json, { flag: "wx" });
fs.renameSync(temp, active);
console.log(json);
