# mithra-flow v1.0.1

Maintenance release focused on CI stability, packaging polish, and async tracing compatibility.

## Fixed

- Improved async coroutine suspension detection across Python versions.
- Fixed CI support matrix by targeting Python 3.10+.
- Updated GitHub Actions runtime versions to avoid Node.js 20 deprecation warnings.

## Changed

- Package versioning now comes from Git tags via `hatch-vcs`.
- Release flow is simpler: create a GitHub Release tag like `v1.0.1` to publish PyPI version `1.0.1`.
- Added project polish files: changelog, MIT license, CI workflow, README badges, and package metadata.

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
