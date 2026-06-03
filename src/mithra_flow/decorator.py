from __future__ import annotations

import contextvars
import dis
import fnmatch
import functools
import inspect
import json
import os
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, Literal, TypeVar, overload

from rich.console import Console
from rich.text import Text
from rich.tree import Tree

from .models import TraceNode
from .version import __version__

F = TypeVar("F", bound=Callable[..., Any])
OutputFormat = Literal["terminal", "dict", "json", "mermaid", "none"]


@dataclass
class MFlowResult:
    value: Any
    trace: dict[str, Any] | str | None


@dataclass
class _TraceConfig:
    title: str | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    enabled: bool = True
    min_duration_ms: float = 0.0
    max_depth: int | None = None
    show_args: bool = False
    show_return: bool = False
    show_file: bool = False
    show_line: bool = False
    on_error: bool = False
    output: OutputFormat = "terminal"
    save_to: str | None = None
    return_trace: bool = False


@dataclass
class _TraceState:
    config: _TraceConfig
    stack: list[TraceNode] = field(default_factory=list)
    frame_nodes: dict[int, TraceNode] = field(default_factory=dict)
    root: TraceNode | None = None
    previous_profile: Callable[[FrameType, str, Any], Any] | None = None
    had_error: bool = False
    exported_trace: dict[str, Any] | str | None = None


_active_trace: contextvars.ContextVar[_TraceState | None] = contextvars.ContextVar(
    "mithra_flow_active_trace",
    default=None,
)


@overload
def mflow(func: F) -> F:
    ...


@overload
def mflow(
    *,
    name: str | None = None,
    title: str | None = None,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    enabled: bool | None = None,
    min_duration_ms: float = 0.0,
    max_depth: int | None = None,
    show_args: bool = False,
    show_return: bool = False,
    show_file: bool = False,
    show_line: bool = False,
    on_error: bool = False,
    output: OutputFormat = "terminal",
    save_to: str | None = None,
    return_trace: bool = False,
) -> Callable[[F], F]:
    ...


def mflow(
    func: F | None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    enabled: bool | None = None,
    min_duration_ms: float = 0.0,
    max_depth: int | None = None,
    show_args: bool = False,
    show_return: bool = False,
    show_file: bool = False,
    show_line: bool = False,
    on_error: bool = False,
    output: OutputFormat = "terminal",
    save_to: str | None = None,
    return_trace: bool = False,
) -> F | Callable[[F], F]:
    """Trace project calls made while the decorated function executes."""

    config = _make_config(
        name=name,
        title=title,
        include=include,
        exclude=exclude,
        enabled=enabled,
        min_duration_ms=min_duration_ms,
        max_depth=max_depth,
        show_args=show_args,
        show_return=show_return,
        show_file=show_file,
        show_line=show_line,
        on_error=on_error,
        output=output,
        save_to=save_to,
        return_trace=return_trace,
    )

    def decorate(target: F) -> F:
        if inspect.iscoroutinefunction(target):

            @functools.wraps(target)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not config.enabled:
                    return await target(*args, **kwargs)
                state, token = _start_trace(config)
                try:
                    value = await target(*args, **kwargs)
                    _finish_trace(state)
                    return _return_value(value, state)
                except Exception as error:
                    _mark_error(state, error)
                    _finish_trace(state)
                    raise
                finally:
                    _active_trace.reset(token)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(target)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not config.enabled:
                return target(*args, **kwargs)
            state, token = _start_trace(config)
            try:
                value = target(*args, **kwargs)
                _finish_trace(state)
                return _return_value(value, state)
            except Exception as error:
                _mark_error(state, error)
                _finish_trace(state)
                raise
            finally:
                _active_trace.reset(token)

        return sync_wrapper  # type: ignore[return-value]

    if func is None:
        return decorate

    return decorate(func)


