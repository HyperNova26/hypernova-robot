// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import type { localizationStates } from "./model";
import {
  snapWalkway,
  walkwayRoute,
  walkwaySegment,
  walkwayWidth,
  type WalkwayPoint,
} from "./walkways";

export type OperationMode = "TELEOP" | "AUTO";
export type OperationPose = { x: number; y: number; yaw: number };
export type OperationVelocity = { forward: number; left: number; turn: number };
export type MapIdentity = { id: string; version: string; frame: string };
export type CampusMissionNetwork = {
  identity: MapIdentity;
  containsRoute: (points: readonly WalkwayPoint[]) => boolean;
  demoStart?: OperationPose;
  allowsDemoMotion?: (from: WalkwayPoint, to: WalkwayPoint) => boolean;
};
export type Waypoint = OperationPose & {
  id: string;
  name: string;
  dwell: number;
};
export type Mission = {
  id: string;
  name: string;
  map: MapIdentity;
  waypoints: Waypoint[];
  routing?: "walkway" | "campus";
};
type WalkwayApproach = {
  from: WalkwayPoint;
  points: WalkwayPoint[];
  nextIndex: number;
};
export type MissionRun = {
  mission: Mission;
  status: "running" | "paused" | "completed" | "cancelled" | "failed";
  targetIndex: number;
  approach?: WalkwayApproach;
  resumePose?: OperationPose;
  reachedAt?: number;
  dwellElapsed: number;
  reason?: string;
};

export const demoMap = {
  id: "campus-demo",
  version: "1",
  frame: "campus_demo_map",
  label: "전자정보대학관 주변 · 합성 평면",
  bounds: { minX: -12, maxX: 12, minY: -8, maxY: 8 },
};
const origin: OperationPose = { x: -8, y: -4, yaw: 0 };
export const exampleMission: Mission = {
  id: "khu-global-electronics-walkway",
  name: "전자정보대학관 보행로 순찰",
  routing: "walkway",
  map: { id: demoMap.id, version: demoMap.version, frame: demoMap.frame },
  waypoints: [
    {
      id: "entrance",
      name: "대학관 출입구 앞",
      x: -5,
      y: -4,
      yaw: 0,
      dwell: 1,
    },
    {
      id: "walkway-start",
      name: "인접 보행로 진입",
      x: 0,
      y: -4,
      yaw: 90,
      dwell: 1,
    },
    {
      id: "walkway-check",
      name: "보행로 점검 지점",
      x: 0,
      y: 1,
      yaw: 90,
      dwell: 2,
    },
    {
      id: "turnaround",
      name: "보행로 회차 지점",
      x: 0,
      y: 4,
      yaw: 180,
      dwell: 1,
    },
  ],
};

let fallbackId = 0;
export function newOperationId() {
  return (
    globalThis.crypto?.randomUUID?.() ?? `demo-${Date.now()}-${++fallbackId}`
  );
}

function sameMap(a: MapIdentity, b: MapIdentity) {
  return a.id === b.id && a.version === b.version && a.frame === b.frame;
}

export function missionError(
  mission: Mission,
  map: MapIdentity = demoMap,
  campusNetwork?: CampusMissionNetwork,
) {
  if (!mission.name.trim()) return "임무 이름을 입력하세요.";
  const campus = mission.routing === "campus";
  if (!campus && campusNetwork?.demoStart)
    return "현재 캠퍼스 지도에서 그린 임무를 선택하세요.";
  const activeMap = campus ? campusNetwork?.identity : map;
  if (!activeMap) return "캠퍼스 보행로 지도를 불러오세요.";
  if (!sameMap(mission.map, activeMap))
    return "이 임무의 지도 ID·버전·frame이 현재 지도와 일치해야 합니다.";
  const minimumWaypoints = campus ? 2 : 1;
  if (
    mission.waypoints.length < minimumWaypoints ||
    mission.waypoints.length > 50
  )
    return `Waypoint를 ${minimumWaypoints}개 이상 50개 이하로 지정하세요.`;
  const { minX, maxX, minY, maxY } = demoMap.bounds;
  const ids = new Set<string>();
  for (const [index, point] of mission.waypoints.entries()) {
    const label = `Waypoint ${index + 1}`;
    if (!point.id || ids.has(point.id))
      return `${label}의 식별자가 유효하지 않습니다.`;
    if (!point.name.trim()) return `${label}의 이름을 입력하세요.`;
    if (![point.x, point.y].every(Number.isFinite))
      return `${label}의 지도 좌표를 확인하세요.`;
    if (
      !campus &&
      (point.x < minX || point.x > maxX || point.y < minY || point.y > maxY)
    )
      return `${label}을 데모 평면 지면 안에 배치하세요.`;
    if (!Number.isFinite(point.yaw) || point.yaw < -180 || point.yaw > 180)
      return `${label}의 도착 방향을 -180°에서 180° 사이로 지정하세요.`;
    if (!Number.isFinite(point.dwell) || point.dwell < 0 || point.dwell > 60)
      return `${label}의 대기 시간을 0초에서 60초 사이로 지정하세요.`;
    if (mission.routing === "walkway") {
      if (!walkwaySegment(point, point))
        return `${label}을 보행로 중심선에 배치하세요.`;
      const previous = mission.waypoints[index - 1];
      if (previous && !walkwaySegment(previous, point))
        return `Waypoint ${index}–${index + 1} 구간이 보행로를 벗어납니다.`;
    }
    ids.add(point.id);
  }
  if (campus && !campusNetwork?.containsRoute(mission.waypoints))
    return "캠퍼스 경로의 모든 구간을 연결된 보행로에 배치하세요.";
}

