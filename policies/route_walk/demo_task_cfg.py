# SPDX-License-Identifier: Apache-2.0
"""PAIR360 지형만 얹은 Rough 재생·평가용 환경(학습용이 아님). 로봇 버전마다 클래스가 하나씩 있습니다.

로봇·액추에이터·접촉·height scanner 설정은 각 버전의 env.py(policies/urdf_v0/env.py, policies/urdf_v1/env.py)를 그대로 쓰고,
지형만 USD 충돌 메시로 바꿉니다(지형·장애물 파일은 재생기의 --hn-terrain-usd, --hn-obstacles-usd).
좌표는 지형 파일의 좌표 그대로입니다. env origin (0, 0, 0)은 그 좌표의 원점이고 로봇은 재생기가 시작점으로 옮깁니다.
기본 지형(MAP=v3, pair360_map 좌표)은 docs/decisions/0005-pair360-map-frame.md, 예전 데모 지형(MAP=demo)은 0003을 따릅니다.
"""
import os

import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils import configclass

from policies.urdf_v0.env import HnGo2V0RoughEnvCfg
from policies.urdf_v1.env import HnHyperV1RoughEnvCfg

DATA = os.environ.get("HN_DEMO_DATA", "/data")   # 컨테이너 안 데이터 폴더(호스트 HN_DATA_DIR)
# 지형 충돌 메시(Git 밖). 재생기의 --hn-terrain-usd(환경 변수 HN_TERRAIN_USD)로 바꿉니다. 기본은 예전 데모 지형(데모 프레임).
DEFAULT_TERRAIN_USD = f"{DATA}/pair360_demo_frame/isaac/ground_collision_demo.usdc"


def _use_demo_terrain(cfg) -> None:
    terrain_usd = os.environ.get("HN_TERRAIN_USD", DEFAULT_TERRAIN_USD)
    cfg.scene.terrain = TerrainImporterCfg(prim_path="/World/ground", terrain_type="usd", usd_path=terrain_usd)
    # 이동 금지 장애물과 나무: 충돌만 하고 height scanner(/World/ground만 봄)에는 안 보입니다. MuJoCo의 group 0(지면) 밖 충돌 geom과 같은 역할.
    obstacles_usd = os.environ.get("HN_OBSTACLES_USD")
    if obstacles_usd:
        cfg.scene.obstacles = AssetBaseCfg(prim_path="/World/obstacles", spawn=sim_utils.UsdFileCfg(usd_path=obstacles_usd))
    cfg.curriculum.terrain_levels = None  # 지형 생성기가 없으므로 난이도 curriculum 끔


@configclass
class HnGo2V0DemoRoughEnvCfg(HnGo2V0RoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        _use_demo_terrain(self)


@configclass
class HnHyperV1DemoRoughEnvCfg(HnHyperV1RoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        _use_demo_terrain(self)
        # v1 Rough는 몸통-바닥 접촉 센서의 filter를 지형 생성기 메시 경로(/World/ground/terrain/mesh)로 잡습니다.
        # 데모는 지형을 USD로 바꿔 그 경로가 없으므로, 이 센서와 이를 읽는 종료 조건을 함께 끕니다(재생기는 종료 조건을 쓰지 않습니다).
        self.scene.base_ground_contact = None
        self.terminations.base_contact = None
