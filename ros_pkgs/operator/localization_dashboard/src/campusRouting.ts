// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
export type CampusPoint = { x: number; y: number };
type LatLon = readonly [number, number];
export type CampusMapData = {
  source: {
    url: string;
    timestamp: string;
    attribution: string;
    license: string;
  };
  origin: { lat: number; lon: number };
  campusOutline?: readonly LatLon[];
  nodes: Record<string, LatLon>;
  features: readonly {
    id: number;
    nodes: readonly number[];
    kind: "walkway" | "road" | "building" | "water" | "green";
    name?: string;
  }[];
  places?: readonly { position: LatLon; name: string }[];
};

const degreesToRadians = Math.PI / 180;
const metresPerDegree = 6378137 * degreesToRadians;

export function projectCampus(
  data: CampusMapData,
  [lat, lon]: LatLon,
): CampusPoint {
  return {
    x:
      (lon - data.origin.lon) *
      Math.cos(data.origin.lat * degreesToRadians) *
      metresPerDegree,
    y: (lat - data.origin.lat) * metresPerDegree,
  };
}

type Edge = {
  from: number;
  to: number;
  start: CampusPoint;
  end: CampusPoint;
  length: number;
};
type Neighbor = { id: number; distance: number };
type Snap = {
  edge: Edge;
  point: CampusPoint;
  offset: number;
  distance: number;
};

const endpointTolerance = 8;
const sampleTolerance = 10;
const maximumExcursion = 24;
const anchorSpacing = 2;
const maximumUntracedDetourRatio = 3;
const detourAllowance = 10;
const epsilon = 1e-7;
// Retain OSM topology while accepting millimetre rounding in saved coordinates.
const routeTolerance = 0.002;
const distance = (a: CampusPoint, b: CampusPoint) =>
  Math.hypot(a.x - b.x, a.y - b.y);
const isFinitePoint = ({ x, y }: CampusPoint) =>
  Number.isFinite(x) && Number.isFinite(y);

function pathLength(start: CampusPoint, points: readonly CampusPoint[]) {
  return points.reduce(
    (total, point, i) => total + distance(points[i - 1] ?? start, point),
    0,
  );
}

function appendPoint(path: CampusPoint[], point: CampusPoint) {
  const previous = path.at(-1);
  if (!previous) {
    path.push(point);
    return;
  }
  const step = distance(previous, point);
  if (step <= epsilon) return;
  const before = path.at(-2);
  if (before) {
    const entry = distance(before, previous);
    const direct = distance(before, point);
    // Simplify straight travel, preserving intentional reversals and actual bends.
    if (Math.abs(entry + step - direct) <= epsilon) path.pop();
  }
  path.push(point);
}

function segmentRatio(
  point: CampusPoint,
  start: CampusPoint,
  end: CampusPoint,
  length: number,
) {
  return Math.max(
    0,
    Math.min(
      1,
      ((point.x - start.x) * (end.x - start.x) +
        (point.y - start.y) * (end.y - start.y)) /
        (length * length),
    ),
  );
}

function interpolate(
  start: CampusPoint,
  end: CampusPoint,
  ratio: number,
): CampusPoint {
  return {
    x: start.x + ratio * (end.x - start.x),
    y: start.y + ratio * (end.y - start.y),
  };
}

function snapToEdge(point: CampusPoint, edge: Edge): Snap {
  const { start, end, length } = edge;
  const ratio = segmentRatio(point, start, end, length);
  const projected = interpolate(start, end, ratio);
  return {
    edge,
    point: projected,
    offset: length * ratio,
    distance: distance(point, projected),
  };
}

function followsRoute(
  stroke: readonly CampusPoint[],
  route: readonly CampusPoint[],
) {
  let furthest = 0;
  // Favor the connected direct route when the stroke advances alongside it.
  // This avoids entering nearby short branches that the cursor never followed.
  for (const sample of stroke.slice(1, -1)) {
    let closest = Infinity;
    let progress = 0;
    let offset = 0;
    for (let i = 1; i < route.length; i++) {
      const from = route[i - 1],
        to = route[i];
      const span = distance(from, to);
      if (span <= epsilon) continue;
      const ratio = segmentRatio(sample, from, to, span);
      const gap = distance(sample, interpolate(from, to, ratio));
      if (gap < closest) {
        closest = gap;
        progress = offset + ratio * span;
      }
      offset += span;
    }
    if (closest > 6 || progress < furthest - anchorSpacing) return false;
    furthest = Math.max(furthest, progress);
  }
  return true;
}

