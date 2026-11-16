// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Rebuild the dashboard map and terrain previews when map-release changes. Reads the release only.
// Usage: [HN_MAP_RELEASE=dir] node adapters/sync-map.mjs [--check] [--manifest path/to/manifest.json] [--terrain path/to/terrain/scene]
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const check = args.includes("--check");
// Release folder layout: <release>/output/manifest.json + reference_map.pcd, <release>/terrain/scene/.
// HN_MAP_RELEASE overrides the default sibling folder used in the original workspace.
const release = process.env.HN_MAP_RELEASE
  ? path.resolve(process.env.HN_MAP_RELEASE)
  : fileURLToPath(new URL("../../../map-release", import.meta.url));
const option = (name, fallback) => {
  const at = args.indexOf(name);
  return path.resolve(at >= 0 ? (args[at + 1] ?? "") : path.join(release, fallback));
};
const manifestPath = option("--manifest", "output/manifest.json");
// An explicit --manifest without --terrain means a custom release: skip the default terrain.
const terrainDir =
  args.includes("--terrain") || !args.includes("--manifest")
    ? option("--terrain", "terrain/scene")
    : undefined;
const sha = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const readJson = (file) =>
  fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
const inPublic = (file) =>
  typeof file === "string" && fs.existsSync(path.resolve("public", file));
const run = (script, ...rest) =>
  spawnSync(
    process.execPath,
    [fileURLToPath(new URL(script, import.meta.url)), ...rest],
    { stdio: "inherit" },
  ).status ?? 1;

// Point-cloud map preview.
if (!fs.existsSync(manifestPath))
  throw Error("Release manifest not found: " + manifestPath + " (set HN_MAP_RELEASE or pass --manifest)");
const manifestBytes = fs.readFileSync(manifestPath);
const manifest = JSON.parse(manifestBytes.toString("utf8"));
if (!/^[0-9a-f]{64}$/.test(manifest.reference_sha256 ?? ""))
  throw Error("manifest.json has no reference_sha256");
const active = readJson(path.resolve("public/reference-map.json"));
const mapStale = [
  active.source_sha256 !== manifest.reference_sha256 && "map hash changed",
  active.manifest_sha256 !== sha(manifestBytes) && "manifest changed",
  !inPublic(active.file) && "preview file missing",
].filter(Boolean);
const label = `${manifest.reference_sha256.slice(0, 12)} · ${manifest.status ?? "unknown"}`;

// Terrain display mesh (MuJoCo heightfields).
let terrainStale = [];
if (terrainDir) {
  const scene = path.join(terrainDir, "scene.xml");
  if (!fs.existsSync(scene)) throw Error("Terrain scene not found: " + scene);
  const mesh = readJson(path.resolve("public/terrain-mesh.json"));
  const sceneManifest = path.join(terrainDir, "manifest.json");
  terrainStale = [
    mesh.scene_sha256 !== sha(fs.readFileSync(scene)) &&
      "terrain scene changed",
    mesh.scene_manifest_sha256 !== sha(fs.readFileSync(sceneManifest)) &&
      "terrain manifest changed",
    !inPublic(mesh.file) && "terrain mesh missing",
  ].filter(Boolean);
  const terrainMap = readJson(sceneManifest).reference_map_sha256;
  if (terrainMap !== manifest.reference_sha256)
    console.warn(
      `Warning: terrain was built from map ${String(terrainMap).slice(0, 12)}, release map is ${label}`,
    );
}

const stale = [...mapStale, ...terrainStale];
if (!stale.length) {
  console.log(`Map preview is current: ${label}`);
  process.exit(0);
}
if (check) {
  console.log(`Map preview is stale (${stale.join(", ")}): release ${label}`);
  process.exit(1);
}
console.log(`Rebuilding (${stale.join(", ")}): release ${label}`);
if (mapStale.length) {
  const source = path.join(path.dirname(manifestPath), "reference_map.pcd");
  const status = run(
    "./prepare-map.mjs",
    source,
    "--activate",
    "--require-manifest",
  );
  if (status) process.exit(status);
}
if (terrainStale.length) process.exit(run("./prepare-terrain.mjs", terrainDir));
