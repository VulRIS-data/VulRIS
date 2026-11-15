"""Laravel routes, middleware, authorization and request accessor candidates.

Plain PHP superglobals are reported under the ``php`` framework name.
"""

import re

from .base import AUTH_RE, Evidence, literal

VERSION = "laravel-rules-v2"
ROUTE_CALLS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "delete": "DELETE", "options": "OPTIONS", "any": "ANY", "match": "ANY", "resource": "RESOURCES", "apiResource": "RESOURCES"}
REQUEST_METHODS = {"input", "query", "post", "get", "all", "only", "except", "file", "cookie", "header", "json", "route", "validated", "string", "integer", "boolean"}


def extract(entry, content):
    facts = []
    ev = Evidence(entry, content, "laravel", VERSION)
    if ev.imports("Illuminate") or any(call.get("receiver") == "Route" for call in ev.calls):
        for call in ev.calls:
            caller = ev.by_id.get(call["caller_id"])
            receiver, name, args = call.get("receiver", ""), call["name"], call["arguments"]
            if receiver == "Route" and name in ROUTE_CALLS and args:
                index = 1 if name == "match" and len(args) > 1 else 0
                path = literal(args[index])
                if path is None:
                    continue
                ev.add("route", caller, call["start_line"], call["end_line"], note="Laravel route; groups and prefixes are not resolved",
                       http_method=ROUTE_CALLS[name], paths=["/" + path.lstrip("/")], handler=args[-1][:200], path_resolution="literal", evidence=call["expression"][:200])
            elif name == "middleware" and any(AUTH_RE.search(item) for item in args):
                ev.add("guard", caller, call["start_line"], note="Middleware with an authentication-like name; enforcement unverified", evidence=call["expression"][:200])
            elif name in {"authorize", "can", "cannot", "allows", "denies", "check"} and (receiver in {"$this", "Gate", "$user", "auth()->user()"} or receiver.endswith("user()")):
                ev.add("guard", caller, call["start_line"], note="Authorization call; enforcement unverified", evidence=call["expression"][:200])
            elif name in REQUEST_METHODS and (re.fullmatch(r"\$request|request\(\)|Request", receiver)):
                ev.add("input", caller, call["start_line"], note="Laravel request accessor", source=name, evidence=call["expression"][:200])
            elif name == "request" and not receiver and args:
                ev.add("input", caller, call["start_line"], note="Laravel request() helper", source="request", evidence=call["expression"][:200])
        facts.extend(ev.facts)
    php = Evidence(entry, content, "php", VERSION)
    php.scan("input", r"\$_(GET|POST|REQUEST|COOKIE|FILES|SERVER)\b", "PHP superglobal request input")
    facts.extend(php.facts)
    return facts
