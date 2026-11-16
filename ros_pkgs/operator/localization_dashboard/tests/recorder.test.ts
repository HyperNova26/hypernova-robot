// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from "vitest";
import { McapIndexedReader, TempBuffer } from "@mcap/core";
import { BagRecorder } from "../src/recorder";

const odom = {
  topic: "/localization/odometry",
  schemaName: "nav_msgs/msg/Odometry",
  schema: "std_msgs/Header header\nstring child_frame_id\n",
  schemaEncoding: "ros2msg",
  encoding: "cdr",
};
const clock = {
  ...odom,
  topic: "/clock",
  schemaName: "rosgraph_msgs/msg/Clock",
};

describe("ROS 2 bag recorder", () => {
  it("writes raw messages as a ros2-profile MCAP with one schema per topic", async () => {
    const r = new BagRecorder();
    const source = new Uint8Array([0, 1, 0, 0, 9, 9]);
    r.write(odom, source, 10n);
    source[4] = 0; // the recorder must have copied the bytes already
    r.write(clock, new Uint8Array([7]), 11n);
    r.write(odom, new Uint8Array([0, 1, 0, 0, 8]), 12n);
    const blob = await r.finish();
    const reader = await McapIndexedReader.Initialize({
      readable: new TempBuffer(new Uint8Array(await blob.arrayBuffer())),
    });
    expect(reader.header.profile).toBe("ros2");
    const channels = [...reader.channelsById.values()];
    expect(channels.map((c) => c.topic).sort()).toEqual([
      "/clock",
      "/localization/odometry",
    ]);
    expect(channels.every((c) => c.messageEncoding === "cdr")).toBe(true);
    const schemas = [...reader.schemasById.values()];
    expect(schemas.map((s) => s.name).sort()).toEqual([
      "nav_msgs/msg/Odometry",
      "rosgraph_msgs/msg/Clock",
    ]);
    expect(schemas.every((s) => s.encoding === "ros2msg")).toBe(true);
    const messages = [];
    for await (const m of reader.readMessages()) messages.push(m);
    expect(messages.map((m) => m.logTime)).toEqual([10n, 11n, 12n]);
    expect(Array.from(messages[0].data)).toEqual([0, 1, 0, 0, 9, 9]);
    expect(r.messages).toBe(3);
  });
  it("stops at the size limit and reports it once", async () => {
    const onLimit = vi.fn();
    const r = new BagRecorder(64, onLimit);
    for (let i = 0; i < 20; i++) r.write(odom, new Uint8Array(32), BigInt(i));
    await r.finish();
    expect(onLimit).toHaveBeenCalledTimes(1);
    expect(r.messages).toBe(2); // 32 + 32 bytes reach the 64-byte limit
  });
});
