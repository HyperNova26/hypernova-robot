// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it, vi } from "vitest";
import { connect } from "../src/bridge";
import { Telemetry } from "../src/store";
import { parse } from "@foxglove/rosmsg";
import { MessageWriter } from "@foxglove/rosmsg2-serialization";
class FakeSocket {
  static latest: FakeSocket;
  onopen?: (event: any) => void;
  onclose?: (event: any) => void;
  onerror?: (event: any) => void;
  onmessage?: (event: any) => void;
  binaryType = "";
  sent: string[] = [];
  constructor() {
    FakeSocket.latest = this;
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
  send(data: string) {
    this.sent.push(data);
  }
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it("ignores late events from a closed connection after switching sessions", () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
  const s = new Telemetry();
  const stop = connect(s);
  stop();
  s.connection = "UI 시험 · 합성 데이터";
  s.lastReceived = 100;
  FakeSocket.latest.onclose?.({ code: 1000 });
  FakeSocket.latest.onopen?.({});
  FakeSocket.latest.onerror?.({ error: new Error("old session") });
  FakeSocket.latest.onmessage?.({
    data: JSON.stringify({
      op: "serverInfo",
      name: "old server",
      capabilities: [],
    }),
  });
  expect(s.connection).toBe("UI 시험 · 합성 데이터");
  expect(s.lastReceived).toBe(100);
  expect(s.error).toBe("");
});
it("reports a genuine bridge close while connected", () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
  const s = new Telemetry();
  const stop = connect(s);
  FakeSocket.latest.onclose?.({ code: 1006 });
  expect(s.connection).toBe("연결 종료");
  expect(s.lastReceived).toBe(0);
  stop();
});
it("decodes an advertised custom status layout instead of assuming the message fields", () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
  const s = new Telemetry();
  s.config.statusField = "state";
  const stop = connect(s);
  const schema = "uint8 state\n",
    socket = FakeSocket.latest;
  socket.onmessage?.({
    data: JSON.stringify({
      op: "advertise",
      channels: [
        {
          id: 7,
          topic: s.config.status,
          encoding: "cdr",
          schemaEncoding: "ros2msg",
          schemaName: "hn_interfaces/msg/LocalizationStatus",
          schema,
        },
      ],
    }),
  });
  const subscription = JSON.parse(socket.sent[0]).subscriptions[0];
  expect(subscription.channelId).toBe(7);
  const payload = new MessageWriter(parse(schema, { ros2: true })).writeMessage(
    { state: 4 },
  );
  const wire = new Uint8Array(13 + payload.length);
  wire[0] = 1;
  new DataView(wire.buffer).setUint32(1, subscription.id, true);
  wire.set(payload, 13);
  socket.onmessage?.({ data: wire.buffer });
  expect(s.localization?.label).toBe("STALE_INPUT");
  expect(s.localization?.t).toBeUndefined();
  expect(s.receiving).toBe(false);
  stop();
});
it("rejects a topic whose advertised message type differs from the contract", () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
  const s = new Telemetry();
  const stop = connect(s);
  FakeSocket.latest.onmessage?.({
    data: JSON.stringify({
      op: "advertise",
      channels: [
        {
          id: 7,
          topic: s.config.status,
          encoding: "cdr",
          schemaEncoding: "ros2msg",
          schemaName: "std_msgs/msg/String",
          schema: "string data\n",
        },
      ],
    }),
  });
  expect(s.error).toContain("hn_interfaces/LocalizationStatus");
  expect(FakeSocket.latest.sent).toHaveLength(0);
  stop();
});
