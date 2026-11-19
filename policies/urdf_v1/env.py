# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""HYPER v1 보행 과제 설정 (2026-11-15 결정 기준).

Isaac Lab 3.0.0 내장 Go2 velocity 과제를 상속합니다. v0와 다른 점:

1. 로봇은 HN_HYPER_V1_CFG입니다(자기충돌 켬).
2. actor(정책) 입력은 실기에서 얻을 수 있는 값만 둡니다. 48차원이고 아래 순서로 이어 붙입니다(Go2 기본 순서).
       base_lin_vel 3 (IMU 기반 몸통 선속도) | base_ang_vel 3 (IMU 각속도) | projected_gravity 3 (IMU 중력 방향) |
       velocity_commands 3 | joint_pos − default 12 | joint_vel 12 | last action 12
   base_lin_vel은 실기에서 IMU로 잰다고 확인되어(2026-11-19) actor에 넣었습니다. 값은 trunk link 질량중심의
   속도를 trunk frame으로 나타낸 것입니다(Isaac Lab root_com_lin_vel_b). 질량중심은 원점 아래 0.64 mm라서
   원점 속도와의 차이는 회전 2 rad/s에서 약 1 mm/s입니다. 2026-11-19 이전 학습(체크포인트 model_2998 등)은 이 항목이 없는 45차원 입력입니다.
   잡음 설정은 Go2 값을 그대로 씁니다(선속도 ±0.1 m/s, 실측 잡음·지연은 아직 반영하지 않음).
3. critic 입력은 Go2 기본 입력 전체입니다(학습 때만 씀, 비대칭 actor-critic).
4. 관절 순서는 HYPER와 같은 종류 단위(FL, FR, RL, RR의 hip → thigh → calf)이고, preserve_order=True로
   action·관측 모두 이 순서를 고정합니다. PhysX 내부 순서에 맡기지 않습니다.
5. 보상은 policies/common/rewards.py의 보상표(HnRewards)입니다. __post_init__ 맨 끝에서 apply_hn_rewards()로
   통째로 바꾸므로 Go2 설정이 바꾼 보상 값은 남지 않습니다. v1 값: 허벅지 접촉 벌점 켬(자기충돌이 켜져 있어 몸체·바닥에
   닿는 허벅지를 막음), 몸통 높이 목표는 v1 선 자세 높이(Go2 0.4 m 대신).
6. base_contact 종료는 몸통-바닥 접촉만 셉니다. 몸통 전체 접촉력에는 허벅지-몸통 자기충돌도 섞이기 때문입니다.
7. PPO는 좌우 대칭 데이터 증강을 씁니다(policies/common/symmetry.py). 정책이 이유 없이 한쪽으로 도는 습관을 막습니다.

Rough는 비교용(배포 안 함, 2026-11-19 결정)으로 Isaac Lab 기본 height scan(몸통 위 20 m에서 수직으로 쏘는 1.6 × 1.0 m grid, 0.1 m 간격,
187칸)을 actor와 critic에 넣습니다(actor 235차원). 실기에서 같은 입력을 만들 수 없어 Rough-Lidar가 LiDAR 입력으로
얼마나 떨어지는지 비교하는 기준으로만 씁니다. 지형 조정은 v0 Rough와 같습니다.

