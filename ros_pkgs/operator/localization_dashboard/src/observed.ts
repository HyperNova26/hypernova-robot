// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Turbo colormap, polynomial fit by Google (Apache-2.0), input clamped to [0, 1].
export function turbo(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)),
    x2 = x * x,
    x3 = x2 * x,
    x4 = x3 * x,
    x5 = x4 * x;
  const c = (v: number) => Math.min(1, Math.max(0, v));
  return [
    c(
      0.13572138 +
        4.6153926 * x -
        42.66032258 * x2 +
        132.13108234 * x3 -
        152.94239396 * x4 +
        59.28637943 * x5,
    ),
    c(
      0.09140261 +
        2.19418839 * x +
        4.84296658 * x2 -
        14.18503333 * x3 +
        4.27729857 * x4 +
        2.82956604 * x5,
    ),
    c(
      0.1066733 +
        12.64194608 * x -
        60.58204836 * x2 +
        110.36276771 * x3 -
        89.90310912 * x4 +
        27.34824973 * x5,
    ),
  ];
}
// Skip turbo's near-black ends so low ground still reads as blue on the dark background.
export const rainbow = (t: number) =>
  turbo(0.1 + 0.85 * Math.min(1, Math.max(0, t)));
// Terrain-mesh vertices bucketed on the mesh's own grid, for the ground height under a point.
export class TerrainIndex {
  private cells = new Map<number, number[]>();
  constructor(
    private positions: Float32Array,
    private cell = 0.4,
  ) {
    for (let i = 0; i < positions.length / 3; i++) {
      const k = this.key(positions[i * 3], positions[i * 3 + 1]);
      const list = this.cells.get(k);
      if (list) list.push(i);
      else this.cells.set(k, [i]);
    }
  }
  private key(x: number, y: number) {
    return (
      (Math.floor(x / this.cell) + 32768) * 65536 +
      (Math.floor(y / this.cell) + 32768)
    );
  }
  // Lowest vertex in the cell (the walkable surface under trees and posts);
  // neighbouring cells only when this one has no vertex.
  groundAt(x: number, y: number) {
    const lowest = (keys: number[]) => {
      let best = Infinity;
      for (const k of keys)
        for (const v of this.cells.get(k) ?? [])
          best = Math.min(best, this.positions[v * 3 + 2]);
      return best;
    };
    let best = lowest([this.key(x, y)]);
    if (!Number.isFinite(best)) {
      const around: number[] = [];
      for (let dx = -1; dx <= 1; dx++)
        for (let dy = -1; dy <= 1; dy++)
          around.push(this.key(x + dx * this.cell, y + dy * this.cell));
      best = lowest(around);
    }
    return Number.isFinite(best) ? best : undefined;
  }
}
// Every LiDAR scan received this session, one point per voxel, coloured by height above
// the ground under it (blue at the ground, red at `span` metres up). Display only.
export class LidarMap {
  readonly positions: Float32Array;
  readonly colors: Float32Array;
  private seen = new Set<number>();
  count = 0;
  constructor(
    readonly capacity = 2_000_000,
    private voxel = 0.1,
    private span = 5,
  ) {
    this.positions = new Float32Array(capacity * 3);
    this.colors = new Float32Array(capacity * 3);
  }
  clear() {
    this.seen.clear();
    this.count = 0;
  }
  get full() {
    return this.count >= this.capacity;
  }
  // Adds new voxels from xyz triples in the map frame; returns the index of the first new point.
  add(
    points: Float32Array,
    groundAt: (x: number, y: number) => number | undefined,
    fallbackGround: number,
  ) {
    const start = this.count,
      v = this.voxel;
    for (let i = 0; i + 2 < points.length && !this.full; i += 3) {
      const x = points[i],
        y = points[i + 1],
        z = points[i + 2];
      if (!Number.isFinite(x + y + z)) continue;
      // 2^16 cells per horizontal axis and 2^12 vertically: the key stays below 2^44,
      // exact in a double, and covers +-1.6 km x +-100 m at 0.05 m.
      const ix = Math.floor(x / v) + 32768,
        iy = Math.floor(y / v) + 32768,
        iz = Math.floor(z / v) + 2048;
      if (ix < 0 || ix >= 65536 || iy < 0 || iy >= 65536 || iz < 0 || iz >= 4096)
        continue;
      const key = (ix * 65536 + iy) * 4096 + iz;
      if (this.seen.has(key)) continue;
      this.seen.add(key);
      const n = this.count++;
      this.positions.set([x, y, z], n * 3);
      const ground = groundAt(x, y) ?? fallbackGround;
      this.colors.set(rainbow((z - ground) / this.span), n * 3);
    }
    return start;
  }
}