const walkwayTolerance = 1e-8;

function planWalkwayApproach(
  pose: WalkwayPoint,
  mission: Mission,
  targetIndex: number,
): WalkwayApproach | string | undefined {
  if (mission.routing !== "walkway") return;
  const snap = snapWalkway(pose);
  if (!snap || snap.distance > walkwayWidth / 2 + walkwayTolerance)
    return "TELEOP으로 로봇을 보행로 안에 옮기세요.";
  const target = mission.waypoints[targetIndex];
  const route = target && walkwayRoute(snap.point, target);
  if (!route?.length) return "현재 위치에서 목표까지 이어진 보행로가 없습니다.";
  const needsProjection = snap.distance > walkwayTolerance;
  if (route.length === 1 && !needsProjection) return;
  const points = route.slice(1, -1);
  if (needsProjection) points.unshift(snap.point);
  return { from: { x: pose.x, y: pose.y }, points, nextIndex: 0 };
}

export function walkwayApproachError(
  pose: WalkwayPoint,
  mission: Mission,
  targetIndex = 0,
) {
  const plan = planWalkwayApproach(pose, mission, targetIndex);
  if (typeof plan === "string") return plan;
}

export type IncidentKind =
  | "degraded"
  | "lost"
  | "timeout"
  | "disconnect"
  | "obstacle"
  | "battery"
  | "field";
export const incidentKinds: IncidentKind[] = [
  "degraded",
  "lost",
  "timeout",
  "disconnect",
  "obstacle",
  "battery",
  "field",
];
export type IncidentDescription = {
  title: string;
  severity: "critical" | "warning" | "info";
  category: "system" | "field";
  description: string;
  impact: string;
  action: string;
};
export const incidentCatalog: Record<IncidentKind, IncidentDescription> = {
  degraded: {
    title: "위치추정 품질 저하",
    severity: "warning",
    category: "system",
    description: "모의 위치추정 상태가 DEGRADED로 전환되었습니다.",
    impact: "위치 신뢰도가 낮아졌습니다. 실행 중인 임무는 계속 진행합니다.",
    action: "지도와 센서 상태를 확인하고 필요하면 임무를 일시정지하세요.",
  },
  lost: {
    title: "위치추정 유실",
    severity: "critical",
    category: "system",
    description: "모의 위치추정 상태가 LOST로 전환되었습니다.",
    impact: "이동이 중단되고 실행 중이던 AUTO 임무가 일시정지됩니다.",
    action:
      "위치추정이 회복되면 운용 화면에서 임무 재개 또는 취소를 선택하세요.",
  },
  timeout: {
    title: "입력 데이터 시간 초과",
    severity: "critical",
    category: "system",
    description:
      "모의 Odometry 입력이 중단되어 INPUT_TIMEOUT으로 전환되었습니다.",
    impact: "마지막 수신 위치를 유지하고 이동 명령을 차단합니다.",
    action:
      "데이터 수신을 복구한 뒤 위치추정 상태를 확인하고 임무를 재개하세요.",
  },
  disconnect: {
    title: "통신 끊김",
    severity: "critical",
    category: "system",
    description: "모의 텔레메트리 연결이 끊겼습니다.",
    impact: "마지막 수신 위치를 유지하고 이동 명령을 차단합니다.",
    action: "연결이 돌아오면 수신 시각과 위치를 확인하고 운용을 재개하세요.",
  },
  obstacle: {
    title: "장애물로 진행 불가",
    severity: "warning",
    category: "system",
    description: "모의 시나리오에서 현재 구간의 진행이 차단되었습니다.",
    impact: "AUTO 임무가 일시정지됩니다. TELEOP으로 개입할 수 있습니다.",
    action:
      "대기, 임무 취소 또는 TELEOP 개입을 선택하세요. 원인 해소 뒤 AUTO를 재개할 수 있습니다.",
  },
  battery: {
    title: "배터리 부족",
    severity: "critical",
    category: "system",
    description: "모의 배터리 잔량이 8%로 전환되었습니다.",
    impact:
      "이동이 차단되고 실행 중이거나 일시정지된 임무가 실패로 종료됩니다.",
    action: "모의 배터리 상태를 복구한 뒤 새 임무 실행을 선택하세요.",
  },
  field: {
    title: "보행로 통행 방해물",
    severity: "warning",
    category: "field",
    description:
      "전자정보대학관 보행로 순찰 시나리오에서 통행을 방해하는 물체가 보고되었습니다.",
    impact: "사건 위치가 지도에 표시됩니다. 기존 임무는 계속 진행합니다.",
    action:
      "사건 기록을 열어 발생 시점과 위치를 확인하고 대응 내용을 남기세요.",
  },
};

