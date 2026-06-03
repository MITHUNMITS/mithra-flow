# mithra-flow v1.0.1

Maintenance release focused on CI stability, packaging polish, and async tracing compatibility.

## Fixed

- Improved async coroutine suspension detection across Python versions.
- Filtered dependency/library frames by default so traces stay focused on code under the project root.
- Automatically detects the project root from the decorated function file, so plain `@mflow` is usually enough.
- Fixed CI support matrix by targeting Python 3.10+.
- Updated GitHub Actions runtime versions to avoid Node.js 20 deprecation warnings.

## Changed

- Package versioning now comes from Git tags via `hatch-vcs`.
- Release flow is simpler: create a GitHub Release tag like `v1.0.1` to publish PyPI version `1.0.1`.
- Added project polish files: changelog, MIT license, CI workflow, README badges, and package metadata.

## Default Trace Scope

By default, `mithra-flow` detects the project root from the decorated function file, traces project code only, and ignores dependency folders such as `.venv`, `venv`, `site-packages`, `dist-packages`, and `__pypackages__`.

To trace dependency/library internals, opt in explicitly:

```python
@mflow(trace_dependencies=True)
def parent():
    ...
```

## Verified

- Test suite passes locally.
- Package build validated.

## GitHub Release Fields

Tag:

```text
v1.0.1
```

Title:

```text
mithra-flow v1.0.1
```
