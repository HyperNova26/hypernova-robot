# SPDX-License-Identifier: Apache-2.0
"""패키지를 설치하지 않고 시험하도록 import 경로만 잡습니다(ros_pkgs/hn_robot_state를 sys.path에 추가)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
