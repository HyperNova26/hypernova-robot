# AGENTS.md

Repository instructions for Codex. As of 2026-10-27.

## Shared repository guidance

- Read [CLAUDE.md](CLAUDE.md) before starting work and follow its shared repository guidance. It covers the current repo state, setup, validation commands, directory boundaries, data policy, writing conventions, and robot safety.
- Keep shared technical guidance in `CLAUDE.md` rather than maintaining a second copy here. This file adds Codex working agreements. Follow applicable instructions in deeper directories for work in those paths.
- Inspect current files before relying on a scaffold description or historical project snapshot. Distinguish implemented behavior, proposed decisions, planned work, and verified results.

## Global instructions

### Use agents to spread token use on complicated tasks

- For any task that touches many files, needs broad search, or has independent parts, split it up and delegate to subagents instead of doing everything in this one context.
- Good candidates for delegation: codebase exploration and "where is X" searches, reading large files or logs, running and summarizing long test or build output, independent edits in separate files or modules, and second-opinion review of a finished change.
- Before delegating, write a short plan: the sub-tasks, which are independent, and what each agent should return.
- Give each agent a self-contained prompt (paths, goal, constraints, expected output). It does not share your context.
- Ask agents to return concise findings: file paths with line numbers, the conclusion, and anything surprising. Do not ask for raw dumps.
- Run independent agents in parallel. Do not give two agents overlapping files to edit.
- Keep the main context for coordination, decisions, and integration. Do small, quick tasks (a one-file fix, a single lookup) yourself; delegation has overhead.
- Check what agents report before relying on it, especially claims that something works or that a bug is fixed.

### Git: do not commit

- Never run `git commit`, `git commit --amend`, `git push`, `git rebase`, `git reset`, `git stash`, or anything else that changes history or the remote. Leave edits in the working tree.
- Read-only git (`status`, `diff`, `log`, `show`) is fine.
- After each logical chunk of edits (a feature piece, a fix, a refactor step, before moving to an unrelated change), stop and tell me it is a good point to commit. Include:
  - **Suggested commit message**: a one-line summary (imperative, under about 72 characters), then a short body.
  - **Summary of work done**: bullets covering what changed and why.
  - **Files touched**: the list of paths.
  - **Not verified / caveats**: tests not run, assumptions made, follow-ups.
- Do not stage files (`git add`) unless I ask. Do not mix unrelated changes into one suggested commit; suggest separate commits instead.
- Do not use a connector to perform prohibited Git operations. Preserve existing user edits. Repository branch, PR, and merge conventions in `CLAUDE.md` describe the human workflow; they do not authorize Codex to commit or publish.

## Task context from Notion and the roadmap

- For work tied to a roadmap/task ID or a request about priorities or progress, read the relevant task's current goal and completion criteria when connected tools are available. Prefer the connected Notion and GitHub tools for those sources.
- The [AI/CV task planner](https://hypernova26.github.io/hypernova-robot/) is backed by `data/roadmap.json` on this repository's `gh-pages` branch. Read that branch through the GitHub connector or read-only Git inspection; do not switch the active checkout just to consult it.
- The planner JSON contains task IDs, dates, statuses, and Notion links. It is a separately maintained snapshot, not a live Notion feed. Follow the linked Notion task for current operational status and completion criteria; use repository files and validation results to establish implementation state. Report conflicts rather than silently treating either source as synchronized.
- Access depends on the active connection. If a source is unavailable, state the coverage limit and continue work that does not depend on it. Never claim access merely because a connector or page shell exists.
- Read access does not authorize task mutations. Update Notion pages, task status, dates, assignees, or planner data only when the user requests it. Do not mark work complete solely because a code change exists, or automatically synchronize the two trackers.
- Keep private task content and credentials out of repository instructions. Reference the live source instead of copying task inventories, personal details, or current deadlines here.

## Validation and delivery

- Report concrete outcomes, changed paths, checks performed, and material limits. Do not claim that a simulator run, physical test, build, or task is complete without evidence.
- Use the relevant checks listed in `CLAUDE.md`. Run `git diff --check` for edited tracked files and inspect new files as well; report missing tools or environment mismatches explicitly.
- Documentation changes use `npx markdownlint-cli2`; terrain changes use the documented synthetic pytest suite. Dependency or container changes require the documented image builds and self-tests. Match validation to the change and distinguish automated checks from real-data, GUI, and hardware verification.
- Keep these instructions tracked. Codex's repository instruction format is documented in the [official AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