type IncidentHistoryType =
  | "opened"
  | "repeated"
  | "acknowledged"
  | "muted"
  | "resolved"
  | "closed"
  | "note";
export type Incident = IncidentDescription & {
  id: string;
  kind: IncidentKind;
  openedAt: number;
  lastAt: number;
  count: number;
  pose: OperationPose;
  map?: MapIdentity;
  missionId?: string;
  missionName?: string;
  waypointId?: string;
  waypointName?: string;
  acknowledgedAt?: number;
  mutedAt?: number;
  resolvedAt?: number;
  closedAt?: number;
  history: { at: number; type: IncidentHistoryType; text: string }[];
};

export type OperationState = {
  sessionId: string;
  timeOrigin: number;
  mode: OperationMode;
  pose: OperationPose;
  trail: OperationPose[];
  campus?: { map: MapIdentity; pose: OperationPose; trail: OperationPose[] };
  requested: OperationVelocity;
  observed: OperationVelocity;
  teleopSpeed: number;
  lastReceived: number;
  connected: boolean;
  localization: (typeof localizationStates)[number];
  battery: number;
  run?: MissionRun;
  incidents: Incident[];
};

function pausedRun(
  run: MissionRun,
  state: OperationState,
  reason: string,
): MissionRun {
  const pose =
    run.mission.routing === "campus" ? state.campus?.pose : undefined;
  return { ...run, status: "paused", reason, resumePose: pose && { ...pose } };
}

function planCampusResume(
  state: OperationState,
  run: MissionRun,
  network?: CampusMissionNetwork,
): WalkwayApproach | string | undefined {
  const invalid = missionError(run.mission, demoMap, network);
  if (invalid) return invalid;
  const { campus } = state;
  const { resumePose, approach } = run;
  if (!campus || !resumePose || !sameMap(campus.map, run.mission.map))
    return "같은 캠퍼스 지도의 일시정지 위치를 확인하세요.";
  const { x, y } = campus.pose;
  if (Math.hypot(x - resumePose.x, y - resumePose.y) <= walkwayTolerance)
    return approach;
  const points = [
    resumePose,
    ...(approach?.points.slice(approach.nextIndex) ?? []),
  ];
  const remaining = run.mission.waypoints.slice(run.targetIndex);
  if (!network?.containsRoute([campus.pose, ...points, ...remaining]))
    return "일시정지 지점과 이어진 보행로로 TELEOP 이동 후 다시 시도하거나 임무를 취소하세요.";
  return { from: { x, y }, points, nextIndex: 0 };
}

export function campusResumeError(
  state: OperationState,
  network?: CampusMissionNetwork,
) {
  const run = state.run;
  if (run?.status !== "paused" || run.mission.routing !== "campus") return;
  const plan = planCampusResume(state, run, network);
  if (typeof plan === "string") return plan;
}

type EngineCommand =
  | { type: "mode"; mode: OperationMode }
  | ({ type: "teleop" } & OperationVelocity)
  | { type: "speed"; speed: number }
  | { type: "start"; mission: Mission }
  | {
      type:
        | "pause"
        | "resume"
        | "cancel"
        | "stop"
        | "reset"
        | "release"
        | "suspend";
    }
  | { type: "inject" | "recover"; kind: IncidentKind }
  | { type: "acknowledge" | "mute" | "close"; incidentId: string }
  | { type: "note"; incidentId: string; text: string };
