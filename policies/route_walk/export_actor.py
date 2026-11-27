# SPDX-License-Identifier: Apache-2.0
"""rsl_rl 체크포인트(.pt)의 actor 가중치를 numpy용 .npz로 내보냅니다.

torch가 있는 환경(Isaac Lab의 Python)에서 한 번만 실행합니다. 결과 .npz는 torch 없이 runner.py가 읽습니다.
체크포인트는 `weights_only=True`로 읽고, yaml에 적힌 sha256·구조와 맞는지 확인한 뒤에만 씁니다.
출력 파일은 가중치라 저장소에 커밋하지 않습니다(policies/README.md).

  <Isaac Lab python> policies/route_walk/export_actor.py policies/urdf_v0/policy_io.yaml \
      policies/urdf_v0/pretrained/hn_go2v0_rough_model_3849.pt actor.npz
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy_io import PolicyIOError, load_policy_io  # noqa: E402


def export(yaml_path: str, ckpt_path: str, out_path: str) -> None:
    io = load_policy_io(yaml_path)
    sha = hashlib.sha256(Path(ckpt_path).read_bytes()).hexdigest()
    want_sha = io.raw["policy"]["checkpoint"]["sha256"]
    if sha != want_sha:
        raise PolicyIOError(f"체크포인트 sha256 {sha}가 yaml({want_sha})과 다릅니다")
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    sd = ck["actor_state_dict"]
    idx = sorted({int(k.split(".")[1]) for k in sd if k.startswith("mlp.") and k.endswith(".weight")})
    ws = [sd[f"mlp.{i}.weight"].numpy().astype(np.float32) for i in idx]
    bs = [sd[f"mlp.{i}.bias"].numpy().astype(np.float32) for i in idx]
    dims = [ws[0].shape[1]] + [w.shape[0] for w in ws]
    want = [io.obs_dim, *io.hidden_dims, len(io.joints)]
    if dims != want:
        raise PolicyIOError(f"체크포인트 구조 {dims}가 yaml과 다릅니다({want})")
    if int(ck.get("iter", -1)) != int(io.raw["policy"]["checkpoint"]["iteration"]):
        raise PolicyIOError(f"체크포인트 iteration {ck.get('iter')}이 yaml과 다릅니다")
    arrays = {"num_layers": np.array(len(ws))}
    for i, (w, b) in enumerate(zip(ws, bs)):
        arrays[f"w{i}"], arrays[f"b{i}"] = w, b
    arrays["source_sha256"] = np.array(sha)
    arrays["source_iteration"] = np.array(int(ck["iter"]))
    np.savez(out_path, **arrays)
    print(f"저장: {out_path}  층 {dims}  원본 sha256 {sha[:12]}…  iteration {int(ck['iter'])}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    export(*sys.argv[1:])
