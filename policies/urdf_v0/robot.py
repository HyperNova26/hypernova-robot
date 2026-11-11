# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""hypernova_go2 v0 URDF를 Isaac Lab ArticulationCfg로 정의합니다.

- 형상·관성·관절 한계의 원본은 저장소의 description/hn_v0_go2/hypernova_go2.urdf입니다.
  mesh는 git에 없으므로 처음 한 번 `python3 tools/description/fetch_go2_meshes.py --convert`로 받습니다.
- 모터 한계(effort, velocity)는 URDF 값을 그대로 씁니다. Isaac Lab의 UNITREE_GO2_CFG(calf 45.43 N·m, 15.70 rad/s)와
  다르므로(URDF calf 35.55 N·m, 20 rad/s) Go2 설정을 그대로 가져오지 않습니다.
- PD gain(stiffness 25, damping 0.5)과 초기 자세는 Isaac Lab UNITREE_GO2_CFG 값을 따릅니다. 실기 값이 정해지면 바꿉니다.
"""

import os

from isaaclab_newton.sim.schemas import NewtonArticulationCfg
from isaaclab_physx.sim.schemas import PhysxArticulationCfg, PhysxRigidBodyCfg

import isaaclab.sim as sim_utils
from isaaclab.actuators import DCMotorCfg
from isaaclab.assets.articulation import ArticulationCfg

# 저장소 루트 기준으로 찾으므로 호스트와 컨테이너(/workspace/hypernova) 모두 같은 경로를 씁니다.
# 다른 URDF를 쓰려면 환경변수로 바꿉니다.
# urdf_v0/ → policies/ → 저장소 루트
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URDF_PATH = os.environ.get("HN_GO2_URDF", os.path.join(_REPO_ROOT, "description/hn_v0_go2/hypernova_go2.urdf"))
# 변환된 USD를 캐시해 두는 폴더. 생성 파일이라 저장소 밖(/data = 호스트 ~/hypernova-data)에 둡니다.
# URDF가 바뀌지 않으면 다음 실행부터 다시 변환하지 않습니다.
# 예전 /data/urdf_v0 URDF로 만든 캐시(/data/urdf_v0/usd, usd_feet)와 섞이지 않게 따로 둡니다.
USD_DIR = os.environ.get("HN_GO2_USD_DIR", "/data/usd/hn_v0_go2")

# 발 접촉·속도를 쓰는 보상은 이 이름으로 발 body를 찾습니다.
# merge_fixed_joints=False라서 *_foot(구 충돌체, calf에서 (0, 0, -0.213) m)이 별도 body입니다.
FOOT_BODY_REGEX = ".*_foot"

HN_GO2_V0_CFG = ArticulationCfg(
    spawn=sim_utils.UrdfFileCfg(
        asset_path=URDF_PATH,
        usd_dir=USD_DIR,
        fix_base=False,
        # *_foot(고정 관절)을 별도 body로 남겨 발끝 기준으로 접촉·속도를 계산합니다.
        # 다른 고정 링크(Head_*, *_rotor, *_calflower*, 센서, equipment_payload)도 별도 body가 됩니다.
        merge_fixed_joints=False,
        # inertial이 없는 링크(*_calflower*, front_lidar)는 PhysX가 충돌체 부피 × 1000 kg/m³로 질량을 매겨
        # URDF에 없는 질량(총 약 0.55 kg)이 생깁니다. 밀도를 낮춰 사실상 0에 가깝게 둡니다(kg/m³).
        # imu·radar·front_camera는 충돌체도 없어서 body로 만들어지지 않습니다.
        link_density=10.0,
        activate_contact_sensors=True,
        rigid_props=PhysxRigidBodyCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=[
            PhysxArticulationCfg(
                enabled_self_collisions=False, solver_position_iteration_count=4, solver_velocity_iteration_count=0
            ),
            NewtonArticulationCfg(self_collision_enabled=False),
        ],
        # gain은 아래 actuator가 정하므로 URDF importer가 drive gain을 쓰지 않게 둡니다.
        joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(
            gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=None, damping=None)
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.4),
        joint_pos={
            ".*L_hip_joint": 0.1,
            ".*R_hip_joint": -0.1,
            "F[L,R]_thigh_joint": 0.8,
            "R[L,R]_thigh_joint": 1.0,
            ".*_calf_joint": -1.5,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        "base_legs": DCMotorCfg(
            joint_names_expr=[".*_hip_joint", ".*_thigh_joint", ".*_calf_joint"],
            # URDF <limit effort velocity> 값 (N·m, rad/s)
            actuator_effort_limit={".*_hip_joint": 23.7, ".*_thigh_joint": 23.7, ".*_calf_joint": 35.55},
            saturation_effort={".*_hip_joint": 23.7, ".*_thigh_joint": 23.7, ".*_calf_joint": 35.55},
            actuator_velocity_limit={".*_hip_joint": 30.0, ".*_thigh_joint": 30.0, ".*_calf_joint": 20.0},
            stiffness=25.0,
            damping=0.5,
            friction=0.0,
        ),
    },
)
