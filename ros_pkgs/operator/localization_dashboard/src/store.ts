// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import {
  defaults,
  nearest,
  pose,
  sample,
  stamp,
  pointCloud,
  localizationStatus,
  type Config,
  type Pose,
  type Cloud,
  type LocalizationStatus,
  type Sample,
} from "./model";
import { FrameTransforms } from "./transforms";
export class Telemetry {
  config: Config = { ...defaults };
  lio: Pose[] = [];
  gt: Pose[] = [];
  clouds: Cloud[] = [];
  statuses: LocalizationStatus[] = [];
  frames = new FrameTransforms();
  rows: Sample[] = [];
  events: { t: number; event: string }[] = [];
  simTime = 0;
  clockAvailable = false;
  lastReceived = 0;
  receiving = false;
  connection = "미연결";
  error = "";
  demo = false;
  pausedInput = false;
  version = 0;
  listeners = new Set<() => void>();
  notify = () => {
    this.version++;
    this.listeners.forEach((f) => f());
  };
  subscribe = (f: () => void) => {
    this.listeners.add(f);
    return () => {
      this.listeners.delete(f);
    };
  };
  reset(preserveStatic = false) {
    this.lio = [];
    this.gt = [];
    this.clouds = [];
    this.statuses = [];
    this.frames.clear(preserveStatic);
    if (!preserveStatic) {
      this.livePrior = undefined;
      this.liveSession = false;
    }
    this.rows = [];
    this.events = [];
    this.simTime = 0;
    this.clockAvailable = false;
    this.lastReceived = 0;
    this.receiving = false;
    this.error = "";
    this.notify();
  }
  event(event: string) {
    this.events.push({ t: this.simTime, event });
    if (this.events.length > 1000) this.events.shift();
  }
  tick() {
    const receiving =
      this.lastReceived > 0 &&
      Date.now() - this.lastReceived < this.config.timeout;
    if (receiving !== this.receiving) {
      this.receiving = receiving;
      this.event(receiving ? "수신 재개" : "수신 중단");
    }
    this.notify();
  }
  ingest(role: string, m: any) {
    try {
      if (role === "tf" || role === "tf_static")
        this.frames.ingest(m, role === "tf_static");
      if (role === "status") {
        const status = localizationStatus(
          m,
          this.config.statusField,
          Date.now(),
        );
        const previous = this.statuses.at(-1);
        this.statuses.push(status);
        if (this.statuses.length > 1000) this.statuses.shift();
        if (status.label !== previous?.label)
          this.event("위치추정 상태: " + status.label);
        if (status.t !== undefined)
          for (
            let i = Math.max(0, this.rows.length - 200);
            i < this.rows.length;
            i++
          ) {
            const row = this.rows[i];
            const match = this.statusAt(row.t);
            if (match) this.rows[i] = { ...row, localization: match };
          }
      }
      if (role === "clock") {
        const t = stamp(m.clock);
        if (t < this.simTime - 0.001) {
          this.reset(true);
          this.event("SIM 시각 재설정");
        }
        this.simTime = t;
        this.clockAvailable = true;
      }
      if (role === "lio" || role === "gt") {
        const p = pose(m);
        const list = role === "lio" ? this.lio : this.gt;
        if (list.length && p.t < list[list.length - 1].t) {
          this.event("순서가 뒤바뀐 " + role + " 메시지 제외");
          return;
        }
        if (list.at(-1)?.t === p.t) return;
        list.push(p);
        if (list.length > 6000) list.shift();
        if (role === "lio") {
          this.frames.odometry(p);
          this.lastReceived = Date.now();
          const gt = nearest(this.gt, p.t, this.config.tolerance);
          this.rows.push({
            ...sample(p, list.at(-2), gt, this.config, this.lastReceived),
            localization: this.statusAt(p.t),
          });
          if (this.rows.length > 6000) this.rows.shift();
        } else {
          for (let i = this.rows.length - 1; i >= 0; i--) {
            const row = this.rows[i];
            if (p.t - row.t > this.config.tolerance) break;
            const l = this.lio.find((x) => x.t === row.t);
            if (l) {
              const g = nearest(this.gt, row.t, this.config.tolerance);
              this.rows[i] = sample(
                l,
                this.lio[this.lio.indexOf(l) - 1],
                g,
                this.config,
                row.received,
              );
              this.rows[i].localization = row.localization;
            }
          }
        }
      }
      if (role === "scan" || role === "prior") {
        const cloud = pointCloud(
          m,
          role === "prior" ? 100000 : 24000,
          role === "prior",
        );
        if (role === "prior") this.livePrior = cloud;
        else {
          this.clouds.push(cloud);
          if (this.clouds.length > 30) this.clouds.shift();
        }
      }
      this.tick();
    } catch (e) {
      this.error = String(e);
      this.notify();
    }
  }
  localPrior?: Cloud;
  livePrior?: Cloud;
  liveSession = false;
  get prior() {
    return (
      this.livePrior ??
      (!this.liveSession || this.config.mapVerified
        ? this.localPrior
        : undefined)
    );
  }
  get mapAligned() {
    const map = this.prior;
    return (
      this.demo ||
      (map !== undefined &&
        (map === this.livePrior
          ? map.frame === this.config.frame
          : this.config.mapVerified))
    );
  }
  get current() {
    return this.rows.at(-1);
  }
  get cloud() {
    return this.current
      ? nearest(this.clouds, this.current.t, 0.12)
      : undefined;
  }
  statusAt(t: number) {
    return nearest(
      this.statuses.filter(
        (s): s is LocalizationStatus & { t: number } => s.t !== undefined,
      ),
      t,
      this.config.tolerance,
    );
  }
  get localization() {
    return this.statuses.at(-1);
  }
  get mapCloud() {
    const cloud = this.cloud;
    return cloud ? this.frames.cloud(cloud, this.config.frame) : undefined;
  }
  get lidarCloud() {
    const cloud = this.cloud;
    return cloud
      ? (this.frames.cloud(cloud, this.config.base) ?? cloud)
      : undefined;
  }
}
export const telemetry = new Telemetry();
// Synthetic preview route: the walking-test route of map-release/terrain/scene/manifest.json
// (route_xyz_m, pair360_map ground points, reference map 223c6135c606). Copied, not live-linked.
export const demoRoute = [
  [-16, 170, 1.215],
  [-16, 175, 1.22],
  [-17, 179, 1.387],
  [-18, 182, 1.447],
  [-16, 185, 1.503],
  [-12, 185, 1.72],
  [-10, 185, 2.05],
] as const;
const demoSpeed = 0.6, // m/s, display only
  demoSensorHeight = 0.45; // m above ground, display assumption, not the Go2 extrinsic
