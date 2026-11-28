// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { telemetry as s } from "./store";
import { mapReviewLabel, priorExcluded } from "./model";
import { createGo2Marker } from "./Go2Marker";
import { loadRobot, type RobotModel } from "./RobotModel";
import { LidarMap, TerrainIndex, rainbow } from "./observed";
const priorGray = "#9aa4ad";
// Camera presets. "free" = the user moved the camera since the last preset.
type View = "follow" | "overview" | "plan" | "free";
const views: [Exclude<View, "free">, string, string][] = [
  [
    "follow",
    "로봇 따라가기",
    "로봇 뒤에서 따라가며 봅니다. 드래그로 둘레를 돌 수 있습니다",
  ],
  ["overview", "지도 전체", "지도 전체를 비스듬히 내려다봅니다"],
  ["plan", "평면도", "지도 전체를 바로 위에서 내려다봅니다 (x 오른쪽, y 위쪽)"],
];
// CSS gradient of the LiDAR height colours, for the legend.
const rainbowCss = `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1]
  .map((t) => `rgb(${rainbow(t).map((c) => Math.round(c * 255))})`)
  .join(", ")})`;
export function MapView() {
  const host = useRef<HTMLDivElement>(null),
    api = useRef<
      { overview: () => void; plan: () => void; focus: () => void } | undefined
    >(undefined);
  const [view, setView] = useState<View>("overview"),
    [gt, setGt] = useState(true),
    [scan, setScan] = useState(true),
    [prior, setPrior] = useState(true),
    [mesh, setMesh] = useState(true),
    [paint, setPaint] = useState(true),
    [plan, setPlan] = useState(true),
    [meshInfo, setMeshInfo] = useState(""),
    [robotInfo, setRobotInfo] = useState("로봇 모델 읽는 중"),
    [painted, setPainted] = useState(0),
    [size, setSize] = useState(1),
    [failure, setFailure] = useState("");
  const options = useRef({ view, gt, scan, prior, mesh, paint, plan, size });
  options.current = { view, gt, scan, prior, mesh, paint, plan, size };
  useEffect(() => {
    const el = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setFailure("WebGL을 사용할 수 없습니다.");
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0d151d");
    const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 10000);
    camera.up.set(0, 0, 1);
    camera.position.set(50, -50, 50);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.rotateSpeed = 0.35;
    controls.panSpeed = 0.6;
    controls.zoomSpeed = 0.7;
    controls.screenSpacePanning = true;
    // The pair360_map origin lies ~60 m outside the map, so the grid sits under the map
    // (terrain, else prior map) instead of at the origin, and no origin axes are drawn.
    const grid = new THREE.GridHelper(400, 80, 0x314454, 0x1a2b38);
    grid.rotation.x = Math.PI / 2;
    const placeGrid = (g: THREE.BufferGeometry) => {
      g.computeBoundingBox();
      const b = g.boundingBox;
      if (!b || b.isEmpty()) return false;
      grid.position.set(
        (b.min.x + b.max.x) / 2,
        (b.min.y + b.max.y) / 2,
        b.min.z - 0.05,
      );
      return true;
    };
    let gridOnTerrain = false;
    scene.add(grid, new THREE.HemisphereLight(0xe9f4ff, 0x324253, 3));
    const light = new THREE.DirectionalLight(0xffffff, 2);
    light.position.set(10, -10, 30);
    scene.add(light);
    const mapGeometry = new THREE.BufferGeometry(),
      scanGeometry = new THREE.BufferGeometry();
    const mapMaterial = new THREE.PointsMaterial({
        size: 0.13,
        vertexColors: true,
      }),
      scanMaterial = new THREE.PointsMaterial({ size: 0.1, color: 0xf4f7fa });
    const map = new THREE.Points(mapGeometry, mapMaterial),
      currentScan = new THREE.Points(scanGeometry, scanMaterial);
    scene.add(map, currentScan);
    // Terrain display mesh from the MuJoCo heightfields (pair360_map, declared by the package).
    const terrain = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({
        color: 0x6f7880,
        roughness: 0.95,
        flatShading: true,
        transparent: true,
        opacity: 0.85,
        polygonOffset: true,
        polygonOffsetFactor: 1,
        polygonOffsetUnits: 1,
      }),
    );
    terrain.visible = false;
    scene.add(terrain);
    let terrainIndex: TerrainIndex | undefined;
    // Accumulated LiDAR map over the gray prior: turbo by height above the ground (display only).
    const lidarMap = new LidarMap(3_000_000, 0.07),
      lidarGeometry = new THREE.BufferGeometry(),
      lidarPositions = new THREE.BufferAttribute(lidarMap.positions, 3),
      lidarColors = new THREE.BufferAttribute(lidarMap.colors, 3);
    lidarGeometry.setAttribute("position", lidarPositions);
    lidarGeometry.setAttribute("color", lidarColors);
    lidarGeometry.setDrawRange(0, 0);
    const lidarPoints = new THREE.Points(
      lidarGeometry,
      new THREE.PointsMaterial({ size: 0.09, vertexColors: true }),
    );
    lidarPoints.frustumCulled = false;
    scene.add(lidarPoints);
    const meshLoad = new AbortController();
    fetch("/terrain-mesh.json", { signal: meshLoad.signal, cache: "no-cache" })
      .then(async (response) => {
        if (!response.ok) throw Error("메시 없음");
        const meta = await response.json();
        if (
          typeof meta.file !== "string" ||
          !/^[a-zA-Z0-9._-]+\.bin$/.test(meta.file) ||
          !Number.isInteger(meta.vertices) ||
          !Number.isInteger(meta.triangles)
        )
          throw Error("잘못된 메시 메타데이터");
        const bin = await fetch("/" + meta.file, { signal: meshLoad.signal });
        const bytes = await bin.arrayBuffer();
        if (bytes.byteLength !== meta.vertices * 12 + meta.triangles * 12)
          throw Error("메시 길이 불일치");
        const geometry = terrain.geometry;
        geometry.setAttribute(
          "position",
          new THREE.BufferAttribute(
            new Float32Array(bytes, 0, meta.vertices * 3),
            3,
          ),
        );
        geometry.setIndex(
          new THREE.BufferAttribute(
            new Uint32Array(bytes, meta.vertices * 12, meta.triangles * 3),
            1,
          ),
        );
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
        gridOnTerrain = placeGrid(geometry);
        terrainIndex = new TerrainIndex(
          geometry.getAttribute("position").array as Float32Array,
          meta.cell_m ?? 0.4,
        );
        setMeshInfo(
          `지형 메시 ${meta.scene_sha256.slice(0, 12)} · ${meta.triangles.toLocaleString()} 삼각형`,
        );
      })
      .catch((e) => {
        if (!meshLoad.signal.aborted)
          setMeshInfo("지형 메시 없음: " + String(e));
      });
    const pathGeometry = new THREE.BufferGeometry(),
      gtGeometry = new THREE.BufferGeometry();
    const path = new THREE.Line(
      pathGeometry,
      new THREE.LineBasicMaterial({ color: 0x55adff }),
    );
    const gtLine = new THREE.Line(
      gtGeometry,
      new THREE.LineDashedMaterial({
        color: 0xe8edf2,
        dashSize: 0.3,
        gapSize: 0.2,
      }),
    );
    // Global path (S-012): magenta, lifted 0.15 m so it is not hidden in the terrain mesh.
    const planGeometry = new THREE.BufferGeometry();
    const planLine = new THREE.Line(
      planGeometry,
      new THREE.LineBasicMaterial({ color: 0xff4fd8 }),
    );
    planLine.position.z = 0.15;
    planLine.frustumCulled = false;
    scene.add(path, gtLine, planLine);
    let lastPlan: unknown;
    const robot = createGo2Marker();
    scene.add(robot.root);
    // Team URDF (v1 HYPER) replaces the box marker once loaded.
    let model: RobotModel | undefined;
    const modelRoot = new THREE.Group();
    modelRoot.visible = false;
    scene.add(modelRoot);
    loadRobot("/robot/hn_v1_hyper", meshLoad.signal)
      .then((m) => {
        model = m;
        modelRoot.add(m.root);
        setRobotInfo("v1 HYPER URDF");
      })
      .catch((e) => {
        if (!meshLoad.signal.aborted)
          setRobotInfo("URDF 없음, Go2 간략 모델: " + String(e));
      });
    let lastFrame = performance.now(),
      lastYaw: number | undefined,
      smoothYaw = 0,
      smoothZ: number | undefined,
      lastXY: { x: number; y: number } | undefined,
      screenSpeed = 0,
      followed = false,
      followYaw = 0,
      robotGround = 0,
      lastPaintCount = 0,
      lastPaintLabel = 0,
      paintedUntil = -Infinity;
    let previousMap: unknown,
      previousScan: unknown,
      lastPath = -1,
      lastGT = -1,
      lastPathT: number | undefined,
      lastGTT: number | undefined,
      lastPrior = true,
      id = 0;
    const center = new THREE.Vector3(),
      extent = new THREE.Vector3(40, 40, 10);
    // Map extent: the prior map (else the terrain mesh) plus the travelled path and 10 m
    // around it, so the whole session fits once the robot has left the map's area.
    const bounds = () => {
      const box = new THREE.Box3();
      for (const g of [mapGeometry, terrain.geometry]) {
        g.computeBoundingBox();
        if (g.boundingBox && !g.boundingBox.isEmpty()) {
          box.copy(g.boundingBox);
          break;
        }
      }
      pathGeometry.computeBoundingBox();
      const route = pathGeometry.boundingBox;
      if (route && !route.isEmpty())
        box.union(route.clone().expandByVector(new THREE.Vector3(10, 10, 0)));
      if (!box.isEmpty()) {
        box.getCenter(center);
        box.getSize(extent);
      }
    };
    const fit = () => {
      bounds();
      const distance = Math.max(5, extent.length() * 0.9);
      controls.target.copy(center);
      camera.position
        .copy(center)
        .add(
          new THREE.Vector3(distance * 0.6, -distance * 0.8, distance * 0.65),
        );
      camera.far = Math.max(1000, distance * 10);
      camera.updateProjectionMatrix();
    };
    // Straight down on the whole map, x to the right and y up the screen.
    const plan = () => {
      bounds();
      const half = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      const d = Math.max(
        5,
        (extent.y / 2 / half) * 1.08,
        (extent.x / 2 / (half * camera.aspect)) * 1.08,
      );
      controls.target.copy(center);
      camera.position.set(center.x, center.y - 0.001, center.z + d);
      camera.far = Math.max(1000, d * 4);
      camera.updateProjectionMatrix();
    };
    // Behind and above the robot's heading.
    const focus = () => {
      const target = modelRoot.visible
        ? modelRoot.position
        : robot.root.visible
          ? robot.root.position
          : undefined;
      if (!target) return false;
      const back = new THREE.Vector3(-7, 0, 0).applyAxisAngle(
        new THREE.Vector3(0, 0, 1),
        smoothYaw,
      );
      controls.target.copy(target);
      camera.position
        .copy(target)
        .add(back)
        .add(new THREE.Vector3(0, 0, 4));
      return true;
    };
    api.current = { overview: fit, plan, focus: () => void focus() };
    // Dragging leaves a fixed preset (the follow camera keeps following).
    const userMove = () => {
      if (options.current.view !== "follow") setView("free");
    };
    controls.addEventListener("start", userMove);
    const resize = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      renderer.setSize(r.width, r.height);
      camera.aspect = r.width / r.height;
      camera.updateProjectionMatrix();
    });
    resize.observe(el);
    const posePoints = (poses: typeof s.lio) =>
      new Float32Array(
        poses
          .filter(
            (p) => p.frame === s.config.frame && p.child === s.config.base,
          )
          .flatMap((p) => [p.p.x, p.p.y, p.p.z]),
      );
    const draw = () => {
      const opts = options.current,
        prior = s.prior;
      if (prior !== previousMap || opts.prior !== lastPrior) {
        const changed = prior !== previousMap;
        previousMap = prior;
        lastPrior = opts.prior;
        const all = prior?.points ?? new Float32Array(0);
        // Prior map = every labelled class except vehicles and noise (never prior map).
        const labels = prior?.labels;
        const pts = !opts.prior
          ? new Float32Array(0)
          : labels
            ? all.filter(
                (_, i) => !priorExcluded.has(labels[Math.floor(i / 3)]),
              )
            : all;
        mapGeometry.setAttribute("position", new THREE.BufferAttribute(pts, 3));
        const color = new THREE.Color(priorGray),
          colors = new Float32Array(pts.length);
        for (let k = 0; k < colors.length; k += 3)
          colors.set([color.r, color.g, color.b], k);
        mapGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        mapGeometry.computeBoundingSphere();
        if (changed && prior && !gridOnTerrain) placeGrid(mapGeometry);
        if (changed && prior && opts.view === "overview") fit();
      }
      terrain.visible =
        opts.mesh &&
        !!terrain.geometry.index &&
        (s.demo ||
          !s.liveSession ||
          s.config.mapVerified ||
          s.livePrior?.frame === s.config.frame);
      const aligned = s.mapAligned ? s.mapCloud : undefined;
      if (s.lio.length < lastPath) {
        lidarMap.clear();
        lidarGeometry.setDrawRange(0, 0);
        paintedUntil = -Infinity;
      }
      // Every scan received, not only the one paired with the latest pose: several can
      // arrive between two animation frames.
      const first = lidarMap.count;
      if (s.mapAligned)
        for (const c of s.clouds) {
          if (c.t <= paintedUntil || lidarMap.full) continue;
          const world = s.frames.cloud(c, s.config.frame);
          if (!world) continue;
          paintedUntil = c.t;
          lidarMap.add(
            world.points,
            (x, y) => terrainIndex?.groundAt(x, y),
            robotGround,
          );
        }
      if (lidarMap.count > first) {
        for (const attr of [lidarPositions, lidarColors]) {
          attr.clearUpdateRanges();
          attr.addUpdateRange(first * 3, (lidarMap.count - first) * 3);
          attr.needsUpdate = true;
        }
        lidarGeometry.setDrawRange(0, lidarMap.count);
      }
      lidarPoints.visible = opts.paint;
      // The count label re-renders the panel; twice a second is enough.
      if (
        lidarMap.count !== lastPaintCount &&
        performance.now() - lastPaintLabel > 500
      ) {
        lastPaintCount = lidarMap.count;
        lastPaintLabel = performance.now();
        setPainted(lidarMap.count);
      }
      const cloud = opts.scan ? aligned : undefined;
      if (cloud !== previousScan) {
        previousScan = cloud;
        scanGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(cloud?.points ?? new Float32Array(0), 3),
        );
        scanGeometry.computeBoundingSphere();
      }
      // At the 6,000-pose cap the length stops changing; the newest stamp still does.
      if (lastPath !== s.lio.length || lastPathT !== s.lio.at(-1)?.t) {
        lastPath = s.lio.length;
        lastPathT = s.lio.at(-1)?.t;
        pathGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(posePoints(s.lio), 3),
        );
        pathGeometry.computeBoundingSphere();
      }
      if (lastGT !== s.gt.length || lastGTT !== s.gt.at(-1)?.t) {
        lastGT = s.gt.length;
        lastGTT = s.gt.at(-1)?.t;
        gtGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(posePoints(s.gt), 3),
        );
        gtGeometry.computeBoundingSphere();
        gtLine.computeLineDistances();
      }
      const planInMap = s.plan && s.frames.cloud(s.plan, s.config.frame);
      if (planInMap !== lastPlan) {
        lastPlan = planInMap;
        planGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(
            planInMap?.points ?? new Float32Array(0),
            3,
          ),
        );
        planGeometry.computeBoundingSphere();
      }
      planLine.visible = opts.plan && s.mapAligned && !!planInMap;
      path.visible = s.mapAligned;
      gtLine.visible = s.mapAligned && opts.gt;
      const p = s.current,
        now = performance.now(),
        dt = Math.min(0.1, (now - lastFrame) / 1000);
      lastFrame = now;
      const shown =
        !!p &&
        s.mapAligned &&
        p.frame === s.config.frame &&
        p.child === s.config.base;
      robot.root.visible = shown && !model;
      modelRoot.visible = shown && !!model;
      if (p && shown) {
        // Leg cadence follows how far the marker moves on screen per wall second, not the
        // reported speed, so feet stay planted at any replay rate (bag --rate 0.5, 1/3, ...).
        const step = lastXY
          ? Math.hypot(p.p.x - lastXY.x, p.p.y - lastXY.y)
          : 0;
        lastXY = { x: p.p.x, y: p.p.y };
        if (dt > 0)
          screenSpeed +=
            ((step < 2 ? step : 0) / dt - screenSpeed) * Math.min(1, dt * 4);
        const q = s.lio.at(-1)?.q,
          moving = s.receiving ? screenSpeed : 0;
        // Heading only: the recording is hand-held, so its roll/pitch is not the robot's.
        const forward = q
          ? new THREE.Vector3(1, 0, 0).applyQuaternion(
              new THREE.Quaternion(q.x, q.y, q.z, q.w),
            )
          : new THREE.Vector3(1, 0, 0);
        const yaw = Math.atan2(forward.y, forward.x);
        const turn =
          lastYaw === undefined
            ? 0
            : Math.atan2(Math.sin(yaw - lastYaw), Math.cos(yaw - lastYaw));
        if (lastYaw === undefined) smoothYaw = yaw;
        lastYaw = yaw;
        const k = Math.min(1, dt * 8);
        smoothYaw +=
          Math.atan2(Math.sin(yaw - smoothYaw), Math.cos(yaw - smoothYaw)) * k;
        if (model) {
          const scale = opts.size,
            offset = new THREE.Vector3(
              model.lidarOffset.x,
              model.lidarOffset.y,
              0,
            )
              .applyAxisAngle(new THREE.Vector3(0, 0, 1), smoothYaw)
              .multiplyScalar(scale),
            x = p.p.x - offset.x,
            y = p.p.y - offset.y,
            ground = terrainIndex?.groundAt(x, y),
            bob = model.animate(dt, moving, dt > 0 ? turn / dt : 0);
          const z =
            ground !== undefined
              ? ground + (model.standHeight + bob) * scale
              : // Off the terrain mesh: the 11-15 recording held the LiDAR about
                // 0.94 m above the trunk height used in isaac-runpod/trajectory_1115_base.csv.
                p.p.z - 0.94;
          smoothZ = smoothZ === undefined ? z : smoothZ + (z - smoothZ) * k;
          robotGround = ground ?? p.p.z - 0.94 - model.standHeight;
          modelRoot.position.set(x, y, smoothZ);
          modelRoot.rotation.set(0, 0, smoothYaw);
          modelRoot.scale.setScalar(scale);
        } else {
          robot.root.position.set(p.p.x, p.p.y, p.p.z);
          if (q) robot.root.quaternion.set(q.x, q.y, q.z, q.w);
          robot.root.scale.setScalar(opts.size * 3);
          robot.animate(p.t * 8, moving > 0.03);
        }
        if (opts.view === "follow") {
          if (!followed) {
            followed = focus();
            followYaw = smoothYaw;
          }
          const target = model ? modelRoot.position : robot.root.position;
          // Keep the user's chosen offset, turned with the robot's heading so it stays behind.
          const offset = camera.position
            .clone()
            .sub(controls.target)
            .applyAxisAngle(new THREE.Vector3(0, 0, 1), smoothYaw - followYaw);
          followYaw = smoothYaw;
          camera.position.copy(target).add(offset);
          controls.target.copy(target);
        }
      } else {
        lastYaw = undefined;
        lastXY = undefined;
      }
      if (opts.view !== "follow") followed = false;
      controls.update();
      renderer.render(scene, camera);
      id = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      cancelAnimationFrame(id);
      controls.removeEventListener("start", userMove);
      meshLoad.abort();
      resize.disconnect();
      controls.dispose();
      scene.traverse((obj) => {
        if (
          obj instanceof THREE.Mesh ||
          obj instanceof THREE.Points ||
          obj instanceof THREE.Line
        ) {
          obj.geometry.dispose();
          const materials = Array.isArray(obj.material)
            ? obj.material
            : [obj.material];
          materials.forEach((m) => m.dispose());
        }
      });
      renderer.dispose();
      el.removeChild(renderer.domElement);
      api.current = undefined;
    };
  }, []);
  const pick = (next: Exclude<View, "free">) => {
    setView(next);
    if (next === "overview") api.current?.overview();
    if (next === "plan") api.current?.plan();
  };
  return (
    <section className="panel map-panel">
      <div className="panel-head compact map-head">
        <h2>3D 지도</h2>
        <div className="view-switch" role="group" aria-label="시점">
          {views.map(([key, label, hint]) => (
            <button
              key={key}
              className={view === key ? "active" : ""}
              title={hint}
              onClick={() => pick(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="subtle">
          왼쪽 드래그 회전 · 오른쪽 드래그 이동 · 휠 확대
        </span>
      </div>
      <div className="map-surface">
        <div className="map-three" ref={host} />
        {failure && <div className="map-empty">{failure}</div>}
        {!s.mapAligned && s.link === "open" && (
          <div className="map-tags">
            <span
              className="chip unreviewed"
              title="ROS 지도가 표시 frame과 다르거나 아직 오지 않았습니다. 연결 설정에서 정합 확인을 켜면 로컬 지도에 겹칩니다"
            >
              지도 좌표 정합 미확인
            </span>
          </div>
        )}
        <div className="map-bottom">
          <span className="layer-group" aria-label="표시 레이어">
            <label title={meshInfo}>
              <input
                type="checkbox"
                checked={mesh}
                onChange={(e) => setMesh(e.target.checked)}
              />
              지형 메시
            </label>
            <label title="기준 지도 점(회색). 차량·노이즈 라벨은 제외">
              <input
                type="checkbox"
                checked={prior}
                onChange={(e) => setPrior(e.target.checked)}
              />
              기준 지도
            </label>
            <label title="이번 세션에 받은 LiDAR 점을 0.07 m 칸마다 하나씩 누적해, 바닥에서의 높이(0~5 m)로 무지개색을 칠합니다(표시용)">
              <input
                type="checkbox"
                checked={paint}
                onChange={(e) => setPaint(e.target.checked)}
              />
              LiDAR 누적
            </label>
            <label title="현재 LiDAR 스캔(흰색)">
              <input
                type="checkbox"
                checked={scan}
                onChange={(e) => setScan(e.target.checked)}
              />
              현재 스캔
            </label>
            {s.plan && (
              <label title={`${s.config.path} (nav_msgs/Path), 자홍색 선`}>
                <input
                  type="checkbox"
                  checked={plan}
                  onChange={(e) => setPlan(e.target.checked)}
                />
                글로벌 경로
              </label>
            )}
            {s.config.gt && (
              <label title="GT 경로(점선)">
                <input
                  type="checkbox"
                  checked={gt}
                  onChange={(e) => setGt(e.target.checked)}
                />
                GT
              </label>
            )}
          </span>
          <label title="1이 실제 크기입니다">
            로봇 크기
            <input
              aria-label="로봇 표시 배율"
              type="range"
              min="1"
              max="8"
              step=".5"
              value={size}
              onChange={(e) => setSize(+e.target.value)}
            />
          </label>
        </div>
      </div>
      <div
        className="map-legend"
        title={`${robotInfo} · 위치 기준 ${s.config.base}(수평 위치·방향만, 높이는 지형) · 다리는 이동 거리 기반 trot 표시용 애니메이션(관절 실측 아님) · ${meshInfo || "지형 메시 읽는 중"}${s.prior ? ` · 지도 ${s.prior.mapVersion} ${mapReviewLabel(s.prior.review)}` : ""}`}
      >
        <span className="height-scale">
          LiDAR 높이 0 m<i style={{ background: rainbowCss }} />5 m
        </span>
        <span>LiDAR 누적 {painted.toLocaleString()}점</span>
        <span>
          <i className="line blue" /> LIO 경로
        </span>
        {s.plan && (
          <span title={s.config.path}>
            <i className="line magenta" /> 글로벌 경로{" "}
            {(s.plan.points.length / 3).toLocaleString()}점
          </span>
        )}
        <em>
          {s.prior
            ? `지도 ${s.prior.mapVersion ?? "ROS 발행본"} · ${(s.prior.points.length / 3).toLocaleString()}점`
            : "지도 대기"}
        </em>
      </div>
    </section>
  );
}
