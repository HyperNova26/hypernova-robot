// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Circle,
  Download,
  Pause,
  Play,
  Plug,
  Radio,
  Square,
  Terminal,
  Upload,
  X,
} from "lucide-react";
import { PCDLoader } from "three/addons/loaders/PCDLoader.js";
import { telemetry as s } from "./store";
import {
  csv,
  mapLabel,
  mapReviewLabel,
  type Config,
  type Sample,
} from "./model";
import { BagRecorder } from "./recorder";
import { LidarView } from "./LidarView";

const n = (v: number | undefined, d = 2) =>
  v === undefined || !Number.isFinite(v) ? "N/A" : v.toFixed(d);
function LocalizationState() {
  const status = s.localization;
  const age = status ? Date.now() - status.received : undefined;
  const stale = age !== undefined && age >= s.config.timeout;
  const quality = status?.quality;
  const provenance = [
    quality?.source && `추정기 ${quality.source}`,
    quality?.statusText && `세부 상태 ${quality.statusText}`,
    quality?.poseAccepted === undefined
      ? undefined
      : `해당 스캔 자세 ${quality.poseAccepted ? "발행" : "미발행"}`,
  ].filter(Boolean);
  const measurements = [
    quality?.latencyMs === undefined
      ? undefined
      : `처리 지연 ${n(quality.latencyMs, 1)} ms`,
    quality?.fitness === undefined
      ? undefined
      : `정합 inlier 비율 ${n(quality.fitness * 100, 1)}%`,
    quality?.rmseM === undefined
      ? undefined
      : `정합 RMSE ${n(quality.rmseM, 3)} m`,
  ].filter(Boolean);
  return (
    <div className="localization-state">
      <div className="localization-label">
        <span>위치추정 상태</span>
        <span>
          {stale ? "상태 수신 지연" : status ? "상태 수신 중" : "상태 미수신"}
        </span>
      </div>
      <div className="localization-value">
        <strong data-code={status?.code} className={stale ? "stale" : ""}>
          {status?.label ??
            (s.liveSession || s.demo ? "상태 메시지 없음" : "대기 중")}
        </strong>
        <small>
          {status?.code === undefined ? "—" : "CODE " + status.code}
        </small>
      </div>
      <div className="localization-detail">
        {status?.issue ??
          (status
            ? "측정 t=" +
              (status.t === undefined ? "미제공" : status.t.toFixed(3) + " s") +
              " · 수신 " +
              Math.round(age!) +
              " ms 전"
            : "/localization/status · 코드 0–5")}
      </div>
      {provenance.length > 0 && (
        <div className="localization-detail">{provenance.join(" · ")}</div>
      )}
      {measurements.length > 0 && (
        <div className="localization-detail">{measurements.join(" · ")}</div>
      )}
      {status?.issue && (
        <details>
          <summary>수신 메시지 확인</summary>
          <pre>
            {JSON.stringify(
              status.raw,
              (_, v) => (typeof v === "bigint" ? String(v) : v),
              2,
            )}
          </pre>
        </details>
      )}
    </div>
  );
}
function State() {
  const a = s.current;
  const age = s.current ? Date.now() - s.current.received : undefined;
  return (
    <section className="panel state-panel">
      <div className="panel-head compact">
        <h2>
          <Activity size={14} /> Robot State
        </h2>
        <span className={s.receiving ? "status good" : "status"}>
          <i />
          {s.receiving ? "Odometry 수신 중" : "Odometry 수신 없음"}
        </span>
      </div>
      <LocalizationState />
      <div className="state-body">
        <div className="state-label">
          POSITION{" "}
          <span>
            m · {a?.frame || s.config.frame} → {a?.child || s.config.base}
          </span>
        </div>
        <div className="triplet">
          {(["x", "y", "z"] as const).map((k) => (
            <div key={k}>
              <small>{k.toUpperCase()}</small>
              <strong>{n(a?.p[k])}</strong>
            </div>
          ))}
        </div>
        <div className="attitude">
          {(["x", "y", "z"] as const).map((k, i) => (
            <div key={k}>
              <small>{["ROLL", "PITCH", "YAW"][i]}</small>
              <b>
                {n(a?.rpy[k], 1)}
                <em>°</em>
              </b>
            </div>
          ))}
        </div>
        <div className="metrics">
          <div>
            <small>수평 속력</small>
            <b>
              {n(a?.speed)}
              <em>m/s</em>
            </b>
          </div>
          <div title={a?.reason || "동일 시각·기준 좌표의 3D 위치 차이"}>
            <small>GT 위치 오차</small>
            <b>
              {n(a?.error, 3)}
              <em>m</em>
            </b>
          </div>
          <div>
            <small>마지막 LIO 수신</small>
            <b>
              {age === undefined ? "N/A" : n(age, 0)}
              <em>ms</em>
            </b>
          </div>
        </div>
        <div className="state-foot">
          {a
            ? `속력: ${a.speedSource} · 측정 t=${n(a.t, 3)} s`
            : "Odometry 메시지를 기다리고 있습니다."}
        </div>
      </div>
    </section>
  );
}
// Close the active bag and hand it to the browser as a download. Safe to call when idle.
export async function finishRecording() {
  const recorder = s.recorder;
  if (!recorder) return;
  const epoch = s.epoch;
  s.recorder = undefined;
  s.notify();
  try {
    const blob = await recorder.finish();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `hyper-${new Date(recorder.started).toISOString().replace(/[:.]/g, "-")}.mcap`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    if (s.epoch === epoch)
      s.event(
        `bag 저장: ${recorder.messages.toLocaleString()}개 메시지, ${(blob.size / 1e6).toFixed(1)} MB`,
      );
  } catch (e) {
    if (s.epoch === epoch) s.error = "bag 저장 실패: " + String(e);
  }
  s.notify();
}
function Logger() {
  const [paused, setPaused] = useState(false);
  const frozen = useRef<Sample[]>([]);
  const rows = paused ? frozen.current : s.rows;
  const exportCsv = () => {
    const url = URL.createObjectURL(
      new Blob([csv(s.rows, s.events, s.statuses)], {
        type: "text/csv;charset=utf-8",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `hyper-${s.demo ? "ui-test" : "telemetry"}-${Date.now()}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };
  return (
    <section className="panel logger">
      <div className="panel-head compact">
        <h2>
          <Terminal size={14} /> Telemetry Logger{" "}
          <span className="chip">{s.rows.length.toLocaleString()} / 6,000</span>
        </h2>
        <div className="toolbar">
          <span className="subtle">
            {paused ? "화면 정지 · 수집 계속" : "최근 200행 · 자동 갱신"}
          </span>
          <button
            onClick={() => {
              if (!paused) frozen.current = [...s.rows];
              setPaused(!paused);
            }}
          >
            {paused ? <Play size={13} /> : <Pause size={13} />}{" "}
            {paused ? "재개" : "일시정지"}
          </button>
          <button
            className={s.recorder ? "recording" : ""}
            disabled={!s.recorder && s.transport !== "open"}
            title={
              s.transport === "open"
                ? "받은 ROS 메시지를 원본(CDR) 그대로 ROS 2 bag(MCAP)으로 기록합니다. 대시보드가 구독한 토픽만 들어갑니다."
                : "ROS 수신 중에만 기록할 수 있습니다"
            }
            onClick={() => {
              if (s.recorder) void finishRecording();
              else {
                s.recorder = new BagRecorder(undefined, () => {
                  s.event("bag 1 GB 도달: 자동 저장");
                  void finishRecording();
                });
                s.recorder.seed(s.latched.values());
                s.event("bag 기록 시작");
                s.notify();
              }
            }}
          >
            {s.recorder ? <Square size={13} /> : <Circle size={13} />}{" "}
            {s.recorder
              ? `기록 종료 · ${(s.recorder.bytes / 1e6).toFixed(1)} MB`
              : "bag 기록"}
          </button>
          <button onClick={exportCsv}>
            <Download size={13} /> CSV 저장
          </button>
        </div>
      </div>
      <div className="log-table">
        <table>
          <thead>
            <tr>
              {[
                "SIM TIME (s)",
                "X (m)",
                "Y (m)",
                "Z (m)",
                "ROLL (°)",
                "PITCH (°)",
                "YAW (°)",
                "SPEED (m/s)",
                "GT ERROR (m)",
                "위치추정 상태",
                "LIO 수신",
              ].map((x) => (
                <th key={x}>{x}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(-200)
              .reverse()
              .map((a) => (
                <tr key={a.t}>
                  <td>{n(a.t, 3)}</td>
                  <td>{n(a.p.x, 3)}</td>
                  <td>{n(a.p.y, 3)}</td>
                  <td>{n(a.p.z, 3)}</td>
                  <td>{n(a.rpy.x, 2)}</td>
                  <td>{n(a.rpy.y, 2)}</td>
                  <td>{n(a.rpy.z, 2)}</td>
                  <td>{n(a.speed, 3)}</td>
                  <td title={a.reason}>{n(a.error, 3)}</td>
                  <td>{a.localization?.label || "N/A"}</td>
                  <td>
                    <span className="table-status">● 수신 중</span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {!rows.length && (
          <div className="log-empty">
            수신한 위치 데이터가 여기에 기록됩니다.
          </div>
        )}
      </div>
      <div className="logger-foot">
        <span>
          <i className={s.receiving ? "live-dot" : "idle-dot"} />
          {s.events.at(-1)?.event || "세션 준비 완료"}
          {s.events.length > 0 && ` · t=${n(s.events.at(-1)!.t, 2)} s`}
        </span>
        <span>BUFFER 6,000 · CSV에 시각·좌표계·GT·수신 이벤트 보존</span>
      </div>
    </section>
  );
}
export function ConnectionSettings({
  close,
  onConnect,
}: {
  close: () => void;
  onConnect: () => void;
}) {
  const [c, set] = useState<Config>({ ...s.config });
  const fields: [keyof Config, string][] = [
    ["url", "Foxglove WebSocket"],
    ["frame", "표시 기준 frame"],
    ["base", "추정·비교 기준점 frame"],
    ["lio", "공통 Odometry 토픽"],
    ["gt", "GT Odometry 토픽 (선택, SIM 등)"],
    ["scan", "현재 PointCloud2 토픽"],
    ["status", "LocalizationStatus 토픽"],
    ["statusField", "상태 코드 필드 경로 (기본 status · 미확정)"],
    ["prior", "Reference Map PointCloud2 토픽"],
  ];
  return (
    <div className="modal-backdrop">
      <form
        className="settings"
        onSubmit={(e) => {
          e.preventDefault();
          s.config = c;
          close();
          onConnect();
        }}
      >
        <div className="panel-head">
          <div>
            <span className="eyebrow">DATA CONNECTION</span>
            <h2>데이터 연결 설정</h2>
          </div>
          <button type="button" aria-label="닫기" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <p>
          S-005 명세의 공통 토픽과 좌표를 사용합니다. GT 토픽과 상태 코드
          필드명은 실제 메시지를 확인해 지정하세요.
        </p>
        <div className="settings-grid">
          {fields.map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={String(c[key])}
                onChange={(e) => set({ ...c, [key]: e.target.value })}
                required={["url", "frame", "base", "lio"].includes(key)}
                placeholder={
                  key === "gt"
                    ? "비우면 GT 없음 (REAL). MuJoCo SIM: /ground_truth/odom"
                    : undefined
                }
              />
            </label>
          ))}
          <label>
            GT 시각 허용 차이 (초)
            <input
              type="number"
              min="0"
              max="0.2"
              step="0.001"
              value={c.tolerance}
              onChange={(e) => set({ ...c, tolerance: Number(e.target.value) })}
            />
          </label>
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={c.twistValid}
            onChange={(e) => set({ ...c, twistValid: e.target.checked })}
          />{" "}
          주행 속력에 LIO twist 선속도 사용 (FAST-LIO2는 twist 패치 필요, 0이면
          위치 차분으로 대체)
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={c.mapVerified}
            onChange={(e) => set({ ...c, mapVerified: e.target.checked })}
          />{" "}
          지도 좌표와 표시 frame의 정합을 확인함
        </label>
        <p>
          GT도 mlx_lidar와 같은 기준점을 사용해야 합니다. 상태 코드 필드명은
          명세 캡처에 없어 기본 status를 사용하며, 다르면 위 경로를 변경하세요.
        </p>
        <button className="primary" type="submit">
          <Plug size={15} /> 적용하고 연결
        </button>
      </form>
    </div>
  );
}

function loadPointCloud(
  buffer: ArrayBuffer,
  mapVersion: string,
  meta: { review?: string; reviewReason?: string } = {},
) {
  try {
    const cloud = new PCDLoader().parse(buffer);
    try {
      const positions = cloud.geometry.getAttribute("position");
      const classes = cloud.geometry.getAttribute("label");
      const labels: number[] | undefined = classes ? [] : undefined;
      const stride = Math.max(1, Math.ceil(positions.count / 100000));
      const points: number[] = [];
      for (let i = 0; i < positions.count; i += stride) {
        const xyz = [positions.getX(i), positions.getY(i), positions.getZ(i)];
        if (xyz.every(Number.isFinite)) {
          points.push(...xyz);
          labels?.push(mapLabel(classes.getX(i)));
        }
      }
      s.localPrior = {
        t: 0,
        frame: "unverified",
        mapVersion,
        ...meta,
        points: new Float32Array(points),
        labels: labels && Uint8Array.from(labels),
      };
    } finally {
      cloud.geometry.dispose();
      cloud.material.dispose();
    }
  } catch (error) {
    s.error = "PCD 읽기 실패: " + String(error);
  }
  s.notify();
}

export function useLocalMap() {
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal, cache: "no-cache" as const };
    void fetch("/reference-map.json", options)
      .then(async (response) => {
        if (
          response.status === 404 ||
          response.headers.get("content-type")?.includes("text/html")
        )
          return;
        if (!response.ok) throw Error("지도 목록을 열 수 없습니다.");
        const manifest = await response.json();
        if (
          typeof manifest.file !== "string" ||
          !/^[a-zA-Z0-9._-]+\.pcd$/.test(manifest.file)
        )
          throw Error("잘못된 지도 파일명");
        const map = await fetch("/" + manifest.file, options);
        if (!map.ok) throw Error(manifest.file);
        const bytes = await map.arrayBuffer();
        if (!controller.signal.aborted && !s.localPrior)
          loadPointCloud(bytes, String(manifest.version), {
            review:
              typeof manifest.review_status === "string"
                ? manifest.review_status
                : undefined,
            reviewReason:
              typeof manifest.review_reason === "string"
                ? manifest.review_reason
                : undefined,
          });
      })
      .catch((error) => {
        if (!controller.signal.aborted && !s.localPrior) {
          s.error = "로컬 지도 읽기 실패: " + String(error);
          s.notify();
        }
      });
    return () => controller.abort();
  }, []);
}

export function Diagnostics() {
  const [open, setOpen] = useState(false);
  const upload = useRef<HTMLInputElement>(null);
  return (
    <details
      className="ops-disclosure"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>진단 · LiDAR, GT, TF, CSV·MCAP</summary>
      <div className="ops-diagnostics">
        <div className="ops-row">
          <button onClick={() => upload.current?.click()}>
            <Upload size={16} /> 로컬 지도 PCD 열기
          </button>
          <input
            type="file"
            accept=".pcd"
            hidden
            ref={upload}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file)
                void file
                  .arrayBuffer()
                  .then((bytes) => loadPointCloud(bytes, file.name))
                  .catch((error) => {
                    s.error = "PCD 읽기 실패: " + String(error);
                    s.notify();
                  });
              event.currentTarget.value = "";
            }}
          />
          <span>
            {s.localPrior
              ? `지도 ${s.localPrior.mapVersion} · ${mapReviewLabel(s.localPrior.review)}`
              : "로컬 지도 없음"}
          </span>
          <span>
            표시 frame {s.current?.frame ?? s.config.frame} · 기준점{" "}
            {s.current?.child ?? s.config.base}
          </span>
        </div>
        <div className="ops-diagnostics-grid">
          <State />
          <section className="panel sensor-panel">
            <div className="panel-head compact">
              <h2>
                <Radio size={14} /> LiDAR 3D
              </h2>
              <span className="subtle">
                {s.demo ? "합성 스캔" : s.config.scan || "토픽 미지정"}
              </span>
            </div>
            {open && <LidarView />}
            <div className="sensor-foot">
              {s.cloud && !s.mapCloud
                ? "지도 변환 없음 · 원본 좌표"
                : "드래그 회전 · 휠 확대"}
            </div>
          </section>
        </div>
        <Logger />
      </div>
    </details>
  );
}