export function demoPose(t: number) {
  const lengths = demoRoute
    .slice(1)
    .map((p, i) => Math.hypot(p[0] - demoRoute[i][0], p[1] - demoRoute[i][1]));
  const total = lengths.reduce((a, b) => a + b, 0);
  const travelled = (t * demoSpeed) % (2 * total);
  const back = travelled > total;
  let d = back ? 2 * total - travelled : travelled;
  let i = 0;
  while (i < lengths.length - 1 && d > lengths[i]) d -= lengths[i++];
  const [a, b] = [demoRoute[i], demoRoute[i + 1]];
  const f = Math.min(1, d / lengths[i]);
  const yaw = Math.atan2(b[1] - a[1], b[0] - a[0]) + (back ? Math.PI : 0);
  return {
    x: a[0] + (b[0] - a[0]) * f,
    y: a[1] + (b[1] - a[1]) * f,
    z: a[2] + (b[2] - a[2]) * f + demoSensorHeight,
    yaw,
  };
}
// Fake scan: nearby points of the loaded map (so the overlay lines up), else a plain ring.
function demoScan(
  map: Float32Array | undefined,
  x: number,
  y: number,
  z: number,
) {
  const near: number[] = [];
  if (map)
    for (let i = 0; i < map.length; i += 3)
      if (
        Math.hypot(map[i] - x, map[i + 1] - y) < 15 &&
        Math.abs(map[i + 2] - z) < 6
      )
        near.push(map[i], map[i + 1], map[i + 2]);
  if (near.length) {
    const step = Math.max(1, Math.ceil(near.length / 3 / 2000));
    const out: number[] = [];
    for (let i = 0; i < near.length; i += 3 * step)
      out.push(near[i], near[i + 1], near[i + 2]);
    return new Float32Array(out);
  }
  const ring = new Float32Array(720 * 3);
  for (let i = 0; i < 720; i++) {
    const a = (i / 720) * Math.PI * 2;
    ring.set(
      [x + 8 * Math.cos(a), y + 8 * Math.sin(a), z - demoSensorHeight],
      i * 3,
    );
  }
  return ring;
}
export function demo(store: Telemetry) {
  store.reset();
  store.demo = true;
  store.connection = "UI 시험 · 합성 데이터";
  let t = 0;
  const timer = setInterval(() => {
    t += 0.1;
    store.ingest("clock", {
      clock: { sec: Math.floor(t), nanosec: Math.round((t % 1) * 1e9) },
    });
    const { x, y, z, yaw } = demoPose(t);
    const od = (dx: number) => ({
      header: {
        stamp: { sec: Math.floor(t), nanosec: Math.round((t % 1) * 1e9) },
        frame_id: store.config.frame,
      },
      child_frame_id: store.config.base,
      pose: {
        pose: {
          position: { x: x + dx, y, z },
          orientation: {
            x: 0,
            y: 0,
            z: Math.sin(yaw / 2),
            w: Math.cos(yaw / 2),
          },
        },
      },
    });
    store.ingest("gt", od(0));
    if (!store.pausedInput) {
      store.ingest("status", {
        header: od(0).header,
        [store.config.statusField]: 1,
      });
      store.ingest("lio", od(0.08 * Math.sin(t)));
    }
    const points = demoScan(store.localPrior?.points, x, y, z);
    store.clouds.push({ t, frame: store.config.frame, points });
    if (store.clouds.length > 30) store.clouds.shift();
    store.notify();
  }, 100);
  return () => {
    clearInterval(timer);
    store.demo = false;
    store.pausedInput = false;
    store.connection = "미연결";
    store.reset();
  };
}
