// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
export type V3 = { x: number; y: number; z: number };
export type Q = V3 & { w: number };
export type Pose = {
  t: number;
  frame: string;
  child: string;
  p: V3;
  q: Q;
  v?: V3;
};
export type Cloud = {
  t: number;
  frame: string;
  points: Float32Array;
  labels?: Uint8Array;
  mapVersion?: string;
  review?: string;
  reviewReason?: string;
};
// Release review state is shown verbatim; only the one observed value gets a Korean label.
export function mapReviewLabel(status?: string) {
  if (!status) return "검수 정보 없음";
  if (status === "review_candidate") return "검수 후보 · 최종 승인 전";
  return status;
}
export const mapClasses = [
  { name: "미분류", color: "#687683" },
  { name: "지면", color: "#8aa6be" },
  { name: "줄기", color: "#ec9660" },
  { name: "수관·관목", color: "#55b886" },
  { name: "시설물", color: "#bc9bdf" },
  // Ids follow map-release/classification/classify.py NAMES. Vehicles and noise are not prior map.
  { name: "차량", color: "#e08a3c" },
  { name: "노이즈", color: "#5a5f66" },
] as const;
export const priorExcluded = new Set([5, 6]);
export function mapLabel(value: number) {
  return Number.isInteger(value) && value > 0 && value < mapClasses.length
    ? value
    : 0;
}
export const localizationStates = [
  "ACQUIRING",
  "TRACKING",
  "DEGRADED",
  "LOST",
  "STALE_INPUT",
  "INPUT_TIMEOUT",
] as const;
export type LocalizationStatus = {
  code?: number;
  label: string;
  t?: number;
  received: number;
  field: string;
  issue?: string;
  raw: unknown;
};
export function localizationStatus(
  message: any,
  field: string,
  received: number,
): LocalizationStatus {
  const value = field
    .split(".")
    .reduce((object, key) => object?.[key], message);
  const code =
    typeof value === "number" && Number.isInteger(value) ? value : undefined;
  const t = message.header?.stamp ? stamp(message.header.stamp) : undefined;
  return {
    code,
    label:
      code === undefined
        ? "필드 확인 필요"
        : (localizationStates[code] ?? `UNKNOWN(${code})`),
    t: t !== undefined && Number.isFinite(t) ? t : undefined,
    received,
    field,
    issue:
      code === undefined
        ? `정수 상태 코드 필드 '${field}'를 확인하세요.`
        : localizationStates[code] === undefined
          ? "명세에 없는 상태 코드입니다."
          : undefined,
    raw: message,
  };
}
export type Sample = {
  t: number;
  frame: string;
  child: string;
  p: V3;
  gt?: V3;
  gtTime?: number;
  rpy: V3;
  speed?: number;
  speedSource: string;
  error?: number;
  reason: string;
  received: number;
  localization?: LocalizationStatus;
};
export type Config = {
  url: string;
  frame: string;
  base: string;
  lio: string;
  gt: string;
  scan: string;
  status: string;
  statusField: string;
  prior: string;
  twistValid: boolean;
  tolerance: number;
  timeout: number;
  mapVerified: boolean;
};
export const defaults: Config = {
  url: "ws://localhost:8765",
  frame: "pair360_map",
  base: "mlx_lidar",
  lio: "/localization/odometry",
  gt: "",
  scan: "/lidar/points",
  status: "/localization/status",
  statusField: "status",
  prior: "/localization/reference_map",
  twistValid: false,
  tolerance: 0.05,
  timeout: 1500,
  mapVerified: false,
};
export const stamp = (h: any) =>
  Number(h?.sec ?? h?.secs ?? 0) + Number(h?.nanosec ?? h?.nsecs ?? 0) * 1e-9;
