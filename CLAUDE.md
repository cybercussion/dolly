# Dolly — Claude Code Rules

## After every change

1. **README.md** — If you add, remove, or change a feature, command, config option, or dependency, update `README.md` to match. This includes new Makefile targets, new camera integrations, changed setup steps, and new test scripts.

2. **Python syntax check** — Before considering any Python change complete, run:
   ```bash
   python3 -m py_compile <changed_file.py>
   ```
   Do this for every `.py` file you create or modify. Fix any syntax errors before moving on.

3. **requirements.txt** — If you add a new `import` for a third-party package (anything not in the Python standard library), add it to `requirements.txt`. If you remove the last usage of a package, remove it from `requirements.txt`. Keep the file sorted alphabetically.

4. **config.yaml.example** — If you add or change config options, keep `config.yaml.example` in sync so it serves as a working template.

## Code style

- **Type hints** on all function signatures. Use Python 3.10+ syntax (`Path | None`, `list[str]`).
- **Logging** — Use `_LOGGER = logging.getLogger(__name__)` per module. Never `print()` in library code (only in test scripts). Use `%` formatting in log calls for lazy evaluation.
- **Paths** — Use `pathlib.Path` throughout, not `os.path`. Resolve relative paths via `__file__`.
- **Async** — All public `CameraSource` methods are async. Wrap sync SDK calls with `loop.run_in_executor(None, ...)`. Use `aiohttp.ClientSession` for HTTP (lazy init, reuse). Never block in async code.
- **Dataclasses** for simple data containers. Mutable (no `frozen`). Use `field(default_factory=...)` for mutable defaults.
- **Imports** — Standard library first, then third-party, then local (PEP 8). Alias long imports when it helps readability.
- **F-strings** for general formatting; `%` formatting for logging.

## Error handling

- Entry points: catch specific exceptions (`FileNotFoundError`, `ValueError`), log, `sys.exit(1)`.
- Background tasks (poll loop): catch broad `Exception`, log with `_LOGGER.exception()`, continue.
- `RuntimeError` for expected failures (auth, API).
- Assertions for internal preconditions only (not user input).
- All async sources must cleanly close resources via `close()` and `try/finally`.

## Camera integrations

- All sources inherit from `CameraSource` ABC in `dolly/cameras/base.py`.
- Implement: `authenticate`, `refresh`, `list_cameras`, `get_new_events`, `save_snapshot`, `close`.
- Event dedup: each source manages its own `_seen_events: set[str]`. Trim when `> 500` to last 200.
- Register new sources in `dolly/config.py:build_sources()`.
- New camera file goes in `dolly/cameras/{brand}.py`.

## Testing

- Test scripts live in `tests/` as standalone executables — no pytest, no framework.
- Name tests simply: `tests/auth.py`, not `tests/test_auth.py`.
- Each script uses `asyncio.run(main())` and adds the project root to `sys.path`.
- Run with `python tests/<script>.py` directly.
- Debug APIs in isolation — don't use the daemon as a test runner.

## Naming

- Keep names simple. No redundant prefixes (`auth.py` not `test_auth.py`, `blink.py` not `camera_blink.py`).

## Makefile

- All targets must be listed in `.PHONY`.
- `run` target uses `.venv/bin/python` directly (no `source activate`).
- Any new target must be documented in the README under the Manage section.

## Security

- Never commit `config.yaml`, `blink.json`, or `.env` — these are in `.gitignore`.
- `config.yaml.example` is the tracked template (no real credentials).

## Logging configuration

- Default level: `INFO`.
- Suppress noisy third-party loggers (`wyze_sdk`, `blinkpy`) at `WARNING`.
- Format: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`.
