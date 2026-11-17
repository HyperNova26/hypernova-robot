# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""HyperNova 보행 보상표 (v1부터, 2026-11-17).

이 파일의 HnRewards가 최종 보상입니다. 항목·함수·가중치·매개변수를 모두 여기에 직접 적습니다.

Isaac Lab Go2 과제 설정은 자기 __post_init__에서 보상 가중치를 바꾸고 항목을 끕니다. 그래서 과제 설정(urdf_vN/env.py)은
__post_init__ 맨 끝에서 apply_hn_rewards()를 불러 보상을 이 표로 통째로 바꿉니다. 최종 값은 이 파일만 보면 되고,
Isaac Lab 기본값이 바뀌어도 영향을 받지 않습니다. v0(urdf_v0)는 동결되어 urdf_v0/rewards.py를 씁니다.

한 step(0.02 s)의 보상 = Σ 항목 값 × weight × step 시간. weight가 양수면 보상, 음수면 벌점입니다.

각 항목 주석의 [출처]는 Isaac Lab 3.0.0 값과의 관계입니다.
    기본 = isaaclab_tasks/core/velocity/velocity_env_cfg.py RewardsCfg, Go2 = config/go2/rough_env_cfg.py의 조정,
    우리 = 이 저장소에서 바꾸거나 추가한 값(날짜). "기본 그대로"는 Isaac Lab 값을 바꾸지 않았다는 뜻입니다.

지형별 차이(apply_hn_rewards의 terrain)
    항목                    rough                          flat
    base_height_l2 기준     height_scanner 바닥 평균 + 목표   world z = 목표
    feet_air_time 기준 시간   0.25 s                         0.5 s
    stand_still            켬 (−1.0)                       없음
    flat_orientation_l2    0 (끔)                          −2.5
