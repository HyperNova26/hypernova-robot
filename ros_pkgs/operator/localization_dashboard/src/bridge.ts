// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { FoxgloveClient } from "@foxglove/ws-protocol";
import { parse } from "@foxglove/rosmsg";
import { MessageReader } from "@foxglove/rosmsg2-serialization";
import { type Telemetry } from "./store";
import { type RecordChannel } from "./recorder";
export function connect(store: Telemetry) {
  const endpoint = new URL(store.config.url);
  if (!["ws:", "wss:"].includes(endpoint.protocol))
    throw Error("WebSocket 주소는 ws:// 또는 wss://로 시작해야 합니다.");
  let active = true;
  const socket = new WebSocket(store.config.url, [
    "foxglove.sdk.v1",
    "foxglove.websocket.v1",
  ]);
  const client = new FoxgloveClient({ ws: socket });
  const subscriptions = new Map<
    number,
    { role: string; reader: MessageReader; channel: RecordChannel }
  >();
  const channelSubs = new Map<number, number>();
  const topics: Record<string, string> = {
    lio: store.config.lio,
    gt: store.config.gt,
    scan: store.config.scan,
    status: store.config.status,
    locomotion: store.config.locomotion,
    prior: store.config.prior,
    path: store.config.path,
    clock: "/clock",
    tf: "/tf",
    tf_static: "/tf_static",
  };
  store.connection = "연결 중";
  store.link = "connecting";
  store.livePrior = undefined;
  store.liveSession = true;
  store.notify();
  // A browser WebSocket error carries no reason; whether the socket ever opened tells
  // "nothing is listening at this address" apart from a bridge that went away.
  let opened = false;
  client.on("open", () => {
    if (!active) return;
    opened = true;
    store.link = "open";
    store.connection = "Bridge 연결 · 토픽 대기";
    store.event("Bridge 연결");
    store.notify();
  });
  client.on("serverInfo", (info) => {
    if (!active) return;
    store.connection = info.name || "Bridge 연결";
    store.event("서버: " + store.connection);
    store.notify();
  });
  client.on("error", (e) => {
    if (!active) return;
    store.error = opened
      ? "Bridge 연결 오류: " + e.message
      : `${store.config.url}에 연결하지 못했습니다. 데이터 소스(bag 재생·시뮬)가 켜져 있는지 확인하세요.`;
    store.notify();
  });
  client.on("close", () => {
    if (!active) return;
    store.link = opened ? "closed" : "failed";
    store.connection = opened ? "연결 종료" : "연결 실패";
    store.event(opened ? "Bridge 연결 종료" : "Bridge 연결 실패");
    if (opened && !store.error)
      store.error =
        "Bridge 연결이 끊겼습니다. bag 재생이 끝났거나 데이터 소스가 꺼졌습니다.";
    store.lastReceived = 0;
    store.tick();
  });
  client.on("advertise", (channels) => {
    if (!active) return;
    for (const channel of channels) {
      const role = Object.keys(topics).find(
        (r) => topics[r] && topics[r] === channel.topic,
      );
      if (!role || channelSubs.has(channel.id)) continue;
      try {
        const expected: Record<string, string> = {
          lio: "nav_msgs/Odometry",
          gt: "nav_msgs/Odometry",
          scan: "sensor_msgs/PointCloud2",
          prior: "sensor_msgs/PointCloud2",
          path: "nav_msgs/Path",
          status: "hn_interfaces/LocalizationStatus",
          locomotion: "hn_interfaces/LocomotionStatus",
          tf: "tf2_msgs/TFMessage",
          tf_static: "tf2_msgs/TFMessage",
          clock: "rosgraph_msgs/Clock",
        };
        const type = channel.schemaName.replace("/msg/", "/");
        // G-006 and the provisional localization status use DiagnosticArray; the hn_interfaces
        // drafts are still accepted.
        const accepted =
          role === "locomotion" || role === "status"
            ? [expected[role], "diagnostic_msgs/DiagnosticArray"]
            : [expected[role]];
        if (!accepted.includes(type))
          throw Error(
            `${channel.topic}: 예상 형식 ${expected[role]}, 실제 ${channel.schemaName}`,
          );
        if (channel.encoding !== "cdr" || channel.schemaEncoding === "ros2idl")
          throw Error(
            "지원 형식: CDR + ros2msg. 현재 " +
              channel.encoding +
              " / " +
              channel.schemaEncoding,
          );
        const reader = new MessageReader(parse(channel.schema, { ros2: true }));
        const id = client.subscribe(channel.id);
        subscriptions.set(id, {
          role,
          reader,
          channel: {
            topic: channel.topic,
            schemaName: channel.schemaName,
            schema: channel.schema,
            schemaEncoding: channel.schemaEncoding ?? "ros2msg",
            encoding: channel.encoding,
            // Both status topics are transient_local depth 1 (ADR-0004), like the map and static TF.
            latched:
              role === "prior" ||
              role === "tf_static" ||
              role === "locomotion" ||
              role === "status",
          },
        });
        channelSubs.set(channel.id, id);
        store.event("구독: " + channel.topic);
      } catch (e) {
        store.error = String(e);
        store.notify();
      }
    }
  });
  client.on("unadvertise", (ids) => {
    if (!active) return;
    for (const id of ids) {
      const sub = channelSubs.get(id);
      if (sub !== undefined) {
        subscriptions.delete(sub);
        channelSubs.delete(id);
      }
    }
  });
  client.on("message", (message) => {
    if (!active) return;
    const sub = subscriptions.get(message.subscriptionId);
    if (!sub) return;
    // Raw CDR bytes go to the bag before decoding, so a decode error never drops a record.
    const raw = new Uint8Array(
      message.data.buffer,
      message.data.byteOffset,
      message.data.byteLength,
    );
    store.recorder?.write(sub.channel, raw, message.timestamp);
    // Latched topics arrive once at subscribe time; keep the last one so a bag started
    // later still contains them (BagRecorder.seed).
    if (sub.channel.latched)
      store.latched.set(sub.channel.topic, {
        channel: sub.channel,
        data: raw.slice(),
        logTimeNs: message.timestamp,
      });
    try {
      store.ingest(sub.role, sub.reader.readMessage(message.data));
    } catch (e) {
      store.error = "CDR 디코딩 실패: " + String(e);
      store.notify();
    }
  });
  const timer = setInterval(() => store.tick(), 200);
  return () => {
    active = false;
    store.link = "idle";
    clearInterval(timer);
    client.close();
  };
}
