"""Allowlisted, read-only query interface for an external LLM tool adapter."""

from __future__ import annotations

from typing import Any

from .queries import Queries

TOOLS: dict[str, tuple[str, set[str]]] = {
    "get_source_scope": ("overview", set()),
    "list_files": ("files", {"query", "limit", "offset", "language"}),
    "find_symbols": ("symbols", {"query", "kind", "limit", "offset", "language"}),
    "get_symbol": ("symbol", {"symbol_id"}),
    "trace_relations": (
        "relations",
        {"symbol_id", "direction", "limit", "offset"},
    ),
    "search_relation_facts": ("facts", {"kind", "limit", "offset"}),
    "search_code": ("search", {"query", "limit", "offset"}),
    "read_file": ("read", {"path", "start_line", "end_line"}),
    "get_relation_scope": ("context", {"symbol_id", "limit"}),
}
REQUIRED = {
    "get_symbol": {"symbol_id"},
    "trace_relations": {"symbol_id"},
    "search_code": {"query"},
    "read_file": {"path"},
    "get_relation_scope": {"symbol_id"},
}
INTEGER_ARGUMENTS = {"limit", "offset", "start_line", "end_line"}
STRING_ARGUMENTS = {"query", "symbol_id", "path", "direction", "language"}


def invoke(index: Queries, name: str, arguments: dict[str, Any]) -> object:
    """Dispatch one query; no build, file-write, shell or arbitrary SQL operation exists."""
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object")
    method, allowed = TOOLS[name]
    unexpected = set(arguments) - allowed
    if unexpected:
        raise ValueError(f"Unexpected arguments: {', '.join(sorted(unexpected))}")
    missing = REQUIRED.get(name, set()) - set(arguments)
    if missing:
        raise ValueError(f"Missing arguments: {', '.join(sorted(missing))}")
    for key, value in arguments.items():
        if key in INTEGER_ARGUMENTS and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"{key} must be an integer")
        if key in STRING_ARGUMENTS and not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        if key == "kind" and not (
            isinstance(value, str)
            or (isinstance(value, list) and all(isinstance(item, str) for item in value))
        ):
            raise ValueError("kind must be a string or an array of strings")
    return getattr(index, method)(**arguments)


def definitions() -> list[dict[str, object]]:
    result = []
    for name, (_, allowed) in TOOLS.items():
        properties: dict[str, object] = {}
        for key in sorted(allowed):
            if key == "kind":
                properties[key] = {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                }
            else:
                properties[key] = {
                    "type": "integer" if key in INTEGER_ARGUMENTS else "string"
                }
        result.append(
            {
                "name": name,
                "read_only": True,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": sorted(REQUIRED.get(name, set())),
                    "additionalProperties": False,
                },
            }
        )
    return result
