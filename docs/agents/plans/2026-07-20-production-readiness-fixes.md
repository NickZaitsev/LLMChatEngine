# Plan: Production readiness fixes (post-master-plan review)

Status: plan, 2026-07-20.

## Context

A full repo review was performed on 2026-07-20, after the master refactoring/RAG plan (`docs/plans/master-plan.md`) was completed (audit in that file marks all Part 1, Part 2, and Workstream A items `[done]`, 240 tests passing). The application code itself is in good shape: async Redis, token resolution at delivery boundary, typed `AppSettings`, `ServiceContainer` composition root, privacy-safe logging, Alembic migrations, deterministic test suite.

The remaining production gaps are almost entirely in the **deployment surface** (docker-compose, CI, logging config) and a few **delivery-resilience** details. This plan lists them in priority order. Several items are direct violations of the repo's own rules in `AGENTS.md` (secret scoping per service, pinned image tags, prefixed volumes/networks, no dev patterns in production compose, bounded exponential backoff for transient failures).

## Approved decisions

Defaults chosen per `AGENTS.md` rules and reviewer judgment; none required user input beyond the original "make it production ready" request:

1. Fix compose in place (no separate `docker-compose.prod.yml`); if a dev override is ever needed, it goes into `docker-compose.override.yml` later.
2. Redis stays password-less on the internal network (no host ports are published); adding Redis AUTH is out of scope.
3. No monitoring/metrics/tracing stack is added (YAGNI rule) — only log-level configurability and Docker log rotation.
4. CI is fixed by installing `requirements-dev.txt` alongside the lock file, not by adding dev tools to the lock file.

## Key codebase facts

- `docker-compose.yml`: `celery-worker` (line 93), `celery-beat` (line 118), `celery-memory` (line 144) bind-mount `.:/app` over the built image — a dev pattern; it defeats the image's `chown bot:bot` and means running code differs from the built artifact.
- `docker-compose.yml`: every app service has `env_file: .env` (lines 7, 81, 108, 133), giving each container the entire `.env` including secrets it doesn't need; explicit `environment:` entries duplicate some of the same variables (violates the AGENTS.md secret-scoping rule).
- `docker-compose.yml:62`: `redis:alpine` is an unpinned floating tag (`pgvector/pgvector:pg15` and `postgres:15` in `backup/Dockerfile` are pinned).
- `docker-compose.yml` volumes (`postgres_data`, `backups`, `redis_data`, `celery_beat_schedule`, `celery_worker_state`, `book_files`) and network (`backup_network`) have no project prefix (AGENTS.md rule).
- Migrations run only inside the app container command: `bash -c "alembic upgrade head && python run_multibot.py"` (`docker-compose.yml:6`). Celery services depend only on `postgres: service_healthy`, so on a fresh deploy workers can start before tables exist.
- No `logging:` limits are configured for any service — the default `json-file` driver grows unbounded.
- `run_multibot.py:20-23` hardcodes `logging.basicConfig(level=logging.INFO)`; no `LOG_LEVEL` env var exists anywhere in the project (verified by grep).
- `.github/workflows/ci.yml` installs **only** `requirements-lock.txt`, then runs `ruff check .` and `pytest -q`. Neither `ruff` nor `pytest` is present in `requirements-lock.txt` (verified by grep; they live in `requirements-dev.txt` / `requirements.txt`). CI is therefore broken or accidentally relying on stale caches.
- `pytest==8.4.2` and `pytest-asyncio==1.2.0` are pinned in the **runtime** `requirements.txt` (lines 9-10) and thus shipped inside the production image.
- `pyproject.toml` ruff config selects only `E9, F63, F7, F82` (syntax-level checks); `mypy` config exists but mypy is not run in CI.
- `messaging/dispatcher.py:663-674`: failed sends are requeued atomically (`requeue_script`) with `retry_count` bounded by `max_retries`, but with **no delay/backoff** — an immediate retry loop. No handler distinguishes `telegram.error.RetryAfter` (flood control, carries `retry_after` seconds), `TimedOut`, or `NetworkError` (verified: no such imports in `messaging/` or `bot.py`).
- `backup/Dockerfile` healthcheck only asserts `crontab -l` succeeds — it never verifies a recent backup file exists. `backup/backup_db.sh` keeps 14 days of dumps; there is no documented restore procedure.
- README.md and `docs/architecture.md` / `docs/user-identity.md` are in English; AGENTS.md requires README/docs in Russian (`docs/persona-bots.md` already is).
- `message_manager.py` is a re-export shim over the `messaging/` package, kept "for one release" per master plan.
- Plans live in `docs/agents/plans/` per AGENTS.md; the old master plan predates this rule and stays at `docs/plans/master-plan.md`.

## Implementation

### 1. Fix CI (highest priority — it likely fails right now)

Modify `.github/workflows/ci.yml`:
- Install step: `pip install -r requirements-lock.txt -r requirements-dev.txt`.
- Add a step running `mypy` on the packages already covered by the master-plan audit (`mypy messaging message_manager.py --ignore-missing-imports`) so the existing type guarantees don't rot. Do not widen mypy scope in this plan.

