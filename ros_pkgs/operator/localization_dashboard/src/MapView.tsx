// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { telemetry as s } from "./store";
import { mapClasses, mapReviewLabel, priorExcluded } from "./model";
import { createGo2Marker } from "./Go2Marker";
const groundLabel = mapClasses.findIndex((c) => c.name === "지면"),
  priorGray = "#9aa4ad";
type IncidentPosition = { x: number; y: number; z: number; frame: string };
export function MapView({ incident }: { incident?: IncidentPosition } = {}) {
  const incidentPosition = useRef(incident);
  incidentPosition.current = incident;
  const host = useRef<HTMLDivElement>(null),
    api = useRef<
      | { fit: () => void; top: () => void; iso: () => void; focus: () => void }
      | undefined
    >(undefined);
  const [follow, setFollow] = useState(false),
    [gt, setGt] = useState(true),
    [scan, setScan] = useState(true),
    [classify, setClassify] = useState(false),
    [ground, setGround] = useState(true),
    [offGround, setOffGround] = useState(true),
    [mesh, setMesh] = useState(true),
    [meshInfo, setMeshInfo] = useState(""),
    [size, setSize] = useState(3),
    [failure, setFailure] = useState("");
  const options = useRef({
    follow,
    gt,
    scan,
    classify,
    ground,
    offGround,
    mesh,
    size,
  });
  options.current = {
    follow,
    gt,
    scan,
    classify,
    ground,
    offGround,
    mesh,
    size,
  };
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
    const grid = new THREE.GridHelper(400, 80, 0x314454, 0x1a2b38);
    grid.rotation.x = Math.PI / 2;
    scene.add(
      grid,
      new THREE.AxesHelper(5),
      new THREE.HemisphereLight(0xe9f4ff, 0x324253, 3),
    );
    const light = new THREE.DirectionalLight(0xffffff, 2);
    light.position.set(10, -10, 30);
    scene.add(light);
    const mapGeometry = new THREE.BufferGeometry(),
      scanGeometry = new THREE.BufferGeometry();
    const mapMaterial = new THREE.PointsMaterial({
        size: 0.13,
        vertexColors: true,
      }),
      scanMaterial = new THREE.PointsMaterial({ size: 0.1, color: 0xe9bd57 });
    const map = new THREE.Points(mapGeometry, mapMaterial),
      currentScan = new THREE.Points(scanGeometry, scanMaterial);
    scene.add(map, currentScan);
    // Terrain display mesh from the MuJoCo heightfields (pair360_map, declared by the package).
    const terrain = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({
        color: 0x4f6b5c,
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
    const meshLoad = new AbortController();
    fetch("/terrain-mesh.json", { signal: meshLoad.signal, cache: "no-cache" })
      .then(async (response) => {
        if (
          response.status === 404 ||
          response.headers.get("content-type")?.includes("text/html")
        ) {
          setMeshInfo("지형 메시 없음");
          return;
        }
        if (!response.ok) throw Error("지형 메시를 읽을 수 없습니다.");
        const meta = await response.json();
        if (
          typeof meta.file !== "string" ||
          !/^[a-zA-Z0-9._-]+\.bin$/.test(meta.file) ||
          !Number.isInteger(meta.vertices) ||
          !Number.isInteger(meta.triangles)
        )
          throw Error("잘못된 메시 메타데이터");
        const bin = await fetch("/" + meta.file, { signal: meshLoad.signal });
        if (!bin.ok) throw Error("지형 메시 파일을 읽을 수 없습니다.");
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
    scene.add(path, gtLine);
    const robot = createGo2Marker();
    scene.add(robot.root);
    const marker = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.5),
      new THREE.MeshBasicMaterial({ color: 0xffc579 }),
    );
    marker.visible = false;
    scene.add(marker);
    let previousMap: unknown,
      previousScan: unknown,
      lastPath = -1,
      lastGT = -1,
      lastColor = false,
      lastLayers = "",
      lastEpoch = -1,
      lastIncident: IncidentPosition | undefined,
      id = 0;
    const center = new THREE.Vector3(),
      extent = new THREE.Vector3(40, 40, 10);
    const fit = () => {
      mapGeometry.computeBoundingBox();
      const bounds = mapGeometry.boundingBox;
      if (bounds && !bounds.isEmpty()) {
        bounds.getCenter(center);
        bounds.getSize(extent);
      }
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
    api.current = {
      fit,
      top: () => {
        const d = Math.max(5, camera.position.distanceTo(controls.target));
        camera.position
          .copy(controls.target)
          .add(new THREE.Vector3(0, -0.001, d));
      },
      iso: fit,
      focus: () => {
        if (!s.current) return;
        const p = s.current.p;
        controls.target.set(p.x, p.y, p.z);
        camera.position.set(p.x + 6, p.y - 8, p.z + 5);
      },
    };
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
            (p) => p.frame === s.displayFrame && p.child === s.displayBase,
          )
          .flatMap((p) => [p.p.x, p.p.y, p.p.z]),
      );
    const draw = () => {
      const opts = options.current,
        prior = s.prior;
      if (
        prior !== previousMap ||
        opts.classify !== lastColor ||
        `${opts.ground}${opts.offGround}` !== lastLayers
      ) {
        const changed = prior !== previousMap;
        previousMap = prior;
        lastColor = opts.classify;
        lastLayers = `${opts.ground}${opts.offGround}`;
        const all = prior?.points ?? new Float32Array(0);
        // Without labels the ground/non-ground split is unknown: either box shows every point.
        // Prior = ground + non-ground; vehicle/noise labels are never prior map.
        const keep = (i: number) =>
          prior?.labels
            ? priorExcluded.has(prior.labels[i])
              ? false
              : prior.labels[i] === groundLabel
                ? opts.ground
                : opts.offGround
            : opts.ground || opts.offGround;
        const pts =
          opts.ground && opts.offGround && !prior?.labels
            ? all
            : all.filter((_, i) => keep(Math.floor(i / 3)));
        mapGeometry.setAttribute("position", new THREE.BufferAttribute(pts, 3));
        const colors = new Float32Array(pts.length),
          color = new THREE.Color();
        for (let i = 0, k = 0; i < all.length; i += 3) {
          if (!keep(i / 3)) continue;
          color.set(
            opts.classify && prior?.labels
              ? (mapClasses[prior.labels[i / 3]]?.color ?? priorGray)
              : priorGray,
          );
          colors.set([color.r, color.g, color.b], k);
          k += 3;
        }
        mapGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        mapGeometry.computeBoundingSphere();
        if (changed && prior) fit();
      }
      terrain.visible =
        opts.mesh &&
        !!terrain.geometry.index &&
        !s.syntheticFrame &&
        (!s.liveSession ||
          s.config.mapVerified ||
          s.livePrior?.frame === s.displayFrame);
      const cloud = s.mapAligned && opts.scan ? s.mapCloud : undefined;
      if (cloud !== previousScan) {
        previousScan = cloud;
        scanGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(cloud?.points ?? new Float32Array(0), 3),
        );
        scanGeometry.computeBoundingSphere();
      }
      if (lastEpoch !== s.epoch) {
        lastEpoch = s.epoch;
        lastPath = lastGT = -1;
        lastIncident = undefined;
      }
      if (lastPath !== s.lio.length || lastPath === 6000) {
        lastPath = s.lio.length;
        pathGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(posePoints(s.lio), 3),
        );
        pathGeometry.computeBoundingSphere();
      }
      if (lastGT !== s.gt.length || lastGT === 6000) {
        lastGT = s.gt.length;
        gtGeometry.setAttribute(
          "position",
          new THREE.BufferAttribute(posePoints(s.gt), 3),
        );
        gtGeometry.computeBoundingSphere();
        gtLine.computeLineDistances();
      }
      const positionAligned = s.mapAligned || !s.prior;
      path.visible = positionAligned;
      gtLine.visible = positionAligned && opts.gt;
      const incident = incidentPosition.current;
      marker.visible =
        !!incident && positionAligned && incident.frame === s.displayFrame;
      if (incident && marker.visible) {
        marker.position.set(incident.x, incident.y, incident.z + 0.55);
        if (
          !lastIncident ||
          incident.x !== lastIncident.x ||
          incident.y !== lastIncident.y ||
          incident.z !== lastIncident.z
        ) {
          const delta = marker.position.clone().sub(controls.target);
          camera.position.add(delta);
          controls.target.copy(marker.position);
        }
      }
      lastIncident = incident;
      const p = s.current;
      robot.root.visible =
        !!p &&
        positionAligned &&
        p.frame === s.displayFrame &&
        p.child === s.displayBase;
      if (p && robot.root.visible) {
        robot.root.position.set(p.p.x, p.p.y, p.p.z);
        const q = s.lio.at(-1)?.q;
        if (q) robot.root.quaternion.set(q.x, q.y, q.z, q.w);
        robot.root.scale.setScalar(opts.size);
        robot.animate(p.t * 8, s.receiving && (p.speed ?? 0) > 0.03);
        if (opts.follow) {
          const delta = robot.root.position.clone().sub(controls.target);
          camera.position.add(delta);
          controls.target.copy(robot.root.position);
        }
      }
      controls.update();
      renderer.render(scene, camera);
      id = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      cancelAnimationFrame(id);
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
  return (
    <section className="panel map-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow">LOCALIZATION · XYZ</span>
          <h2>3D 지도 & 이동 궤적</h2>
        </div>
        <span className="subtle">
          {s.syntheticFrame
            ? "합성 평면"
            : s.livePrior
              ? "ROS 지도"
              : s.prior
                ? "로컬 지도"
                : "기준 지도 대기"}
          <span className="chip">Z 포함 · m</span>
        </span>
      </div>
      <div className="map-surface">
        <div className="map-three" ref={host} />
        {failure && <div className="map-empty">{failure}</div>}
        <div className="map-tags">
          <span className="chip">
            {s.demo
              ? "합성 데이터 미리보기"
              : s.mapAligned
                ? s.displayFrame
                : "지도 좌표 정합 미확인"}
          </span>
          {s.prior && s.prior === s.localPrior && (
            <span
              className={"chip" + (s.prior.review ? " review" : " unreviewed")}
              title={s.prior.reviewReason ?? "map-release manifest 검수 상태"}
            >
              {mapReviewLabel(s.prior.review)}
            </span>
          )}
        </div>
        <div className="map-controls">
          <button onClick={() => api.current?.fit()}>전체 보기</button>
          <button onClick={() => api.current?.top()}>위에서</button>
          <button onClick={() => api.current?.iso()}>입체 보기</button>
        </div>
        <div className="map-bottom">
          <button
            className={follow ? "active" : ""}
            onClick={() => {
              if (!follow) api.current?.focus();
              setFollow(!follow);
            }}
          >
            로봇 따라가기 {follow ? "ON" : "OFF"}
          </button>
          <label>
            <input
              type="checkbox"
              checked={gt}
              onChange={(e) => setGt(e.target.checked)}
            />
            GT
          </label>
          <span className="layer-group" aria-label="표시 레이어">
            <label title={meshInfo}>
              <input
                type="checkbox"
                checked={mesh}
                onChange={(e) => setMesh(e.target.checked)}
              />
              메시
            </label>
            <label
              title={
                s.prior?.labels
                  ? "prior map 중 지면 라벨 점"
                  : "이 지도에는 분류 라벨이 없어 지면을 구분하지 못합니다"
              }
            >
              <input
                type="checkbox"
                checked={ground}
                onChange={(e) => setGround(e.target.checked)}
              />
              Prior 지면
            </label>
            <label title="prior map 중 지면이 아닌 점(줄기·수관·시설물·미분류). 차량·노이즈는 제외">
              <input
                type="checkbox"
                checked={offGround}
                onChange={(e) => setOffGround(e.target.checked)}
              />
              Prior 비지면
            </label>
            <label title="현재 LiDAR 스캔">
              <input
                type="checkbox"
                checked={scan}
                onChange={(e) => setScan(e.target.checked)}
              />
              LiDAR
            </label>
          </span>
          <label>
            <input
              type="checkbox"
              checked={classify}
              onChange={(e) => setClassify(e.target.checked)}
            />
            분류색
          </label>
          <label title="실제 크기가 아닌 표시용 배율">
            Go2 표시 배율
            <input
              aria-label="Go2 표시 배율"
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
      <div className="map-legend">
        <span>
          {s.syntheticFrame
            ? "합성 데모 평면"
            : (s.prior?.mapVersion ?? "실시간 기준 지도")}{" "}
          · 왼쪽 드래그 회전 · 오른쪽 드래그 이동 · 휠 확대
        </span>
        <em>
          {s.prior
            ? (s.prior.points.length / 3).toLocaleString() + " pts"
            : "지도 대기"}
        </em>
      </div>
      <div className="map-model-note">
        Go2 간략 모델 · 위치 기준 {s.displayBase} · 보행은 속도 기반 표시용
        애니메이션 (관절 실측 아님) ·{" "}
        {s.syntheticFrame
          ? "합성 평면 · z=0 m"
          : meshInfo || "지형 메시 읽는 중"}
      </div>
    </section>
  );
}