class trace:
    def __init__(
        self,
        name: str = "manual trace",
        *,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
        enabled: bool | None = None,
        min_duration_ms: float = 0.0,
        max_depth: int | None = None,
        show_args: bool = False,
        show_return: bool = False,
        show_file: bool = False,
        show_line: bool = False,
        on_error: bool = False,
        output: OutputFormat = "terminal",
        save_to: str | None = None,
        return_trace: bool = False,
    ) -> None:
        self.config = _make_config(
            name=name,
            title=name,
            include=include,
            exclude=exclude,
            enabled=enabled,
            min_duration_ms=min_duration_ms,
            max_depth=max_depth,
            show_args=show_args,
            show_return=show_return,
            show_file=show_file,
            show_line=show_line,
            on_error=on_error,
            output=output,
            save_to=save_to,
            return_trace=return_trace,
        )
        self.state: _TraceState | None = None
        self.token: contextvars.Token[_TraceState | None] | None = None
        self.result: dict[str, Any] | str | None = None

    def __enter__(self) -> trace:
        if self.config.enabled:
            self.state, self.token = _start_trace(self.config, root_name=self.config.title)
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> None:
        if self.state is None or self.token is None:
            return
        if exc is not None:
            _mark_error(self.state, exc)
        _finish_trace(self.state)
        self.result = self.state.exported_trace
        _active_trace.reset(self.token)


class span:
    def __init__(self, name: str) -> None:
        self.name = name
        self.node: TraceNode | None = None

    def __enter__(self) -> span:
        state = _active_trace.get()
        if state is None:
            return self
        now = time.perf_counter()
        self.node = TraceNode(
            name=f"{self.name}()",
            filename="<manual>",
            lineno=0,
            start=now,
            is_span=True,
        )
        if state.stack:
            state.stack[-1].children.append(self.node)
        elif state.root is None:
            state.root = self.node
        state.stack.append(self.node)
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> None:
        state = _active_trace.get()
        if state is None or self.node is None:
            return
        if exc is not None:
            self.node.exception = f"{type(exc).__name__}: {exc}"
            state.had_error = True
        self.node.end = time.perf_counter()
        if state.stack and state.stack[-1] is self.node:
            state.stack.pop()


def _make_config(
    *,
    name: str | None,
    title: str | None,
    include: Iterable[str] | None,
    exclude: Iterable[str] | None,
    enabled: bool | None,
    min_duration_ms: float,
    max_depth: int | None,
    show_args: bool,
    show_return: bool,
    show_file: bool,
    show_line: bool,
    on_error: bool,
    output: OutputFormat,
    save_to: str | None,
    return_trace: bool,
) -> _TraceConfig:
    env_enabled = os.getenv("MITHRA_FLOW", "1").lower() not in {"0", "false", "no", "off"}
    return _TraceConfig(
        title=title or name,
        include=_normalize_filters(include),
        exclude=_normalize_filters(exclude),
        enabled=env_enabled if enabled is None else enabled,
        min_duration_ms=max(0.0, min_duration_ms),
        max_depth=max_depth,
        show_args=show_args,
        show_return=show_return,
        show_file=show_file,
        show_line=show_line,
        on_error=on_error,
        output=output,
        save_to=save_to,
        return_trace=return_trace,
    )


def _normalize_filters(filters: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in filters or () if str(item))


def _start_trace(
    config: _TraceConfig,
    *,
    root_name: str | None = None,
) -> tuple[_TraceState, contextvars.Token[_TraceState | None]]:
    state = _TraceState(config=config)
    token = _active_trace.set(state)
    if root_name is not None:
        now = time.perf_counter()
        root = TraceNode(root_name, "<manual>", 0, now, is_span=True)
        state.root = root
        state.stack.append(root)
    _install_profile(state)
    return state, token


def _install_profile(state: _TraceState) -> None:
    state.previous_profile = sys.getprofile()
    sys.setprofile(_profile)


def _finish_trace(state: _TraceState) -> None:
    sys.setprofile(state.previous_profile)
    now = time.perf_counter()
    while state.stack:
        node = state.stack.pop()
        if node.end is None:
            node.end = now
    if state.root is None:
        return
    state.exported_trace = _export_trace(state)
    _save_trace(state)
    if state.config.on_error and not state.had_error:
        return
    if state.config.output == "terminal":
        _print_trace(state.root, state.config)


def _return_value(value: Any, state: _TraceState) -> Any:
    if state.config.return_trace:
        return MFlowResult(value=value, trace=state.exported_trace)
    if state.config.output == "dict":
        return state.exported_trace
    if state.config.output in {"json", "mermaid"}:
        return state.exported_trace
    return value


