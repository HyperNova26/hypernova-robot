# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""hypernova_go2 보행 과제 공용 보상.

envs/ 아래 버전별 과제(Flat, Rough)가 함께 씁니다.
"""

from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass

import isaaclab_tasks.contrib.velocity.config.spot.mdp as spot_mdp
import isaaclab_tasks.core.velocity.mdp as mdp
from isaaclab_tasks.core.velocity.config.go2.rough_env_cfg import UnitreeGo2Rewards

# 발 body 이름 규칙(*_foot)은 로봇 설정에서 가져옵니다.
from .robots.hn_v0_go2 import FOOT_BODY_REGEX


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
