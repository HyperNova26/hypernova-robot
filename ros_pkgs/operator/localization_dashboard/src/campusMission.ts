// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
/// <reference types="vite/client" />
import {
  CampusRouter,
  projectCampus,
  type CampusMapData,
  type CampusPoint,
} from "./campusRouting";
import type { CampusMissionNetwork } from "./operation";

// OSM nodes on the road north of the hall and on its north facade.
const hallRoadNodes = ["1762481725", "1762481729"];
const hallFacadeNodes = ["4681081847", "4681081858"];
const hallDemoDistance = 22; // metres toward the Plaza of Contemplation

export function hallDemoRoute(data: CampusMapData): CampusPoint[] {
  const [west, east, facadeWest, facadeEast] = [
    ...hallRoadNodes,
    ...hallFacadeNodes,
  ].map((id) => {
    const location = data.nodes[id];
    return location && projectCampus(data, location);
  });
  if (!west || !east || !facadeWest || !facadeEast) return [];

  const dx = east.x - west.x;
  const dy = east.y - west.y;
  const facadeCenter = (facadeWest.x + facadeEast.x) / 2;
  const start = (facadeCenter - west.x) / dx;
  if (!(start > 0 && start < 1)) return [];

  const end = Math.max(0, start - hallDemoDistance / Math.hypot(dx, dy));
  return [start, end].map((fraction) => ({
    x: west.x + fraction * dx,
    y: west.y + fraction * dy,
  }));
}

const boundaryTolerance = 1e-6; // metres; retain points on the outline

type BoundaryEdge = readonly [CampusPoint, CampusPoint];

function insideCampus(point: CampusPoint, edges: BoundaryEdge[]) {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return false;
  let inside = false;
  for (const [a, b] of edges) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const x = point.x - a.x;
    const y = point.y - a.y;
    const length = Math.hypot(dx, dy);
    if (length > 0) {
      const along = (x * dx + y * dy) / length;
      const deviation = Math.abs(x * dy - y * dx) / length;
      if (
        deviation <= boundaryTolerance &&
        along >= -boundaryTolerance &&
        along <= length + boundaryTolerance
      )
        return true;
    }
    if (a.y > point.y !== b.y > point.y && point.x < a.x + (dx * y) / dy) {
      inside = !inside;
    }
  }
  return inside;
}

function withinCampus(
  from: CampusPoint,
  to: CampusPoint,
  edges: BoundaryEdge[],
) {
  if (!insideCampus(from, edges) || !insideCampus(to, edges)) return false;
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  if (length <= boundaryTolerance) return true;
  const dx = (to.x - from.x) / length;
  const dy = (to.y - from.y) / length;

  // Inside status can change only where the move touches the outline.
  // Test those intervals individually so a move cannot cut a concave corner.
  const intersections = [0, length];
  const addIntersection = (distance: number) => {
    if (distance > 0 && distance < length) intersections.push(distance);
  };
  for (const [a, b] of edges) {
    const ax = a.x - from.x;
    const ay = a.y - from.y;
    const bx = b.x - from.x;
    const by = b.y - from.y;
    const distA = ax * dx + ay * dy;
    const distB = bx * dx + by * dy;
    const sideA = ay * dx - ax * dy;
    const sideB = by * dx - bx * dy;
    if (Math.abs(sideA) <= boundaryTolerance) addIntersection(distA);
    if (Math.abs(sideB) <= boundaryTolerance) addIntersection(distB);
    if ((sideA < 0 && sideB > 0) || (sideA > 0 && sideB < 0)) {
      addIntersection(distA + ((distB - distA) * sideA) / (sideA - sideB));
    }
  }
  intersections.sort((a, b) => a - b);
  return intersections.slice(1).every((end, index) => {
    const start = intersections[index];
    if (end - start <= boundaryTolerance) return true;
    const middle = (start + end) / 2;
    return insideCampus(
      { x: from.x + middle * dx, y: from.y + middle * dy },
      edges,
    );
  });
}

