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

import isaaclab_tasks.core.velocity.mdp as mdp
from isaaclab_tasks.core.velocity.config.go2.agents.rsl_rl_ppo_cfg import (
    UnitreeGo2FlatPPORunnerCfg,
    UnitreeGo2RoughPPORunnerCfg,
)
from isaaclab_tasks.core.velocity.config.go2.flat_env_cfg import UnitreeGo2FlatEnvCfg
from isaaclab_tasks.core.velocity.config.go2.rough_env_cfg import UnitreeGo2RoughEnvCfg

from ..rewards import HnGo2V0Rewards
from ..robots.hn_v0_go2 import FOOT_BODY_REGEX, HN_GO2_V0_CFG


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
