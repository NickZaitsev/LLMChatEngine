# General rules

Write README.md, documentation, MRs and UI text in Russian.
Target production-ready quality: no quick hacks, temporary workarounds, or fragile solutions unless explicitly requested.

Only spawn subagents when I ask you to.

## Commits and branches

- Commit completed work yourself when a task or phase is finished
- Before every commit, run the project's existing lint, type-check, and test commands. If no such tooling is configured, use the following defaults:
Python: before finishing, run uv run ruff check . && uv run pyright; if tests are configured, also run uv run pytest. Fix all errors caused by your changes.
TypeScript: before finishing, run `npm run check` when available. Otherwise, run the project's existing lint and type-check scripts plus relevant tests. If `typecheck` is missing, add `"typecheck": "tsc --noEmit"`. Fix all errors caused by your changes.
- Commit messages and MR titles follow Git Atomic Conventional Commits: keep the type and scope in English (`feat(auth):`, `fix(db):`), write the description after the colon in Russian — e.g. `feat(consent): интегрировать Яндекс.Метрику`.
- Commit completed work yourself when a task or phase is finished — atomic conventional commits.
- Maintain .gitignore yourself: add generated, local, temporary, cache, build, and environment files as they appear.
- In the Bash tool, pass multi-line commit messages via `-m` with a regular double-quoted string (or heredoc), NOT PowerShell `@'...'@` syntax — the `@` leaks into the message text.
- Do not create new branches without explicit user confirmation. Work in the current branch; сreate a branch only on explicit request.

## Tests and completion

- Add or update tests for changed behavior. Run the relevant test scope when a change could affect behavior; run the full suite for broad, cross-cutting, risky, or release-level changes. Trivial non-behavioral edits (docs, comments, formatting, isolated constants) may skip tests.
- A task is "Done" only when tests pass and the change is verified end-to-end.

## YAGNI

- Do not add infrastructure or integrations nobody asked for (monitoring, metrics, tracing, admin panels). Propose first; add only after explicit approval.
- Do not relax security checks "just in case" (e.g. leeway/clock-skew tolerance in token validation). Strict validation is the default; loosening it requires an explicit request.
- Do not set arbitrary resource limits (memory/cpu) without a measured justification.

## Error handling

- Retry transient failures (network, 5xx, 429, timeouts) with bounded exponential backoff; no retries for deterministic 4xx/logic errors. Surface errors with clear context and clean up resources. Keep it proportional — don't wrap every line in try/catch.

## Secrets

- Never commit secrets or .env files; never print secrets to logs, error messages, events, or API responses.

## Docker and Compose (when the project uses them)

- Use `npm ci` (lockfile-driven), not `npm install`. Pin base image tags (`nginx:1.27-alpine`, not `nginx:latest`). No dev servers (`npm run dev`, `--reload`) in production images — dev mode lives only in the compose dev override.
- Use multi-stage builds only when the runtime image is actually lighter than the builder; otherwise use a single stage.
- Do not hardcode ports — take them from env with a default (`"${API_PORT:-8000}:${BACKEND_PORT:-8000}"`), including internal ports (CMD, healthchecks).
- Prefix volumes and networks with the project name so ownership is obvious and collisions are impossible.
- Configuration comes from env files, without duplicating variables across `args` and `environment`. Scope secrets per service: a container gets only its own variables, never the whole `.env`.

# Implementation plans

- Implementation plans (features, refactors, migrations — any task) live in `docs/agents/plans/YYYY-MM-DD-<kebab-case-slug>.md` (date = creation date), written in English (create via the `make-plan` skill).
- Every plan has a `Status:` line right under the H1: `Status: plan, YYYY-MM-DD.` → after implementation `Status: implemented YYYY-MM-DD in branch \`feat/<name>\`.` (also: `in progress`, `rejected — <reason>`).
- When you implement a plan from `docs/agents/plans/`, updating its `Status:` line is part of "Done" — and if the implementation diverged from the plan, correct the affected sections so the plan doesn't lie.

# Gotchas and observations

While working, record observations in docs/agents/ folder. Before finishing a task, ask: "would the next agent working here make a mistake without knowing this AND it is important enough?" If yes, add it to AGENTS.md as a bullet of at most two lines; if two lines are not enough, put the full write-up in docs/agents/<topic>.md and link it from here. Everything else stays only in docs/agents/ folder.

Do not add trivial, obvious, stylistic, temporary, or low-impact notes to AGENTS.md. Keep those only in docs/agents/ .
