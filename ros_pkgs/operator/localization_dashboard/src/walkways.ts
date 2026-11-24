// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
export type WalkwayPoint = { x: number; y: number };
type WalkwayPath = { from: WalkwayPoint; to: WalkwayPoint };

const trunk = { from: { x: 0, y: -4 }, to: { x: 0, y: 6.5 } };
export const walkwayPaths: readonly WalkwayPath[] = [
  { from: { x: -11, y: -4 }, to: { x: 10, y: -4 } },
  trunk,
  { from: { x: -9, y: 1 }, to: { x: 9, y: 1 } },
];
export const walkwayWidth = 0.8;

const epsilon = 1e-8;
const endpointTolerance = walkwayWidth;
const sampleTolerance = 1;
const sampleSpacing = 0.35;
const minimumStrokeLength = 0.5;
const maximumWaypoints = 50;

function distance(a: WalkwayPoint, b: WalkwayPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function project(point: WalkwayPoint, { from, to }: WalkwayPath): WalkwayPoint {
  // Each centerline is axis-aligned, so its bounding box is the segment.
  return {
    x: Math.max(
      Math.min(from.x, to.x),
      Math.min(Math.max(from.x, to.x), point.x),
    ),
    y: Math.max(
      Math.min(from.y, to.y),
      Math.min(Math.max(from.y, to.y), point.y),
    ),
  };
}

export function snapWalkway(point: WalkwayPoint) {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return undefined;
  let closest: { point: WalkwayPoint; distance: number } | undefined;
  for (const path of walkwayPaths) {
    const projected = project(point, path);
    const gap = distance(point, projected);
    if (!closest || gap < closest.distance) {
      closest = { point: projected, distance: gap };
    }
  }
  return closest;
}

export function walkwaySegment(a: WalkwayPoint, b: WalkwayPoint) {
  return walkwayPaths.some(
    (path) =>
      distance(project(a, path), a) <= epsilon &&
      distance(project(b, path), b) <= epsilon,
  );
}

function routeOnWalkways(
  start: WalkwayPoint,
  end: WalkwayPoint,
): WalkwayPoint[] {
  if (distance(start, end) <= epsilon) return [start];
  if (walkwaySegment(start, end)) return [start, end];

  // The two crosswalks connect only through the vertical trunk. Their
  // projections onto it are the junctions that the route must pass through.
  const route = [start, project(start, trunk), project(end, trunk), end];
  return route.filter(
    (point, index) =>
      index === 0 || distance(point, route[index - 1]) > epsilon,
  );
}

export function walkwayRoute(start: WalkwayPoint, end: WalkwayPoint) {
  if (!walkwaySegment(start, start) || !walkwaySegment(end, end))
    return undefined;
  return routeOnWalkways(start, end);
}

function appendSimplified(route: WalkwayPoint[], point: WalkwayPoint) {
  const previous = route.at(-1);
  if (previous && distance(previous, point) <= epsilon) return;
  const before = route.at(-2);
  if (before && previous && walkwaySegment(before, point)) {
    const through = distance(before, previous) + distance(previous, point);
    // A collinear point which doubles back carries an intentional turn.
    if (Math.abs(through - distance(before, point)) <= epsilon) route.pop();
  }
  route.push(point);
}

export function planWalkwayStroke(
  points: readonly WalkwayPoint[],
): { points: WalkwayPoint[]; length: number } | { error: string } {
  if (points.length < 2) {
    return { error: "보행로를 따라 드래그해 경로를 그리세요." };
  }
  const start = snapWalkway(points[0]);
  const end = snapWalkway(points[points.length - 1]);
  if (
    !start ||
    !end ||
    start.distance > endpointTolerance ||
    end.distance > endpointTolerance
  ) {
    return { error: "드래그의 시작점과 끝점을 보행로 가까이에 놓으세요." };
  }

  const route = [start.point];
  let previous = start.point;
  for (const raw of points.slice(1, -1)) {
    const snapped = snapWalkway(raw);
    if (!snapped) return { error: "경로를 읽을 수 없습니다. 다시 그리세요." };
    // Samples far from the corridor cannot be anchors. Connect the nearby
    // samples on the graph so a shortcut across a corner stays on the walkways.
    if (
      snapped.distance > sampleTolerance ||
      distance(previous, snapped.point) < sampleSpacing
    )
      continue;
    for (const point of routeOnWalkways(previous, snapped.point).slice(1)) {
      appendSimplified(route, point);
    }
    previous = snapped.point;
  }
  for (const point of routeOnWalkways(previous, end.point).slice(1)) {
    appendSimplified(route, point);
  }

  if (route.length > maximumWaypoints) {
    return { error: "경유점이 50개를 넘었습니다. 경로를 짧게 그리세요." };
  }
  const length = route
    .slice(1)
    .reduce((total, point, index) => total + distance(route[index], point), 0);
  if (length < minimumStrokeLength) {
    return { error: "보행로 위에서 0.5 m 이상 떨어진 지점까지 드래그하세요." };
  }
  return { points: route, length };
}
