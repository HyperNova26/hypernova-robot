# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Publish a selected binary PCD to the S-005 reference map topic."""
import argparse
from array import array
from pathlib import Path


def read_pcd(path):
    """Validate a packed little-endian XYZI/XYZ cloud with optional semantic labels."""
    header = {}
    with path.open("rb") as stream:
        while stream.tell() < 65536:
            line = stream.readline(65536)
            if not line:
                raise ValueError("Incomplete PCD header")
            text = line.decode("ascii").strip()
            if not text or text.startswith("#"):
                continue
            name, *values = text.split()
            header[name] = values
            if name == "DATA":
                break
        if header.get("DATA") != ["binary"]:
            raise ValueError("Expected binary PCD")
        names = header["FIELDS"]
        sizes = list(map(int, header["SIZE"]))
        types = header["TYPE"]
        counts = list(map(int, header.get("COUNT", ["1"] * len(names))))
        if not (len(names) == len(sizes) == len(types) == len(counts)):
            raise ValueError("Inconsistent PCD fields")
        if len(set(names)) != len(names) or not {"x", "y", "z"}.issubset(names):
            raise ValueError("Expected unique fields with XYZ")
        offsets = []
        step = 0
        for name, size, kind, count in zip(names, sizes, types, counts):
            expected = {"F"} if name in {"x", "y", "z", "intensity"} else {"I", "U"} if name == "label" else set()
            if size != 4 or kind not in expected or count != 1:
                raise ValueError(f"Unsupported PCD field: {name}, {kind}{size}, count={count}")
            offsets.append((name, step, kind))
            step += size
        width, height, total = (int(header[key][0]) for key in ("WIDTH", "HEIGHT", "POINTS"))
        if width < 1 or height < 1 or width * height != total:
            raise ValueError("Invalid PCD dimensions")
        if path.stat().st_size - stream.tell() != total * step:
            raise ValueError("PCD length does not match dimensions")
        payload = array("B")
        payload.fromfile(stream, total * step)
    return width, height, step, offsets, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcd", type=Path)
    parser.add_argument("--frame", required=True, help="Coordinate frame of the input points; no transformation is applied.")
    parser.add_argument("--topic", default="/localization/reference_map")
    args, ros_args = parser.parse_known_args()
    if not args.frame.strip():
        parser.error("--frame is required")
    width, height, step, fields, payload = read_pcd(args.pcd)

    import rclpy
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import PointCloud2, PointField

    rclpy.init(args=ros_args)
    node = rclpy.create_node("reference_map_file")
    try:
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                         reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        publisher = node.create_publisher(PointCloud2, args.topic, qos)
        msg = PointCloud2()
        msg.header.frame_id = args.frame
        msg.header.stamp = node.get_clock().now().to_msg()
        msg.width, msg.height = width, height
        dtype = {"F": PointField.FLOAT32, "U": PointField.UINT32, "I": PointField.INT32}
        msg.fields = [PointField(name=name, offset=offset, datatype=dtype[kind], count=1)
                      for name, offset, kind in fields]
        msg.point_step, msg.row_step = step, width * step
        msg.is_bigendian = False
        msg.is_dense = False
        msg.data = payload
        publisher.publish(msg)
        node.get_logger().info(f"{args.pcd.name}: {width * height} points, {args.frame}, {args.topic}")
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