export type OperationCommand = EngineCommand & { deadline?: number };
type CommandErrorCode =
  "unavailable" | "blocked" | "invalid" | "duplicate" | "timeout";
export type CommandResult =
  | { ok: true; id: number }
  | { ok: false; id: number; code: CommandErrorCode; reason: string };
export interface CommandAdapter {
  request(command: OperationCommand, now?: number): CommandResult;
}

const zero: OperationVelocity = { forward: 0, left: 0, turn: 0 };
const radians = Math.PI / 180;
const autoSpeed = 1.5;
const turnSpeed = 90;
const denyCampusMovement = () => false;
const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));
const normalizeYaw = (angle: number) =>
  ((((angle + 180) % 360) + 360) % 360) - 180;
const moving = (velocity: OperationVelocity) =>
  Boolean(velocity.forward || velocity.left || velocity.turn);
const activeFault = (state: OperationState, kind: IncidentKind) =>
  state.incidents.some(
    (incident) =>
      incident.kind === kind &&
      incident.resolvedAt === undefined &&
      incident.closedAt === undefined,
  );
const activeRun = (run: MissionRun | undefined) =>
  run?.status === "running" || run?.status === "paused";
export const teleopSpeedRange = { min: 0.2, max: 2, initial: 0.8 };

export function commandBlock(state: OperationState, mode = state.mode) {
  if (!state.connected) return "모의 통신을 복구하세요.";
  if (state.localization === "INPUT_TIMEOUT")
    return "모의 데이터 수신을 복구하세요.";
  if (state.localization === "LOST") return "모의 위치추정을 복구하세요.";
  if (activeFault(state, "battery")) return "모의 배터리 상태를 복구하세요.";
  if (mode === "AUTO" && activeFault(state, "obstacle"))
    return "장애물 사건의 원인을 해소하세요.";
}

function campusAt(map: MapIdentity, pose: OperationPose) {
  const start = { ...pose };
  return { map: { ...map }, pose: start, trail: [start] };
}

function newState(now: number, network?: CampusMissionNetwork): OperationState {
  return {
    sessionId: newOperationId(),
    timeOrigin: now,
    mode: "TELEOP",
    pose: { ...origin },
    trail: [{ ...origin }],
    campus: network?.demoStart
      ? campusAt(network.identity, network.demoStart)
      : undefined,
    requested: zero,
    observed: zero,
    teleopSpeed: teleopSpeedRange.initial,
    lastReceived: now,
    connected: true,
    localization: "TRACKING",
    battery: 96,
    incidents: [],
  };
}

function updateConditions(state: OperationState, now: number): OperationState {
  const connected = !activeFault(state, "disconnect");
  const localization = activeFault(state, "timeout")
    ? "INPUT_TIMEOUT"
    : activeFault(state, "lost")
      ? "LOST"
      : activeFault(state, "degraded")
        ? "DEGRADED"
        : "TRACKING";
  return {
    ...state,
    connected,
    localization,
    lastReceived:
      connected && localization !== "INPUT_TIMEOUT" ? now : state.lastReceived,
    battery: activeFault(state, "battery") ? 8 : 96,
  };
}

function missionSnapshot(mission: Mission): Mission {
  return {
    ...mission,
    map: { ...mission.map },
    waypoints: mission.waypoints.map((point) => ({ ...point })),
  };
}

function teleopPose(
  pose: OperationPose,
  requested: OperationVelocity,
  dt: number,
  allowsCampusMotion?: CampusMissionNetwork["allowsDemoMotion"],
) {
  const yaw = pose.yaw * radians;
  const candidate = {
    x:
      pose.x +
      (Math.cos(yaw) * requested.forward - Math.sin(yaw) * requested.left) * dt,
    y:
      pose.y +
      (Math.sin(yaw) * requested.forward + Math.cos(yaw) * requested.left) * dt,
  };
  const { minX, maxX, minY, maxY } = demoMap.bounds;
  const { x, y } = allowsCampusMotion
    ? allowsCampusMotion(pose, candidate)
      ? candidate
      : pose
    : { x: clamp(candidate.x, minX, maxX), y: clamp(candidate.y, minY, maxY) };
  const dx = (x - pose.x) / dt;
  const dy = (y - pose.y) / dt;
  return {
    pose: { x, y, yaw: normalizeYaw(pose.yaw + requested.turn * dt) },
    observed: {
      forward: Math.cos(yaw) * dx + Math.sin(yaw) * dy,
      left: Math.cos(yaw) * dy - Math.sin(yaw) * dx,
      turn: requested.turn,
    },
  };
}

