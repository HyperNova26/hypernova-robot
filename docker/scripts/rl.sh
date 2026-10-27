#!/usr/bin/env bash
# Isaac Lab 학습·재생 wrapper. sim 이미지에서 `hn-rl`로 부릅니다.
#
#   hn-rl train --task Isaac-Velocity-Rough-UnitreeGo2 --num_envs 2048 --max_iterations 20
#   hn-rl play  --task Isaac-Velocity-Rough-UnitreeGo2 --num_envs 16 --checkpoint <경로>
#
# 왜 있나: Isaac Lab 3.0.0 내장 과제의 기본 physics는 PhysX가 아니라 newton_mjwarp이고, 지정하지 않으면
# 아무 오류 없이 다른 엔진으로 학습됩니다. 우리는 PhysX로 학습하기로 했으므로(ADR-0002) 이 wrapper가
# `physics=isaacsim_physx`와 `--rl_library rsl_rl`을 대신 붙입니다. 인자로 직접 주면 그 값을 씁니다(경고를 출력).
#   예: hn-rl train ... physics=newton_mjwarp
# 나머지 인자는 scripts/reinforcement_learning/{train,play}.py에 그대로 넘깁니다. 실행 위치는 /workspace/isaaclab.
# HN_RL_DRY_RUN=1이면 실행하지 않고 만들어진 명령만 출력합니다(점검용).
set -euo pipefail

mode="${1:-}"
case "$mode" in
  train | play) shift ;;
  *) echo "사용법: hn-rl train|play [train.py/play.py 인자...]" >&2; exit 2 ;;
esac

args=("$@")
has_lib=0
physics=""
for a in "${args[@]}"; do
  case "$a" in
    --rl_library | --rl_library=*) has_lib=1 ;;
    physics=*) physics="${a#physics=}" ;;
  esac
done

if [ "$has_lib" = 0 ]; then
  args=(--rl_library rsl_rl "${args[@]}")
fi
if [ -z "$physics" ]; then
  args+=(physics=isaacsim_physx)
elif [ "$physics" != isaacsim_physx ]; then
  echo "[hn-rl] 경고: physics=$physics 로 실행합니다. 우리 기본은 isaacsim_physx(PhysX)입니다(ADR-0002)." >&2
fi

cmd=(./isaaclab.sh -p "scripts/reinforcement_learning/${mode}.py" "${args[@]}")
if [ -n "${HN_RL_DRY_RUN:-}" ]; then
  printf '%q ' "${cmd[@]}"; printf '\n'
  exit 0
fi
cd /workspace/isaaclab
exec "${cmd[@]}"