function endpointDistances({ edge, offset }: Snap): Neighbor[] {
  return [
    { id: edge.from, distance: offset },
    { id: edge.to, distance: edge.length - offset },
  ];
}

export class CampusRouter {
  private readonly points = new Map<number, CampusPoint>();
  private readonly edges: Edge[] = [];
  private readonly neighbors = new Map<number, Neighbor[]>();

  constructor(data: CampusMapData) {
    const seen = new Set<string>();
    const pointFor = (id: number) => {
      const cached = this.points.get(id);
      if (cached) return cached;
      const position = data.nodes[id];
      if (!position) return;
      const point = projectCampus(data, position);
      if (!isFinitePoint(point)) return;
      this.points.set(id, point);
      this.neighbors.set(id, []);
      return point;
    };
    for (const feature of data.features) {
      if (feature.kind !== "walkway") continue;
      for (let i = 1; i < feature.nodes.length; i++) {
        const from = feature.nodes[i - 1];
        const to = feature.nodes[i];
        if (from === to) continue;
        const key = `${Math.min(from, to)}:${Math.max(from, to)}`;
        if (seen.has(key)) continue;
        const start = pointFor(from);
        const end = pointFor(to);
        if (!start || !end) continue;
        seen.add(key);
        const length = distance(start, end);
        this.neighbors.get(from)!.push({ id: to, distance: length });
        this.neighbors.get(to)!.push({ id: from, distance: length });
        if (length > epsilon) this.edges.push({ from, to, start, end, length });
      }
    }
  }

  plan(
    stroke: readonly CampusPoint[],
  ): { points: CampusPoint[]; length: number } | { error: string } {
    if (stroke.length < 2 || stroke.some((point) => !isFinitePoint(point)))
      return { error: "보행로 위에서 출발점부터 도착점까지 드래그하세요." };
    const start = this.snap(stroke[0]);
    const end = this.snap(stroke[stroke.length - 1]);
    if (
      !start ||
      !end ||
      start.distance > endpointTolerance ||
      end.distance > endpointTolerance
    )
      return {
        error: "시작점과 끝점을 지도에 표시된 보행로 가까이에 놓으세요.",
      };

    const direct = this.route(start, end);
    if (direct && stroke.length > 2) {
      const path = [start.point, ...direct];
      const length = pathLength(start.point, direct);
      if (length >= anchorSpacing && followsRoute(stroke, path)) {
        const points: CampusPoint[] = [];
        for (const point of path) appendPoint(points, point);
        return { points: points.map((point) => ({ ...point })), length };
      }
    }

    const points = [start.point];
    let previous = start;
    let outside = false;
    let excursion = 0;
    let drawnSinceAnchor = 0;
    for (let i = 1; i < stroke.length; i++) {
      const isEnd = i === stroke.length - 1;
      const snap = this.snap(stroke[i], previous.edge)!;
      const outsideNow = snap.distance > sampleTolerance;
      const drawnStep = distance(stroke[i - 1], stroke[i]);
      drawnSinceAnchor += drawnStep;
      if (outside || outsideNow) excursion += drawnStep;
      if (excursion > maximumExcursion)
        return {
          error:
            "드래그가 보행로에서 멀어졌습니다. 보행로를 따라 다시 그리세요.",
        };
      outside = outsideNow;
      if (outside) continue;
      excursion = 0;
      if (!isEnd && distance(previous.point, snap.point) < anchorSpacing)
        continue;
      const route = this.route(previous, snap);
      if (!route)
        return {
          error:
            "이어지지 않은 보행로 구간입니다. 연결된 보행로를 따라 다시 그리세요.",
        };
      // Brief cursor drift across parallel walkways can snap to a distant loop.
      if (
        !isEnd &&
        pathLength(previous.point, route) >
          drawnSinceAnchor * maximumUntracedDetourRatio + detourAllowance
      )
        continue;
      for (const point of route) appendPoint(points, point);
      previous = snap;
      drawnSinceAnchor = 0;
    }
    const length = pathLength(points[0], points);
    if (length < anchorSpacing)
      return { error: "보행로를 따라 2 m 이상 경로를 그리세요." };
    return { points: points.map((point) => ({ ...point })), length };
  }

  containsRoute(points: readonly CampusPoint[]): boolean {
    if (!points.length || points.some((point) => !isFinitePoint(point)))
      return false;
    let reachable = this.routeAnchors(points[0]);
    for (let i = 1; reachable.length && i < points.length; i++) {
      reachable = this.segmentAnchors(points[i - 1], points[i], reachable);
    }
    return reachable.length > 0;
  }

