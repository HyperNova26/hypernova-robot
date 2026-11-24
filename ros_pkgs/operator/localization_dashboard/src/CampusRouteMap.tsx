// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import {
  Crosshair,
  Expand,
  Minus,
  MousePointer2,
  PencilLine,
  Plus,
  RotateCcw,
} from "lucide-react";
import {
  CampusRouter,
  projectCampus,
  type CampusMapData,
  type CampusPoint,
} from "./campusRouting";
import type {
  Incident,
  Mission,
  MissionRun,
  OperationPose,
  Waypoint,
} from "./operation";
import "./campus-route-map.css";

type Route = { points: CampusPoint[]; length: number };
type View = { x: number; y: number; scale: number };
type Props = {
  data?: CampusMapData;
  loadError?: string;
  editing: boolean;
  draft?: Mission;
  run?: MissionRun;
  position?: OperationPose;
  trail?: readonly OperationPose[];
  incidents?: readonly Incident[];
  selectedIncidentId?: string;
  onSelectIncident?: (id: string) => void;
  onApply: (points: CampusPoint[]) => string | undefined;
  onPendingRouteChange?: (pending: boolean) => void;
};
const home: View = { x: 0, y: 0, scale: 2 };
const mapWidth = 466,
  mapHeight = 352;
function pointBounds(points: readonly CampusPoint[]) {
  return points.reduce(
    ({ minX, maxX, minY, maxY }, { x, y }) => ({
      minX: Math.min(x, minX),
      maxX: Math.max(x, maxX),
      minY: Math.min(y, minY),
      maxY: Math.max(y, maxY),
    }),
    { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity },
  );
}

function fitView(
  bounds: ReturnType<typeof pointBounds>,
  margin: number,
  maxScale: number,
): View {
  const { minX, maxX, minY, maxY } = bounds;
  return {
    x: (minX + maxX) / 2,
    y: (minY + maxY) / 2,
    scale: Math.min(
      maxScale,
      mapWidth / (maxX - minX + 2 * margin),
      mapHeight / (maxY - minY + 2 * margin),
    ),
  };
}

const storageKey = "hypernova.khu-walkway-route.v1";
const maxSamples = 1400;
const sourceLink = "https://www.openstreetmap.org/copyright";
const order = { green: 0, water: 1, building: 2, road: 3, walkway: 4 };
const runStatus: Record<MissionRun["status"], string> = {
  running: "실행 중",
  paused: "일시정지",
  completed: "완료",
  cancelled: "취소",
  failed: "실패",
};

const svgPoints = (points: readonly CampusPoint[]) =>
  points.map(({ x, y }) => `${x.toFixed(3)},${(-y).toFixed(3)}`).join(" ");
const pointGap = (a: CampusPoint, b: CampusPoint) =>
  Math.hypot(a.x - b.x, a.y - b.y);
const validPoint = (point: unknown): point is CampusPoint =>
  !!point &&
  typeof point === "object" &&
  "x" in point &&
  "y" in point &&
  typeof point.x === "number" &&
  Number.isFinite(point.x) &&
  typeof point.y === "number" &&
  Number.isFinite(point.y);

function loadLegacyRoute(
  data: CampusMapData,
  router: CampusRouter,
): Route | undefined {
  try {
    const stored: unknown = JSON.parse(
      localStorage.getItem(storageKey) ?? "null",
    );
    if (
      !stored ||
      typeof stored !== "object" ||
      !("revision" in stored) ||
      stored.revision !== data.source.timestamp ||
      !("stroke" in stored) ||
      !Array.isArray(stored.stroke) ||
      stored.stroke.length > maxSamples ||
      !stored.stroke.every(validPoint)
    )
      return;
    const route = router.plan(stored.stroke);
    if (!("error" in route)) return route;
  } catch {
    /* The map remains usable when browser storage is unavailable. */
  }
}

function remainingLength(run: MissionRun, position?: OperationPose) {
  if (run.status === "completed") return 0;
  if (!position) return;
  const approach = run.approach?.points.slice(run.approach.nextIndex) ?? [];
  const remaining = [
    ...approach,
    ...run.mission.waypoints.slice(run.targetIndex),
  ];
  return remaining.reduce(
    (length, point, index) =>
      length + pointGap(remaining[index - 1] ?? position, point),
    0,
  );
}

