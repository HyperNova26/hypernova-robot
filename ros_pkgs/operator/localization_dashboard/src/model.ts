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
  reason?: string;
  rate?: number;
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
// Provisional /localization/status (2026-11-28, docs/interfaces/localization-status.md): the same
// DiagnosticArray layout as G-006, one status "localization/state". t is sim_t (odometry stamp),
// because header.stamp is wall time there.
export function localizationFromDiagnostics(
  m: any,
  received: number,
): LocalizationStatus {
  const list: any[] = Array.isArray(m.status) ? m.status : [];
  const entry =
    list.find((s) => s?.name === "localization/state") ?? list[0] ?? {};
  const values: Record<string, string> = {};
  for (const kv of entry.values ?? [])
    if (typeof kv?.key === "string") values[kv.key] = String(kv.value);
  const num = (key: string) =>
    values[key] === undefined || values[key].trim() === ""
      ? undefined
      : Number(values[key]);
  const code = num("code");
  const known = code !== undefined && Number.isInteger(code);
  const t = num("sim_t");
  return {
    code: known ? code : undefined,
    label: !known
      ? "필드 확인 필요"
      : (localizationStates[code] ?? `UNKNOWN(${code})`),
    t: t !== undefined && Number.isFinite(t) ? t : undefined,
    received,
    field: "values.code",
    reason: values.reason,
    rate: num("rate_hz"),
    issue: !known
      ? "localization/state 항목에 정수 code 값이 없습니다."
      : localizationStates[code] === undefined
        ? "명세에 없는 상태 코드입니다."
        : undefined,
    raw: m,
  };
}
// G-006 hn_interfaces/msg/LocomotionStatus (feat/sim-fault-injection, 2026-11-20, ADR-0004 Proposed).
// header.stamp is wall time by default; sim_time_s carries SIM time (NaN on the real robot).
export const locomotionStates = [
  "INITIALIZING",
  "STANDING",
  "WALKING",
  "TILTING",
  "SLIPPING",
  "FALLEN",
  "STALE_INPUT",
] as const;
export const locomotionSeverities = ["OK", "WARN", "ERROR", "STALE"] as const;
export type LocomotionStatus = {
  code?: number;
  label: string;
  state?: string;
  severity?: number;
  severityLabel: string;
  reason?: string;
  sinceS?: number;
  robotId?: string;
  tilt?: number;
  roll?: number;
  pitch?: number;
  speed?: number;
  height?: number;
  t?: number;
  timeSource: "sim_time_s" | "header.stamp" | "없음";
  received: number;
  issue?: string;
  raw: unknown;
};
const finite = (v: unknown) =>
  typeof v === "number" && Number.isFinite(v) ? v : undefined;
const integer = (v: unknown) =>
  typeof v === "number" && Number.isInteger(v) ? v : undefined;
