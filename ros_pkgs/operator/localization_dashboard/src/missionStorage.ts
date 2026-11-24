// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import {
  demoMap,
  exampleMission,
  newOperationId,
  type MapIdentity,
  type Mission,
  type Waypoint,
} from "./operation";

const missionsKey = "hypernova.operations.missions.v1";
const draftKey = "hypernova.operations.draft.v1";
const campusDraftKey = "hypernova.operations.campus-draft.v1";

type StoredValue<T> = { value: T; error?: string };

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isWaypoint(value: unknown): value is Waypoint {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    finite(value.x) &&
    finite(value.y) &&
    finite(value.yaw) &&
    finite(value.dwell)
  );
}

function isMission(value: unknown): value is Mission {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    (value.routing === undefined ||
      value.routing === "walkway" ||
      value.routing === "campus") &&
    isObject(value.map) &&
    typeof value.map.id === "string" &&
    typeof value.map.version === "string" &&
    typeof value.map.frame === "string" &&
    Array.isArray(value.waypoints) &&
    value.waypoints.length <= 50 &&
    value.waypoints.every(isWaypoint) &&
    new Set(value.waypoints.map(({ id }) => id)).size === value.waypoints.length
  );
}

function load<T>(
  key: string,
  fallback: T,
  validate: (value: unknown) => value is T,
  storage?: Pick<Storage, "getItem">,
): StoredValue<T> {
  try {
    const raw = (storage ?? window.localStorage).getItem(key);
    if (raw === null) return { value: fallback };
    const parsed: unknown = JSON.parse(raw);
    if (validate(parsed)) return { value: parsed };
    return { value: fallback, error: "저장된 임무 형식을 읽을 수 없습니다." };
  } catch {
    return {
      value: fallback,
      error: "브라우저의 임무 데이터를 읽을 수 없습니다.",
    };
  }
}

function save(
  key: string,
  value: unknown,
  storage?: Pick<Storage, "setItem">,
): string | undefined {
  try {
    (storage ?? window.localStorage).setItem(key, JSON.stringify(value));
  } catch {
    return "브라우저에 저장할 수 없습니다. 현재 화면에서 임무를 사용할 수 있습니다.";
  }
}

export function loadMissions(storage?: Pick<Storage, "getItem">) {
  return load(
    missionsKey,
    [],
    (value): value is Mission[] =>
      Array.isArray(value) &&
      value.every(isMission) &&
      new Set(value.map(({ id }) => id)).size === value.length,
    storage,
  );
}

export function saveMissions(
  missions: readonly Mission[],
  storage?: Pick<Storage, "setItem">,
) {
  return save(missionsKey, missions, storage);
}

export function loadDraft(storage?: Pick<Storage, "getItem">) {
  return load(
    draftKey,
    structuredClone(exampleMission),
    (value): value is Mission => isMission(value) && value.routing !== "campus",
    storage,
  );
}

export function loadCampusDraft(storage?: Pick<Storage, "getItem">) {
  const stored = load<Mission | null>(
    campusDraftKey,
    null,
    (value): value is Mission | null =>
      value === null || (isMission(value) && value.routing === "campus"),
    storage,
  );
  return { ...stored, value: stored.value ?? undefined };
}

export function saveCampusDraft(
  draft: Mission | undefined,
  storage?: Pick<Storage, "setItem">,
) {
  return save(campusDraftKey, draft ?? null, storage);
}

export function saveDraft(draft: Mission, storage?: Pick<Storage, "setItem">) {
  return save(draftKey, draft, storage);
}

export function createMission(): Mission {
  const { id, version, frame } = demoMap;
  return {
    id: newOperationId(),
    name: "새 순찰 임무",
    map: { id, version, frame },
    waypoints: [],
  };
}

export function createWaypoint(
  point: Pick<Waypoint, "x" | "y">,
  index: number,
): Waypoint {
  return {
    id: newOperationId(),
    name: `경유점 ${index + 1}`,
    x: point.x,
    y: point.y,
    yaw: 0,
    dwell: 1,
  };
}

export function createRouteWaypoints(
  points: readonly Pick<Waypoint, "x" | "y">[],
): Waypoint[] {
  return points.map((point, index) => {
    const from = points[index + 1] ? point : points[Math.max(0, index - 1)];
    const to = points[index + 1] ?? point;
    const yaw = (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI;
    return { ...createWaypoint(point, index), yaw, dwell: 0 };
  });
}

export function createCampusMission(
  map: MapIdentity,
  points: readonly Pick<Waypoint, "x" | "y">[],
): Mission {
  return {
    id: newOperationId(),
    name: "캠퍼스 순찰 임무",
    map: { ...map },
    routing: "campus",
    waypoints: createRouteWaypoints(points),
  };
}
