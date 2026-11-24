// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { CircleAlert, Film, Pause, Play, VideoOff } from "lucide-react";
import {
  findRecord,
  replayTelemetry,
  type OperationRecording,
  type RecordSelection,
} from "./recordings";

const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  dateStyle: "medium",
  timeStyle: "short",
});
const timelineLabel = (ms: number) => {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}.${Math.floor((ms % 1000) / 100)}`;
};

function RecordPlayer({
  record,
  initialOffsetMs,
}: {
  record: OperationRecording;
  initialOffsetMs: number;
}) {
  const [offsetMs, setOffsetMs] = useState(initialOffsetMs);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [ready, setReady] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [stepFrames, setStepFrames] = useState(false);
  const player = useRef<HTMLVideoElement>(null);
  const currentOffset = Math.min(offsetMs, record.durationMs);
  const video = record.video.status === "ready" ? record.video : undefined;
  const videoOffset = video
    ? (currentOffset - video.offsetMs) / 1000
    : undefined;
  const videoAvailable =
    video !== undefined &&
    videoOffset !== undefined &&
    videoOffset >= 0 &&
    videoOffset * 1000 <= video.durationMs;

  useEffect(() => {
    if (!playing) return;
    let previous = performance.now();
    const interval = window.setInterval(() => {
      const now = performance.now();
      const elapsed = now - previous;
      previous = now;
      setOffsetMs((position) =>
        Math.min(record.durationMs, position + elapsed * rate),
      );
    }, 50);
    return () => window.clearInterval(interval);
  }, [playing, rate, record.durationMs]);

  useEffect(() => {
    if (playing && currentOffset >= record.durationMs) setPlaying(false);
  }, [playing, currentOffset, record.durationMs]);

  useEffect(() => {
    const element = player.current;
    if (
      !element ||
      !ready ||
      mediaError ||
      !videoAvailable ||
      videoOffset === undefined
    )
      return;
    // Some browsers end a freshly recorded, video-only WebM immediately
    // after a seek. In that case use the session clock for frame selection.
    const drift = Math.abs(element.currentTime - videoOffset);
    if (!playing || drift > (stepFrames ? 0.075 : 0.25)) {
      const seekAt = Number.isFinite(element.duration)
        ? Math.min(videoOffset, element.duration)
        : videoOffset;
      if (
        Math.abs(element.currentTime - seekAt) < 0.015 ||
        (stepFrames && element.seeking)
      )
        return;
      try {
        element.currentTime = seekAt;
      } catch {
        setMediaError(true);
      }
    }
  }, [playing, videoOffset, videoAvailable, ready, mediaError, stepFrames]);

  useEffect(() => {
    const element = player.current;
    if (!element) return;
    if (!playing || !videoAvailable || mediaError || stepFrames) {
      element.pause();
      return;
    }
    element.playbackRate = rate;
    if (ready) {
      void element.play().catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setMediaError(true);
      });
    }
  }, [playing, videoAvailable, rate, ready, mediaError, stepFrames]);

  const sample = replayTelemetry(record).sampleAt(currentOffset);
  const marker = record.events.find(
    (event) => event.at - record.timeOrigin === currentOffset,
  );
  const dismissPlayback = (offset: number) => {
    setPlaying(false);
    setOffsetMs(Math.max(0, Math.min(record.durationMs, offset)));
  };
  const videoStatus =
    record.video.status === "processing"
      ? record.active
        ? "영상 기록 중 · 기록 종료 후 재생 가능"
        : "합성 영상 처리 중"
      : record.video.status === "missing" || record.video.status === "error"
        ? record.video.reason
        : mediaError
          ? "영상 재생 오류"
          : !videoAvailable
            ? "이 시점의 영상 없음"
            : !ready
              ? "영상 불러오는 중"
              : undefined;

  return (
    <section className="record-detail" aria-label="기록 상세">
      <header className="record-detail-head">
        <h3>{record.mission ?? "운용 세션"}</h3>
        <span>
          {record.example
            ? "합성 예제"
            : record.active
              ? "기록 중"
              : "기록 종료"}{" "}
          · {record.source}
        </span>
      </header>
      <p className="record-metadata">
        {dateFormat.format(record.timeOrigin)} · 세션 {record.sessionId}
        {record.stopReason ? ` · ${record.stopReason}` : ""}
      </p>
      <div className="record-media">
        {video && (
          <video
            ref={player}
            src={video.url}
            aria-label={video.camera}
            preload="metadata"
            muted
            playsInline
            hidden={!videoAvailable || mediaError || !ready}
            onLoadedMetadata={() => setReady(true)}
            onEnded={() => {
              if (
                playing &&
                videoOffset !== undefined &&
                videoOffset * 1000 < video.durationMs - 250
              ) {
                setStepFrames(true);
              }
            }}
            onError={() => setMediaError(true)}
          />
        )}
        {videoStatus && (
          <div
            className="record-video-status"
            role={mediaError ? "alert" : "status"}
          >
            <VideoOff size={24} aria-hidden />
            <p>{videoStatus}</p>
          </div>
        )}
      </div>
      {video && (
        <p className="record-media-caption">
          {video.camera} · 영상 시작 {timelineLabel(video.offsetMs)}
        </p>
      )}
      <div className="record-timeline">
        <div className="record-controls">
          <button
            type="button"
            disabled={record.durationMs <= 0}
            onClick={() => {
              if (!playing && currentOffset >= record.durationMs)
                setOffsetMs(0);
              setPlaying(!playing);
            }}
          >
            {playing ? (
              <Pause size={16} aria-hidden />
            ) : (
              <Play size={16} aria-hidden />
            )}
            {playing ? "일시정지" : "재생"}
          </button>
          <output aria-label="재생 시간">
            {timelineLabel(currentOffset)} / {timelineLabel(record.durationMs)}
          </output>
          <label>
            배속
            <select
              value={rate}
              onChange={(event) => setRate(Number(event.target.value))}
            >
              {[0.5, 1, 1.5, 2].map((speed) => (
                <option key={speed} value={speed}>
                  {speed}×
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="record-scrubber">
          <input
            type="range"
            min={0}
            max={Math.max(1, record.durationMs)}
            step={1}
            value={currentOffset}
            disabled={record.durationMs <= 0}
            aria-label="기록 시점 탐색"
            aria-valuetext={timelineLabel(currentOffset)}
            onChange={(event) => dismissPlayback(Number(event.target.value))}
          />
          <div className="record-track-markers" aria-label="타임라인 이벤트">
            {record.events.map((event) => {
              const position = event.at - record.timeOrigin;
              return (
                <button
                  className="record-track-marker"
                  key={event.id}
                  type="button"
                  style={{
                    left: `${(100 * position) / Math.max(1, record.durationMs)}%`,
                  }}
                  onClick={() => dismissPlayback(position)}
                  title={`${timelineLabel(position)} · ${event.title}`}
                  aria-label={`${timelineLabel(position)} ${event.title} 시점으로 이동`}
                >
                  {event.incidentId ? (
                    <CircleAlert size={13} aria-hidden />
                  ) : (
                    <span aria-hidden>•</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
        {marker && (
          <p className="record-marker-detail">
            {marker.title} · {timelineLabel(currentOffset)}
            {video &&
              marker.at - record.timeOrigin < video.offsetMs &&
              " · 사건 시점 영상 없음"}
          </p>
        )}
        {record.events.length > 0 && (
          <ul className="record-event-list">
            {record.events.map((event) => (
              <li key={event.id}>
                <button
                  type="button"
                  onClick={() => dismissPlayback(event.at - record.timeOrigin)}
                >
                  {timelineLabel(event.at - record.timeOrigin)} · {event.title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="record-state">
        <h4>기록 시점의 텔레메트리</h4>
        {sample ? (
          <dl>
            <div>
              <dt>지도 위치</dt>
              <dd>
                {sample.pose
                  ? `X ${sample.pose.x.toFixed(2)} m · Y ${sample.pose.y.toFixed(2)} m · 방향 ${((sample.pose.yaw * 180) / Math.PI).toFixed(0)}°`
                  : "위치 없음"}
                {sample.coordinateFrame && (
                  <small> · {sample.coordinateFrame}</small>
                )}
              </dd>
            </div>
            <div>
              <dt>운용 모드</dt>
              <dd>{sample.mode ?? "제공되지 않음"}</dd>
            </div>
            <div>
              <dt>임무 상태</dt>
              <dd>{sample.phase ?? "제공되지 않음"}</dd>
            </div>
            <div>
              <dt>임무 / 목표</dt>
              <dd>
                {sample.mission ?? "—"} / {sample.waypoint ?? "—"}
              </dd>
            </div>
            <div>
              <dt>위치추정</dt>
              <dd>{sample.localization ?? "상태 미수신"}</dd>
            </div>
            <div>
              <dt>활성 알람</dt>
              <dd>{sample.incidents?.join(", ") || "없음"}</dd>
            </div>
            {sample.rosTimeSeconds !== undefined && (
              <div>
                <dt>ROS 측정 시각</dt>
                <dd>{sample.rosTimeSeconds.toFixed(3)} s</dd>
              </div>
            )}
          </dl>
        ) : (
          <p>이 시점에 연결된 텔레메트리가 없습니다.</p>
        )}
      </div>
    </section>
  );
}

export function RecordsView({
  records,
  selection,
  onReturn,
}: {
  records: readonly OperationRecording[];
  selection?: RecordSelection;
  onReturn: () => void;
}) {
  const [session, setSession] = useState("");
  const [mission, setMission] = useState("");
  const [incident, setIncident] = useState("");
  const [chosen, setChosen] = useState<string>();
  const target = chosen ? undefined : findRecord(records, selection);
  const sessions = [...new Set(records.map((record) => record.sessionId))];
  const missions = [...new Set(records.flatMap((record) => record.missions))];
  const events = new Map(
    records.flatMap((record) =>
      record.events.flatMap((event) =>
        event.incidentId ? [[event.incidentId, event.title] as const] : [],
      ),
    ),
  );
  const visibleRecords = records.filter(
    (record) =>
      (!session || record.sessionId === session) &&
      (!mission || record.missions.includes(mission)) &&
      (!incident ||
        record.events.some((event) => event.incidentId === incident)),
  );
  const selected =
    visibleRecords.find((record) => record.id === chosen) ??
    (target && visibleRecords.some((record) => record.id === target.record.id)
      ? target.record
      : chosen || !selection
        ? (visibleRecords.find((record) => !record.active) ?? visibleRecords[0])
        : undefined);
  const targetOffset =
    selected?.id === target?.record.id ? (target?.offsetMs ?? 0) : 0;
  return (
    <section className="records-view" aria-label="기록 열람">
      <header className="records-head">
        <div>
          <h2>기록 열람</h2>
          <p>REPLAY · 과거 세션</p>
        </div>
        <button type="button" onClick={onReturn}>
          현재 운용으로 돌아가기
        </button>
      </header>
      <div className="records-filters" aria-label="기록 검색">
        <label>
          세션
          <select
            value={session}
            onChange={(event) => setSession(event.target.value)}
          >
            <option value="">모든 세션</option>
            {sessions.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <label>
          임무
          <select
            value={mission}
            onChange={(event) => setMission(event.target.value)}
          >
            <option value="">모든 임무</option>
            {missions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          이상 사건
          <select
            value={incident}
            onChange={(event) => setIncident(event.target.value)}
          >
            <option value="">모든 사건</option>
            {[...events].map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="records-layout">
        {visibleRecords.length > 0 ? (
          <ul className="records-list" aria-label="기록 목록">
            {visibleRecords.map((record) => {
              const eventCount = new Set(
                record.events.map((event) => event.incidentId).filter(Boolean),
              ).size;
              const media =
                record.video.status === "ready"
                  ? "합성 영상"
                  : record.video.status === "processing"
                    ? "영상 처리 중"
                    : "영상 없음";
              return (
                <li key={record.id}>
                  <button
                    type="button"
                    aria-pressed={record.id === selected?.id}
                    onClick={() => setChosen(record.id)}
                  >
                    <Film size={16} aria-hidden />
                    <span>
                      <strong>{record.mission ?? "운용 세션"}</strong>
                      <span>
                        {record.example && "예제 · "}
                        {record.source} · {dateFormat.format(record.timeOrigin)}
                      </span>
                      <span>
                        {timelineLabel(record.durationMs)} · 사건 {eventCount}건
                        · {media}
                        {record.samples.length > 0 && " · 텔레메트리"}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p role="status">조건에 맞는 기록이 없습니다.</p>
        )}
        {selected ? (
          <RecordPlayer
            key={`${selected.id}:${targetOffset}`}
            record={selected}
            initialOffsetMs={targetOffset}
          />
        ) : (
          selection?.incidentId && (
            <p role="status">이 사건에 연결된 운용 기록이 없습니다.</p>
          )
        )}
      </div>
    </section>
  );
}
