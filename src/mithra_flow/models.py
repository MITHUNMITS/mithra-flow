from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceNode:
    name: str
    filename: str
    lineno: int
    start: float
    end: float | None = None
    args: str | None = None
    return_value: str | None = None
    exception: str | None = None
    is_span: bool = False
    children: list["TraceNode"] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end is None:
            return 0.0
        return (self.end - self.start) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "filename": self.filename,
            "lineno": self.lineno,
            "duration_ms": round(self.duration_ms, 3),
            "args": self.args,
            "return_value": self.return_value,
            "exception": self.exception,
            "is_span": self.is_span,
            "children": [child.to_dict() for child in self.children],
        }