2026-11-17 이전 v1 과제의 최종 값과 같게 맞췄습니다(정리 전후 과제별 보상 설정 비교로 확인).
"""

import math

from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass

import isaaclab_tasks.contrib.velocity.config.spot.mdp as spot_mdp
import isaaclab_tasks.core.velocity.mdp as mdp

# apply_hn_rewards가 버전별 값으로 채우는 자리표시. 이 값이 남아 있으면 apply_hn_rewards를 부르지 않은 것입니다.
_FOOT = "<foot_body_regex>"


@configclass
class HnRewards:
    """보상표. 순서는 묶음별(명령 → 몸통 안정 → 동작 부드러움 → 걸음새 → 접촉 → 정지)입니다."""

    # ---- 명령 따라가기 (+) ----
    # 몸통 앞뒤·옆 속도 [m/s]가 명령과 가까울수록 보상: exp(−오차² / std²)
    # [출처] weight 기본 1.0 → Go2 1.5. std 기본 그대로
    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_exp, weight=1.5, params={"command_name": "base_velocity", "std": math.sqrt(0.25)}
    )
    # 회전 속도 [rad/s]가 명령과 가까울수록 보상
    # [출처] weight 기본 0.5 → Go2 0.75. std 기본 그대로
    track_ang_vel_z_exp = RewTerm(
        func=mdp.track_ang_vel_z_exp, weight=0.75, params={"command_name": "base_velocity", "std": math.sqrt(0.25)}
    )

    # ---- 몸통 안정 (−) ----
    lin_vel_z_l2 = RewTerm(func=mdp.lin_vel_z_l2, weight=-2.0)  # 위아래로 튀는 속도². [출처] 기본 그대로
    ang_vel_xy_l2 = RewTerm(func=mdp.ang_vel_xy_l2, weight=-0.05)  # 앞뒤·좌우로 흔들리는 각속도². [출처] 기본 그대로
    # 몸통 높이가 목표에서 벗어난 정도². 목표 [m]와 지면 기준(sensor_cfg)은 apply_hn_rewards가 채웁니다.
    # [출처] 기본에는 없음. Go2가 추가(weight −30, 목표 0.4 m, rough는 height_scanner 기준) → 우리 목표 v1 0.30 m(2026-11-15)
    base_height_l2 = RewTerm(
        func=mdp.base_height_l2, weight=-30.0, params={"target_height": 0.0, "sensor_cfg": None}
    )
    # 몸통 기울기². 지형별 weight. [출처] 기본 0(끔), Isaac Lab Go2 flat −2.5 그대로
    flat_orientation_l2 = RewTerm(func=mdp.flat_orientation_l2, weight=0.0)

    # ---- 동작 부드러움 (−) ----
    dof_torques_l2 = RewTerm(func=mdp.joint_torques_l2, weight=-2.0e-4)  # 관절 토크² (에너지). [출처] 기본 −1e-5 → Go2 −2e-4
    dof_acc_l2 = RewTerm(func=mdp.joint_acc_l2, weight=-2.5e-7)  # 관절 가속도² (덜컥거림). [출처] 기본 그대로
    # 이전 action과의 차이² (떨림). [출처] 기본 −0.01 → Go2 −0.005 (Go2: 강하면 뒷발을 끄는 걸음이 생김)
    action_rate_l2 = RewTerm(func=mdp.action_rate_l2, weight=-0.005)
    dof_pos_limits = RewTerm(func=mdp.joint_pos_limits, weight=0.0)  # 관절 한계 근접 (끔). [출처] 기본 그대로

    # ---- 걸음새 ----
    # 발이 threshold [s]보다 오래 떠 있다가 디디면 보상(발을 들고 걷게). threshold는 지형별
    # [출처] weight 기본 0.125 → Go2 rough 0.01, Go2 flat 0.25 → 우리 0.25(rough도, 2026-11-05).
    #        threshold 기본 0.5 s → 우리 rough 0.25 s(2026-11-05), flat은 기본 0.5 s 그대로
    feet_air_time = RewTerm(
        func=mdp.feet_air_time,
        weight=0.25,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=_FOOT),
            "threshold": 0.0,
        },
    )
    # 트롯(Isaac Lab Spot GaitReward): 대각선 쌍 (FL, RR), (FR, RL)의 공중·접지 시간 [s]은 같게, 쌍끼리는 엇갈리게.
    # 값은 0~1이고, 명령 속도가 0이고 몸통 속도가 velocity_threshold [m/s] 이하면 0입니다.
    # [출처] 기본에 없음. 우리 추가(2026-11-05). 함수와 std·max_err는 Isaac Lab Spot 과제, weight는 Spot(10)의 tracking 대비 비율로
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
    # 수평으로 움직이는 발의 높이(world z)가 target_height [m]에 가까울수록 보상(Isaac Lab Spot foot_clearance_reward).
    # 평지 칸과 낮은 난이도에서만 의미가 있습니다.
    # [출처] 기본에 없음. 우리 추가(2026-11-05). std를 Spot(0.05)보다 작은 0.01로 둬서 발 끌기와 차이가 드러나게 함
    foot_clearance = RewTerm(
        func=spot_mdp.foot_clearance_reward,
        weight=0.5,
        params={"std": 0.01, "tanh_mult": 2.0, "target_height": 0.08, "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT)},
    )
    # 네 발의 마지막 공중·접지 시간 [s](max_time에서 자름)의 분산. 한 발만 들거나 끄는 걸음을 잡습니다.
    # [출처] 기본에 없음. 우리 추가(2026-11-05, 처음 −1.0에서 −2.0으로 키움)
    feet_air_time_variance = RewTerm(
        func=mdp.feet_air_time_variance,
        weight=-2.0,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=_FOOT),
            "max_time": 0.5,
        },
    )
    # 접촉 중인 발의 수평 속도 [m/s] 합. 바닥을 끄는 발을 잡습니다.
    # [출처] 기본에 없음. 우리 추가(2026-11-05, 처음 −0.1에서 −0.3으로 키움)
    feet_slide = RewTerm(
        func=mdp.feet_slide,
        weight=-0.3,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=_FOOT),
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT),
        },
    )

    # ---- 접촉 (−) ----
    # 허벅지가 몸체·바닥에 threshold [N] 넘게 닿으면 벌점(v1: 자기충돌을 켜서 필요). apply_hn_rewards(thigh_contact=False)면 끔
    # [출처] 기본 있음(−1.0, 1 N, body ".*THIGH") → Go2가 끔 → 우리 v1에서 다시 켬, body ".*_thigh"(HYPER, 2026-11-15)
    undesired_contacts = RewTerm(
        func=mdp.undesired_contacts,
        weight=-1.0,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_thigh"), "threshold": 1.0},
    )

    # ---- 정지 ----
    # 정지 명령일 때 기본 자세에서 벗어난 관절 각도 [rad] 합. rough만 켭니다.
    # [출처] 기본에 없음. 우리 추가(2026-11-05). Isaac Lab Digit 과제 −0.4에서 시작해 −1.0으로 키움
    stand_still = RewTerm(
        func=mdp.stand_still_joint_deviation_l1,
        weight=-1.0,
        params={"command_name": "base_velocity", "asset_cfg": SceneEntityCfg("robot")},
    )


def apply_hn_rewards(
    env_cfg,
    *,
    terrain: str,
    foot_body_regex: str,
    standing_height: float,
    thigh_contact: bool = True,
) -> None:
    """env_cfg.rewards를 HnRewards로 통째로 바꾸고 버전·지형별 값을 채웁니다. __post_init__ 맨 끝에서 부릅니다.

    terrain: "rough"(height scanner 있음) 또는 "flat". foot_body_regex: 발 body 이름.
    standing_height: 선 자세 몸통 높이 [m](base_height_l2 목표). thigh_contact: 허벅지 접촉 벌점 사용.
    """
    if terrain not in ("rough", "flat"):
        raise ValueError(f"terrain은 'rough' 또는 'flat'입니다: {terrain}")
    r = HnRewards()
    for term in (r.feet_air_time, r.feet_air_time_variance, r.feet_slide):
        term.params["sensor_cfg"].body_names = foot_body_regex
    r.feet_slide.params["asset_cfg"].body_names = foot_body_regex
    r.foot_clearance.params["asset_cfg"].body_names = foot_body_regex
    r.base_height_l2.params["target_height"] = standing_height
    if terrain == "rough":
        # 목표 = height scanner가 본 바닥들의 평균 + standing_height
        r.base_height_l2.params["sensor_cfg"] = SceneEntityCfg("height_scanner")
        r.feet_air_time.params["threshold"] = 0.25
    else:
        # 평지: 목표 = world z standing_height, 몸통 기울기 벌점 켬, 정지 벌점 없음
        r.feet_air_time.params["threshold"] = 0.5
        r.flat_orientation_l2.weight = -2.5
        r.stand_still = None
    if not thigh_contact:
        r.undesired_contacts = None
    env_cfg.rewards = r
