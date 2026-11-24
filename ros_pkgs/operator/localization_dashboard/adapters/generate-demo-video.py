#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Render the bundled synthetic patrol clip with Python 3 and FFmpeg/libvpx.

Run from any directory: python3 adapters/generate-demo-video.py
Keep the camera poses synchronized with sampleDemoPatrol() in recordings.ts.
"""

from pathlib import Path
import math
import subprocess

WIDTH = 480
HEIGHT = 270
FPS = 12
SECONDS = 12


def render(second):
    travel = min(second, 10)
    robot_x = -3 + 0.7 * travel
    robot_y = -2 + 0.22 * travel
    yaw = 0.3045
    c, s = math.cos(yaw), math.sin(yaw)
    sky = bytes.fromhex("192c3e")
    ground = bytes.fromhex("263d40")
    grid = bytes.fromhex("4e696b")
    hud = bytes.fromhex("10202d")
    crosshair = bytes.fromhex("bddee6")
    image = bytearray(sky * (WIDTH * 113) + ground * (WIDTH * (HEIGHT - 113)))

    def rect(x, y, width, height, color):
        left, right = max(0, x), min(WIDTH, x + width)
        if left >= right:
            return
        row = color * (right - left)
        for r in range(max(0, y), min(HEIGHT, y + height)):
            start = 3 * (r * WIDTH + left)
            image[start:start + len(row)] = row

    def project(x, y):
        dx, dy = x - robot_x, y - robot_y
        return (c * dx + s * dy, -s * dx + c * dy)

    def screen(depth, side):
        return (WIDTH / 2 - side * 170 / depth, 113 + 115 / depth)

    def grid_line(x1, y1, x2, y2):
        (depth_a, side_a), (depth_b, side_b) = sorted(
            (project(x1, y1), project(x2, y2))
        )
        near = 0.65
        if depth_b <= near:
            return
        if depth_a < near:
            f = (near - depth_a) / (depth_b - depth_a)
            side_a += f * (side_b - side_a)
            depth_a = near
        start_x, start_y = screen(depth_a, side_a)
        end_x, end_y = screen(depth_b, side_b)
        # Sample the projected segment in its visible rows and columns.
        for x in range(max(0, round(min(start_x, end_x))), min(WIDTH - 1, round(max(start_x, end_x))) + 1):
            f = 0 if start_x == end_x else (x - start_x) / (end_x - start_x)
            rect(x, round(start_y + f * (end_y - start_y)), 1, 1, grid)
        for y in range(max(0, round(min(start_y, end_y))), min(HEIGHT - 1, round(max(start_y, end_y))) + 1):
            f = 0 if start_y == end_y else (y - start_y) / (end_y - start_y)
            rect(round(start_x + f * (end_x - start_x)), y, 1, 1, grid)

    for meter in range(-30, 31, 2):
        grid_line(-30, meter, 30, meter)
        grid_line(meter, -30, meter, 30)
    for x, y, color in [
        (5, 0, "ffa859"), (8, -5, "68acc6"), (12, 4, "68acc6"), (13, -7, "68acc6")
    ]:
        depth, side = project(x, y)
        if depth <= 0.65:
            continue
        x, y = screen(depth, side)
        size = 44 / depth
        rect(round(x - size / 2), round(y - size * 1.6),
             max(1, round(size)), max(1, round(size * 1.6)), bytes.fromhex(color))
    rect(229, 130, 22, 1, crosshair)
    rect(240, 119, 1, 22, crosshair)
    rect(0, 0, WIDTH, 29, hud)
    rect(0, HEIGHT - 29, WIDTH, 29, hud)
    return image


def main():
    output = Path(__file__).resolve().parents[1] / "public" / "demo-patrol.webm"
    overlays = (
        "drawtext=font=monospace:fontsize=12:fontcolor=0xd9edf1:x=13:y=9:"
        "text='HYPER / SYNTHETIC CAMERA',"
        "drawtext=font=monospace:fontsize=12:fontcolor=0xd9edf1:x=13:y=h-21:"
        "text='CAMPUS PATROL EXAMPLE'"
    )
    ffmpeg = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", "-",
        "-vf", overlays, "-pix_fmt", "yuv420p", "-an", "-c:v", "libvpx",
        "-crf", "28", "-b:v", "220k", "-g", str(FPS), str(output),
    ]
    with subprocess.Popen(ffmpeg, stdin=subprocess.PIPE) as process:
        assert process.stdin is not None
        for frame in range(FPS * SECONDS):
            process.stdin.write(render(frame / FPS))
        process.stdin.close()
        if process.wait() != 0:
            raise SystemExit("FFmpeg failed to encode the synthetic clip.")
    print(output)


if __name__ == "__main__":
    main()
