"""Isaac Sim ROS 2 bridge 점검: 시뮬레이션 시각을 /clock 토픽으로 N초 동안 발행합니다.

hn:sim 컨테이너에서 이 스크립트를 돌리고, 다른 컨테이너(hn:ros)에서 토픽을 받아 보면
"컨테이너 사이 ROS 통신"이 되는지 확인할 수 있습니다. GPU가 있는 PC의 hn:sim에서만 돌아갑니다.

  사용   터미널 1:  ./docker/hn sim ./isaaclab.sh -p /workspace/hypernova/tools/isaac_clock_pub.py --seconds 90
         터미널 2:  ./docker/hn ros ros2 topic echo /clock rosgraph_msgs/msg/Clock
  주의   Isaac Sim이 뜨고 bridge가 켜질 때까지 20초쯤 걸립니다. 토픽 타입(rosgraph_msgs/msg/Clock)을 적어 주면
         echo가 토픽이 생길 때까지 기다리고, 안 적으면 토픽이 아직 없을 때 바로 끝납니다.
  환경   hn:sim 컨테이너(Isaac Sim 6.2, 시스템 ROS Jazzy를 bridge가 그대로 씁니다)

NVIDIA의 standalone_examples/api/isaacsim.ros2.bridge/clock.py(Apache-2.0)를 바탕으로 만들었습니다.
"""

import argparse
import time

from isaacsim import SimulationApp

parser = argparse.ArgumentParser(description="Isaac Sim 시뮬레이션 시각을 /clock으로 발행합니다.")
parser.add_argument("--seconds", type=float, default=60.0, help="발행을 유지할 시간(초). 기본 60")
args = parser.parse_args()

# Isaac Sim 모듈은 SimulationApp을 만든 뒤에 import해야 합니다.
simulation_app = SimulationApp({"headless": True})

import isaacsim.core.experimental.utils.app as app_utils  # noqa: E402
import omni.graph.core as og  # noqa: E402

app_utils.enable_extension("isaacsim.ros2.bridge")
simulation_app.update()

og.Controller.edit(
    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
    {
        og.Controller.Keys.CREATE_NODES: [
            ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
            ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
            ("PublishClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
        ],
        og.Controller.Keys.CONNECT: [
            ("OnPlaybackTick.outputs:tick", "PublishClock.inputs:execIn"),
            ("ReadSimTime.outputs:simulationTime", "PublishClock.inputs:timeStamp"),
        ],
        og.Controller.Keys.SET_VALUES: [("PublishClock.inputs:topicName", "clock")],
    },
)
simulation_app.update()

app_utils.play()
print(f"[isaac_clock_pub] /clock 발행 시작 ({args.seconds:.0f}초). 다른 컨테이너에서: ros2 topic echo /clock rosgraph_msgs/msg/Clock", flush=True)
end = time.time() + args.seconds
while time.time() < end:
    simulation_app.update()
app_utils.stop()
simulation_app.close()
print("[isaac_clock_pub] 끝", flush=True)