function autoPose(
  pose: OperationPose,
  run: MissionRun,
  dt: number,
  now: number,
) {
  const waypoint = run.mission.waypoints[run.targetIndex];
  const approach = run.approach;
  const approachPoint = approach?.points[approach.nextIndex];
  const target = approachPoint ?? waypoint;
  const dx = target.x - pose.x;
  const dy = target.y - pose.y;
  const distance = Math.hypot(dx, dy);
  const step = Math.min(distance, autoSpeed * dt);
  const arrived = step === distance;
  const available = dt - step / autoSpeed;
  const atWaypoint = arrived && !approachPoint;
  const travelYaw = distance > 0 ? Math.atan2(dy, dx) / radians : pose.yaw;
  const yawError = normalizeYaw(
    (atWaypoint ? waypoint.yaw : travelYaw) - pose.yaw,
  );
  const turnTime = distance > 0 && atWaypoint ? available : dt;
  const turn = clamp(yawError, -turnSpeed * turnTime, turnSpeed * turnTime);
  const x = arrived ? target.x : pose.x + dx * (step / distance);
  const y = arrived ? target.y : pose.y + dy * (step / distance);
  const yaw = normalizeYaw(pose.yaw + turn);
  const observed = { forward: step / dt, left: 0, turn: turn / dt };
  if (approach && approachPoint) {
    return {
      pose: { x, y, yaw },
      observed,
      run: arrived
        ? {
            ...run,
            approach: { ...approach, nextIndex: approach.nextIndex + 1 },
          }
        : run,
    };
  }
  if (!arrived || Math.abs(normalizeYaw(waypoint.yaw - yaw)) > 1e-8) {
    return {
      pose: { x, y, yaw },
      observed,
      run:
        run.reachedAt === undefined
          ? run
          : { ...run, reachedAt: undefined, dwellElapsed: 0 },
    };
  }
  const dwellElapsed =
    run.dwellElapsed + Math.max(0, available - Math.abs(turn) / turnSpeed);
  if (dwellElapsed + 1e-8 < waypoint.dwell) {
    return {
      pose: { x, y, yaw },
      observed,
      run: { ...run, reachedAt: run.reachedAt ?? now, dwellElapsed },
    };
  }
  const targetIndex = run.targetIndex + 1;
  if (targetIndex === run.mission.waypoints.length) {
    return {
      pose: { x, y, yaw },
      observed: zero,
      run: {
        ...run,
        targetIndex,
        approach: undefined,
        reachedAt: undefined,
        dwellElapsed: 0,
        status: "completed" as const,
      },
    };
  }
  return {
    pose: { x, y, yaw },
    observed,
    run: {
      ...run,
      targetIndex,
      approach: undefined,
      reachedAt: undefined,
      dwellElapsed: 0,
    },
  };
}

function appendPose(
  trail: OperationPose[],
  pose: OperationPose,
  run?: MissionRun,
  previousRun?: MissionRun,
) {
  const last = trail.at(-1)!;
  const routeCorner =
    run?.mission.routing !== undefined &&
    (run.targetIndex !== previousRun?.targetIndex ||
      run.approach?.nextIndex !== previousRun?.approach?.nextIndex);
  // Keep the trail on the centerline when a short step reaches a junction.
  const threshold = routeCorner ? walkwayTolerance : 0.12;
  if (Math.hypot(pose.x - last.x, pose.y - last.y) < threshold) return trail;
  return [...trail.slice(-799), pose];
}

export class DemoOperations implements CommandAdapter {
  private state: OperationState;
  private lastTick: number;
  private lastAction: number;
  private heldAt = 0;
  private listeners = new Set<() => void>();
  private sequence = 0;
  private held = zero;
  private campusNetwork?: CampusMissionNetwork;

  constructor(now = Date.now()) {
    this.state = newState(now);
    this.lastTick = now;
    this.lastAction = now;
  }

  getSnapshot = () => this.state;

  setCampusNetwork = (network: CampusMissionNetwork) => {
    this.campusNetwork = {
      identity: { ...network.identity },
      containsRoute: (points) => network.containsRoute(points),
      demoStart: network.demoStart && { ...network.demoStart },
      allowsDemoMotion: network.allowsDemoMotion?.bind(network),
    };
    let state = this.state;
    const run = state.run;
    if (run?.status === "running") {
      const reason = missionError(run.mission, demoMap, this.campusNetwork);
      if (reason)
        state = { ...this.release(state), run: pausedRun(run, state, reason) };
    }
    if (
      network.demoStart &&
      (!state.campus || !sameMap(state.campus.map, network.identity))
    ) {
      state = this.release(state);
      if (
        !state.campus ||
        run?.mission.routing !== "campus" ||
        !activeRun(state.run)
      )
        state = {
          ...state,
          campus: campusAt(network.identity, network.demoStart),
        };
    }
    this.apply(state);
  };

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  private apply(state: OperationState) {
    if (state === this.state) return;
    this.state = state;
    this.listeners.forEach((listener) => listener());
  }

