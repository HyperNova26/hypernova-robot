# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""HYPER v1 URDF를 Isaac Lab ArticulationCfg로 정의합니다.

- 형상·관성·관절 한계의 원본은 저장소의 description/hn_v1_hyper/hypernova_hyper.urdf입니다.
  mesh는 git에 없으므로 처음 한 번 `python3 tools/description/fetch_hyper_v1_meshes.py`로 받습니다.
- 충돌 설정은 HYPER 저장소(jaemin0319/HYPER @ e5f9ed5)의 isaacsim/convert_urdf.py, isaaclab/hyper_lab/robots.py와 같게 둡니다.
  - 부품별 충돌 STL 하나가 볼록 껍질(Convex Hull) 하나가 됩니다. 발은 반지름 0.025 m 구입니다.
  - 자기충돌을 켭니다. 관절 범위 안에서 허벅지가 몸체에 닿기 때문입니다(앞 허벅지 약 1.40 rad, hip 외전 약 0.85 rad).
  - HYPER는 merge_fixed_joints=True + 발 관절 dont_collapse로 발 링크를 남깁니다. Isaac Lab 3.0 변환기는 고정 관절을
    모두 합치므로 merge_fixed_joints=False로 같은 결과(body 17개)를 냅니다. 고정 관절은 발 4개뿐입니다.
  - 질량·관성은 URDF 값을 그대로 씁니다(link_density 0 = 재계산 안 함).
- 모터는 Unitree GO-M8010-6(출력축 23.7 N·m, 30 rad/s)입니다. calf는 thigh에 달린 모터가 벨트 1:1로 구동합니다.
- PD gain(stiffness 25, damping 0.5), 초기 자세, soft limit 0.9는 HYPER(= Isaac Lab UNITREE_GO2_CFG) 값입니다.
"""

import os

from isaaclab_newton.sim.schemas import NewtonArticulationCfg
from isaaclab_physx.sim.schemas import PhysxArticulationCfg, PhysxRigidBodyCfg

import isaaclab.sim as sim_utils
from isaaclab.actuators import DCMotorCfg
from isaaclab.assets.articulation import ArticulationCfg

# urdf_v1/ → policies/ → 저장소 루트. 호스트와 컨테이너(/workspace/hypernova) 모두 같은 경로를 씁니다.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URDF_PATH = os.environ.get("HN_HYPER_V1_URDF", os.path.join(_REPO_ROOT, "description/hn_v1_hyper/hypernova_hyper.urdf"))
# 변환된 USD 캐시. 생성 파일이라 저장소 밖(/data = 호스트 ~/hypernova-data)에 둡니다.
USD_DIR = os.environ.get("HN_HYPER_V1_USD_DIR", "/data/usd/hn_v1_hyper")

# 발 접촉·속도를 쓰는 보상은 이 이름으로 발 body를 찾습니다. *_foot은 calf에서 (0, 0, -0.2165) m의 구입니다.
FOOT_BODY_REGEX = ".*_foot"

# Unitree GO-M8010-6 출력축 값 (https://www.unitree.com/go1/motor)
GO_M8010_6_MAX_TORQUE = 23.7  # N·m
GO_M8010_6_MAX_SPEED = 30.0  # rad/s

HN_HYPER_V1_CFG = ArticulationCfg(
    spawn=sim_utils.UrdfFileCfg(
        asset_path=URDF_PATH,
        usd_dir=USD_DIR,
        fix_base=False,
        merge_fixed_joints=False,
        collision_type="Convex Hull",
        self_collision=True,
        link_density=0.0,
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
                enabled_self_collisions=True, solver_position_iteration_count=4, solver_velocity_iteration_count=0
            ),
            NewtonArticulationCfg(self_collision_enabled=True),
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
            actuator_effort_limit=GO_M8010_6_MAX_TORQUE,
            saturation_effort=GO_M8010_6_MAX_TORQUE,
            actuator_velocity_limit=GO_M8010_6_MAX_SPEED,
            stiffness=25.0,
            damping=0.5,
            friction=0.0,
        ),
    },
)
