"""Express route, middleware and request accessor candidates."""

import re

from .base import AUTH_RE, HTTP_METHODS, Evidence

VERSION = "express-rules-v2"
RECEIVERS = r"(app|router|server|api|routes|\w*[Rr]outer|\w*[Aa]pp)"


def extract(entry, content):
    ev = Evidence(entry, content, "express", VERSION)
    imported = ev.imports("express")
    found = False
    for call, path in ev.route_calls(HTTP_METHODS | {"all"}, RECEIVERS):
        if len(call["arguments"]) < 2:
            continue
        found = True
        symbol = ev.by_id.get(call["caller_id"])
        middleware = call["arguments"][1:-1]
        ev.add("route", symbol, call["start_line"], call["end_line"], note="Express route registration; mounted prefixes are not resolved",
               http_method=call["name"].upper(), paths=[path], handler=call["arguments"][-1][:200],
               middleware=[item[:120] for item in middleware], path_resolution="literal", evidence=call["expression"][:200])
        for item in middleware:
            if AUTH_RE.search(item):
                ev.add("guard", symbol, call["start_line"], note="Route middleware with an authentication-like name; enforcement unverified", middleware=item[:120], evidence=item[:200])
    for call in ev.calls:
        if call["name"] == "use" and re.fullmatch(RECEIVERS, call.get("receiver", "")) and any(AUTH_RE.search(item) for item in call["arguments"]):
            ev.add("guard", ev.by_id.get(call["caller_id"]), call["start_line"], note="Application middleware with an authentication-like name; order and enforcement unverified", evidence=call["expression"][:200])
    if imported or found:
        ev.scan("input", r"\breq\.(params|query|body|headers|cookies|files|file)\b", "Express request accessor")
    return ev.facts