Rough-Lidar(HnHyperV1RoughLidarEnvCfg)는 actor height scan만 실제 센서(ML-X 120 가정, 앞 윗면 15° 아래로,
바닥이 센서 앞 약 0.63 m부터 보임)를 흉내 낸 값으로 바꿉니다. 같은 크기 grid를 앞으로 0.45 m 옮기고, LiDAR로 본 점을
3 s 기억하며, 못 본 칸은 발끝 평면으로 채웁니다(policies/common/heightmap.py). critic은 같은 grid의 GT height scan입니다.
아래 학습·ablation 숫자는 LiDAR 16.2°, actor 선속도 없음 기준이며 15°·선속도 입력(2026-11-19)으로는 아직 다시
학습하지 않았습니다.
2026-11-17 학습(대칭 증강, 3000 iteration, 마지막 50 iteration 평균)에서 GT Rough와 비슷했습니다:
지형 난이도 5.64 vs 5.63, 선속도 오차 0.166 vs 0.151 m/s, 회전 오차 0.202 vs 0.188 rad/s.
height 입력을 발끝 평면만으로 바꾸면(ablation, 2026-11-17, 지형 7종 × 난이도 2/5/8, 명령 ±0.6 m/s, 16 env, 8 s)
앞으로 걸을 때 올라가는 계단 난이도 8에서 이동 거리가 4.9 → 1.6 m, 상자 4.6 → 2.7 m로 줄어 LiDAR 입력을 실제로 씁니다.
뒤로 걸을 때와 내려가는 계단에서는 차이가 없습니다. 내려가는 계단은 턱 너머 아랫단이 가려져 발끝 평면(지금 높이)으로
채워지기 때문으로 보입니다(걷는 장면 그림 확인). 넘어짐은 LiDAR를 켠 모든 조건에서 0입니다.
"""

import isaaclab.terrains as terrain_gen
import torch

from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.sensors import ContactSensorCfg, RayCasterCfg, patterns
from isaaclab.utils import configclass, replace
from isaaclab.utils.noise import UniformNoiseCfg as Unoise

import isaaclab_tasks.core.velocity.mdp as mdp
from isaaclab_rl.rsl_rl import RslRlSymmetryCfg
from isaaclab_tasks.core.velocity.config.go2.agents.rsl_rl_ppo_cfg import (
    UnitreeGo2FlatPPORunnerCfg,
    UnitreeGo2RoughPPORunnerCfg,
)
from isaaclab_tasks.core.velocity.config.go2.flat_env_cfg import UnitreeGo2FlatEnvCfg
from isaaclab_tasks.core.velocity.config.go2.rough_env_cfg import UnitreeGo2RoughEnvCfg
from isaaclab_tasks.core.velocity.velocity_env_cfg import ObservationsCfg as Go2ObservationsCfg

from ..common.heightmap import lidar_memory_height_scan
from ..common.rewards import apply_hn_rewards
from ..common.symmetry import compute_left_right_symmetric_states
from .robot import FOOT_BODY_REGEX, HN_HYPER_V1_CFG, LIDAR_BODY, TRUNK_BODY

# action과 관절 관측의 순서(HYPER와 같음). 실기 배포 코드도 이 순서를 씁니다.
JOINT_ORDER = [f"{leg}_{part}_joint" for part in ("hip", "thigh", "calf") for leg in ("FL", "FR", "RL", "RR")]

# actor 입력 항목 순서. 배포 코드가 같은 순서로 입력을 만들어야 합니다.
POLICY_OBS_TERMS = ("base_lin_vel", "base_ang_vel", "projected_gravity", "velocity_commands", "joint_pos", "joint_vel", "actions")

# 서 있을 때 몸통 높이 [m]. v0 Flat 환경에서 v1을 세워 본 값(0.29–0.30 m, 2026-11-11)입니다.
STANDING_HEIGHT = 0.30

# Isaac Lab TerrainImporter가 만드는 바닥 충돌체 경로. terrain_type="plane"은 기본 GroundPlane입니다.
GROUND_COLLIDER = {
    "plane": "/World/ground/terrain/GroundPlane/CollisionPlane",
    "generator": "/World/ground/terrain/mesh",
}


def _joints() -> SceneEntityCfg:
    return SceneEntityCfg("robot", joint_names=JOINT_ORDER, preserve_order=True)


def illegal_ground_contact(env, threshold: float, sensor_cfg: SceneEntityCfg) -> torch.Tensor:
    """mdp.illegal_contact와 같지만, 센서 body와 filter 대상(바닥) 사이의 접촉력만 봅니다 (HYPER mdp.py와 같음).

    Isaac Sim PhysX 6.1은 filter 접촉의 법선 성분만 주므로 normal_force_matrix_w_history를 씁니다.
    """
    f = env.scene.sensors[sensor_cfg.name].data.normal_force_matrix_w_history.torch  # (env, hist, body, filter, 3)
    return (torch.linalg.norm(f, dim=-1).amax(dim=1) > threshold).flatten(1).any(dim=1)


@configclass
class HnHyperV1ObservationsCfg:
    """actor: 실기 센서(IMU, 엔코더) + 명령 + 이전 action. critic: Go2 기본 입력 전체."""

    @configclass
    class PolicyCfg(ObsGroup):
        # trunk 질량중심 선속도(원점 아래 0.64 mm), trunk frame (실기: IMU 기반). 잡음은 Go2 기본값.
        base_lin_vel = ObsTerm(func=mdp.base_lin_vel, noise=Unoise(n_min=-0.1, n_max=0.1))
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2))
        projected_gravity = ObsTerm(func=mdp.projected_gravity, noise=Unoise(n_min=-0.05, n_max=0.05))
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        joint_pos = ObsTerm(func=mdp.joint_pos_rel, params={"asset_cfg": _joints()}, noise=Unoise(n_min=-0.01, n_max=0.01))
        joint_vel = ObsTerm(func=mdp.joint_vel_rel, params={"asset_cfg": _joints()}, noise=Unoise(n_min=-1.5, n_max=1.5))
        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    @configclass
    class CriticCfg(Go2ObservationsCfg.PolicyCfg):
        def __post_init__(self):
            super().__post_init__()
            self.enable_corruption = False
            self.joint_pos.params = {"asset_cfg": _joints()}
            self.joint_vel.params = {"asset_cfg": _joints()}

    policy: PolicyCfg = PolicyCfg()
    critic: CriticCfg = CriticCfg()


def _use_hn_robot(cfg) -> None:
    cfg.scene.robot = replace(HN_HYPER_V1_CFG, prim_path="{ENV_REGEX_NS}/Robot")
    # 변환된 USD에서 몸통 prim은 Robot/Geometry/<몸통 이름>에 있습니다(v0와 같음, Go2 공식 USD는 Robot/base).
    if getattr(cfg.scene, "height_scanner", None) is not None:
        cfg.scene.height_scanner.prim_path = f"{{ENV_REGEX_NS}}/Robot/Geometry/{TRUNK_BODY}"
    cfg.actions.joint_pos.joint_names = JOINT_ORDER
    cfg.actions.joint_pos.preserve_order = True

    # 몸통 이름을 쓰는 항목을 TRUNK_BODY로 맞춥니다.
    for event in (cfg.events.add_base_mass, cfg.events.base_com, cfg.events.base_external_force_torque):
        event.params["asset_cfg"].body_names = TRUNK_BODY

    # 몸통-바닥 접촉만 보는 센서와 종료 조건
    cfg.scene.base_ground_contact = ContactSensorCfg(
        prim_path=f"{{ENV_REGEX_NS}}/Robot/{TRUNK_BODY}",
        filter_prim_paths_expr=[GROUND_COLLIDER[cfg.scene.terrain.terrain_type]],
        history_length=3,
        update_period=cfg.sim.dt,
    )
    cfg.terminations.base_contact = DoneTerm(
        func=illegal_ground_contact,
        params={"sensor_cfg": SceneEntityCfg("base_ground_contact"), "threshold": 1.0},
    )


def _use_hn_rewards(cfg, terrain: str) -> None:
    """보상을 공용 보상표로 바꿉니다. 각 과제 __post_init__의 맨 끝에서 부릅니다(Go2 설정이 바꾼 값을 덮어쓰기 위해)."""
    apply_hn_rewards(
        cfg, terrain=terrain, foot_body_regex=FOOT_BODY_REGEX, standing_height=STANDING_HEIGHT, thigh_contact=True
    )


@configclass
class HnHyperV1RoughEnvCfg(UnitreeGo2RoughEnvCfg):
    """비교용: actor height scan = GT(Isaac Lab 기본). 배포하지 않습니다. Rough-Lidar가 이 설정을 상속합니다."""

    observations: HnHyperV1ObservationsCfg = HnHyperV1ObservationsCfg()

    def __post_init__(self):
        super().__post_init__()
        _use_hn_robot(self)
        # actor에도 height scan을 넣습니다(Go2 기본 항목·잡음과 같음). critic은 Go2 기본 입력에 이미 있습니다.
        self.observations.policy.height_scan = ObsTerm(
            func=mdp.height_scan,
            params={"sensor_cfg": SceneEntityCfg("height_scanner")},
            noise=Unoise(n_min=-0.1, n_max=0.1),
            clip=(-1.0, 1.0),
        )
        # 아래는 v0 Rough(urdf_v0/env.py)와 같은 조정입니다.
        # 순수 평지 칸(proportion 0.2, 정규화 후 약 17%). 난이도가 올라가도 평지 보행을 유지시킵니다.
        self.scene.terrain.terrain_generator.sub_terrains["flat"] = terrain_gen.MeshPlaneTerrainCfg(proportion=0.2)
        # 정지 연습: 정지 명령 비율 2% → 15% (정지 자세 벌점 stand_still은 보상표에 있음)
        self.commands.base_velocity.rel_standing_envs = 0.15
        # 방향 유지(heading) 제어를 받는 env 비율 100% → 50%. 나머지는 teleop·실기처럼 회전 속도 명령을 직접 받습니다.
        # 이것만으로는 전진 시 한쪽으로 도는 습관(−0.03 rad/s)이 고쳐지지 않았습니다(2026-11-15 heading50 측정).
        # 그 문제는 PPO 좌우 대칭 증강(_use_symmetry)으로 다룹니다.
        self.commands.base_velocity.rel_heading_envs = 0.5
        _use_hn_rewards(self, "rough")


# ---- LiDAR 기억 height map 과제 (2026-11-15) ----
# SOSLAB ML-X 120. 장착 위치·각도(가정값: trunk 기준 (0.16, 0, 0.10) m, 아래로 15°)는 URDF의 front_lidar_joint에 있고,
# 센서는 그 link에 offset 없이 붙습니다. 선 자세에서 바닥 위 약 0.40 m이고, 바닥이 센서 앞 약 0.63 m(trunk 기준 약 0.79 m)부터
# 보입니다. 맨 위 광선은 수평보다 약 2.5° 위라서 먼 바닥은 광선 최대 거리(6 m)까지 보입니다.
# 시야 가로 120° × 세로 35°(실제 0.209° × 0.625°)를 2° × 2.5°로 줄였습니다. 맞은 점마다 거리 오차 ±30 mm(균일)를 넣습니다.
LIDAR_PERIOD_S = 0.05  # ML-X 20 fps
# 정책 grid: x −0.35–1.25 m, y ±0.5 m, 0.1 m (187칸). GT grid(1.6 × 1.0 m)를 앞으로 0.45 m 옮긴 것과 같습니다.
# 보이기 시작하는 x ≈ 0.79 m 앞으로 보이는 칸이 약 5–6열 남습니다.
BLIND_GRID_OFFSET_X = 0.45


@configclass
class HnHyperV1RoughLidarEnvCfg(HnHyperV1RoughEnvCfg):
    """actor height scan = LiDAR로 본 점의 기억 + 발끝 평면. critic은 같은 grid의 GT height scan."""

    def __post_init__(self):
        super().__post_init__()
        # GT scanner를 정책 grid와 같은 칸으로 옮깁니다(critic 입력, base_height_l2, 비교용).
        self.scene.height_scanner.offset.pos = (BLIND_GRID_OFFSET_X, 0.0, 20.0)
        self.scene.mlx_lidar = RayCasterCfg(
            # 변환된 USD는 link를 부모 아래에 둡니다(Robot/Geometry/trunk/front_lidar).
            prim_path=f"{{ENV_REGEX_NS}}/Robot/Geometry/{TRUNK_BODY}/{LIDAR_BODY}",
            ray_alignment="base",
            pattern_cfg=patterns.LidarPatternCfg(
                channels=15, vertical_fov_range=(-17.5, 17.5), horizontal_fov_range=(-60.0, 60.0), horizontal_res=2.0
            ),
            max_distance=6.0,
            mesh_prim_paths=["/World/ground"],
            # 기억 항목이 LIDAR_PERIOD_S마다 읽을 때만 계산합니다(lazy update).
            update_period=0.0,
            debug_vis=False,
        )
        self.observations.policy.height_scan = ObsTerm(
            func=lidar_memory_height_scan,
            params={
                "lidar_cfg": SceneEntityCfg("mlx_lidar"),
                "ref_sensor_cfg": SceneEntityCfg("height_scanner"),
                "grid_size": (1.6, 1.0),
                "grid_offset_x": BLIND_GRID_OFFSET_X,
                "resolution": 0.1,
                "memory_s": 3.0,
                "scan_period_s": LIDAR_PERIOD_S,
                "foot_body_regex": FOOT_BODY_REGEX,
                "foot_radius": 0.025,
                "foot_window_s": 0.5,
                # 점마다 거리 오차 ±30 mm (ML-X 사양 오차 < 30 mm, 2026-11-20)
                "range_noise_m": 0.03,
            },
            noise=Unoise(n_min=-0.1, n_max=0.1),
            clip=(-1.0, 1.0),
        )


@configclass
class HnHyperV1FlatEnvCfg(UnitreeGo2FlatEnvCfg):
    observations: HnHyperV1ObservationsCfg = HnHyperV1ObservationsCfg()

    def __post_init__(self):
        super().__post_init__()
        _use_hn_robot(self)
        # Flat에는 height scanner가 없습니다.
        self.observations.critic.height_scan = None
        _use_hn_rewards(self, "flat")


# rsl_rl 관측 그룹: actor는 policy 그룹, critic은 critic 그룹을 받습니다.
OBS_GROUPS = {"actor": ["policy"], "critic": ["critic"]}


def _use_symmetry(runner_cfg) -> None:
    """PPO mini-batch에 좌우 뒤집은 복사본을 붙여 학습합니다(batch 2배, mirror loss는 끔)."""
    runner_cfg.algorithm.symmetry_cfg = RslRlSymmetryCfg(
        use_data_augmentation=True, data_augmentation_func=compute_left_right_symmetric_states
    )


# 학습 결과 폴더: /data/isaaclab/logs/rsl_rl/<experiment_name>/<날짜_시각>/
@configclass
class HnHyperV1RoughPPORunnerCfg(UnitreeGo2RoughPPORunnerCfg):
    def __post_init__(self):
        super().__post_init__()  # Go2 rough: 1500 iterations, [512, 256, 128]
        self.experiment_name = "hn_hyperv1_rough"
        self.obs_groups = dict(OBS_GROUPS)
        _use_symmetry(self)


@configclass
class HnHyperV1RoughLidarPPORunnerCfg(HnHyperV1RoughPPORunnerCfg):
    def __post_init__(self):
        super().__post_init__()
        self.experiment_name = "hn_hyperv1_rough_lidar"


@configclass
class HnHyperV1FlatPPORunnerCfg(UnitreeGo2FlatPPORunnerCfg):
    def __post_init__(self):
        super().__post_init__()
        self.experiment_name = "hn_hyperv1_flat"
        self.obs_groups = dict(OBS_GROUPS)
        _use_symmetry(self)
