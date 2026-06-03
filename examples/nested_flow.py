import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from mithra_flow import mflow, span, trace

app = FastAPI(title="Mithra Flow examples")


async def grandchild_a(delay: float = 0.01):
    await asyncio.sleep(delay)
    return "grandchild-a"


async def grandchild_b(delay: float = 0.02):
    await asyncio.sleep(delay)
    return "grandchild-b"


async def grandchild_c(delay: float = 0.01):
    await asyncio.sleep(delay)
    return "grandchild-c"


async def child_one():
    first = await grandchild_a()
    second = await grandchild_b()
    return [first, second]


async def child_two():
    third = await grandchild_c()
    return [third]


async def parent_flow():
    first_branch = await child_one()
    second_branch = await child_two()
    return [first_branch, second_branch]


def sync_price(amount: int, tax: float = 0.05):
    return round(amount + (amount * tax), 2)


def sync_receipt(amount: int):
    total = sync_price(amount)
    return {"amount": amount, "total": total}


async def failing_child():
    await asyncio.sleep(0)
    raise RuntimeError("example failure")


@app.get("/flow/basic")
@mflow(include=["examples"])
async def basic_trace():
    return {"result": await parent_flow()}


@app.get("/flow/title")
@mflow(name="checkout request", include=["examples"])
async def custom_title():
    return {"result": await parent_flow()}


@app.get("/flow/args")
@mflow(include=["examples"], show_args=True, show_return=True)
def args_and_returns(amount: int = 100):
    return sync_receipt(amount)


@app.get("/flow/location")
@mflow(include=["examples"], show_file=True, show_line=True)
async def file_and_line():
    return {"result": await parent_flow()}


@app.get("/flow/max-depth")
@mflow(include=["examples"], max_depth=1)
async def max_depth():
    return {"result": await parent_flow()}


@app.get("/flow/min-duration")
@mflow(include=["examples"], min_duration_ms=15)
async def min_duration():
    return {"result": await parent_flow()}


@app.get("/flow/json", response_class=PlainTextResponse)
@mflow(include=["examples"], output="json", show_args=True)
def json_trace():
    return sync_receipt(50)


@app.get("/flow/mermaid", response_class=PlainTextResponse)
@mflow(include=["examples"], output="mermaid")
async def mermaid_trace():
    await parent_flow()


@app.get("/flow/return-trace")
@mflow(include=["examples"], return_trace=True, show_return=True)
async def return_trace():
    result = await parent_flow()
    return result


@app.get("/flow/include-exclude")
@mflow(include=["examples"], exclude=["grandchild_b"])
async def include_exclude():
    return {"result": await parent_flow()}


@app.get("/flow/save-to")
@mflow(include=["examples"], save_to="/tmp/mithra-flow-example.json")
async def save_to_file():
    await parent_flow()
    return {"saved_to": "/tmp/mithra-flow-example.json"}


@app.get("/flow/manual-span")
@mflow(include=["examples"])
async def manual_span():
    with span("manual database query"):
        await asyncio.sleep(0.01)
    with span("manual cache write"):
        await asyncio.sleep(0)
    return {"ok": True}


@app.get("/flow/context")
async def context_manager():
    with trace("context managed flow", include=["examples"], show_return=True) as traced:
        result = sync_receipt(25)
    return {"result": result, "trace": traced.result}


@app.get("/flow/on-error")
@mflow(include=["examples"], on_error=True)
async def on_error_only():
    try:
        await failing_child()
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/flow/disabled")
@mflow(include=["examples"], enabled=False)
async def disabled_trace():
    return {"result": await parent_flow()}