  private routeAnchors(point: CampusPoint) {
    return this.edges
      .map((edge) => snapToEdge(point, edge))
      .filter((anchor) => anchor.distance <= routeTolerance);
  }

  private segmentAnchors(
    start: CampusPoint,
    end: CampusPoint,
    startAnchors: Snap[],
  ) {
    const endAnchors = this.routeAnchors(end);
    if (!endAnchors.length) return endAnchors;
    const length = distance(start, end);
    const offset = (point: CampusPoint) =>
      length > epsilon
        ? ((point.x - start.x) * (end.x - start.x) +
            (point.y - start.y) * (end.y - start.y)) /
          length
        : 0;
    const offsets = new Map<number, number | undefined>();
    const corridorOffset = (id: number) => {
      if (offsets.has(id)) return offsets.get(id);
      const point = this.points.get(id)!;
      const along = offset(point);
      const closest =
        length > epsilon
          ? interpolate(start, end, Math.max(0, Math.min(1, along / length)))
          : start;
      const value =
        distance(point, closest) <= routeTolerance ? along : undefined;
      offsets.set(id, value);
      return value;
    };

    // Traverse only connected edges inside the segment's tolerance corridor.
    // Keeping reachable edge identities between segments prevents transfers
    // at crossings where the OSM ways have no shared node.
    const nodes: number[] = [];
    const reached = new Set<number>();
    const visit = (id: number) => {
      if (reached.has(id)) return;
      reached.add(id);
      nodes.push(id);
    };
    const startEdges = new Set(startAnchors.map(({ edge }) => edge));
    for (const anchor of startAnchors) {
      const minimum = offset(anchor.point) - routeTolerance;
      for (const id of [anchor.edge.from, anchor.edge.to]) {
        const along = corridorOffset(id);
        if (along !== undefined && along >= minimum) visit(id);
      }
    }
    for (let i = 0; i < nodes.length; i++) {
      const id = nodes[i];
      const along = corridorOffset(id)!;
      for (const neighbor of this.neighbors.get(id)!) {
        const next = corridorOffset(neighbor.id);
        if (next !== undefined && next >= along - epsilon) visit(neighbor.id);
      }
    }
    return endAnchors.filter(
      ({ edge, point }) =>
        startEdges.has(edge) ||
        [edge.from, edge.to].some(
          (id) =>
            reached.has(id) &&
            corridorOffset(id)! <= offset(point) + routeTolerance,
        ),
    );
  }

  private snap(point: CampusPoint, preferred?: Edge) {
    let best: Snap | undefined;
    for (const edge of this.edges) {
      const anchor = snapToEdge(point, edge);
      if (
        !best ||
        anchor.distance < best.distance - epsilon ||
        (Math.abs(anchor.distance - best.distance) <= epsilon &&
          edge === preferred)
      ) {
        best = anchor;
      }
    }
    return best;
  }

  private route(start: Snap, end: Snap): CampusPoint[] | undefined {
    if (start.edge === end.edge) return [end.point];

    // Offset costs include the partial segments between each anchor and its endpoints.
    const costs = new Map(
      endpointDistances(start).map(({ id, distance }) => [id, distance]),
    );
    const targets = new Map(
      endpointDistances(end).map(({ id, distance }) => [id, distance]),
    );
    const frontier = new Set(costs.keys());
    const preceding = new Map<number, number>();
    let goal: number | undefined;
    let goalCost = Infinity;
    while (frontier.size) {
      let current: number | undefined;
      let currentCost = Infinity;
      for (const id of frontier) {
        const cost = costs.get(id)!;
        if (cost < currentCost) {
          current = id;
          currentCost = cost;
        }
      }
      if (current === undefined || currentCost >= goalCost) break;
      frontier.delete(current);
      const targetCost = targets.get(current);
      if (targetCost !== undefined && currentCost + targetCost < goalCost) {
        goal = current;
        goalCost = currentCost + targetCost;
      }
      for (const neighbor of this.neighbors.get(current)!) {
        const candidate = currentCost + neighbor.distance;
        if (candidate >= (costs.get(neighbor.id) ?? Infinity)) continue;
        costs.set(neighbor.id, candidate);
        preceding.set(neighbor.id, current);
        frontier.add(neighbor.id);
      }
    }
    if (goal === undefined) return;
    const path = [end.point];
    for (
      let id: number | undefined = goal;
      id !== undefined;
      id = preceding.get(id)
    ) {
      path.push(this.points.get(id)!);
    }
    return path.reverse();
  }
}
