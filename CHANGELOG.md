# Changelog

All notable changes to `mithra-flow` are documented here.

This project follows tag-based releases. A Git tag like `v1.0.1` publishes PyPI version `1.0.1`.

## 1.0

Initial public release.

Added:

- `@mflow` decorator for sync and async functions.
- Nested child-call tracing with `sys.setprofile`.
- Per-trace isolation with `contextvars`.
- Rich terminal tree output with duration timing.
- Include/exclude filters.
- Custom trace titles.
- Duration and depth filtering.
- Argument, return value, file, and line display options.
- Error-only tracing.
- Dict, JSON, and Mermaid outputs.
- Trace saving with `save_to`.
- `MFlowResult` return wrapper with `return_trace=True`.
- `trace(...)` context manager.
- `span(...)` manual spans.
- FastAPI feature examples.
- GitHub Actions publishing to PyPI with trusted publishing.
