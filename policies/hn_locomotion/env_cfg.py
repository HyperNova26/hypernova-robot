# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""hypernova_go2 v0 보행 과제 설정.

Isaac Lab 3.0.0 내장 Go2 velocity 과제를 상속하고 로봇만 바꿉니다.
- Flat: 평지
- Rough: 평지, 경사 오르막·내리막(hf_pyramid_slope*), 계단, 상자, 울퉁불퉁한 지형 + terrain curriculum
"""

import isaaclab.terrains as terrain_gen
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass, replace

import isaaclab_tasks.contrib.velocity.config.spot.mdp as spot_mdp
import isaaclab_tasks.core.velocity.mdp as mdp
from isaaclab_tasks.core.velocity.config.go2.agents.rsl_rl_ppo_cfg import (
    UnitreeGo2FlatPPORunnerCfg,
    UnitreeGo2RoughPPORunnerCfg,
)
from isaaclab_tasks.core.velocity.config.go2.flat_env_cfg import UnitreeGo2FlatEnvCfg
from isaaclab_tasks.core.velocity.config.go2.rough_env_cfg import UnitreeGo2Rewards, UnitreeGo2RoughEnvCfg

from .robot_cfg import FOOT_BODY_REGEX, HN_GO2_V0_CFG


@configclass
class HnGo2V0Rewards(UnitreeGo2Rewards):
    """Go2 보상에 발 끌기·편발 벌점과 트롯 걸음·발 들기 보상을 더합니다.

    2026-11-04 rough 학습(2500 iter)에서 평지 보행 시 RL 발을 끄는 비대칭 걸음이 나와서
    feet_slide·feet_air_time_variance를 키우고 gait·foot_clearance를 추가했습니다(2026-11-05).
    """

    # 접촉 중인 발의 수평 속도 [m/s] 합에 벌점을 줍니다. 바닥을 끄는 발을 잡습니다.
    feet_slide = RewTerm(
        func=mdp.feet_slide,
        weight=-0.3,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY_REGEX),
            "asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY_REGEX),
        },
    )
    # 네 발의 마지막 공중·접지 시간 [s](0.5 s에서 자름)의 분산에 벌점을 줍니다. 한 발만 들거나 끄는 걸음을 잡습니다.
    # 명령 속도가 0.1 m/s 이하면 0입니다.
    feet_air_time_variance = RewTerm(
        func=mdp.feet_air_time_variance,
        weight=-2.0,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY_REGEX),
            "max_time": 0.5,
        },
    )
    # 트롯 걸음 보상(Isaac Lab Spot GaitReward). 대각선 쌍 (FL, RR), (FR, RL)의 공중·접지 시간 [s]은 같게,
    # 쌍끼리는 엇갈리게 만듭니다. RL이 FR과 같은 박자로 움직여야 해서 한 발만 끄는 걸음을 직접 막습니다.
    # 값은 0~1이고, 명령 속도가 0이고 몸통 속도가 velocity_threshold [m/s] 이하면 0입니다.
    # weight는 Spot(10, tracking 5)과 tracking 대비 비율을 비슷하게 맞춘 시작값입니다.
    gait = RewTerm(
        func=spot_mdp.GaitReward,
        weight=1.0,
        params={
            "std": 0.1,
            "max_err": 0.2,
            "velocity_threshold": 0.5,
            "synced_feet_pair_names": (("FL_foot", "RR_foot"), ("FR_foot", "RL_foot")),
            "asset_cfg": SceneEntityCfg("robot"),
            "sensor_cfg": SceneEntityCfg("contact_forces"),
        },
    )
    # 수평으로 움직이는 발의 높이가 target_height [m]에 가까울수록 보상합니다(Isaac Lab Spot foot_clearance_reward).
    # 높이는 world z 기준이라 평지 칸과 낮은 난이도 지형에서만 의미가 있습니다.
    # *_foot 원점은 구(반지름 0.022 m) 중심이라 서 있을 때 z ≈ 0.022 m입니다.
    # std는 Spot(0.05)보다 작게 두어, 발을 끄는 경우(오차² ≈ 0.003 m²)와 차이가 보상에 드러나게 합니다.
    foot_clearance = RewTerm(
        func=spot_mdp.foot_clearance_reward,
        weight=0.5,
        params={
            "std": 0.01,
            "tanh_mult": 2.0,
            "target_height": 0.08,
            "asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY_REGEX),
        },
    )


def _use_hn_robot(cfg) -> None:
    # 변환된 USD에서 몸통은 Robot/Geometry/base에 있음 (Go2 공식 USD는 Robot/base)
    if getattr(cfg.scene, "height_scanner", None) is not None:
        cfg.scene.height_scanner.prim_path = "{ENV_REGEX_NS}/Robot/Geometry/base"
    cfg.scene.robot = replace(HN_GO2_V0_CFG, prim_path="{ENV_REGEX_NS}/Robot")
    cfg.rewards.feet_air_time.params["sensor_cfg"].body_names = FOOT_BODY_REGEX
    # merge_fixed_joints=False라서 머리·payload·lidar가 base와 별도 body입니다. 닿으면 base처럼 종료합니다.
    cfg.terminations.base_contact.params["sensor_cfg"].body_names = "base|Head_.*|equipment_payload|front_lidar"


@configclass
class HnGo2V0RoughEnvCfg(UnitreeGo2RoughEnvCfg):
    rewards: HnGo2V0Rewards = HnGo2V0Rewards()

    def __post_init__(self):
        super().__post_init__()
        _use_hn_robot(self)
        # 순수 평지 칸. 난이도가 올라가도 평지로 남아서 평지 보행을 끝까지 유지시킵니다.
        # proportion은 합으로 나눠 정규화됩니다(기존 합 1.0 + 0.2 → 평지 약 17%).
        self.scene.terrain.terrain_generator.sub_terrains["flat"] = terrain_gen.MeshPlaneTerrainCfg(proportion=0.2)
        self.rewards.feet_air_time.weight = 0.25
        self.rewards.feet_air_time.params["threshold"] = 0.25
        # 정지 연습: 정지 명령 비율 2% → 15%
        self.commands.base_velocity.rel_standing_envs = 0.15
        # 정지 명령일 때 기본 자세에서 벗어나면 벌점을 줍니다.
        # Isaac Lab Digit 예시(-0.4)에서 시작해 -1.0으로 키웠습니다(2026-11-05).
        self.rewards.stand_still = RewTerm(
            func=mdp.stand_still_joint_deviation_l1,
            weight=-1.0,
            params={"command_name": "base_velocity", "asset_cfg": SceneEntityCfg("robot")},
        )


@configclass
class HnGo2V0FlatEnvCfg(UnitreeGo2FlatEnvCfg):
    rewards: HnGo2V0Rewards = HnGo2V0Rewards()

    def __post_init__(self):
        super().__post_init__()
        _use_hn_robot(self)


# 학습 결과 폴더: /data/isaaclab/logs/rsl_rl/<experiment_name>/<날짜_시각>/
@configclass
class HnGo2V0RoughPPORunnerCfg(UnitreeGo2RoughPPORunnerCfg):
    def __post_init__(self):
        super().__post_init__()
        self.experiment_name = "hn_go2v0_rough"


@configclass
class HnGo2V0FlatPPORunnerCfg(UnitreeGo2FlatPPORunnerCfg):
    def __post_init__(self):
        super().__post_init__()
        self.experiment_name = "hn_go2v0_flat"
