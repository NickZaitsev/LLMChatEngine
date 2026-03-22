# Contributing

Thanks for contributing to **LLMChatEngine**.

## Local setup

1. Create a virtual environment.
2. Install development dependencies:

   ```bash
   pip install -r requirements-dev.txt
   ```

3. Copy the example environment file if you need to run the app locally:

   ```bash
   cp env_example.txt .env
   ```

## Recommended quality workflow

Run the same focused checks that the GitHub Actions workflow uses before opening a PR:

```bash
python tests/verify_code_structure.py
pytest tests/test_prompt_assembler.py tests/test_memory_manager.py tests/test_ai_handler_task_dedupe.py -q
ruff check ai_handler.py app_context.py prompt storage tests
```

To enable automated formatting and lint fixes on commit:

```bash
pre-commit install
```

## Pull request expectations

- Keep runtime dependency changes in `requirements.txt`.
- Keep developer-only tooling in `requirements-dev.txt`.
- Update `README.md` or `docs/publishing-checklist.md` when release or publishing steps change.
- Prefer adding or updating tests when behavior changes.
