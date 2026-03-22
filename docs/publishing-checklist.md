# Before Publishing Checklist

Use this checklist before sharing the repository publicly or tagging a release.

## Product readiness

- [ ] Confirm the README reflects the current feature set, setup steps, and supported providers.
- [ ] Verify `.env` documentation is up to date and contains no secrets.
- [ ] Remove any debug-only files, local logs, or machine-specific artifacts from the branch.

## Quality gates

- [ ] Install development dependencies with `pip install -r requirements-dev.txt`.
- [ ] Run `python tests/verify_code_structure.py`.
- [ ] Run `pytest tests/test_prompt_assembler.py tests/test_memory_manager.py tests/test_ai_handler_task_dedupe.py -q`.
- [ ] Run `ruff check ai_handler.py app_context.py prompt storage tests`.
- [ ] Run `pre-commit run --all-files`.

## Runtime and deployment

- [ ] Build the Docker image locally with `docker build -t llmchatengine .`.
- [ ] Verify the GitHub Actions `CI` workflow passes on the branch.
- [ ] If publishing a release, verify the `Docker Image` workflow can publish to GHCR from `main` or a version tag.

## Final review

- [ ] Confirm commit history is clean and PR title/description describe the release accurately.
- [ ] Re-check branch protection or required checks in GitHub before merging.
- [ ] Tag the release only after CI, docs, and Docker verification are complete.