def _profile(frame: FrameType, event: str, arg: Any) -> None:
    state = _active_trace.get()
    if state is None:
        return

    if event == "call":
        _handle_call(state, frame)
        return

    if event == "return":
        _handle_return(state, frame, arg)


def _handle_call(state: _TraceState, frame: FrameType) -> None:
    if not _should_trace_frame(state, frame):
        return

    frame_id = id(frame)
    if frame_id in state.frame_nodes:
        state.stack.append(state.frame_nodes[frame_id])
        return

    code = frame.f_code
    node = TraceNode(
        name=f"{code.co_name}()",
        filename=os.path.abspath(code.co_filename),
        lineno=code.co_firstlineno,
        start=time.perf_counter(),
        args=_format_args(frame) if state.config.show_args else None,
    )

    if state.stack:
        state.stack[-1].children.append(node)
    elif state.root is None:
        state.root = node
    else:
        return

    state.stack.append(node)
    state.frame_nodes[frame_id] = node


def _handle_return(state: _TraceState, frame: FrameType, arg: Any) -> None:
    if not state.stack:
        return

    code = frame.f_code
    if state.stack[-1].filename != os.path.abspath(code.co_filename):
        return
    if state.stack[-1].lineno != code.co_firstlineno:
        return
    if state.stack[-1].name != f"{code.co_name}()":
        return

    if _is_coroutine_suspension(frame):
        state.stack.pop()
        return

    node = state.stack[-1]
    if state.config.show_return:
        node.return_value = _safe_repr(arg)
    node.end = time.perf_counter()
    state.stack.pop()
    state.frame_nodes.pop(id(frame), None)


def _mark_error(state: _TraceState, error: BaseException) -> None:
    state.had_error = True
    message = f"{type(error).__name__}: {error}"
    if state.stack:
        state.stack[-1].exception = message
    elif state.root is not None:
        state.root.exception = message


def _should_trace_frame(state: _TraceState, frame: FrameType) -> bool:
    filename = os.path.abspath(frame.f_code.co_filename)
    module = frame.f_globals.get("__name__", "")
    target = f"{module}:{frame.f_code.co_name}:{filename}"

    if _matches(target, state.config.exclude):
        return False

    if state.config.include:
        return _matches(target, state.config.include)

    return not _is_external_frame(filename)


def _matches(value: str, filters: tuple[str, ...]) -> bool:
    return any(item in value or fnmatch.fnmatch(value, item) for item in filters)


def _is_external_frame(filename: str) -> bool:
    if filename.startswith("<"):
        return True

    cwd = os.path.abspath(os.getcwd())
    return not os.path.abspath(filename).startswith(cwd + os.sep)


def _is_coroutine_suspension(frame: FrameType) -> bool:
    if not frame.f_code.co_flags & inspect.CO_COROUTINE:
        return False
    if frame.f_lasti < 0 or frame.f_lasti >= len(frame.f_code.co_code):
        return False
    return dis.opname[frame.f_code.co_code[frame.f_lasti]] == "YIELD_VALUE"


def _print_trace(root: TraceNode, config: _TraceConfig) -> None:
    console = Console()
    banner = _banner(config.title)
    console.print()
    console.print(Text(banner, style="dim bold cyan"))
    tree = Tree(_format_node(root, config, depth=0), guide_style="bold bright_blue")
    _append_children(tree, root, config, depth=1)
    console.print(tree)
    console.print(Text("─" * len(banner), style="dim cyan"))
    console.print()


