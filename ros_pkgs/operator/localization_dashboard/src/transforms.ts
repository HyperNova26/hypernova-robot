// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { Quaternion, Vector3 } from "three";
import {
  nearest,
  stamp,
  type V3,
  type Q,
  type Cloud,
  type Pose,
} from "./model";
type Transform = { p: V3; q: Q };
type Edge = Transform & {
  t: number;
  parent: string;
  child: string;
  fixed: boolean;
};
const identity = (): Transform => ({
  p: { x: 0, y: 0, z: 0 },
  q: { x: 0, y: 0, z: 0, w: 1 },
});
const quaternion = (q: Q) => new Quaternion(q.x, q.y, q.z, q.w);
function compose(a: Transform, b: Transform): Transform {
  const p = new Vector3(b.p.x, b.p.y, b.p.z)
    .applyQuaternion(quaternion(a.q))
    .add(new Vector3(a.p.x, a.p.y, a.p.z));
  return { p, q: quaternion(a.q).multiply(quaternion(b.q)) };
}
function inverse(a: Transform): Transform {
  const q = quaternion(a.q).invert();
  return { p: new Vector3(-a.p.x, -a.p.y, -a.p.z).applyQuaternion(q), q };
}
export class FrameTransforms {
  private edges = new Map<string, Edge[]>();
  private version = 0;
  private cache = new WeakMap<
    Cloud,
    Map<string, { version: number; cloud?: Cloud }>
  >();
  clear(preserveStatic = false) {
    if (preserveStatic) {
      for (const [key, list] of this.edges)
        if (!list[0]?.fixed) this.edges.delete(key);
    } else this.edges.clear();
    this.version++;
  }
  private add(edge: Edge) {
    if (
      !edge.parent ||
      !edge.child ||
      edge.parent === edge.child ||
      !Number.isFinite(edge.t)
    )
      return;
    const values = [
      edge.p.x,
      edge.p.y,
      edge.p.z,
      edge.q.x,
      edge.q.y,
      edge.q.z,
      edge.q.w,
    ];
    if (
      !values.every(Number.isFinite) ||
      Math.hypot(edge.q.x, edge.q.y, edge.q.z, edge.q.w) < 1e-8
    )
      return;
    edge = { ...edge, q: quaternion(edge.q).normalize() };
    const key = [edge.fixed, edge.parent, edge.child].join("/");
    if (!this.edges.has(key) && this.edges.size >= 256) return;
    const list = this.edges.get(key) ?? [];
    const index = list.findIndex((x) => x.t === edge.t);
    if (index >= 0) list[index] = edge;
    else list.push(edge);
    list.sort((a, b) => a.t - b.t);
    if (list.length > 1000) list.shift();
    this.edges.set(key, list);
    this.version++;
  }
  ingest(message: any, fixed = false) {
    for (const tf of message.transforms ?? [])
      if (tf.header?.stamp && tf.transform)
        this.add({
          t: stamp(tf.header.stamp),
          parent: tf.header.frame_id,
          child: tf.child_frame_id,
          p: tf.transform.translation,
          q: tf.transform.rotation,
          fixed,
        });
  }
  odometry(pose: Pose) {
    this.add({
      t: pose.t,
      parent: pose.frame,
      child: pose.child,
      p: pose.p,
      q: pose.q,
      fixed: false,
    });
  }
  lookup(
    target: string,
    source: string,
    t: number,
    tolerance = 0.05,
  ): Transform | undefined {
    if (target === source) return identity();
    const edges: Edge[] = [];
    for (const list of this.edges.values()) {
      const edge = list[0]?.fixed ? list.at(-1) : nearest(list, t, tolerance);
      if (edge) edges.push(edge);
    }
    const queue = [{ frame: source, transform: identity(), depth: 0 }],
      visited = new Set([source]);
    while (queue.length) {
      const item = queue.shift()!;
      if (item.depth >= 8) continue;
      for (const edge of edges) {
        const forward = edge.child === item.frame,
          reverse = edge.parent === item.frame;
        if (!forward && !reverse) continue;
        const frame = forward ? edge.parent : edge.child;
        if (visited.has(frame)) continue;
        const transform = compose(
          forward ? edge : inverse(edge),
          item.transform,
        );
        if (frame === target) return transform;
        visited.add(frame);
        queue.push({ frame, transform, depth: item.depth + 1 });
      }
    }
  }
  cloud(cloud: Cloud, target: string): Cloud | undefined {
    if (target === cloud.frame) return cloud;
    const cached = this.cache.get(cloud)?.get(target);
    if (cached?.version === this.version) return cached.cloud;
    const transform = this.lookup(target, cloud.frame, cloud.t);
    let result: Cloud | undefined;
    if (transform) {
      const points = new Float32Array(cloud.points.length),
        rotation = quaternion(transform.q),
        v = new Vector3(),
        translation = new Vector3(transform.p.x, transform.p.y, transform.p.z);
      for (let i = 0; i < points.length; i += 3) {
        v.set(cloud.points[i], cloud.points[i + 1], cloud.points[i + 2])
          .applyQuaternion(rotation)
          .add(translation);
        points.set([v.x, v.y, v.z], i);
      }
      result = { ...cloud, frame: target, points };
    }
    const entries = this.cache.get(cloud) ?? new Map();
    entries.set(target, { version: this.version, cloud: result });
    this.cache.set(cloud, entries);
    return result;
  }
}