function WaypointMarker({
  waypoint,
  index,
  scale,
  state,
}: {
  waypoint: Waypoint;
  index: number;
  scale: number;
  state: "draft" | "pending" | "goal" | "complete";
}) {
  const label = {
    draft: "초안 경유점",
    pending: "대기 경유점",
    goal: "현재 목표",
    complete: "완료 경유점",
  }[state];
  return (
    <g
      className={`campus-waypoint ${state}`}
      transform={`translate(${waypoint.x} ${-waypoint.y}) scale(${1 / scale})`}
      aria-label={`${label} ${index + 1}. ${waypoint.name}`}
    >
      <title>{`${label} ${index + 1}. ${waypoint.name}`}</title>
      {state === "goal" && <circle r="7.5" className="campus-waypoint-focus" />}
      <circle r="4.8" />
      <text>{index + 1}</text>
      {state === "complete" && (
        <text className="campus-waypoint-check" x="5" y="-4.9">
          ✓
        </text>
      )}
    </g>
  );
}

export function CampusRouteMap({ data, loadError, ...editorProps }: Props) {
  if (loadError)
    return (
      <p className="campus-route-notice" role="alert">
        {loadError}
      </p>
    );
  if (!data)
    return (
      <p className="ops-help" role="status">
        캠퍼스 지도를 불러오는 중입니다.
      </p>
    );
  return (
    <CampusEditor key={data.source.timestamp} data={data} {...editorProps} />
  );
}

