# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Print actual model names; never step, render, control or modify the XML."""
import argparse
import json
import mujoco

parser = argparse.ArgumentParser()
parser.add_argument('xml')
args = parser.parse_args()
model = mujoco.MjModel.from_xml_path(args.xml)


def name(kind, i):
    return mujoco.mj_id2name(model, kind, i)


print(json.dumps({
    'nq': model.nq, 'nv': model.nv,
    'bodies': [name(mujoco.mjtObj.mjOBJ_BODY, i) for i in range(model.nbody)],
    'joints': [{'name': name(mujoco.mjtObj.mjOBJ_JOINT, i), 'type': int(model.jnt_type[i]),
                'body': name(mujoco.mjtObj.mjOBJ_BODY, int(model.jnt_bodyid[i]))}
               for i in range(model.njnt)],
    'sensors': [{'name': name(mujoco.mjtObj.mjOBJ_SENSOR, i),
                 'type': int(model.sensor_type[i]), 'dimensions': int(model.sensor_dim[i])}
                for i in range(model.nsensor)],
    'sites': [name(mujoco.mjtObj.mjOBJ_SITE, i) for i in range(model.nsite)],
    'cameras': [name(mujoco.mjtObj.mjOBJ_CAMERA, i) for i in range(model.ncam)]
}, indent=2, ensure_ascii=False))
