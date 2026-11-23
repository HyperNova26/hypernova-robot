# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
cmake_minimum_required(VERSION 3.8)
project(hn_sw_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  # 공통 값
  "msg/Validity.msg"
  "msg/ControlMode.msg"
  "msg/CommandStatus.msg"
  "msg/RunTarget.msg"
  "msg/Reason.msg"
  # 임무·경로 (IF-01, 03, 16)
  "msg/Waypoint.msg"
  "msg/Route.msg"
  "msg/MissionStatus.msg"
  "msg/WaypointEvent.msg"
  "msg/TargetResult.msg"
  "msg/InspectionDetection.msg"
  # 제어권 (IF-02, 04)
  "msg/TeleopCmd.msg"
  "msg/AppHeartbeat.msg"
  "msg/ControlState.msg"
  "msg/SelectedSafeCmd.msg"
  # 안전 (IF-04, 05, 06, 20, 21)
  "msg/Hazard.msg"
  "msg/HazardState.msg"
  "msg/SafetyVerdict.msg"
  "msg/JointTargets.msg"
  "msg/JointCommand.msg"
  # 상태·장치 (IF-07, 10, 11, 22)
  "msg/RobotState.msg"
  "msg/DeviceFault.msg"
  # 지도·이벤트 (IF-13, 14, 18)
  "msg/MapInfo.msg"
  "msg/Event.msg"
  "srv/SubmitRoute.srv"
  "srv/ApproveRoute.srv"
  "srv/RequestMode.srv"
  "srv/AckEvent.srv"
  "srv/QueryRecord.srv"
  "srv/RegisterMap.srv"
  "action/ExecuteMission.action"
  DEPENDENCIES std_msgs geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
