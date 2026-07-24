# Gemini Gateway Local Deployment Implementation Plan

Status: completed, 2026-07-24.

**Goal:** Run LLMChatEngine locally with its PostgreSQL/Redis/Celery stack and route Gemini chat generation through the shared `gemini-gateway` package.

**Architecture:** Keep the existing direct `gemini` provider for compatibility and add an explicit `gemini_gateway` provider backed by the published shared package. Convert chat messages to deterministic JSON at the provider boundary, while the gateway owns Gemini client creation, rate limiting, key rotation, retries, and output-token limits. Docker Compose passes only the Gemini gateway settings needed by each service; local secrets stay in an ignored `.env` copied from the existing local deployment without changing their values.

**Tech Stack:** Python 3.11, pytest, Pydantic Settings, gemini-gateway, Docker Compose, PostgreSQL/pgvector, Redis, Celery.

---

### Task 1: Define gateway provider behavior with failing tests

**Files:**
- Create: `tests/test_gemini_gateway_provider.py`
- Modify: `tests/test_app_settings.py`

**Steps:**
1. Add a test that constructs `ModelClient(provider="gemini_gateway")` with an injected fake gateway and verifies system/user/assistant messages are serialized as deterministic JSON.
2. Verify the gateway receives temperature and max-output-token overrides and its returned text is passed through unchanged.
3. Add settings tests for provider recognition and gateway configuration grouping.
4. Run targeted tests and confirm they fail because gateway support does not exist.

### Task 2: Implement the provider and configuration

**Files:**
- Modify: `settings.py`
- Modify: `config.py`
- Modify: `ai_handler.py`
- Modify: `env_example.txt`
- Modify: `docker-compose.yml`

**Steps:**
1. Add typed gateway settings for multiple keys, quota limits, timeout, and bounded retry controls.
2. Import the gateway optionally and construct it only for the `gemini_gateway` provider.
3. Serialize messages without logging prompts or secrets and call `generate_text` with model generation overrides.
4. Pass gateway variables only to services that invoke Gemini.
5. Run targeted tests until green, then run settings/environment tests.

### Task 3: Pin dependencies and document the workflow

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-lock.txt`
- Modify: `README.md`

**Steps:**
1. Add a pinned compatible `gemini-gateway` dependency.
2. Regenerate the universal lock file with the repository's documented uv command.
3. Document `PROVIDER=gemini_gateway`, multi-key configuration, and local Compose startup in Russian.

### Task 4: Configure and start locally

**Files:**
- Create local ignored file: `.env`

**Steps:**
1. Reuse the existing local LLMChatEngine-compatible secrets without rotating or printing them.
2. Generate only missing non-provider infrastructure values (for example a new database password) without changing source credentials.
3. Set `PROVIDER=gemini_gateway`; preserve the existing working LM Studio embedding configuration.
4. Build and start Docker Compose.

### Task 5: Verification and commit

**Steps:**
1. Run `python -m ruff check .`, formatting check, pyright/mypy as configured, and the full pytest suite.
2. Verify Compose config, migration completion, PostgreSQL/Redis health, and every long-running container state.
3. Execute a real one-shot Gemini Gateway request from the built application image without exposing the key or prompt.
4. Verify the admin bot process remains running and inspect sanitized logs.
5. Commit all tracked changes atomically with a Conventional Commit in the repository's required language format.
6. Confirm the worktree is clean except for the intentionally ignored `.env`.

## Outcome

- Added the `gemini_gateway` provider and verified a real response both on the host and inside the application container.
- Made the legacy migration chain safe for a canonical fresh database.
- Enforced Unix line endings for shell scripts and verified an immediate PostgreSQL backup.
- Started the full local Compose stack successfully.
