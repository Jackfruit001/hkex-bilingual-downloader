# Testing

Filled in as tests are written. Built from the requirements table in `docs/SPEC.md` section 2.

## Run the tests

```
cd backend
uv run pytest              # offline tests (default)
uv run pytest -m live      # opt-in live HKEXnews smoke tests
uv run ruff check . && uv run mypy
```
