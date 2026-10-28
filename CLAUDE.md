# CLAUDE.md

This file provides shared guidance to coding assistants working in this repository. Keep it in Git; personal instructions and settings belong in ignored `CLAUDE.local.md` and `.claude/settings.local.json`.

## Repo state

As of 2026-10-28:

- The repo contains Docker image definitions, a locked Python environment (`pyproject.toml`, `uv.lock`), ROS demo scripts, and the PAIR360 terrain pipeline with synthetic tests in `tools/map/tests/`.
- `description/`, `firmware/`, `ros_pkgs/`, and `policies/` remain README-only scaffolds. Don't assume robot models, ROS packages, firmware, or project-specific policies exist.
- Don't create empty placeholder directory structures.
- Docker setup is implemented and documented in `docker/README.md` and `docs/development/getting-started.md`: Ubuntu 24.04 + ROS 2 Jazzy, with `ros` and `sim` image targets. ADR-0002 still has status *Proposed*; don't describe it as formally Accepted or change its status without a decision.
- `docs/hypernova-project-handoff.md` is a Korean snapshot (2026-08-14) and partly stale. Its status labels TARGET / CANDIDATE / OPEN mean not done. Don't invent quantitative requirements or assume funding beyond what it states.

## Environment and commands

Run commands from the repo root unless stated otherwise.

- Host Python tools target Ubuntu 24.04 and `/usr/bin/python3.12`. Prepare `.venv` with `./tools/setup-venv.sh`; check the lock with `uv lock --check`; run scripts with `uv run python <script.py>`. See `docs/development/python-env.md`. Report host mismatches rather than silently changing the interpreter policy.
- Manage Python dependencies through `uv add`; keep `pyproject.toml` and `uv.lock` together. Don't hand-edit `uv.lock` or install packages directly with pip. ROS packages belong in apt/the ROS image; Isaac Lab, Isaac Sim, and torch stay in the separate Isaac Lab environment.
- Use `./docker/hn` for containers; it prepares personal configuration, mounts, and permissions. In a container, use `/opt/hn-venv/bin/python` for robot tools and the Isaac Lab launcher for Isaac tasks. Don't use the host `.venv` there or activate the robot venv inside `sim`.
- Container dependency/pin changes require both `./docker/hn build ros` and `./docker/hn build sim`, plus an `HN_IMAGE_TAG` bump in `docker/.env`; see `docker/README.md`. State explicitly if either build could not be verified.

## Checks

- Markdown: `npx markdownlint-cli2` (CI: `.github/workflows/docs.yml`). Config in `.markdownlint-cli2.jsonc`: MD013 and MD041 off; inline HTML limited to `div`, `img`, `p`, `strong`.
- Terrain regression tests in the prepared host Python environment: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest tools/map/tests -q`. See `tools/map/README.md` for coverage and limits. Synthetic tests do not establish real-data semantic accuracy, full-resolution completion, or simulator GUI validation.
- Docker CI (`.github/workflows/docker-ros.yml`) builds `ros` for amd64/arm64 and runs the amd64 image self-test on relevant changes. It does not build `sim` or run the terrain pytest suite. In a prepared container, `/opt/hn/scripts/selftest.sh` checks the environment; add `--isaac` in `sim` to check Isaac Lab imports.

## Docs and writing

- Repo docs, PR templates, and ADRs are in Korean, polite-formal (-ㅂ니다/-습니다), with technical terms (ROS, URDF, frame) kept in English. Match this when editing existing docs.
- State an as-of date; attach environment and units to commands, configs, and measurements.
- Link a replacement doc before deleting a stale one.
- Hard-to-reverse or cross-area decisions go in an ADR: `docs/decisions/NNNN-short-title.md`. Status is `Proposed`, `Accepted`, or `Superseded`. Sections: status/date, background, options considered, decision, consequences, conditions to revisit.

## Git workflow

- Branch from `main` as `<feat|fix|docs|chore>/<topic>`. No direct push to `main`; PR with the template, squash merge.
- Commits: Conventional-style prefix (`docs:`, `chore:`), one change per commit. Korean or English is fine.

## Layout and content rules

- Robot geometry, robot frames, and joints live only in `description/`; never duplicate them elsewhere. Scene and terrain coordinate settings belong with the scene, such as `sim_scenes/pair360_parking/frame.yaml`.
- Boundaries: low-level board code in `firmware/`; ROS adapters, runtime nodes, inference nodes, and simulator launch in `ros_pkgs/`; training/eval/export in `policies/`; reusable offline data/conversion tools in `tools/`; scene definitions in `sim_scenes/`.
- Each ROS package keeps its own `config/`, `launch/`, `test/`. Configs state units, parent/child frame, axis convention, and hardware revision; no secrets.
- PAIR360 processing lives in `tools/map/`; its scene/frame configuration is `sim_scenes/pair360_parking/frame.yaml`. Local data now lives under the repository's ignored `data/`: raw data in `data/PAIR360_data/` (`Calibration/`, `T1_Parking_and_OpenTheater/`, `T3_Parking_and_OpenTheater/`) and results in `data/PAIR360_demo/`. These folders were moved from beside the repository. Follow `tools/map/README.md`: use cropped input, preserve raw data, and pass an explicit `--out data/PAIR360_demo/<new-run>` separated from the input. The YAML default still points to legacy `../PAIR360_demo/2026-10-26_v1`; override it until the configuration is updated. Use a fresh output folder when configuration or code changes; reuse upstream results only through the documented `--reuse-heightfield-from` checks. Containers already expose these files at `/workspace/hypernova/data/` through the code mount; `/data` still uses `HN_DATA_DIR` (default `~/hypernova-data`).
- Never commit build outputs, raw rosbags/MCAP/PCD/PLY, checkpoints/weights (including `.onnx.data` sidecars), CAD/EDA originals, secrets, or personal `.env`/paths. Small regression fixtures require purpose, provenance, and review under `tests/data/`; see `docs/development/repository-policy.md`. Files over 10 MiB need a placement decision first (Release asset, submodule, or LFS). No Git LFS yet; decide before the first large mesh.
- `docker/.env` is tracked version-pin configuration; `docker/.env.local` is ignored personal configuration. Keep `docker/.env.local.example` tracked and free of secrets. Avoid blanket ignores for required mesh formats or all NumPy arrays; review their placement and provenance.
- Don't hand-edit generated files. If committed, record source, revision, generation command, and tool versions.
- External code uses package managers, commit-pinned `.repos` manifests, or pinned submodules; never copy external repositories into the tree. New files carry the license for their path (see `LICENSE.md`); third-party files keep their original notices.

## Safety

- PRs touching E-stop, watchdog, current/speed/joint limits, battery protection, or comms authority must state safety impact, failure modes, verification, and rollback. Physical tests follow `docs/operations/safety.md`.
