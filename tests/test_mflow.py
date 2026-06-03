import asyncio
import json
import re

from mithra_flow import MFlowResult, __version__, mflow, span, trace
from mithra_flow.decorator import (
    _banner,
    _discover_project_root,
    _is_dependency_frame,
    _is_dependency_module,
    _is_external_frame,
)


def sync_child():
    return "ok"


@mflow
def bare_parent():
    return sync_child()


@mflow(include=["tests"])
def sync_parent():
    return sync_child()


async def async_child():
    await asyncio.sleep(0)
    return "ok"


@mflow(include=["tests"])
async def async_parent():
    return await async_child()


async def async_grandchild():
    await asyncio.sleep(0.001)
    return "grandchild"


async def async_grandchild_two():
    await asyncio.sleep(0.001)
    return "grandchild-two"


async def async_nested_child():
    first = await async_grandchild()
    second = await async_grandchild_two()
    return [first, second]


async def async_nested_child_two():
    return await async_grandchild_two()


@mflow(include=["tests"])
async def async_nested_parent():
    first_branch = await async_nested_child()
    second_branch = await async_nested_child_two()
    return [first_branch, second_branch]


def excluded_child():
    return "hidden"


@mflow(include=["tests"], exclude=["excluded_child"])
def parent_with_exclude():
    return excluded_child()


@mflow(include=["tests"], enabled=False)
def disabled_parent():
    return sync_child()


@mflow(include=["tests"], output="dict", show_return=True)
def dict_parent():
    return sync_child()


@mflow(include=["tests"], output="json", show_args=True)
def json_parent(value: str = "ok"):
    return value


@mflow(include=["tests"], return_trace=True)
def traced_result_parent():
    return sync_child()


@mflow(include=["tests"], show_args=True, show_return=True)
def args_parent(value: str = "ok"):
    return value


@mflow(include=["tests"])
def manual_span_parent():
    with span("manual work"):
        sync_child()
    return "ok"


def test_sync_trace_prints_nested_tree(capsys):
    assert sync_parent() == "ok"

    output = capsys.readouterr().out

    assert "sync_parent()" in output
    assert "sync_child()" in output
    assert re.search(r"sync_parent\(\).* ms", output)
    assert re.search(r"sync_child\(\).* ms", output)


def test_bare_decorator_form(capsys):
    assert bare_parent() == "ok"

    output = capsys.readouterr().out

    assert "bare_parent()" in output
    assert "sync_child()" in output


async def test_async_trace_prints_nested_tree(capsys):
    assert await async_parent() == "ok"

    output = capsys.readouterr().out

    assert "async_parent()" in output
    assert "async_child()" in output
    assert re.search(r"async_parent\(\).* ms", output)
    assert re.search(r"async_child\(\).* ms", output)


async def test_async_trace_prints_grandchildren(capsys):
    assert await async_nested_parent() == [
        ["grandchild", "grandchild-two"],
        "grandchild-two",
    ]

    output = capsys.readouterr().out

    assert "async_nested_parent()" in output
    assert "async_nested_child()" in output
    assert "async_nested_child_two()" in output
    assert "async_grandchild()" in output
    assert "async_grandchild_two()" in output


def test_exclude_filter_hides_matching_child(capsys):
    assert parent_with_exclude() == "hidden"

    output = capsys.readouterr().out

    assert "parent_with_exclude()" in output
    assert "excluded_child()" not in output


def test_disabled_trace_prints_nothing(capsys):
    assert disabled_parent() == "ok"

    output = capsys.readouterr().out

    assert output == ""


def test_dict_output_returns_trace():
    trace_output = dict_parent()

    assert trace_output["name"] == "dict_parent()"
    assert trace_output["children"][0]["name"] == "sync_child()"
    assert trace_output["children"][0]["return_value"] == "'ok'"


def test_json_output_returns_trace_json():
    trace_output = json_parent("hello")
    payload = json.loads(trace_output)

    assert payload["name"] == "json_parent()"
    assert payload["args"] == "(value='hello')"


def test_return_trace_keeps_value_and_trace():
    result = traced_result_parent()

    assert isinstance(result, MFlowResult)
    assert result.value == "ok"
    assert result.trace["name"] == "traced_result_parent()"


def test_args_and_return_render(capsys):
    assert args_parent("hello") == "hello"

    output = capsys.readouterr().out

    assert "args_parent()" in output
    assert "(value='hello')" in output
    assert "-> 'hello'" in output


def test_manual_span_renders(capsys):
    assert manual_span_parent() == "ok"

    output = capsys.readouterr().out

    assert "manual work()" in output
    assert "sync_child()" in output


def test_context_manager_collects_result(capsys):
    with trace("test context", include=["tests"], show_return=True) as traced:
        sync_child()

    output = capsys.readouterr().out

    assert "test context" in output
    assert "sync_child()" in output
    assert traced.result["name"] == "test context"


def test_banner_uses_package_version():
    assert f"v{__version__}" in _banner()
    assert "v1.00" not in _banner()


def test_dependency_frames_are_detected():
    assert _is_dependency_frame("/project/.venv/lib/python3.12/site-packages/sqlalchemy/sql.py")
    assert _is_dependency_frame("/project/venv/lib/python3.12/site-packages/passlib/hash.py")
    assert not _is_dependency_frame("/project/app/services/auth.py")


def test_dependency_modules_are_detected():
    assert _is_dependency_module("sqlalchemy.sql.elements")
    assert _is_dependency_module("sqlmodel")
    assert _is_dependency_module("passlib.context")
    assert _is_dependency_module("fastapi.routing")
    assert not _is_dependency_module("controllers.user")
    assert not _is_dependency_module("helpers.auth")


def test_project_root_is_discovered_from_decorated_file():
    root = _discover_project_root(__file__)

    assert root.endswith("mithra-flow")


def test_external_frames_are_checked_against_project_root():
    root = _discover_project_root(__file__)

    assert not _is_external_frame(__file__, root)
    assert _is_external_frame("/tmp/outside.py", root)
