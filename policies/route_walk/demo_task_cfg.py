# SPDX-License-Identifier: Apache-2.0
"""v1 urdf_v0의 Rough 과제(HnGo2V0RoughEnvCfg)에 PAIR360 데모 지형만 얹은 재생·평가용 환경입니다(학습용이 아님).

로봇·액추에이터·접촉·height scanner 설정은 policies/urdf_v0/env.py 것을 그대로 쓰고, 지형만 데모 프레임으로 정렬한 USD 충돌 메시로 바꿉니다.
env origin (0, 0, 0)이 데모 프레임 원점입니다(docs/decisions/0003-pair360-demo-frame.md가 제안한 프레임, 아직 Proposed).
"""
import os

from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils import configclass

from policies.urdf_v0.env import HnGo2V0RoughEnvCfg

DATA = os.environ.get("HN_DEMO_DATA", "/data")   # 컨테이너 안 데이터 폴더(호스트 HN_DATA_DIR)
TERRAIN_USD = f"{DATA}/pair360_demo_frame/isaac/ground_collision_demo.usdc"   # 데모 프레임 지형 충돌 메시(Git 밖)


@configclass
class HnGo2V0DemoRoughEnvCfg(HnGo2V0RoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        self.scene.terrain = TerrainImporterCfg(prim_path="/World/ground", terrain_type="usd", usd_path=TERRAIN_USD)
        self.curriculum.terrain_levels = None  # 지형 생성기가 없으므로 난이도 curriculum 끔
