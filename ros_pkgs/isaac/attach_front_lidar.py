# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Attach an idealized RTX LiDAR to the imported URDF front_lidar frame.

Target: Isaac Sim 6.0 experimental RTX API (source inspected in 6.0.1-rc.7).
Run inside Isaac Sim after URDF import, with fixed-joint merging disabled:

    import runpy
    module = runpy.run_path('/absolute/repo/ros_pkgs/isaac/attach_front_lidar.py')
    sensor = module['attach_front_lidar']('/World/hypernova_go2/front_lidar')

Use the actual imported frame path. Keep ``sensor`` alive; play the timeline to
render. ``sensor.get_data('generic-model-output')`` retrieves the raw output.
The helper does not start simulation, change robot drives, or publish ROS topics.
It refuses an existing sensor path and never replaces existing scene objects.

Attribute specification:
https://docs.omniverse.nvidia.com/kit/docs/omni.sensors.nv.lidar/latest/lidar_extension.html
"""

from __future__ import annotations

import json
import math
from pathlib import Path


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[2]
    / 'description/hypernova_go2/config/front_lidar.json'
)


def build_attributes(config: dict) -> dict:
    """Build a centered, simultaneous solid-state scan in SI units/degrees."""
    nx, ny = config['horizontal_samples'], config['vertical_samples']
    hz = config['scan_rate_hz']
    if any(type(value) is not int or value < 2 for value in (nx, ny)):
        raise ValueError('Both sample counts must be integers >= 2')
    if type(hz) is not int or hz <= 0:
        raise ValueError('scan_rate_hz must be a positive integer')
    hfov, vfov = config['horizontal_fov_deg'], config['vertical_fov_deg']
    near, far = config['near_range_m'], config['far_range_m']
    if not all(math.isfinite(value) for value in (hfov, vfov, near, far)):
        raise ValueError('FOV and range values must be finite')
    if not (0 < hfov < 180 and 0 < vfov < 180 and 0 <= near < far):
        raise ValueError('Require 0 < FOV < 180 degrees and 0 <= near < far')
    count = nx * ny
    prefix = 'omni:sensor:Core:'
    values = {
        'scanType': 'SOLID_STATE',
        'rayType': 'IDEALIZED',
        'scanRateBaseHz': hz,
        'patternFiringRateHz': hz,
        'maxReturns': 1,
        'numberOfEmitters': count,
        'numberOfChannels': count,
        'stateResolutionStep': 1,
        'numLines': ny,
        'numRaysPerLine': [nx] * ny,
        'nearRangeM': near,
        'farRangeM': far,
        'elementsCoordsType': 'CARTESIAN',
        'outputFrameOfReference': 'SENSOR',
        'outputMotionCompensationState': 'NONCOMPENSATED',
        'startAzimuthOffsetDeg': 0.0,
        'azimuthErrorMean': 0.0,
        'azimuthErrorStd': 0.0,
        'elevationErrorMean': 0.0,
        'elevationErrorStd': 0.0,
        'rangeAccuracyM': 0.0,
        'emitterState:s001:azimuthDeg': [
            -hfov / 2 + hfov * column / (nx - 1)
            for row in range(ny) for column in range(nx)
        ],
        'emitterState:s001:elevationDeg': [
            -vfov / 2 + vfov * row / (ny - 1)
            for row in range(ny) for column in range(nx)
        ],
        'emitterState:s001:fireTimeNs': [0] * count,
        # OmniLidar schema uses one-based channel IDs, unlike old JSON examples.
        'emitterState:s001:channelId': list(range(1, count + 1)),
        'emitterState:s001:bank': [row for row in range(ny) for _ in range(nx)],
    }
    return {prefix + key: value for key, value in values.items()}


def attach_front_lidar(parent_prim_path: str, config_path=DEFAULT_CONFIG):
    """Return LidarSensor attached at the imported frame's identity transform.

    Parent must exist, be named front_lidar, and retain the URDF frame axes.
    No fallback mount pose is guessed if the importer merged away that frame.
    """
    import omni.usd
    from isaacsim.sensors.experimental.rtx import Lidar, LidarSensor
    from pxr import Gf, Sdf, UsdGeom

    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    attributes = build_attributes(config)
    parent_path = Sdf.Path(parent_prim_path)
    if not parent_path.IsAbsolutePath() or not parent_path.IsPrimPath():
        raise ValueError('Provide an absolute USD prim path')
    stage = omni.usd.get_context().get_stage()
    parent = stage.GetPrimAtPath(parent_path) if stage else None
    if not parent or not parent.IsValid() or parent.GetName() != config['frame']:
        raise ValueError('Existing front_lidar frame required; disable fixed-joint merging at URDF import')
    sensor_path = parent_path.AppendChild('rtx_sensor')
    if stage.GetPrimAtPath(sensor_path).IsValid():
        raise ValueError(f'Sensor path already exists: {sensor_path}')
    try:
        lidar = Lidar(
            str(sensor_path),
            schemas=['OmniSensorGenericLidarCoreEmitterStateAPI:s001'],
            tick_rate=float(config['scan_rate_hz']),
            accumulate_outputs=True,
        )
        prim = stage.GetPrimAtPath(sensor_path)
        # Author arrays through USD: Replicator 1.13.27 incorrectly splats Python
        # lists into Vt.FloatArray's constructor when passed via attributes=.
        for name, value in attributes.items():
            attribute = prim.GetAttribute(name)
            if not attribute.IsValid():
                raise RuntimeError(f'Unsupported RTX schema attribute: {name}')
            if not attribute.Set(value):
                raise RuntimeError(f'Cannot set RTX schema attribute: {name}')
        # Set LOCAL identity explicitly; the Lidar orientations argument is world-space.
        xform = UsdGeom.Xformable(prim)
        xform.ClearXformOpOrder()
        xform.AddTransformOp().Set(Gf.Matrix4d(1.0))
        return LidarSensor(lidar, annotators=['generic-model-output'])
    except Exception:
        # The path was absent before this call; preserve the imported parent and
        # every other scene object if sensor setup fails partway through.
        if stage.GetPrimAtPath(sensor_path).IsValid():
            stage.RemovePrim(sensor_path)
        raise
