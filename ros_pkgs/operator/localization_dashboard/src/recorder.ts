// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Records the raw CDR messages the dashboard receives into a ROS 2 MCAP bag in memory.
// Read-only: nothing is published to ROS. Only subscribed topics are recorded, as the
// Bridge delivered them (a Bridge can drop messages under load); use `ros2 bag record`
// on the robot for a complete log.
import { McapWriter, type IWritable } from "@mcap/core";

export type RecordChannel = {
  topic: string;
  schemaName: string;
  schema: string;
  schemaEncoding: string;
  encoding: string;
  /** Published once with transient-local durability (reference map, /tf_static). */
  latched?: boolean;
};
export type LatchedMessage = {
  channel: RecordChannel;
  data: Uint8Array;
  logTimeNs: bigint;
};
// rosbag2 reads the offered QoS from channel metadata on playback. For latched topics we
// declare RELIABLE + TRANSIENT_LOCAL, KEEP_LAST 1, so late subscribers still get them.
// Format copied from `ros2 bag record` on Jazzy (string enums; 9223372036 s 854775807 ns = infinite).
const infinite = "\n    sec: 9223372036\n    nsec: 854775807";
const latchedQos =
  "- history: keep_last\n  depth: 1\n  reliability: reliable\n  durability: transient_local\n" +
  `  deadline:${infinite}\n  lifespan:${infinite}\n  liveliness: automatic\n` +
  `  liveliness_lease_duration:${infinite}\n  avoid_ros_namespace_conventions: false\n`;

class Chunks implements IWritable {
  parts: Uint8Array[] = [];
  size = 0;
  async write(buffer: Uint8Array) {
    this.parts.push(buffer.slice());
    this.size += buffer.byteLength;
  }
  position() {
    return BigInt(this.size);
  }
}

export class BagRecorder {
  readonly started = Date.now();
  messages = 0;
  private out = new Chunks();
  private writer = new McapWriter({ writable: this.out });
  private channels = new Map<string, Promise<number>>();
  private queue: Promise<unknown>;
  private sequence = 0;
  // Message payload accepted so far. The writer buffers ~1 MB chunks before they reach
  // `out`, so the limit and the on-screen size use this instead of the flushed size.
  private payload = 0;
  constructor(
    readonly limitBytes = 1024 ** 3,
    private onLimit: () => void = () => {},
  ) {
    this.queue = this.writer.start({
      profile: "ros2",
      library: "hyper-dashboard",
    });
  }
  get bytes() {
    return this.payload;
  }
  get full() {
    return this.payload >= this.limitBytes;
  }
  /** Queue one received message. Order is kept; logTime is the receive time in ns. */
  write(channel: RecordChannel, data: Uint8Array, logTimeNs: bigint) {
    if (this.full) return;
    const copy = data.slice();
    this.messages++;
    this.payload += copy.byteLength;
    if (this.full) queueMicrotask(this.onLimit);
    this.queue = this.queue.then(async () => {
      let id = this.channels.get(channel.topic);
      if (!id) {
        id = (async () => {
          const schemaId = await this.writer.registerSchema({
            name: channel.schemaName,
            encoding: channel.schemaEncoding,
            data: new TextEncoder().encode(channel.schema),
          });
          return this.writer.registerChannel({
            topic: channel.topic,
            schemaId,
            messageEncoding: channel.encoding,
            metadata: new Map(
              channel.latched ? [["offered_qos_profiles", latchedQos]] : [],
            ),
          });
        })();
        this.channels.set(channel.topic, id);
      }
      await this.writer.addMessage({
        channelId: await id,
        sequence: this.sequence++,
        logTime: logTimeNs,
        publishTime: logTimeNs,
        data: copy,
      });
    });
  }
  /** Write the last copy of each latched topic first, stamped at the bag start. */
  seed(latched: Iterable<LatchedMessage>) {
    const start = BigInt(this.started) * 1_000_000n;
    for (const m of latched) this.write(m.channel, m.data, start);
  }
  /** Finish the file (summary and index) and return it as a Blob. */
  async finish() {
    await this.queue;
    await this.writer.end();
    return new Blob(this.out.parts as BlobPart[], {
      type: "application/octet-stream",
    });
  }
}
