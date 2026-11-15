"""Flask route, request accessor and decorator guard candidates."""

import re

from .base import AUTH_RE, Evidence, literal, short

VERSION = "flask-rules-v2"
ROUTE = re.compile(r"^[\w.]+\.(route|get|post|put|delete|patch)$")
GUARDS = {"login_required", "roles_required", "roles_accepted", "permission_required", "jwt_required", "fresh_jwt_required", "auth_required", "admin_required"}


def extract(entry, content):
    ev = Evidence(entry, content, "flask", VERSION)
    if not ev.imports("flask"):
        return []
    for symbol in ev.callables():
        for decorator in symbol.get("decorators", []):
            match = ROUTE.match(decorator["name"])
            name = short(decorator["name"])
            if match:
                path = literal(decorator["args"][0]) if decorator["args"] else None
                methods = re.search(r"methods\s*=\s*[\[(]([^\])]*)", decorator["text"])
                if match.group(1) != "route":
                    method = match.group(1).upper()
                else:
                    method = ",".join(value.upper() for value in re.findall(r"[\"'](\w+)[\"']", methods.group(1))) if methods else "GET"
                ev.add("route", symbol, decorator["line"], symbol["end_line"], note="Flask decorator; blueprint prefixes are not resolved",
                       http_method=method, paths=[path] if path else [], path_resolution="literal" if path is not None else "unresolved", evidence=decorator["text"][:200])
                for variable in re.findall(r"<(?:\w+:)?(\w+)>", path or ""):
                    ev.add("input", symbol, decorator["line"], note="Flask URL variable", parameter=variable, source="path", evidence=path)
            elif name in GUARDS or (name.endswith("_required") and AUTH_RE.search(name)):
                ev.add("guard", symbol, decorator["line"], note="Authentication decorator name; enforcement unverified", evidence=decorator["text"][:200])
    ev.scan("input", r"\brequest\.(args|form|values|json|data|files|cookies|headers|get_json|get_data|stream)\b", "Flask request accessor")
    return ev.facts
