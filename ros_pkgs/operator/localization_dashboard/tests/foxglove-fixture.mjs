// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Synthetic WebSocket/CDR integration fixture. NOT a ROS or MuJoCo process.
import { WebSocketServer } from "ws";
import protocol from "@foxglove/ws-protocol";
import serialization from "@foxglove/rosmsg2-serialization";
import rosmsg from "@foxglove/rosmsg";
const { FoxgloveServer } = protocol,
  { MessageWriter } = serialization,
  { parse } = rosmsg;
const header = `std_msgs/Header header\n`;
const deps = `\n================================================================================\nMSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id\n================================================================================\nMSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n`;
const odom =
  header +
  `string child_frame_id\ngeometry_msgs/PoseWithCovariance pose\ngeometry_msgs/TwistWithCovariance twist\n` +
  deps +
  `
================================================================================
MSG: geometry_msgs/PoseWithCovariance
geometry_msgs/Pose pose
float64[36] covariance
================================================================================
MSG: geometry_msgs/Pose
geometry_msgs/Point position
geometry_msgs/Quaternion orientation
================================================================================
MSG: geometry_msgs/Point
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/Quaternion
float64 x
float64 y
float64 z
float64 w
================================================================================
MSG: geometry_msgs/TwistWithCovariance
geometry_msgs/Twist twist
float64[36] covariance
================================================================================
MSG: geometry_msgs/Twist
geometry_msgs/Vector3 linear
geometry_msgs/Vector3 angular
================================================================================
MSG: geometry_msgs/Vector3
float64 x
float64 y
float64 z
`;
const cloud =
  header +
  `uint32 height\nuint32 width\nsensor_msgs/PointField[] fields\nbool is_bigendian\nuint32 point_step\nuint32 row_step\nuint8[] data\nbool is_dense\n` +
  deps +
  `\n================================================================================\nMSG: sensor_msgs/PointField\nstring name\nuint32 offset\nuint8 datatype\nuint32 count\n`;
// Fixture layout only; actual LocalizationStatus.msg has not been supplied.
const status = header + "uint8 status\n" + deps;
const separator =
  "================================================================================";
const tf =
  [
    "geometry_msgs/TransformStamped[] transforms",
    separator,
    "MSG: geometry_msgs/TransformStamped",
    "std_msgs/Header header",
    "string child_frame_id",
    "geometry_msgs/Transform transform",
    separator,
    "MSG: geometry_msgs/Transform",
    "geometry_msgs/Vector3 translation",
    "geometry_msgs/Quaternion rotation",
    separator,
    "MSG: geometry_msgs/Vector3",
    "float64 x",
    "float64 y",
    "float64 z",
    separator,
    "MSG: geometry_msgs/Quaternion",
    "float64 x",
    "float64 y",
    "float64 z",
    "float64 w",
  ].join("\n") + deps;
const clock = `builtin_interfaces/Time clock\n================================================================================\nMSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n`;
const server = new FoxgloveServer({
  name: "HYPER synthetic CDR fixture",
  supportedEncodings: ["cdr"],
});
server.on("error", console.error);
const channels = [
  ["/localization/odometry", "nav_msgs/msg/Odometry", odom],
  ["/test/gt_lidar", "nav_msgs/msg/Odometry", odom],
  ["/lidar/points", "sensor_msgs/msg/PointCloud2", cloud],
  ["/localization/status", "hn_interfaces/msg/LocalizationStatus", status],
  ["/clock", "rosgraph_msgs/msg/Clock", clock],
  ["/localization/reference_map", "sensor_msgs/msg/PointCloud2", cloud],
  ["/tf", "tf2_msgs/msg/TFMessage", tf],
].map(([topic, schemaName, schema]) => ({
  id: server.addChannel({
    topic,
    schemaName,
    schema,
    encoding: "cdr",
    schemaEncoding: "ros2msg",
  }),
  writer: new MessageWriter(parse(schema, { ros2: true })),
}));
const ws = new WebSocketServer({
  host: "127.0.0.1",
  port: 8766,
  handleProtocols: (p) =>
    p.has("foxglove.sdk.v1") ? "foxglove.sdk.v1" : "foxglove.websocket.v1",
});
ws.on("connection", (socket) =>
  server.handleConnection(socket, "browser-test"),
);
const vec = (x = 0, y = 0, z = 0) => ({ x, y, z });
let t = 0;
const pointMessage = (stamp, frame, points) => ({
  header: { stamp, frame_id: frame },
  height: 1,
  width: points.length,
  fields: ["x", "y", "z"].map((name, i) => ({
    name,
    offset: i * 4,
    datatype: 7,
    count: 1,
  })),
  is_bigendian: false,
  point_step: 12,
  row_step: 12 * points.length,
  data: Buffer.from(new Float32Array(points.flat()).buffer),
  is_dense: true,
});
const mapPoints = [];
for (let x = 20; x <= 50; x++)
  for (let y = 0; y <= 30; y++)
    if (x % 5 === 0 || y % 5 === 0) mapPoints.push([x, y, 0]);
const publish = (index, message) =>
  server.sendMessage(
    channels[index].id,
    BigInt(Math.round(t * 1e9)),
    channels[index].writer.writeMessage(message),
  );
server.on("subscribe", (id) => {
  if (id === channels[5].id)
    publish(5, pointMessage({ sec: 0, nanosec: 0 }, "pair360_map", mapPoints));
});
let tick = 0;
setInterval(() => {
  t = ++tick / 10;
  const stamp = { sec: Math.floor(t), nanosec: (tick % 10) * 100000000 },
    h = { stamp, frame_id: "pair360_map" };
  const p = vec(35 + Math.sin(t) * 3, 15 + Math.cos(t) * 3, 0.45),
    q = { x: 0, y: 0, z: 0, w: 1 };
  const od = (dx) => ({
    header: h,
    child_frame_id: "mlx_lidar",
    pose: {
      pose: { position: { ...p, x: p.x + dx }, orientation: q },
      covariance: Array(36).fill(0),
    },
    twist: {
      twist: { linear: vec(), angular: vec() },
      covariance: Array(36).fill(0),
    },
  });
  publish(1, od(0));
  publish(3, { header: h, status: Math.floor(t / 2) % 6 });
  publish(0, od(0.1));
  publish(
    2,
    pointMessage(
      stamp,
      "mlx_lidar",
      Array.from({ length: 64 }, (_, i) => [
        5 * Math.cos((i / 64) * Math.PI * 2),
        5 * Math.sin((i / 64) * Math.PI * 2),
        -0.45,
      ]),
    ),
  );
  publish(4, { clock: stamp });
  publish(6, {
    transforms: [
      {
        header: h,
        child_frame_id: "mlx_lidar",
        transform: { translation: { ...p, x: p.x + 0.1 }, rotation: q },
      },
    ],
  });
}, 100);
console.log(
  "SYNTHETIC ONLY: ws://127.0.0.1:8766 · S-005 topics · mock status field · no RGB",
);