  private release(state: OperationState) {
    this.held = zero;
    this.heldAt = 0;
    return moving(state.requested) || moving(state.observed)
      ? { ...state, requested: zero, observed: zero }
      : state;
  }

  tick = (now = Date.now()) => {
    if (!Number.isFinite(now) || now <= this.lastTick) return;
    const previousTick = this.lastTick;
    this.lastTick = now;
    const elapsed = (now - previousTick) / 1000;
    const manualDt = Math.min(
      (now - Math.max(previousTick, this.heldAt)) / 1000,
      0.2,
    );
    const dt = Math.min(elapsed, 0.2);
    // A suspended browser must never catch up an input held before the suspension.
    const staleHold =
      elapsed > 0.75 &&
      this.heldAt <= previousTick &&
      this.state.mode === "TELEOP";
    let state = updateConditions(
      staleHold ? this.release(this.state) : this.state,
      now,
    );
    if (
      state.mode === "TELEOP" &&
      manualDt > 0 &&
      moving(state.requested) &&
      !commandBlock(state)
    ) {
      const network = this.campusNetwork;
      if (network?.demoStart) {
        const campus = state.campus;
        if (campus && sameMap(campus.map, network.identity)) {
          const next = teleopPose(
            campus.pose,
            state.requested,
            manualDt,
            network.allowsDemoMotion ?? denyCampusMovement,
          );
          state = {
            ...state,
            observed: next.observed,
            campus: {
              ...campus,
              pose: next.pose,
              trail: appendPose(campus.trail, next.pose),
            },
          };
        } else {
          state = this.release(state);
        }
      } else {
        const next = teleopPose(state.pose, state.requested, manualDt);
        state = {
          ...state,
          ...next,
          trail: appendPose(state.trail, next.pose),
        };
      }
    } else if (
      state.mode === "AUTO" &&
      state.run?.status === "running" &&
      !commandBlock(state)
    ) {
      const run = state.run;
      if (run.mission.routing === "campus") {
        const campus = state.campus;
        if (campus) {
          const next = autoPose(campus.pose, run, dt, now);
          state = {
            ...state,
            run: next.run,
            observed: this.campusNetwork?.demoStart ? next.observed : zero,
            campus: {
              ...campus,
              pose: next.pose,
              trail: appendPose(campus.trail, next.pose, next.run, run),
            },
          };
        }
      } else {
        const next = autoPose(state.pose, run, dt, now);
        state = {
          ...state,
          ...next,
          trail: appendPose(state.trail, next.pose, next.run, run),
        };
      }
    }
    this.apply(state);
  };