Move `pytest` / `pytest-asyncio` / `aiosqlite` out of `requirements.txt` into `requirements-dev.txt` (keep versions), regenerate `requirements-lock.txt` accordingly, and rebuild the Docker image to confirm the app still starts without them (`conftest.py` is not imported at runtime). This shrinks the production image and makes the lock file purely runtime.

Verification: CI green on a branch push; `docker compose build` succeeds; `docker compose config` unchanged semantically.

### 2. Production-grade docker-compose.yml

All edits in `docker-compose.yml` (and `env_example.txt` where new vars appear):

1. **Remove `.:/app` bind mounts** from `celery-worker`, `celery-beat`, `celery-memory`. Keep the named volumes (`celery_worker_state`, `celery_beat_schedule`, `book_files`). Code comes from the image only.
2. **Scope secrets per service — drop `env_file: .env` everywhere.** Enumerate explicitly in `environment:` what each service needs:
   - `llm-chat-engine`: `DATABASE_URL`, `REDIS_URL`, `TOKEN_ENCRYPTION_KEY`, `ADMIN_BOT_TOKEN`, `ADMIN_USER_IDS`, LLM provider vars (`AZURE_OPENAI_*` / `GEMINI_API_KEY` / `LMSTUDIO_*`), plus any tuning vars actually read by `AppSettings` at runtime (source them as `${VAR:-default}` from `.env`).
   - `celery-worker` (proactive): `DATABASE_URL`, `REDIS_URL`, `TOKEN_ENCRYPTION_KEY`, LLM provider vars, `PYTHONPATH`.
   - `celery-memory`: `DATABASE_URL`, `REDIS_URL`, embedding provider vars, `PYTHONPATH`; keeps `book_files` volume.
   - `celery-beat`: `REDIS_URL` only (the scheduler does not touch DB or tokens — verify against `celeryconfig.py` before removing `DATABASE_URL`; if beat imports app modules that require settings at import time, keep the minimal set that `AppSettings` validation demands).
   - `postgres-backup`: `DB_PASSWORD` only (already correct).
   Compose still reads `.env` at the top level for `${VAR}` interpolation — that file never enters containers wholesale.