export function pose(m: any): Pose {
  const p = m.pose?.pose;
  if (
    !p ||
    !m.header?.stamp ||
    !m.header.frame_id ||
    !m.child_frame_id ||
    !Number.isFinite(stamp(m.header.stamp))
  )
    throw Error("Odometry pose·시각·frame 누락");
  const q = p.orientation;
  const values = [p.position.x, p.position.y, p.position.z, q.x, q.y, q.z, q.w];
  if (!values.every(Number.isFinite) || Math.hypot(q.x, q.y, q.z, q.w) < 1e-8)
    throw Error("유효하지 않은 Odometry");
  const n = Math.hypot(q.x, q.y, q.z, q.w);
  return {
    t: stamp(m.header.stamp),
    frame: m.header.frame_id,
    child: m.child_frame_id,
    p: p.position,
    q: { x: q.x / n, y: q.y / n, z: q.z / n, w: q.w / n },
    v: m.twist?.twist?.linear,
  };
}
export function rpy(q: Q): V3 {
  const d = 180 / Math.PI;
  return {
    x:
      Math.atan2(2 * (q.w * q.x + q.y * q.z), 1 - 2 * (q.x * q.x + q.y * q.y)) *
      d,
    y: Math.asin(Math.max(-1, Math.min(1, 2 * (q.w * q.y - q.z * q.x)))) * d,
    z:
      Math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)) *
      d,
  };
}
export function nearest<T extends { t: number }>(
  items: T[],
  t: number,
  tolerance: number,
): T | undefined {
  let best: T | undefined;
  let delta = Infinity;
  for (const x of items) {
    const v = Math.abs(x.t - t);
    if (v <= tolerance && v < delta) {
      best = x;
      delta = v;
    }
  }
  return best;
}
export function sample(
  p: Pose,
  previous: Pose | undefined,
  gt: Pose | undefined,
  c: Config,
  received: number,
): Sample {
  const dt = previous ? p.t - previous.t : 0;
  const validTwist = Boolean(
    c.twistValid && p.v && [p.v.x, p.v.y].every(Number.isFinite),
  );
  const speed = validTwist
    ? Math.hypot(p.v!.x, p.v!.y)
    : previous &&
        previous.frame === p.frame &&
        previous.child === p.child &&
        dt > 0 &&
        dt <= 1
      ? Math.hypot(p.p.x - previous.p.x, p.p.y - previous.p.y) / dt
      : undefined;
  let reason =
    !c.gt.trim() && !gt
      ? "GT 토픽 미지정"
      : !gt
        ? "동일 시각 GT 없음"
        : Math.abs(gt.t - p.t) > c.tolerance
          ? "시각 불일치"
          : gt.frame !== p.frame || p.frame !== c.frame
            ? "기준 좌표 불일치"
            : gt.child !== p.child || p.child !== c.base
              ? "비교 기준점 불일치"
              : "";
  return {
    t: p.t,
    frame: p.frame,
    child: p.child,
    p: p.p,
    rpy: rpy(p.q),
    speed,
    speedSource: validTwist ? "odometry.twist" : "pose 차분",
    gt: reason ? undefined : gt?.p,
    gtTime: reason ? undefined : gt?.t,
    error:
      !reason && gt
        ? Math.hypot(p.p.x - gt.p.x, p.p.y - gt.p.y, p.p.z - gt.p.z)
        : undefined,
    reason,
    received,
  };
}
export function pointCloud(m: any, max = 24000, readLabels = false): Cloud {
  const bytes =
    typeof m.data === "string"
      ? Uint8Array.from(atob(m.data), (c) => c.charCodeAt(0))
      : new Uint8Array(m.data);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const fields = ["x", "y", "z"].map((n) =>
    m.fields.find((f: any) => f.name === n),
  );
  if (fields.some((f) => !f) || !m.point_step || !m.row_step)
    throw Error("PointCloud2 레이아웃 누락");
  const getters: Record<number, [number, (o: number) => number]> = {
    1: [1, (o) => view.getInt8(o)],
    2: [1, (o) => view.getUint8(o)],
    3: [2, (o) => view.getInt16(o, !m.is_bigendian)],
    4: [2, (o) => view.getUint16(o, !m.is_bigendian)],
    5: [4, (o) => view.getInt32(o, !m.is_bigendian)],
    6: [4, (o) => view.getUint32(o, !m.is_bigendian)],
    7: [4, (o) => view.getFloat32(o, !m.is_bigendian)],
    8: [8, (o) => view.getFloat64(o, !m.is_bigendian)],
  };
  const label = readLabels && m.fields.find((f: any) => f.name === "label");
  const reader = label && getters[label.datatype];
  const labels: number[] | undefined =
    reader &&
    label.datatype <= 6 &&
    (label.count === undefined || label.count === 1) &&
    Number.isInteger(label.offset) &&
    label.offset >= 0 &&
    label.offset + reader[0] <= m.point_step
      ? []
      : undefined;
  const out: number[] = [];
  const step = Math.max(1, Math.ceil((m.width * m.height) / max));
  for (let i = 0; i < m.width * m.height; i += step) {
    const base =
      Math.floor(i / m.width) * m.row_step + (i % m.width) * m.point_step;
    const xyz = fields.map((f) => {
      const spec = getters[f.datatype];
      if (
        !spec ||
        f.offset + spec[0] > m.point_step ||
        base + f.offset + spec[0] > bytes.length
      )
        throw Error("PointCloud2 범위 오류");
      return spec[1](base + f.offset);
    });
    if (xyz.every(Number.isFinite)) {
      out.push(...xyz);
      if (labels) labels.push(mapLabel(reader[1](base + label.offset)));
    }
  }
  return {
    t: stamp(m.header.stamp),
    frame: m.header.frame_id,
    points: new Float32Array(out),
    labels: labels && Uint8Array.from(labels),
  };
}
export const csv = (
  rows: Sample[],
  events: { t: number; event: string }[],
  statuses: LocalizationStatus[] = [],
) => {
  const header = [
    "kind",
    "sim_time_s",
    "frame",
    "child",
    "x_m",
    "y_m",
    "z_m",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
    "speed_m_s",
    "speed_source",
    "gt_x_m",
    "gt_y_m",
    "gt_z_m",
    "gt_error_m",
    "gt_time_s",
    "gt_time_delta_s",
    "received_wall_ms",
    "status",
    "reason",
    "localization_code",
    "localization_state",
    "localization_time_s",
    "localization_field",
    "localization_issue",
    "localization_payload_json",
  ];
  const statusColumns = (s?: LocalizationStatus) => ({
    localization_code: s?.code,
    localization_state: s?.label,
    localization_time_s: s?.t,
    localization_field: s?.field,
    localization_issue: s?.issue,
  });
  const records: Record<string, unknown>[] = [
    ...rows.map((s) => ({
      kind: "sample",
      sim_time_s: s.t,
      frame: s.frame,
      child: s.child,
      x_m: s.p.x,
      y_m: s.p.y,
      z_m: s.p.z,
      roll_deg: s.rpy.x,
      pitch_deg: s.rpy.y,
      yaw_deg: s.rpy.z,
      speed_m_s: s.speed,
      speed_source: s.speedSource,
      gt_x_m: s.gt?.x,
      gt_y_m: s.gt?.y,
      gt_z_m: s.gt?.z,
      gt_error_m: s.error,
      gt_time_s: s.gtTime,
      gt_time_delta_s: s.gtTime === undefined ? undefined : s.gtTime - s.t,
      received_wall_ms: s.received,
      status: "수신 중",
      reason: s.reason,
      ...statusColumns(s.localization),
    })),
    ...events.map((e) => ({ kind: "event", sim_time_s: e.t, status: e.event })),
    ...statuses.map((s) => ({
      kind: "localization_status",
      sim_time_s: s.t,
      received_wall_ms: s.received,
      ...statusColumns(s),
      localization_payload_json: JSON.stringify(s.raw, (_, v) =>
        typeof v === "bigint" ? String(v) : v,
      ),
    })),
  ];
  const escape = (value: unknown) =>
    '\"' + String(value ?? "").replaceAll('\"', '\"\"') + '\"';
  return (
    "\uFEFF" +
    [header, ...records.map((row) => header.map((key) => row[key]))]
      .map((row) => row.map(escape).join(","))
      .join("\r\n")
  );
};