  request = (command: OperationCommand, now = Date.now()): CommandResult => {
    const id = ++this.sequence;
    const success = (): CommandResult => ({ ok: true, id });
    const reject = (
      reason: string,
      code: CommandErrorCode = "invalid",
    ): CommandResult => ({ ok: false, id, reason, code });
    if (!Number.isFinite(now)) return reject("명령 시각이 유효하지 않습니다.");
    now = Math.max(now, this.lastTick, this.lastAction);
    if (
      command.deadline !== undefined &&
      (!Number.isFinite(command.deadline) || now > command.deadline)
    )
      return reject(
        "명령 적용 시간이 초과되었습니다. 다시 시도하세요.",
        "timeout",
      );
    this.lastAction = now;
    let state = this.state;
    const run = state.run;
    switch (command.type) {
      case "reset":
        this.held = zero;
        this.heldAt = 0;
        this.lastTick = now;
        state = newState(now, this.campusNetwork);
        break;
      case "release":
        if (state.mode === "TELEOP") state = this.release(state);
        break;
      case "stop":
      case "suspend":
      case "pause": {
        if (command.type === "pause" && run?.status !== "running")
          return reject("실행 중인 AUTO 임무가 없습니다.", "duplicate");
        state = this.release(state);
        if (run?.status === "running") {
          const reason =
            command.type === "stop"
              ? "운용 정지"
              : command.type === "suspend"
                ? "데이터 출처 전환"
                : "운영자 일시정지";
          state = { ...state, run: pausedRun(run, state, reason) };
        }
        break;
      }
      case "mode": {
        if (command.mode === state.mode)
          return reject("이미 선택된 운용 모드입니다.", "duplicate");
        const why = commandBlock(state, "TELEOP");
        if (why) return reject(why, "blocked");
        state = { ...this.release(state), mode: command.mode };
        if (run?.status === "running")
          state.run = pausedRun(run, state, "TELEOP 개입");
        break;
      }
      case "teleop": {
        const { forward, left, turn } = command;
        if (
          ![forward, left, turn].every(Number.isFinite) ||
          [forward, left, turn].some((axis) => Math.abs(axis) > 1)
        )
          return reject("이동 입력이 범위를 벗어났습니다.");
        if (state.mode !== "TELEOP")
          return reject("TELEOP으로 전환하세요.", "blocked");
        if (!moving(command)) {
          state = this.release(state);
          break;
        }
        const why = commandBlock(state);
        if (why) return reject(why, "blocked");
        const network = this.campusNetwork;
        if (
          network?.demoStart &&
          (!state.campus || !sameMap(state.campus.map, network.identity))
        )
          return reject(
            "캠퍼스 지도 버전을 확인한 뒤 시연을 초기화하세요.",
            "blocked",
          );
        this.held = { forward, left, turn };
        this.heldAt = now;
        state = { ...state, requested: this.manualVelocity(state.teleopSpeed) };
        break;
      }
      case "speed": {
        const { min, max } = teleopSpeedRange;
        if (
          !Number.isFinite(command.speed) ||
          command.speed < min ||
          command.speed > max
        )
          return reject(`시연 속도를 ${min}–${max} m/s 범위로 지정하세요.`);
        state = {
          ...state,
          teleopSpeed: command.speed,
          requested: this.manualVelocity(command.speed),
        };
        break;
      }
      case "start":
      case "resume": {
        if (state.mode !== "AUTO")
          return reject("AUTO로 전환하세요.", "blocked");
        const why = commandBlock(state);
        if (why) return reject(why, "blocked");
        if (command.type === "start") {
          if (activeRun(run))
            return reject(
              "진행 중인 임무를 먼저 완료하거나 취소하세요.",
              "duplicate",
            );
          const invalid = missionError(
            command.mission,
            demoMap,
            this.campusNetwork,
          );
          if (invalid) return reject(invalid);
          const approach = planWalkwayApproach(state.pose, command.mission, 0);
          if (typeof approach === "string") return reject(approach, "blocked");
          let campus = state.campus;
          if (command.mission.routing === "campus") {
            const { x, y, yaw } = command.mission.waypoints[0];
            campus = campusAt(command.mission.map, { x, y, yaw });
          }
          state = {
            ...state,
            campus,
            run: {
              status: "running",
              mission: missionSnapshot(command.mission),
              targetIndex: 0,
              approach,
              dwellElapsed: 0,
            },
          };
        } else {
          if (run?.status !== "paused")
            return reject("일시정지된 임무가 없습니다.", "duplicate");
          const invalid = missionError(
            run.mission,
            demoMap,
            this.campusNetwork,
          );
          if (invalid) return reject(invalid, "blocked");
          const approach =
            run.mission.routing === "campus"
              ? planCampusResume(state, run, this.campusNetwork)
              : planWalkwayApproach(state.pose, run.mission, run.targetIndex);
          if (typeof approach === "string") return reject(approach, "blocked");
          state = {
            ...state,
            run: {
              ...run,
              approach,
              resumePose: undefined,
              status: "running",
              reason: undefined,
              reachedAt: approach ? undefined : run.reachedAt,
              dwellElapsed: approach ? 0 : run.dwellElapsed,
            },
          };
        }
        break;
      }
      case "cancel":
        if (!run || !activeRun(run))
          return reject("취소할 임무가 없습니다.", "duplicate");
        state = {
          ...(state.mode === "AUTO" ? this.release(state) : state),
          run: { ...run, status: "cancelled", reason: "운영자 취소" },
        };
        break;
      case "inject":
      case "recover": {
        if (!incidentKinds.includes(command.kind))
          return reject("알 수 없는 시나리오입니다.");
        if (command.type === "recover" && !activeFault(state, command.kind))
          return reject("해소할 원인이 없습니다.", "duplicate");
        state = updateConditions(this.applyFault(state, command, now), now);
        if (command.type === "inject" && commandBlock(state)) {
          state = this.release(state);
          if (run && activeRun(run) && command.kind === "battery") {
            state = {
              ...state,
              run: {
                ...run,
                status: "failed",
                reason: incidentCatalog.battery.title,
              },
            };
          } else if (run?.status === "running") {
            state = {
              ...state,
              run: pausedRun(run, state, incidentCatalog[command.kind].title),
            };
          }
        }
        break;
      }
      case "acknowledge":
      case "mute":
      case "note":
      case "close": {
        const incident = state.incidents.find(
          (candidate) => candidate.id === command.incidentId,
        );
        if (!incident) return reject("해당 사건을 찾을 수 없습니다.");
        const outcome = this.incidentResponse(incident, command, now);
        if (typeof outcome === "string") return reject(outcome, "blocked");
        state = {
          ...state,
          incidents: state.incidents.map((candidate) =>
            candidate.id === incident.id ? outcome : candidate,
          ),
        };
        break;
      }
    }
    this.apply(state);
    return success();
  };

