# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
# Start a data source in Docker plus the dashboard dev server, then open the browser.
#   ./run-demo.ps1 -Bag D:/bags/20261115T120809_074988Z_measurement_e03893/rosbag2   # 11-15 recording -> Super-LIO
#   ./run-demo.ps1 -Bag <dir> -Lio fastlio      # same recording through FAST-LIO2 (previous pipeline)
#   ./run-demo.ps1 -Mode sim -SimScene <pair360-map/results/mesh_v3/mujoco>   # MuJoCo SIM (GT: /ground_truth/odom)
#   ./run-demo.ps1 -Bag <dir> -Rate 0.5         # slower replay if the page stutters
#   ./run-demo.ps1 -Stop                        # stop containers and the dev server
# The registration in registration/*.env is only valid for the 11-15 recording.
# Port 8765 on 127.0.0.1; ROS_DOMAIN_ID=42 keeps other ROS containers on this host out of the replay.
param([ValidateSet('bag', 'sim')][string]$Mode = 'bag', [ValidateSet('superlio', 'fastlio')][string]$Lio = 'superlio',
  [string]$Bag, [string]$SimScene, [double]$Rate = 1.0, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$pkg = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mount = ($pkg -replace '\\', '/') + ':/pkg:ro'
$env:MSYS_NO_PATHCONV = '1'

foreach ($name in 'hyper-bag-fastlio-1115', 'hyper-bag-superlio-1115', 'hyper-sim-mujoco-v3') { docker rm -f $name 2>$null | Out-Null }
Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -match 'vite.*5173' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
if ($Stop) { 'stopped'; return }

$map = (Get-Content (Join-Path $pkg 'public/reference-map.json') -Raw | ConvertFrom-Json).file
if ($Mode -eq 'bag') {
  if (-not $Bag) { throw '-Bag <rosbag2 folder> is required in bag mode' }
  $bagMount = ((Resolve-Path $Bag).Path -replace '\\', '/') + ':/bag:ro'
  # Images: ../adapters/fast_lio_twist/Dockerfile (twist), ./Dockerfile.superlio (Super-LIO on top of twist).
  $cfg = @{
    superlio = @('hyper-bag-superlio-1115', '1115_superlio.env', 'hn:ros-2026.10.1-local-superlio', 'run_bag_superlio.sh')
    fastlio  = @('hyper-bag-fastlio-1115', '1115.env', 'hn:ros-2026.10.1-local-twist', 'run_bag_lio.sh')
  }[$Lio]
  docker run -d --rm --name $cfg[0] -p 127.0.0.1:8765:8765 -e ROS_DOMAIN_ID=42 `
    --env-file (Join-Path $PSScriptRoot "registration/$($cfg[1])") -v $mount -v $bagMount `
    -e BRIDGE_ADDRESS=0.0.0.0 -e ADAPTERS=/pkg/adapters -e MAP_PCD=/pkg/public/$map `
    $cfg[2] bash "/pkg/replay/$($cfg[3])" /bag $Rate | Out-Null
  $hint = 'GT 토픽은 비워 두세요(실측에는 GT 없음). 11-15 기록은 1배속에서 약 5분 30초 뒤 끝납니다.'
} else {
  if (-not $SimScene) { throw '-SimScene <mesh_v3/mujoco folder> is required in sim mode' }
  $sceneMount = ((Resolve-Path $SimScene).Path -replace '\\', '/') + ':/scene:ro'
  $cmd = @"
source /opt/ros/jazzy/setup.bash; cd /pkg/adapters; PY=/opt/hn-venv/bin/python; export PYTHONDONTWRITEBYTECODE=1
`$PY -u mujoco_route_sim.py /scene --rate $Rate > /tmp/sim.log 2>&1 &
`$PY -u reference_map_ros.py ../public/$map --frame pair360_map > /tmp/map.log 2>&1 &
ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=0.0.0.0 port:=8765 > /tmp/bridge.log 2>&1 &
wait
"@
  docker run -d --rm --name hyper-sim-mujoco-v3 -p 127.0.0.1:8765:8765 -e ROS_DOMAIN_ID=42 -v $mount -v $sceneMount `
    hn:ros-2026.10.1-local bash -lc $cmd | Out-Null
  $hint = "GT 오차를 보려면 'ROS 주소·토픽 설정'에서 GT 토픽에 /ground_truth/odom 을 넣으세요."
}
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$pkg'; npm run dev -- --port 5173 --strictPort" -WindowStyle Minimized
Start-Sleep 6
Start-Process 'http://127.0.0.1:5173'
"데이터 소스: $Mode $(if ($Mode -eq 'bag') { $Lio }) (배속 $Rate). 브라우저에서 '수신 시작'을 누르고 '로봇 따라가기'를 켜세요."
$hint
"끝낼 때: ./run-demo.ps1 -Stop"