// Team main publishes G-006 as diagnostic_msgs/DiagnosticArray (ADR-0004, docs/interfaces/
// locomotion-status.md): one status "locomotion/state", level = severity, string values.
// This maps it onto the LocomotionStatus field names so one parser handles both.
export function locomotionFromDiagnostics(m: any) {
  const list: any[] = Array.isArray(m.status) ? m.status : [];
  const entry =
    list.find((s) => s?.name === "locomotion/state") ?? list[0] ?? {};
  const values: Record<string, string> = {};
  for (const kv of entry.values ?? [])
    if (typeof kv?.key === "string") values[kv.key] = String(kv.value);
  const num = (key: string) =>
    values[key] === undefined || values[key].trim() === ""
      ? undefined
      : Number(values[key]);
  const level =
    typeof entry.level === "number"
      ? entry.level
      : entry.level instanceof Uint8Array || Array.isArray(entry.level)
        ? entry.level[0]
        : undefined;
  return {
    header: m.header,
    code: num("code"),
    state: values.state ?? entry.message,
    severity: level,
    reason: values.reason,
    since_s: num("since_s"),
    robot_id: entry.hardware_id,
    sim_time_s: num("sim_t"),
    tilt_deg: num("tilt_deg"),
    roll_deg: num("roll_deg"),
    pitch_deg: num("pitch_deg"),
    speed_mps: num("speed_mps"),
    height_m: num("height_m"),
  };
}
export function locomotionStatus(
  message: any,
  received: number,
): LocomotionStatus {
  const code = integer(message.code),
    severity = integer(message.severity);
  const sim = finite(message.sim_time_s),
    header = message.header?.stamp
      ? finite(stamp(message.header.stamp))
      : undefined;
  const label =
    code === undefined
      ? "필드 확인 필요"
      : (locomotionStates[code] ?? `UNKNOWN(${code})`);
  const state = typeof message.state === "string" ? message.state : undefined;
  return {
    code,
    label,
    state,
    severity,
    severityLabel:
      severity === undefined
        ? "—"
        : (locomotionSeverities[severity] ?? `UNKNOWN(${severity})`),
    reason: typeof message.reason === "string" ? message.reason : undefined,
    sinceS: finite(message.since_s),
    robotId:
      typeof message.robot_id === "string" ? message.robot_id : undefined,
    tilt: finite(message.tilt_deg),
    roll: finite(message.roll_deg),
    pitch: finite(message.pitch_deg),
    speed: finite(message.speed_mps),
    height: finite(message.height_m),
    t: sim ?? header,
    timeSource:
      sim !== undefined
        ? "sim_time_s"
        : header !== undefined
          ? "header.stamp"
          : "없음",
    received,
    issue:
      code === undefined
        ? "정수 code 필드가 없습니다."
        : locomotionStates[code] === undefined
          ? "명세에 없는 상태 코드입니다."
          : state !== undefined && state !== label
            ? `code ${code}와 state '${state}'가 다릅니다.`
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
  locomotion?: LocomotionStatus;
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
  locomotion: string;
  prior: string;
  path: string;
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
  locomotion: "/locomotion/status",
  prior: "/localization/reference_map",
  // S-012 global path. Nav2 planner_server publishes nav_msgs/Path on /plan by default.
  path: "/plan",
  twistValid: true,
  tolerance: 0.05,
  timeout: 1500,
  mapVerified: false,
};
// Where the dashboard listens. All are read-only Foxglove bridges; replay/run-demo.sh starts the
// local ones on 8765. "custom" keeps whatever address and topics the settings form holds.
export const sources = {
  bag: {
    label: "핸드헬드 기록 재생 (11-15 bag · Super-LIO)",
    start: "replay/run-demo.sh bag",
    config: { url: "ws://localhost:8765", gt: "" },
  },
  sim: {
    label: "시뮬레이터 (Isaac Sim·MuJoCo 등)",
    start:
      "시뮬레이터가 RUN.md의 토픽을 내보내고 foxglove_bridge를 실행",
    config: { url: "ws://localhost:8765", gt: "/ground_truth/odom" },
  },
  robot: {
    label: "실물 로봇 (원격 연결)",
    start:
      "로봇 PC에서 foxglove_bridge address:=0.0.0.0 실행 후 ⚙에서 ws://<로봇 IP>:8765 입력",
    config: { gt: "" },
  },
  custom: {
    label: "직접 지정 (다른 주소·토픽)",
    start: "",
    config: {},
  },
} as const satisfies Record<
  string,
  { label: string; start: string; config: Partial<Config> }
>;
export type Source = keyof typeof sources;
// Saved choice: unknown keys and wrong types fall back to the defaults.
export function savedSettings(raw: string | null): {
  source: Source;
  config: Config;
} {
  let saved: any = {};
  try {
    saved = JSON.parse(raw ?? "{}") ?? {};
  } catch {
    saved = {};
  }
  const config = { ...defaults };
  for (const key of Object.keys(defaults) as (keyof Config)[])
    if (typeof saved.config?.[key] === typeof defaults[key])
      (config as any)[key] = saved.config[key];
  const source: Source =
    saved.source in sources ? (saved.source as Source) : "bag";
  return { source, config: { ...config, ...sources[source].config } };
}
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
// Rotate a child-frame vector into the parent frame with a unit quaternion (xyzw).
export function rotate(q: Q, v: V3): V3 {
  const tx = 2 * (q.y * v.z - q.z * v.y),
    ty = 2 * (q.z * v.x - q.x * v.z),
    tz = 2 * (q.x * v.y - q.y * v.x);
  return {
    x: v.x + q.w * tx + (q.y * tz - q.z * ty),
    y: v.y + q.w * ty + (q.z * tx - q.x * tz),
    z: v.z + q.w * tz + (q.x * ty - q.y * tx),
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
  // Odometry twist is expressed in child_frame_id (REP-105); rotate it into the map
  // frame before taking the horizontal part. An exactly-zero vector is treated as
  // unfilled (upstream FAST-LIO2 leaves twist at 0), so the speed falls back to poses.
  const twist =
    p.v && [p.v.x, p.v.y, p.v.z ?? 0].every(Number.isFinite) ? p.v : undefined;
  const unfilled = twist !== undefined && !twist.x && !twist.y && !twist.z;
  const validTwist = Boolean(c.twistValid && twist && !unfilled);
  const mapVelocity = validTwist ? rotate(p.q, twist!) : undefined;
  const speed = mapVelocity
    ? Math.hypot(mapVelocity.x, mapVelocity.y)
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
    speedSource: validTwist
      ? "LIO twist 선속도"
      : c.twistValid && unfilled
        ? "pose 차분 (twist 미기재)"
        : "pose 차분",
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
// nav_msgs/Path → the poses' positions as a polyline in the path's frame (empty path = no plan).
export function globalPath(m: any): Cloud {
  const poses: any[] = Array.isArray(m.poses) ? m.poses : [];
  const out: number[] = [];
  for (const ps of poses) {
    const p = ps?.pose?.position;
    if (p && [p.x, p.y, p.z].every(Number.isFinite)) out.push(p.x, p.y, p.z);
  }
  return {
    t: stamp(m.header?.stamp),
    frame: m.header?.frame_id || poses[0]?.header?.frame_id || "",
    points: new Float32Array(out),
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
  locomotion: LocomotionStatus[] = [],
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
    "locomotion_code",
    "locomotion_state",
    "locomotion_severity",
    "locomotion_reason",
    "locomotion_time_s",
    "locomotion_time_source",
    "locomotion_tilt_deg",
    "locomotion_roll_deg",
    "locomotion_pitch_deg",
    "locomotion_speed_m_s",
    "locomotion_height_m",
    "locomotion_issue",
    "locomotion_payload_json",
  ];
  const locomotionColumns = (s?: LocomotionStatus) => ({
    locomotion_code: s?.code,
    locomotion_state: s?.label,
    locomotion_severity: s?.severity,
    locomotion_reason: s?.reason,
    locomotion_time_s: s?.t,
    locomotion_time_source: s?.timeSource,
    locomotion_tilt_deg: s?.tilt,
    locomotion_roll_deg: s?.roll,
    locomotion_pitch_deg: s?.pitch,
    locomotion_speed_m_s: s?.speed,
    locomotion_height_m: s?.height,
    locomotion_issue: s?.issue,
  });
  const json = (raw: unknown) =>
    JSON.stringify(raw, (_, v) => (typeof v === "bigint" ? String(v) : v));
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
      ...locomotionColumns(s.locomotion),
    })),
    ...events.map((e) => ({ kind: "event", sim_time_s: e.t, status: e.event })),
    ...statuses.map((s) => ({
      kind: "localization_status",
      sim_time_s: s.t,
      received_wall_ms: s.received,
      ...statusColumns(s),
      localization_payload_json: json(s.raw),
    })),
    ...locomotion.map((s) => ({
      kind: "locomotion_status",
      sim_time_s: s.t,
      received_wall_ms: s.received,
      ...locomotionColumns(s),
      locomotion_payload_json: json(s.raw),
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
