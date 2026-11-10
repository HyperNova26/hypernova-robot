# CLAUDE.md

This file provides shared guidance to coding assistants working in this repository. Keep it in Git; personal instructions and settings belong in ignored `CLAUDE.local.md` and `.claude/settings.local.json`.

## Repo state

As of 2026-10-30:

- The repo contains Docker image definitions, a locked Python environment (`pyproject.toml`, `uv.lock`), ROS demo scripts, and point-cloud scene tools in `tools/map/`, with paired `.sh` launchers and `.py` implementations and regression tests in `tests/map/`. The converter exports whole-cloud voxel occupancy to USD/MuJoCo; the disassembler only creates an empty dated output directory and reports that decomposition is not implemented. Ground separation and downstream cars/other object segmentation are unfinished; implement/improve and validate them on real PAIR360 data under S-004 ([live task](https://app.notion.com/p/40645bd87178819e9242cff36b48cb3d)).
- `description/`, `firmware/`, `ros_pkgs/`, and `policies/` remain README-only scaffolds. Don't assume robot models, ROS packages, firmware, or project-specific policies exist.
- Don't create empty placeholder directory structures. The explicitly requested disassembler runtime output is an empty directory by contract, not a repository scaffold.
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
- Map-script regression tests in the prepared host Python environment: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest tests/map -q`. See `sim_scenes/README.md` for the script contract and limits. Synthetic tests do not establish real-data full-resolution completion, simulator GUI validation, physical success, or ground/object segmentation accuracy. Ground/cars/other segmentation remains S-004 follow-up work; do not infer completion from old quick artifacts or current whole-scene exports.
- Docker CI (`.github/workflows/docker-ros.yml`) builds `ros` for amd64/arm64 and runs the amd64 image self-test on relevant changes. It does not build `sim` or run the map-script regression suite. In a prepared container, `/opt/hn/scripts/selftest.sh` checks the environment; add `--isaac` in `sim` to check Isaac Lab imports.

## Docs and writing

- Repo docs, PR templates, and ADRs are in Korean, polite-formal (-ㅂ니다/-습니다), with technical terms (ROS, URDF, frame) kept in English. Match this when editing existing docs.
- State an as-of date; attach environment and units to commands, configs, and measurements.
- Link a replacement doc before deleting a stale one.
- Hard-to-reverse or cross-area decisions go in an ADR: `docs/decisions/NNNN-short-title.md`. Status is `Proposed`, `Accepted`, or `Superseded`. Sections: status/date, background, options considered, decision, consequences, conditions to revisit.

## Git workflow

- Branch from `main` as `<feat|fix|docs|chore>/<topic>`. No direct push to `main`; PR with the template, squash merge.
- Commits: Conventional-style prefix (`docs:`, `chore:`), one change per commit. Korean or English is fine.

## Layout and content rules

- Robot geometry, robot frames, and joints live only in `description/`; never duplicate them elsewhere. Scene and terrain coordinate settings belong with the scene. `sim_scenes/pair360_parking/frame.yaml` is preserved historical configuration; the current converter does not read it.
- Boundaries: low-level board code in `firmware/`; ROS adapters, runtime nodes, inference nodes, and simulator launch in `ros_pkgs/`; training/eval/export in `policies/`; reusable offline data/conversion tools in `tools/`; scene definitions in `sim_scenes/`.
- Each ROS package keeps its own `config/`, `launch/`, `test/`. Configs state units, parent/child frame, axis convention, and hardware revision; no secrets.
- `tools/map/` contains `demo_sim_converter.sh`, `demo_sim_converter.py`, `demo_sim_disassembler.sh`, and `demo_sim_disassembler.py`; current usage lives in `sim_scenes/README.md`. Each `.sh` is a thin environment/interpreter launcher for the same-named `.py`; keep implementation in Python and support direct `.py` invocation with repository paths resolved from `__file__`. The converter uses every finite XYZ point to build shared voxel occupancy, a static USD triangle Mesh, and static MuJoCo box geoms; it does not segment objects or generate a heightfield. Launcher Python selection is explicit `HN_MAP_PYTHON`, then container `/opt/hn-venv/bin/python`, then `uv run --no-sync --project <repository> python`. Keep dependencies unchanged during execution. Help and the disassembler require Python but use only its standard library; conversion requires the prepared NumPy, Open3D, and usd-core environment. Read common Open3D point-cloud formats directly; native CloudCompare BIN requires optional CloudCompare and is converted from a temporary copy only. Preserve raw data under ignored `data/PAIR360_data/` and existing results under `data/PAIR360_demo/` and `sim_scenes/`. The user input is `data/PAIR360_data/T1_Parking_and_OpenTheater/T1_parking_Seq0_demo.bin`. New output defaults to ignored `sim_scenes/MMDD_demo_whole/` or `sim_scenes/MMDD_demo_disassembled/`, with Asia/Seoul dates; refuse existing output paths. The disassembler creates an empty directory only. Never create success claims for simulator/viewer execution without running them. Containers expose repository data through `/workspace/hypernova/data/`; `/data` still uses `HN_DATA_DIR` (default `~/hypernova-data`).
- Never commit build outputs, raw rosbags/MCAP/PCD/PLY, checkpoints/weights (including `.onnx.data` sidecars), CAD/EDA originals, secrets, or personal `.env`/paths. Small regression fixtures require purpose, provenance, and review under `tests/data/`; see `docs/development/repository-policy.md`. Files over 10 MiB need a placement decision first (Release asset, submodule, or LFS). No Git LFS yet; decide before the first large mesh.
- `docker/.env` is tracked version-pin configuration; `docker/.env.local` is ignored personal configuration. Keep `docker/.env.local.example` tracked and free of secrets. Avoid blanket ignores for required mesh formats or all NumPy arrays; review their placement and provenance.
- Don't hand-edit generated files. If committed, record source, revision, generation command, and tool versions.
- External code uses package managers, commit-pinned `.repos` manifests, or pinned submodules; never copy external repositories into the tree. New files carry the license for their path (see `LICENSE.md`); third-party files keep their original notices.

## Safety

- PRs touching E-stop, watchdog, current/speed/joint limits, battery protection, or comms authority must state safety impact, failure modes, verification, and rollback. Physical tests follow `docs/operations/safety.md`.