3. **Pin Redis**: `redis:7.4-alpine` (match the `redis==7.0.0` client's supported server line; verify actual current 7.x tag at implementation time).
4. **Prefix volumes and network** with the project name: `llmchatengine_postgres_data`, `llmchatengine_backups`, `llmchatengine_redis_data`, `llmchatengine_celery_beat_schedule`, `llmchatengine_celery_worker_state`, `llmchatengine_book_files`, network `llmchatengine_network`. Migration note for the operator (README deploy section): either set `name:` on each volume to the old name to keep data, or document a one-time `docker volume` copy. **Prefer `name:` aliases to the existing volume names to avoid any data migration** — i.e. keep physical names, prefix only the compose-level keys, OR (cleaner) add explicit `name: llmchatengine_*` and document the copy. Decide at implementation time based on whether a production deployment already exists; default to keeping physical names via `name:`.
5. **Migration ordering**: add a dedicated one-shot `migrate` service (`command: alembic upgrade head`, `restart: "no"`, same image/env as the app) and make `llm-chat-engine`, `celery-worker`, `celery-memory` use `depends_on: migrate: condition: service_completed_successfully` (plus existing healthy conditions). Remove `alembic upgrade head &&` from the app command.
6. **Log rotation**: add to every service
   ```yaml
   logging:
     driver: json-file
     options: { max-size: "50m", max-file: "3" }
   ```
   (or a top-level `x-logging: &logging` anchor referenced by all services).
7. Keep: no published host ports for Postgres/Redis, healthchecks, `restart: unless-stopped`.

Verification: `docker compose config` valid; full stack boots from scratch (`docker compose down -v && up`) with migrations completing before workers; each container's `env` (`docker compose exec <svc> env`) contains only its scoped variables.

### 3. Configurable log level

- Add `LOG_LEVEL: str = "INFO"` to `AppSettings` (top level in `settings.py`, with a validator restricting to standard level names).
- `run_multibot.py` (and `bot.py` single-bot path if it configures logging): read the level via `os.getenv("LOG_LEVEL", "INFO")` **before** heavy imports, pass to `basicConfig`. Keep format unchanged.
- Add `LOG_LEVEL` to `env_example.txt` (note: `tests/test_env_example.py` asserts the file matches `AppSettings.model_fields` — adding it to settings keeps that test consistent; run it).

### 4. Telegram flood-control and transient-error handling in delivery

In `messaging/dispatcher.py` where the send failure is caught and requeued (`~line 663`):

- Import `telegram.error.RetryAfter, TimedOut, NetworkError, Forbidden, BadRequest`.
- **`RetryAfter`**: sleep `e.retry_after + 1` seconds (bounded, per-route — it already runs inside the per-user task so it doesn't block other users), then requeue **without** incrementing `retry_count` (flood control is not a delivery failure).
- **`TimedOut` / `NetworkError`**: requeue as today, but add a bounded exponential backoff delay before the requeue becomes deliverable: simplest correct approach is `await asyncio.sleep(min(2 ** retry_count, 30))` before calling `requeue_script` (the per-user task already isolates this delay; do not build a delayed-queue mechanism — YAGNI).
- **`Forbidden` (user blocked the bot) / `BadRequest`**: do NOT retry (deterministic 4xx per repo rule); log at WARNING and drop the message.
- Everything else: current generic path (bounded `max_retries` requeue).

Tests: extend the existing dispatcher test module (`tests/test_message_security.py` / `tests/test_message_ordering.py` style, fake bot client) — one test per branch: RetryAfter sleeps and does not increment retry_count; Forbidden drops without requeue; NetworkError requeues with backoff and respects `max_retries`.

### 5. Backup verification and restore procedure

- `backup/backup_db.sh`: after a successful dump, `gzip -t "$BACKUP_FILE"` and write a `/backups/last_success` timestamp file.
- `backup/Dockerfile` healthcheck: replace `crontab -l` with a check that `/backups/last_success` exists and is newer than 26 hours (`find /backups/last_success -mmin -1560 | grep -q .`); keep the crontab check as a secondary condition. Note: healthcheck will be unhealthy for the first day after a fresh deploy — run the backup once at container start (`CMD ["bash", "-c", "/usr/local/bin/backup_db.sh && cron -f"]`) to avoid that.
- Document the restore procedure in README (Russian): `gunzip -c backup.sql.gz | docker compose exec -T postgres psql -U ai_bot -d ai_bot`, plus the pgvector-extension caveat (init script runs only on empty data dir).

### 6. Documentation language and shim retirement (low priority, mechanical)

- Translate `README.md` to Russian (AGENTS.md rule). Keep code identifiers/commands as-is. `docs/architecture.md` and `docs/user-identity.md` likewise.
- Delete the `message_manager.py` re-export shim: grep for `from message_manager import` / `import message_manager` outside tests, migrate any stragglers to `messaging.*`, update `tests/test_messaging_package.py` (it currently asserts shim compatibility — repurpose it to assert the shim is gone or delete it), remove the file.

### Explicitly reviewed and NOT changed (rationale on record)

- **Redis AUTH**: network is internal-only, no host ports; adding a password would touch every client and the compose file for marginal gain. Revisit only if the network topology changes.
- **`token_encryption.py` SHA256-derived Fernet key**: acceptable for a symmetric secret sourced from env; a KDF (scrypt/HKDF) adds no security when the input is already a high-entropy generated key, and changing derivation would invalidate all stored tokens. Document in `env_example.txt` that the key must be generated (`Fernet.generate_key()`), not a human passphrase — one comment line, no code change.
- **Monitoring/metrics/healthcheck endpoint for the bot container**: the bot is a Telegram long-poller with no HTTP surface; adding one is new infrastructure (YAGNI rule — propose separately if wanted).
- **Broadening ruff rule selection**: current `E9/F63/F7/F82` is deliberate; widening produces a large mechanical diff unrelated to production readiness.
- **`dns: 8.8.8.8` entries in compose**: deployment-environment-specific (host DNS issues); leave as is.

## Testing & verification

- Run the full suite after each step: `python -m pytest -q` (must stay at ≥240 passed), `ruff check .`, `mypy messaging message_manager.py --ignore-missing-imports` (until step 6 removes the shim).
- Step 1: push a branch, confirm the CI workflow is green end-to-end.
- Step 2: `docker compose down -v && docker compose up --build` on a clean machine/VM: migrations run first, all services healthy, a test bot responds; `docker compose exec celery-beat env | grep TOKEN_ENCRYPTION_KEY` returns nothing.
- Step 4: new dispatcher unit tests with a fake Telegram client raising each error class; no real network calls.
- Step 5: exec into the backup container, run `/usr/local/bin/backup_db.sh` manually, confirm `last_success` and a valid gzip; perform one real restore into a scratch database and diff table counts.
- Never call paid external APIs from tests (existing suite is already deterministic — keep it that way).

## Out of scope

- Monitoring, metrics, tracing, alerting, admin web panels.
- Redis AUTH / TLS anywhere.
- Kubernetes or any orchestrator beyond docker-compose.
- Webhook mode for Telegram (long polling stays).
- Re-keying / rotation tooling for `TOKEN_ENCRYPTION_KEY`.
- Widening mypy/ruff coverage beyond what CI already implies.
- Any changes to prompt assembly, memory, book RAG, or storage schemas.

---
**Maintenance note (for the implementing agent):** when this plan is implemented, update the `Status:` line above, e.g. `Status: implemented YYYY-MM-DD in branch `<branch>``. If the plan changes during implementation, update the affected sections too — the plan must not lie about what was built.
