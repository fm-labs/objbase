
## Development

Requires [uv](https://docs.astral.sh/uv/). Install the package with all
development dependencies (pinned in `uv.lock`):

```bash
uv sync
```

### Tests

```bash
uv run pytest
```

The Redis and MongoDB tests start containers via
[testcontainers](https://testcontainers.com/), so Docker must be running. Without
Docker, the shared contract tests skip those backends, but the Redis and MongoDB test
modules fail; exclude them to run everything else:

```bash
uv run pytest --ignore=tests/test_redis_storage.py --ignore=tests/test_async_redis_storage.py \
  --ignore=tests/test_mongodb_storage.py --ignore=tests/test_async_mongodb_storage.py
```

MongoDB tests use
`mongo:7.0`, because `mongo:latest` does not start on Linux kernels 6.19+ (as used by
recent Docker Desktop VMs). Override the image with `INVENTORYDB_TEST_MONGO_IMAGE`.

### Linting and formatting

[Ruff](https://docs.astral.sh/ruff/) checks for likely bugs, style issues, import
order and outdated syntax. The enabled rules are listed under `[tool.ruff.lint]` in
`pyproject.toml`.

```bash
uv run ruff check .        # report issues
uv run ruff check --fix .  # apply safe automatic fixes
```

Code is formatted with Ruff's formatter (line length 120, set under `[tool.ruff]`).
CI fails if any file is not formatted:

```bash
uv run ruff format .          # format all files
uv run ruff format --check .  # check only, as CI does
```

### Type checking

[mypy](https://mypy.readthedocs.io/) checks the library in strict mode (configured
under `[tool.mypy]` in `pyproject.toml`):

```bash
uv run mypy
```

Tests and examples are checked too, with rules for unannotated test functions
relaxed. They use the public API the way users do, so this catches annotations
that are correct internally but awkward for callers:

```bash
uv run mypy --allow-untyped-defs --allow-incomplete-defs --allow-untyped-calls tests examples
```

### Continuous integration

[GitHub Actions](.github/workflows/ci.yml) runs on every push to `main`, every
pull request, and as the first stage of every [release](#releasing):

| Job | What it does |
|---|---|
| Lint, format and type check | Ruff lint, Ruff format check, and the mypy commands above (the library is also checked as Windows sees it, with `--platform win32`) |
| Test | Full test suite on Python 3.13 and 3.14 |
| Test (Windows / macOS, no containers) | Test suite without the Redis and MongoDB tests, covering platform-specific code such as file locking |
| Test (minimum dependency versions) | Test suite with the lowest versions of `redis`, `pymongo` and `pydantic` allowed by `pyproject.toml` |
| Build distributions | Builds the sdist and wheel, and checks their metadata and contents |

Run the lint, format, type check and test commands above before pushing to catch
failures early.

[Dependabot](.github/dependabot.yml) checks weekly for updates and skips
releases less than a week old:

- **GitHub Actions:** all actions in both workflows are pinned to commit SHAs;
  one PR updates the SHAs and their version comments.
- **Python dependencies:** PRs that update `uv.lock`, one for the backend
  libraries (`redis`, `pymongo`, `pydantic`) and one for dev tools. The `>=`
  minimum versions in `pyproject.toml` are left unchanged.

### Releasing

Releases are published by the [release workflow](.github/workflows/release.yml)
when a tag starting with `v` is pushed. Bump the version, commit, then tag the
commit with the same version:

```bash
uv version 0.3.0
git commit -am "release 0.3.0"
git tag v0.3.0
git push origin main v0.3.0
```

The workflow then:

1. Checks that the tag matches the version in `pyproject.toml` (`v0.3.0` ↔ `0.3.0`) and fails otherwise.
2. Runs the full CI workflow.
3. Builds the sdist and wheel and checks their metadata.
4. Publishes to TestPyPI and checks that the new version installs from there.
   If either fails, nothing is published to PyPI.
5. Publishes to PyPI. Both uploads use
   [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API tokens are stored.
6. Creates a GitHub release for the tag with generated release notes and the
   distributions attached. Pre-release versions (`a`, `b`, `rc`, `.dev`) are
   marked as pre-releases.

One-time setup:

- On [PyPI](https://pypi.org), add a trusted publisher for the `fm-labs/objbase`
  repository with workflow `release.yml` and environment `pypi`.
- On [TestPyPI](https://test.pypi.org), add the same trusted publisher with
  environment `testpypi`.
- In the GitHub repository settings, create the `testpypi` and `pypi`
  environments. Add required reviewers to `pypi` to approve each release after
  the TestPyPI check and before it's published.

To publish from a local machine instead, `release.sh` refuses to run with
uncommitted changes, runs the tests, builds into a clean `dist/`, and publishes
to TestPyPI and/or PyPI depending on which of `TESTPYPI_PUBLISH_TOKEN` and
`PYPI_PUBLISH_TOKEN` are set.
