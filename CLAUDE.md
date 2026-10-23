# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo state

- Docs-only scaffold: no code, manifests, tests, or build system yet. Top-level dirs (`description/`, `firmware/`, `ros_pkgs/`, `sim_scenes/`, `policies/`, `tools/`) are README-only. Don't assume ROS packages, URDF, or firmware exist.
- Don't create empty placeholder directory structures.
- ADR-0002 (shared dev environment: Docker, ROS 2 Jazzy, Isaac Lab) is only *Proposed*. Don't treat it as adopted; `docs/development/getting-started.md` still says the environment is undecided.
- `docs/hypernova-project-handoff.md` is a Korean snapshot (2026-08-14) and partly stale. Its status labels TARGET / CANDIDATE / OPEN mean not done. Don't invent quantitative requirements or assume funding beyond what it states.

## Commands

- Only automated check is markdownlint (CI: `.github/workflows/docs.yml`). Run locally with `npx markdownlint-cli2`. Config in `.markdownlint-cli2.jsonc`: MD013 and MD041 off; inline HTML limited to `div`, `img`, `p`, `strong`.

## Docs and writing

- Repo docs, PR templates, and ADRs are in Korean, polite-formal (-ㅂ니다/-습니다), with technical terms (ROS, URDF, frame) kept in English. Match this when editing existing docs.
- State an as-of date; attach environment and units to commands, configs, and measurements.
- Link a replacement doc before deleting a stale one.
- Hard-to-reverse or cross-area decisions go in an ADR: `docs/decisions/NNNN-short-title.md`. Status is `Proposed`, `Accepted`, or `Superseded`. Sections: status/date, background, options considered, decision, consequences, conditions to revisit.

## Git workflow

- Branch from `main` as `<feat|fix|docs|chore>/<topic>`. No direct push to `main`; PR with the template, squash merge.
- Commits: Conventional-style prefix (`docs:`, `chore:`), one change per commit. Korean or English is fine.

## Layout and content rules

- Robot geometry, frames, and joints live only in `description/`; never duplicate them elsewhere.
- Boundaries: low-level board code in `firmware/`; ROS adapters, runtime nodes, inference nodes, and simulator launch in `ros_pkgs/`; training/eval/export in `policies/`.
- Each ROS package keeps its own `config/`, `launch/`, `test/`. Configs state units, parent/child frame, axis convention, and hardware revision; no secrets.
- Never commit build outputs, rosbags/MCAP/PCD/PLY, checkpoints/weights, CAD/EDA originals, secrets, or personal `.env`/paths. Files over 10 MiB need a placement decision first (Release asset, submodule, or LFS). No Git LFS yet; decide before the first large mesh.
- Don't hand-edit generated files. If committed, record source, revision, generation command, and tool versions.
- External repos are pinned submodules, never copied in. New files carry the license for their path (see `LICENSE.md`); third-party files keep their original notices.

## Safety

- PRs touching E-stop, watchdog, current/speed/joint limits, battery protection, or comms authority must state safety impact, failure modes, verification, and rollback. Physical tests follow `docs/operations/safety.md`.