  private manualVelocity(speed: number) {
    const scale =
      speed / Math.max(1, Math.hypot(this.held.forward, this.held.left));
    return {
      forward: this.held.forward * scale,
      left: this.held.left * scale,
      turn: this.held.turn * turnSpeed,
    };
  }

  private applyFault(
    state: OperationState,
    command: { type: "inject" | "recover"; kind: IncidentKind },
    now: number,
  ): OperationState {
    if (command.type === "recover") {
      return {
        ...state,
        incidents: state.incidents.map((incident) =>
          incident.kind === command.kind &&
          incident.resolvedAt === undefined &&
          incident.closedAt === undefined
            ? addHistory(
                { ...incident, resolvedAt: now },
                now,
                "resolved",
                "모의 원인 해소",
              )
            : incident,
        ),
      };
    }
    const run = activeRun(state.run) ? state.run : undefined;
    const campus =
      this.campusNetwork?.demoStart || run?.mission.routing === "campus"
        ? state.campus
        : undefined;
    const map = campus?.map;
    const existing = state.incidents.find(
      (incident) =>
        incident.kind === command.kind &&
        incident.closedAt === undefined &&
        (map && incident.map
          ? sameMap(map, incident.map)
          : map === incident.map),
    );
    if (existing) {
      const incident = addHistory(
        {
          ...existing,
          lastAt: now,
          count: existing.count + 1,
          resolvedAt: undefined,
          acknowledgedAt:
            existing.resolvedAt === undefined
              ? existing.acknowledgedAt
              : undefined,
        },
        now,
        "repeated",
        "동일 이상 재발생",
      );
      return {
        ...state,
        incidents: state.incidents.map((candidate) =>
          candidate.id === existing.id ? incident : candidate,
        ),
      };
    }
    const target = run?.mission.waypoints[run.targetIndex];
    const incident: Incident = {
      ...incidentCatalog[command.kind],
      kind: command.kind,
      id: newOperationId(),
      openedAt: now,
      lastAt: now,
      count: 1,
      pose: { ...(campus?.pose ?? state.pose) },
      map: map && { ...map },
      missionId: target ? run?.mission.id : undefined,
      missionName: target ? run?.mission.name : undefined,
      waypointId: target?.id,
      waypointName: target?.name,
      history: [{ at: now, type: "opened", text: "모의 시나리오에서 발생" }],
    };
    return { ...state, incidents: [incident, ...state.incidents] };
  }

  private incidentResponse(
    incident: Incident,
    command: Extract<EngineCommand, { incidentId: string }>,
    now: number,
  ) {
    if (incident.closedAt !== undefined) return "종료된 사건입니다.";
    switch (command.type) {
      case "acknowledge":
        if (incident.acknowledgedAt !== undefined)
          return "이미 확인한 알람입니다.";
        return addHistory(
          { ...incident, acknowledgedAt: now },
          now,
          "acknowledged",
          "운영자 알람 확인",
        );
      case "mute":
        if (incident.mutedAt !== undefined)
          return "알림음 해제가 이미 적용되었습니다.";
        return addHistory(
          { ...incident, mutedAt: now },
          now,
          "muted",
          "알림음 끄기",
        );
      case "note": {
        const note = command.text.trim();
        if (!note || note.length > 280)
          return "대응 기록을 1–280자로 입력하세요.";
        return addHistory(incident, now, "note", note);
      }
      case "close":
        if (incident.resolvedAt === undefined)
          return "원인을 해소한 뒤 사건을 종료하세요.";
        return addHistory(
          { ...incident, closedAt: now },
          now,
          "closed",
          "운영자 사건 종료",
        );
    }
  }
}

function addHistory(
  incident: Incident,
  at: number,
  type: IncidentHistoryType,
  text: string,
): Incident {
  return { ...incident, history: [...incident.history, { at, type, text }] };
}
