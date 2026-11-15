"""Shared helpers for framework evidence rules.

Framework rules read the common intermediate format (decorators, parameters,
calls, imports) and, for request-input accessors, the source lines. Every fact
is a navigation candidate; none of them proves that a route is reachable, that
input is attacker controlled, or that a guard is enforced.
"""

from __future__ import annotations

import re

from ..languages.base import CALLABLE_KINDS, TYPE_KINDS
from ..languages.treesitter import strings_in
from ..storage import digest

AUTH_RE = re.compile(
    r"auth|login|logged|permission|role|token|jwt|current_?user|admin|guard|session|verify|credential|acl|policy|secured",
    re.IGNORECASE,
)
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def literal(value: str) -> str | None:
    """Return the string literal if ``value`` is exactly one literal."""
    value = (value or "").strip()
    found = strings_in(value)
    if len(found) == 1 and len(value) <= len(found[0]) + 4 and value[:1] in "\"'`@r" :
        return found[0]
    if value.startswith(":") and re.fullmatch(r":\w+", value):
        return value[1:]
    return None


def join_paths(prefix: str, path: str) -> str:
    joined = "/".join(part.strip("/") for part in (prefix, path) if part and part.strip("/"))
    return "/" + joined


def short(name: str) -> str:
    return re.split(r"[.:\\]+", name or "")[-1]


class Evidence:
    def __init__(self, entry, content, framework, version):
        self.entry = entry
        self.path = entry.get("path") or next((item["path"] for item in entry.get("symbols", [])), "")
        self.language = entry.get("language")
        self.framework = framework
        self.version = version
        self.text = content.decode("utf-8", errors="replace")
        self.lines = self.text.splitlines()
        self.symbols = entry.get("symbols", [])
        self.by_id = {symbol["id"]: symbol for symbol in self.symbols}
        self.calls = entry.get("calls", [])
        self.facts = []

    def imports(self, *prefixes) -> bool:
        for item in self.entry.get("imports", []):
            module = (item.get("module") or "").replace("\\", "/").lower()
            raw = (item.get("raw") or "").lower()
            if any(module.startswith(prefix.lower()) or prefix.lower() in raw for prefix in prefixes):
                return True
        return False

    def callables(self):
        return [symbol for symbol in self.symbols if symbol["kind"] in CALLABLE_KINDS]

    def types(self):
        return [symbol for symbol in self.symbols if symbol["kind"] in TYPE_KINDS]

    def owner(self, symbol):
        return self.by_id.get(symbol.get("owner_id"))

    def enclosing(self, line):
        candidates = [symbol for symbol in self.symbols if symbol["start_line"] <= line <= symbol["end_line"]]
        return min(candidates, key=lambda item: (item["end_line"] - item["start_line"], item["kind"] == "module"), default=None)

    def add(self, kind, symbol, start_line, end_line=None, note="", **details):
        evidence = details.get("evidence", "")
        fact = {
            "id": digest([self.path, self.framework, kind, start_line, symbol["id"] if symbol else None, evidence, details.get("parameter", "")])[:24],
            "symbol_id": symbol["id"] if symbol else None,
            "path": self.path, "kind": kind,
            "start_line": start_line, "end_line": end_line or start_line,
            "status": "candidate", "framework": self.framework, "language": self.language,
            "provenance": self.version, "note": note, **details,
        }
        self.facts.append(fact)
        return fact

    def scan(self, kind, pattern, note, **details):
        """Line-level accessor scan, e.g. ``request.args`` or ``req.query``."""
        regex = re.compile(pattern)
        for number, line in enumerate(self.lines, start=1):
            stripped = line.strip()
            if stripped.startswith(("#", "//", "*", "/*")):
                continue
            for match in regex.finditer(line):
                symbol = self.enclosing(number)
                source = match.group(1) if match.groups() else match.group(0)
                self.add(kind, symbol, number, note=note, source=source, evidence=match.group(0), **details)

    def route_calls(self, names, receivers=None, require_slash=True):
        for call in self.calls:
            if call["name"] not in names or not call.get("arguments"):
                continue
            if receivers is not None and not re.fullmatch(receivers, call.get("receiver", "")):
                continue
            path = literal(call["arguments"][0])
            if path is None or (require_slash and not path.startswith(("/", "*"))):
                continue
            yield call, path