export function campusMissionNetwork(
  data: CampusMapData,
  router = new CampusRouter(data),
): CampusMissionNetwork {
  const network: CampusMissionNetwork = {
    identity: {
      id: "khu-global-campus-osm",
      frame: "khu_campus_osm_local",
      version: data.source.timestamp,
    },
    containsRoute: (points) => router.containsRoute(points),
  };
  if (!isCampusOutline(data.campusOutline)) return network;
  const outline = data.campusOutline.map((position) =>
    projectCampus(data, position),
  );
  const edges = outline
    .slice(1)
    .map((point, index) => [outline[index], point] as const);
  const allowsDemoMotion = (from: CampusPoint, to: CampusPoint) =>
    withinCampus(from, to, edges);
  network.allowsDemoMotion = allowsDemoMotion;

  const [start, forward] = hallDemoRoute(data);
  if (start && forward) {
    if (
      router.containsRoute([start, forward]) &&
      allowsDemoMotion(start, forward)
    ) {
      network.demoStart = {
        ...start,
        yaw:
          (Math.atan2(forward.y - start.y, forward.x - start.x) * 180) /
          Math.PI,
      };
    }
  }
  return network;
}

function isCoordinate(value: unknown) {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    value.every((part) => typeof part === "number" && Number.isFinite(part)) &&
    Math.abs(value[0]) <= 90 &&
    Math.abs(value[1]) <= 180
  );
}

function isCampusOutline(
  outline: unknown,
): outline is NonNullable<CampusMapData["campusOutline"]> {
  if (
    !Array.isArray(outline) ||
    outline.length < 4 ||
    !outline.every(isCoordinate)
  ) {
    return false;
  }
  const first = outline[0];
  const last = outline.at(-1);
  return (
    first[0] === last[0] &&
    first[1] === last[1] &&
    new Set(outline.map(([lat, lon]) => `${lat},${lon}`)).size >= 3
  );
}

const featureKinds = new Set(["walkway", "road", "building", "water", "green"]);

function isCampusMap(value: unknown): value is CampusMapData {
  if (!value || typeof value !== "object") return false;
  const { source, origin, campusOutline, nodes, features, places } =
    value as Partial<CampusMapData>;
  return (
    !!source &&
    [source.url, source.timestamp, source.attribution, source.license].every(
      (field) => typeof field === "string" && field.trim().length > 0,
    ) &&
    !!origin &&
    isCoordinate([origin.lat, origin.lon]) &&
    (campusOutline === undefined || isCampusOutline(campusOutline)) &&
    !!nodes &&
    typeof nodes === "object" &&
    !Array.isArray(nodes) &&
    Object.values(nodes).every(isCoordinate) &&
    Array.isArray(features) &&
    features.every(
      (feature) =>
        !!feature &&
        Number.isSafeInteger(feature.id) &&
        featureKinds.has(feature.kind) &&
        Array.isArray(feature.nodes) &&
        feature.nodes.every(
          (id: unknown) =>
            typeof id === "number" &&
            Number.isSafeInteger(id) &&
            Object.hasOwn(nodes, id),
        ) &&
        (feature.name === undefined || typeof feature.name === "string"),
    ) &&
    features.some(
      (feature) => feature.kind === "walkway" && feature.nodes.length >= 2,
    ) &&
    (places === undefined ||
      (Array.isArray(places) &&
        places.every(
          (place) =>
            !!place &&
            isCoordinate(place.position) &&
            typeof place.name === "string",
        )))
  );
}

export async function loadCampusMap(
  signal?: AbortSignal,
): Promise<CampusMapData> {
  const response = await fetch(`${import.meta.env.BASE_URL}khu-osm.json`, {
    signal,
  });
  if (!response.ok) throw new Error("캠퍼스 지도를 불러오지 못했습니다.");
  const data: unknown = await response.json();
  if (!isCampusMap(data)) throw new Error("등록된 보행로 데이터가 없습니다.");
  return data;
}