function CampusEditor({
  data,
  editing,
  draft,
  run,
  position,
  trail = [],
  incidents = [],
  selectedIncidentId,
  onSelectIncident,
  onApply,
  onPendingRouteChange,
}: Omit<Props, "data" | "loadError"> & { data: CampusMapData }) {
  const router = useMemo(() => new CampusRouter(data), [data]);
  const geometry = useMemo(() => {
    const positions = Object.fromEntries(
      Object.entries(data.nodes).map(([id, coordinate]) => [
        id,
        projectCampus(data, coordinate),
      ]),
    );
    return [...data.features]
      .sort((a, b) => order[a.kind] - order[b.kind])
      .flatMap((feature) => {
        const points = feature.nodes.map((id) => positions[id]);
        if (points.length < 2 || points.some((point) => !point)) return [];
        const center = points.reduce(
          (sum, point) => ({
            x: sum.x + point.x / points.length,
            y: sum.y + point.y / points.length,
          }),
          { x: 0, y: 0 },
        );
        return [{ ...feature, points, center }];
      });
  }, [data]);
  const outline = useMemo(
    () =>
      data.campusOutline?.map((coordinate) => projectCampus(data, coordinate)),
    [data],
  );
  const siteBounds = useMemo(
    () =>
      outline
        ? pointBounds(outline)
        : { minX: -350, maxX: 350, minY: -350, maxY: 350 },
    [outline],
  );
  const overview = fitView(siteBounds, 40, 1);
  const placeNames = useMemo(
    () => new Set(data.places?.map(({ name }) => name)),
    [data],
  );
  const [tool, setTool] = useState<"draw" | "pan">(editing ? "draw" : "pan");
  const [view, setView] = useState(home);
  const framedDraft = useRef<string>(undefined);
  const [stroke, setStroke] = useState<CampusPoint[]>([]);
  const [candidate, setCandidate] = useState<Route>();
  const [notice, setNotice] = useState("");
  const hasDraft = Boolean(draft);
  const legacy = useMemo(
    () => (hasDraft ? undefined : loadLegacyRoute(data, router)),
    [data, hasDraft, router],
  );
  const drag = useRef<{
    pointerId: number;
    from: CampusPoint;
    view: View;
    client: CampusPoint;
    unitsPerPixel: number;
    points: CampusPoint[];
    moved: boolean;
    draw: boolean;
  }>(undefined);
  const drawing = editing && tool === "draw";
  const pendingRoute =
    drawing && (stroke.length > 0 || candidate !== undefined);
  const selectedIncident = incidents.find(
    (incident) => incident.id === selectedIncidentId,
  );
  const incidentX = selectedIncident?.pose.x;
  const incidentY = selectedIncident?.pose.y;
  useEffect(() => {
    onPendingRouteChange?.(pendingRoute);
  }, [onPendingRouteChange, pendingRoute]);
  useEffect(() => {
    return () => onPendingRouteChange?.(false);
  }, [onPendingRouteChange]);
  useEffect(() => {
    if (
      !editing ||
      !draft?.waypoints.length ||
      framedDraft.current === draft.id
    )
      return;
    framedDraft.current = draft.id;
    setView(fitView(pointBounds(draft.waypoints), 48, 3));
  }, [draft, editing]);
  useEffect(() => {
    if (incidentX === undefined || incidentY === undefined) return;
    setView((current) => ({ ...current, x: incidentX, y: incidentY }));
  }, [selectedIncidentId, incidentX, incidentY]);
  useEffect(() => {
    if (editing) setTool("draw");
    else {
      setTool("pan");
      drag.current = undefined;
      setStroke([]);
      setCandidate(undefined);
      setNotice("");
    }
  }, [editing]);

  function changeTool(next: "draw" | "pan") {
    if (next === "pan" && tool !== next) {
      drag.current = undefined;
      setStroke([]);
      setCandidate(undefined);
    }
    setNotice("");
    setTool(next);
  }
  function mapPoint(event: PointerEvent<SVGSVGElement>) {
    const canvas = event.currentTarget;
    const matrix = canvas.getScreenCTM();
    if (!matrix) return;
    const point = canvas.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    return { x: local.x, y: -local.y };
  }
  function down(event: PointerEvent<SVGSVGElement>) {
    if (!event.isPrimary || event.button !== 0) return;
    const point = mapPoint(event);
    const pixelsPerUnit = event.currentTarget.getScreenCTM()?.a;
    if (!point || !pixelsPerUnit) return;
    if (drawing) {
      setNotice("");
      setCandidate(undefined);
      setStroke([point]);
    }
    drag.current = {
      pointerId: event.pointerId,
      from: point,
      view,
      points: [point],
      moved: false,
      draw: drawing,
      client: { x: event.clientX, y: event.clientY },
      unitsPerPixel: 1 / pixelsPerUnit,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    const point = mapPoint(event);
    if (!point) return;
    if (active.draw) {
      if (pointGap(active.points.at(-1)!, point) < 0.65) return;
      if (active.points.length >= maxSamples - 1) {
        drag.current = undefined;
        setStroke([]);
        setNotice(
          "한 번에 그릴 수 있는 길이를 넘었습니다. 짧은 구간으로 나눠 그리세요.",
        );
        return;
      }
      active.moved = true;
      active.points.push(point);
      setStroke([...active.points]);
    } else {
      panTo(
        active.view.x -
          (event.clientX - active.client.x) * active.unitsPerPixel,
        active.view.y +
          (event.clientY - active.client.y) * active.unitsPerPixel,
      );
    }
  }
  function up(event: PointerEvent<SVGSVGElement>) {
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    drag.current = undefined;
    if (!active.draw || !drawing) return;
    const point = mapPoint(event);
    if (!point || (!active.moved && pointGap(active.from, point) < 2)) {
      setStroke([]);
      setNotice("보행로 시작점에서 끝점까지 끌어 경로를 그리세요.");
      return;
    }
    const input = [...active.points, point];
    setStroke(input);
    const result = router.plan(input);
    if ("error" in result) setNotice(result.error);
    else setCandidate(result);
  }
  function cancel(event: PointerEvent<SVGSVGElement>) {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = undefined;
    setStroke([]);
  }
  function panTo(x: number, y: number) {
    setView((current) => ({
      ...current,
      x: Math.max(siteBounds.minX, Math.min(siteBounds.maxX, x)),
      y: Math.max(siteBounds.minY, Math.min(siteBounds.maxY, y)),
    }));
  }
  function zoom(factor: number) {
    setView((current) => ({
      ...current,
      scale: Math.max(overview.scale, Math.min(6, current.scale * factor)),
    }));
  }
  function apply() {
    if (!candidate || !editing) return;
    const issue = onApply(candidate.points);
    if (issue) {
      setNotice(issue);
      return;
    }
    changeTool("pan");
  }
  function reviewLegacy() {
    if (!legacy || !editing) return;
    setStroke([]);
    setCandidate(legacy);
    setNotice("");
    setTool("draw");
  }

  const draftWaypoints = draft?.waypoints ?? [];
  const runWaypoints = run?.mission.waypoints ?? [];
  const sameRoute =
    draftWaypoints.length === runWaypoints.length &&
    draftWaypoints.every(
      (point, index) => pointGap(point, runWaypoints[index]) < 1e-7,
    );
  const showDraft = draftWaypoints.length > 0 && !sameRoute;
  const activeRun = run?.status === "running" || run?.status === "paused";
  const targetIndex = run?.targetIndex ?? 0;
  const currentGoal = activeRun ? runWaypoints[targetIndex] : undefined;
  const remaining = run ? remainingLength(run, position) : undefined;

  const plazaNode = data.nodes["11356882031"];
  const plaza = plazaNode && projectCampus(data, plazaNode);
  const width = mapWidth / view.scale,
    height = mapHeight / view.scale;
  const scaleLength =
    [10, 25, 50, 100, 250].find((length) => length * view.scale >= 30) ?? 250;
  const scaleX = view.x + width / 2 - scaleLength - 8;
  const scaleY = -view.y + height / 2 - 6;
  return (
    <section
      className="campus-route"
      aria-label="캠퍼스 보행로 지도"
      data-teleop-ignore
    >
      <div className="campus-route-toolbar">
        {editing && (
          <div className="ops-row" role="group" aria-label="지도 도구">
            <button aria-pressed={!drawing} onClick={() => changeTool("pan")}>
              <MousePointer2 size={15} /> 지도 탐색
            </button>
            <button aria-pressed={drawing} onClick={() => changeTool("draw")}>
              <PencilLine size={15} /> 경로 그리기
            </button>
            {legacy && !candidate && (
              <button type="button" onClick={reviewLegacy}>
                이전 보정 경로 가져오기
              </button>
            )}
          </div>
        )}
        <div className="ops-row" role="group" aria-label="지도 배율 및 위치">
          <button
            aria-label="지도 축소"
            disabled={view.scale === overview.scale}
            onClick={() => zoom(1 / 1.35)}
          >
            <Minus size={15} />
          </button>
          <button
            aria-label="지도 확대"
            disabled={view.scale === 6}
            onClick={() => zoom(1.35)}
          >
            <Plus size={15} />
          </button>
          {position && (
            <button
              aria-label="로봇 위치로 이동"
              title="로봇 위치로 이동"
              onClick={() =>
                setView((current) => ({
                  ...current,
                  x: position.x,
                  y: position.y,
                }))
              }
            >
              <Crosshair size={16} aria-hidden="true" />
            </button>
          )}
          <button onClick={() => setView(home)}>
            <RotateCcw size={15} /> 대학관 주변
          </button>
          {plaza && (
            <button onClick={() => setView({ ...plaza, scale: 2 })}>
              사색의 광장
            </button>
          )}
          <button onClick={() => setView(overview)}>
            <Expand size={15} aria-hidden="true" /> 캠퍼스 전체
          </button>
        </div>
      </div>

      <div className="campus-route-surface">
        <svg
          className={drawing ? "drawing" : undefined}
          viewBox={`${view.x - width / 2} ${-view.y - height / 2} ${width} ${height}`}
          aria-label="경희대학교 국제캠퍼스 OpenStreetMap 보행로"
          role="group"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Escape" && drawing) {
              changeTool("pan");
              return;
            }
            if (drawing || !event.key.startsWith("Arrow")) return;
            event.preventDefault();
            const x =
              ((Number(event.key === "ArrowRight") -
                Number(event.key === "ArrowLeft")) *
                16) /
              view.scale;
            const y =
              ((Number(event.key === "ArrowUp") -
                Number(event.key === "ArrowDown")) *
                16) /
              view.scale;
            panTo(view.x + x, view.y + y);
          }}
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={cancel}
          onLostPointerCapture={cancel}
        >
          {geometry.map(({ id, kind, points }, i) => {
            const shape = svgPoints(points);
            const className = "campus-feature campus-" + kind;
            const closed =
              points.length > 3 && pointGap(points[0], points.at(-1)!) < 0.01;
            return closed &&
              (kind === "building" || kind === "water" || kind === "green") ? (
              <polygon
                key={`${id}/${i}`}
                points={shape}
                className={className}
              />
            ) : (
              <polyline
                key={`${id}/${i}`}
                points={shape}
                className={className}
              />
            );
          })}
          {geometry
            .filter(
              ({ kind, name }) =>
                kind === "building" && name && !placeNames.has(name),
            )
            .map(({ id, center, name }) => (
              <text
                key={`${id}/${center.x}/${center.y}`}
                x={center.x}
                y={-center.y}
                className="campus-route-place"
                fontSize={11 / view.scale}
              >
                {name}
              </text>
            ))}
          {data.places?.map(({ position, name }) => {
            const place = projectCampus(data, position);
            return (
              <text
                key={name + position.join(",")}
                x={place.x}
                y={-place.y}
                className="campus-route-place campus-route-landmark"
                fontSize={14 / view.scale}
              >
                {name}
              </text>
            );
          })}
          {outline && (
            <polyline
              className="campus-route-boundary"
              points={svgPoints(outline)}
              aria-label="캠퍼스 경계"
            />
          )}
          {trail.length > 1 && (
            <polyline
              className="campus-route-trail"
              points={svgPoints(trail)}
              aria-label="모의 로봇 이동 궤적"
            />
          )}
          {showDraft && draftWaypoints.length > 1 && (
            <polyline
              className="campus-route-draft"
              points={svgPoints(draftWaypoints)}
              aria-label="임무 초안 경로"
            />
          )}
          {runWaypoints.length > 1 && (
            <polyline
              className="campus-route-run"
              points={svgPoints(runWaypoints)}
              aria-label="실행 임무 경로"
            />
          )}
          {drawing && stroke.length > 1 && (
            <polyline
              className="campus-route-stroke"
              points={svgPoints(stroke)}
              aria-label="마우스로 그린 경로"
            />
          )}
          {drawing && candidate && (
            <polyline
              className="campus-route-preview"
              points={svgPoints(candidate.points)}
              aria-label="실제 보행로 보정 미리보기"
            />
          )}
          {showDraft &&
            draftWaypoints.map((waypoint, index) => (
              <WaypointMarker
                key={waypoint.id}
                waypoint={waypoint}
                index={index}
                scale={view.scale}
                state="draft"
              />
            ))}
          {runWaypoints.map((waypoint, index) => (
            <WaypointMarker
              key={waypoint.id}
              waypoint={waypoint}
              index={index}
              scale={view.scale}
              state={
                index < targetIndex
                  ? "complete"
                  : currentGoal === waypoint
                    ? "goal"
                    : "pending"
              }
            />
          ))}
          {position && (
            <g
              transform={`translate(${position.x} ${-position.y}) scale(${1 / view.scale})`}
              aria-label="모의 로봇 위치"
            >
              <title>{`모의 로봇 · X ${position.x.toFixed(1)} m · Y ${position.y.toFixed(1)} m · ${position.yaw.toFixed(0)}°`}</title>
              <circle className="campus-route-position" r="6" />
              <path
                className="campus-route-heading"
                d="M4 0 L-2.5 -2.7 L-1.6 0 L-2.5 2.7 Z"
                transform={`rotate(${-position.yaw})`}
              />
            </g>
          )}
          {incidents
            .filter(
              (incident) =>
                !incident.closedAt || incident.id === selectedIncidentId,
            )
            .map((incident) => (
              <g
                key={incident.id}
                className={`campus-route-incident ${incident.id === selectedIncidentId ? "selected" : ""}`}
                transform={`translate(${incident.pose.x} ${-incident.pose.y}) scale(${1 / view.scale})`}
                aria-label={`이상 위치 · ${incident.title}`}
                role={onSelectIncident ? "button" : undefined}
                tabIndex={onSelectIncident ? 0 : undefined}
                onPointerDown={(event) => {
                  if (onSelectIncident) event.stopPropagation();
                }}
                onClick={() => onSelectIncident?.(incident.id)}
                onKeyDown={(event) => {
                  if (
                    !onSelectIncident ||
                    (event.key !== "Enter" && event.key !== " ")
                  )
                    return;
                  event.preventDefault();
                  event.stopPropagation();
                  onSelectIncident(incident.id);
                }}
              >
                <title>{incident.title}</title>
                {onSelectIncident && (
                  <circle className="campus-route-incident-hit" cy="-7" r="7" />
                )}
                <path d="M0 0 L-5 -7 L0 -12 L5 -7 Z" />
                <text y="-7">!</text>
              </g>
            ))}
          <text
            className="campus-route-place"
            x={view.x - width / 2 + 8}
            y={-view.y - height / 2 + 10}
            fontSize={9 / view.scale}
          >
            N ↑
          </text>
          <line
            className="campus-route-scale"
            x1={scaleX}
            x2={scaleX + scaleLength}
            y1={scaleY}
            y2={scaleY}
          />
          <text
            className="campus-route-place"
            x={scaleX + scaleLength / 2}
            y={scaleY - 3 / view.scale}
            fontSize={8 / view.scale}
          >
            {scaleLength} m
          </text>
        </svg>
      </div>
      {drawing && candidate && (
        <div className="campus-route-review">
          <div>
            <strong role="status">
              보정 경로 {candidate.length.toFixed(1)} m
            </strong>
            <p className="ops-help">적용하면 임무 초안의 경유점이 바뀝니다.</p>
          </div>
          <button type="button" className="primary" onClick={apply}>
            보정 경로 적용
          </button>
        </div>
      )}
      {notice && (
        <p className="campus-route-notice" role="status">
          {notice}
        </p>
      )}

      <div className="campus-route-footer">
        <div className="ops-row" aria-label="지도 범례">
          <span className="campus-legend-walkway">DEMO 등록 보행로</span>
          {outline && (
            <span className="campus-legend-boundary">캠퍼스 경계</span>
          )}
          {position && (
            <span className="campus-legend-position">모의 로봇</span>
          )}
          {drawing && stroke.length > 1 && (
            <span className="campus-legend-stroke">그린 선</span>
          )}
          {drawing && candidate && (
            <span className="campus-legend-route">보정 경로</span>
          )}
          {showDraft && <span className="campus-legend-draft">임무 초안</span>}
          {run && <span className="campus-legend-run">실행 임무</span>}
          {trail.length > 1 && (
            <span className="campus-legend-trail">이동 궤적</span>
          )}
        </div>
        <a href={sourceLink} target="_blank" rel="noreferrer">
          {data.source.attribution}
        </a>
      </div>
      {editing && !candidate && (
        <p className="ops-help">
          경로 그리기를 선택하고 청록색 보행로 가까이에서 시작점부터 끝점까지
          드래그하세요.
        </p>
      )}
      {run && (
        <div
          className="campus-route-progress ops-row"
          aria-label="캠퍼스 AUTO 임무 진행"
        >
          <strong role="status">
            {run.mission.name} · {runStatus[run.status]}
          </strong>
          {currentGoal && (
            <span>
              현재 목표 {targetIndex + 1}. {currentGoal.name}
              {run.reachedAt !== undefined ? " · 도착 대기" : ""}
            </span>
          )}
          <span>
            경유점 {targetIndex} / {runWaypoints.length} 완료
          </span>
          {remaining !== undefined && (
            <output aria-label="남은 AUTO 임무 거리" aria-live="off">
              남은 거리 {remaining.toFixed(1)} m
            </output>
          )}
        </div>
      )}
    </section>
  );
}
