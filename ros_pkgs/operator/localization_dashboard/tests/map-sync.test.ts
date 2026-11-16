// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import { mapReviewLabel } from "../src/model";

const script = path.resolve("adapters/sync-map.mjs");
const sha = (bytes: Buffer) =>
  crypto.createHash("sha256").update(bytes).digest("hex");
function pcd(points: number[][]) {
  const header = [
    "VERSION 0.7",
    "FIELDS x y z label",
    "SIZE 4 4 4 4",
    "TYPE F F F U",
    "COUNT 1 1 1 1",
    `WIDTH ${points.length}`,
    "HEIGHT 1",
    "VIEWPOINT 0 0 0 1 0 0 0",
    `POINTS ${points.length}`,
    "DATA binary",
    "",
  ].join("\n");
  const body = Buffer.alloc(points.length * 16);
  points.forEach(([x, y, z, label], i) => {
    body.writeFloatLE(x, i * 16);
    body.writeFloatLE(y, i * 16 + 4);
    body.writeFloatLE(z, i * 16 + 8);
    body.writeUInt32LE(label, i * 16 + 12);
  });
  return Buffer.concat([Buffer.from(header), body]);
}
function release(status: string, cloud: Buffer, hash = sha(cloud)) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "map-sync-"));
  const out = path.join(root, "release");
  fs.mkdirSync(out);
  fs.mkdirSync(path.join(root, "app", "public"), { recursive: true });
  fs.writeFileSync(path.join(out, "reference_map.pcd"), cloud);
  const manifest = path.join(out, "manifest.json");
  const write = (s: string, h = hash) =>
    fs.writeFileSync(
      manifest,
      JSON.stringify({ status: s, reason: "test", frame: "pair360_map", reference_sha256: h }),
    );
  write(status);
  const sync = (...extra: string[]) =>
    spawnSync(process.execPath, [script, "--manifest", manifest, ...extra], {
      cwd: path.join(root, "app"),
      encoding: "utf8",
    });
  const active = () =>
    JSON.parse(
      fs.readFileSync(path.join(root, "app/public/reference-map.json"), "utf8"),
    );
  return { root, sync, write, active };
}

describe("map release sync", () => {
  const cloud = pcd([
    [0, 0, 0, 1],
    [5, 0, 1, 3],
    [0, 5, 2, 4],
  ]);
  it("labels review state without inventing approval", () => {
    expect(mapReviewLabel("review_candidate")).toContain("최종 승인 전");
    expect(mapReviewLabel(undefined)).toBe("검수 정보 없음");
    expect(mapReviewLabel("other_state")).toBe("other_state");
  });
  it("rebuilds only when the manifest changes and copies review state", () => {
    const r = release("review_candidate", cloud);
    expect(r.sync("--check").status).toBe(1);
    expect(r.sync().status).toBe(0);
    const first = r.active();
    expect(first.source_sha256).toBe(sha(cloud));
    expect(first.review_status).toBe("review_candidate");
    expect(first.declared_frame).toBe("pair360_map");
    expect(first.preview_points).toBe(3);
    expect(fs.existsSync(path.join(r.root, "app/public", first.file))).toBe(true);
    expect(r.sync("--check").status).toBe(0);
    r.write("hypothetical_next_state");
    expect(r.sync("--check").status).toBe(1);
    expect(r.sync().status).toBe(0);
    expect(r.active().review_status).toBe("hypothetical_next_state");
    expect(r.active().preview_sha256).toBe(first.preview_sha256);
    fs.rmSync(r.root, { recursive: true, force: true });
  }, 30000); // six child node processes; the 5 s default is too tight under full-suite load
  it("refuses a manifest that does not describe the PCD", () => {
    const r = release("review_candidate", cloud, "0".repeat(64));
    const run = r.sync();
    expect(run.status).not.toBe(0);
    expect(run.stderr).toContain("release may be in progress");
    expect(
      fs.existsSync(path.join(r.root, "app/public/reference-map.json")),
    ).toBe(false);
    fs.rmSync(r.root, { recursive: true, force: true });
  });
});

describe("synthetic demo route", () => {
  it("walks the terrain route forward and back above the ground", async () => {
    const { demoPose, demoRoute } = await import("../src/store");
    const start = demoPose(0);
    expect([start.x, start.y]).toEqual([demoRoute[0][0], demoRoute[0][1]]);
    expect(start.z).toBeCloseTo(demoRoute[0][2] + 0.45);
    expect(start.yaw).toBeCloseTo(Math.PI / 2);
    for (let t = 0; t < 120; t += 0.5) {
      const p = demoPose(t);
      expect(p.x).toBeGreaterThanOrEqual(-18.001);
      expect(p.x).toBeLessThanOrEqual(-9.999);
      expect(p.y).toBeGreaterThanOrEqual(169.999);
      expect(p.y).toBeLessThanOrEqual(185.001);
    }
    // 21.9 m route at 0.6 m/s: near the end at 36 s, heading back by 40 s.
    expect(demoPose(36).x).toBeGreaterThan(-10.5);
    expect(Math.cos(demoPose(40).yaw)).toBeCloseTo(-1);
  });
});

describe("terrain mesh preview", () => {
  it("places MuJoCo heightfield samples in map coordinates", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "terrain-"));
    const scene = path.join(root, "scene");
    fs.mkdirSync(path.join(scene, "hfields"), { recursive: true });
    fs.mkdirSync(path.join(root, "app/public"), { recursive: true });
    const field = Buffer.alloc(8 + 9 * 4);
    field.writeInt32LE(3, 0); // rows along +Y
    field.writeInt32LE(3, 4); // columns along +X
    [0, 0, 0, 0, 0.5, 0, 0, 0, 1].forEach((v, i) =>
      field.writeFloatLE(v, 8 + i * 4),
    );
    fs.writeFileSync(path.join(scene, "hfields/g.bin"), field);
    fs.writeFileSync(
      path.join(scene, "scene.xml"),
      '<mujoco><asset><hfield name="g" file="hfields/g.bin" size="1 2 4 0.1" /></asset>' +
        '<worldbody><geom name="g" type="hfield" hfield="g" pos="10 20 3" /></worldbody></mujoco>',
    );
    fs.writeFileSync(
      path.join(scene, "manifest.json"),
      JSON.stringify({ frame: "pair360_map", reference_map_sha256: "x" }),
    );
    const run = spawnSync(
      process.execPath,
      [path.resolve("adapters/prepare-terrain.mjs"), scene, "--stride", "1"],
      { cwd: path.join(root, "app"), encoding: "utf8" },
    );
    expect(run.status).toBe(0);
    const meta = JSON.parse(
      fs.readFileSync(path.join(root, "app/public/terrain-mesh.json"), "utf8"),
    );
    expect([meta.vertices, meta.triangles]).toEqual([9, 8]);
    const bytes = fs.readFileSync(path.join(root, "app/public", meta.file));
    const xyz = new Float32Array(bytes.buffer, bytes.byteOffset, 27);
    expect(Array.from(xyz.slice(0, 3))).toEqual([9, 18, 3]); // first corner
    expect(Array.from(xyz.slice(12, 15))).toEqual([10, 20, 5]); // centre, 0.5 * 4
    expect(Array.from(xyz.slice(24, 27))).toEqual([11, 22, 7]); // far corner
    fs.rmSync(root, { recursive: true, force: true });
  });
});