def _banner(title: str | None = None) -> str:
    label = title or "MITHRA FLOW"
    text = f"{label}  v{__version__}"
    width = max(36, len(text) + 4)
    side = max(1, (width - len(text) - 2) // 2)
    line = "─" * side
    banner = f"{line} {text} {line}"
    if len(banner) < width:
        banner += "─" * (width - len(banner))
    return banner


def _append_children(tree: Tree, node: TraceNode, config: _TraceConfig, depth: int) -> None:
    if config.max_depth is not None and depth > config.max_depth:
        return
    for child in node.children:
        if not _should_show_node(child, config, depth):
            continue
        branch = tree.add(_format_node(child, config, depth=depth), guide_style=_level_style(depth))
        _append_children(branch, child, config, depth=depth + 1)


def _should_show_node(node: TraceNode, config: _TraceConfig, depth: int) -> bool:
    if config.max_depth is not None and depth > config.max_depth:
        return False
    if node.exception:
        return True
    if node.duration_ms >= config.min_duration_ms:
        return True
    return any(_should_show_node(child, config, depth + 1) for child in node.children)


def _format_node(node: TraceNode, config: _TraceConfig, depth: int) -> Text:
    level_style = "red" if node.exception else _level_style(depth)
    label = Text()
    label.append("◆ " if node.is_span else "● ", style=level_style)
    label.append(node.name, style=f"bold {level_style}")
    if node.args:
        label.append(node.args, style="dim")
    label.append("  ")
    label.append(f"{node.duration_ms:.2f} ms", style="yellow")
    if config.show_return and node.return_value is not None:
        label.append(f" -> {node.return_value}", style="dim green")
    if node.exception:
        label.append(f" ! {node.exception}", style="red")
    location = _format_location(node, config)
    if location:
        label.append(f"  {location}", style="dim")
    return label


def _format_location(node: TraceNode, config: _TraceConfig) -> str:
    if not config.show_file and not config.show_line:
        return ""
    if node.filename == "<manual>":
        return "<manual>"
    location = Path(node.filename).name if config.show_file else ""
    if config.show_line:
        location = f"{location}:{node.lineno}" if location else f":{node.lineno}"
    return location


def _export_trace(state: _TraceState) -> dict[str, Any] | str | None:
    if state.root is None:
        return None
    data = _node_to_dict(state.root, state.config, depth=0)
    if state.config.output == "json":
        return json.dumps(data, indent=2)
    if state.config.output == "mermaid":
        return _to_mermaid(state.root, state.config)
    return data


def _node_to_dict(node: TraceNode, config: _TraceConfig, depth: int) -> dict[str, Any]:
    data = node.to_dict()
    if not config.show_args:
        data.pop("args", None)
    if not config.show_return:
        data.pop("return_value", None)
    if not config.show_file:
        data.pop("filename", None)
    if not config.show_line:
        data.pop("lineno", None)
    children = []
    if config.max_depth is None or depth < config.max_depth:
        for child in node.children:
            if _should_show_node(child, config, depth + 1):
                children.append(_node_to_dict(child, config, depth + 1))
    data["children"] = children
    return data


def _to_mermaid(root: TraceNode, config: _TraceConfig) -> str:
    lines = ["graph TD"]
    ids: dict[int, str] = {}

    def walk(node: TraceNode, depth: int) -> str:
        node_id = ids.setdefault(id(node), f"N{len(ids)}")
        lines.append(f'  {node_id}["{node.name} {node.duration_ms:.2f} ms"]')
        if config.max_depth is not None and depth >= config.max_depth:
            return node_id
        for child in node.children:
            if not _should_show_node(child, config, depth + 1):
                continue
            child_id = walk(child, depth + 1)
            lines.append(f"  {node_id} --> {child_id}")
        return node_id

    walk(root, 0)
    return "\n".join(lines)


def _save_trace(state: _TraceState) -> None:
    if not state.config.save_to or state.exported_trace is None:
        return
    path = Path(state.config.save_to)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(state.exported_trace, str):
        path.write_text(state.exported_trace, encoding="utf-8")
        return
    path.write_text(json.dumps(state.exported_trace, indent=2), encoding="utf-8")


def _format_args(frame: FrameType) -> str:
    try:
        args = inspect.getargvalues(frame)
    except Exception:
        return "()"
    parts = []
    for name in args.args:
        parts.append(f"{name}={_safe_repr(args.locals.get(name))}")
    if args.varargs:
        parts.append(f"*{args.varargs}={_safe_repr(args.locals.get(args.varargs))}")
    if args.keywords:
        parts.append(f"**{args.keywords}={_safe_repr(args.locals.get(args.keywords))}")
    return f"({', '.join(parts)})"


def _safe_repr(value: Any, limit: int = 80) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _level_style(depth: int) -> str:
    styles = (
        "bright_cyan",
        "bright_green",
        "bright_magenta",
        "bright_yellow",
        "bright_blue",
        "bright_red",
    )
    return styles[depth % len(styles)]
