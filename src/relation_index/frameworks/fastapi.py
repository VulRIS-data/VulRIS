"""FastAPI route, parameter and dependency candidates."""

import re

from .base import AUTH_RE, Evidence, literal, short

VERSION = "fastapi-rules-v2"
ROUTE = re.compile(r"^[\w.]+\.(get|post|put|delete|patch|options|head|api_route|websocket)$")
INPUTS = {"Query": "query", "Path": "path", "Body": "body", "Header": "header", "Cookie": "cookie", "Form": "form", "File": "file"}


def extract(entry, content):
    ev = Evidence(entry, content, "fastapi", VERSION)
    if not ev.imports("fastapi"):
        return []
    for symbol in ev.callables():
        routes = []
        for decorator in symbol.get("decorators", []):
            match = ROUTE.match(decorator["name"])
            if not match:
                continue
            method = match.group(1).upper()
            path = literal(decorator["args"][0]) if decorator["args"] else None
            if method == "API_ROUTE":
                listed = re.search(r"methods\s*=\s*\[([^\]]*)\]", decorator["text"])
                method = ",".join(value.upper() for value in re.findall(r"[\"'](\w+)[\"']", listed.group(1))) if listed else "ANY"
            routes.append(path or "")
            ev.add("route", symbol, decorator["line"], symbol["end_line"], note="FastAPI decorator; router prefixes and mounts are not resolved",
                   http_method=method, paths=[path] if path else [], path_resolution="literal" if path is not None else "unresolved", evidence=decorator["text"][:200])
            for dependency in re.findall(r"(?:Depends|Security)\(\s*([\w.]+)", decorator["text"]):
                if AUTH_RE.search(dependency) or "Security(" in decorator["text"]:
                    ev.add("guard", symbol, decorator["line"], note="Route dependency with an authentication-like name; enforcement unverified", dependency=dependency, evidence=decorator["text"][:200])
        if not routes and not any(re.search(r"\b(Depends|Security)\(", item.get("default", "")) for item in symbol.get("parameters", [])):
            continue
        placeholders = {name for path in routes for name in re.findall(r"\{(\w+)", path)}
        for parameter in symbol.get("parameters", []):
            default, name = parameter.get("default", ""), parameter["name"]
            head = short(default.split("(")[0]) if "(" in default else ""
            if head in {"Depends", "Security"}:
                dependency = (re.findall(r"\(\s*([\w.]+)", default) or [""])[0]
                ev.add("injection", symbol, symbol["start_line"], note="FastAPI dependency", parameter=name, dependency=dependency, evidence=default[:200])
                if head == "Security" or AUTH_RE.search(dependency + " " + name):
                    ev.add("guard", symbol, symbol["start_line"], note="Dependency with an authentication-like name; enforcement unverified", parameter=name, dependency=dependency, evidence=default[:200])
            elif head in INPUTS:
                ev.add("input", symbol, symbol["start_line"], note="FastAPI request parameter", parameter=name, source=INPUTS[head], evidence=default[:200])
            elif routes and name not in {"self", "request", "response", "background_tasks"}:
                source = "path" if name in placeholders else "query_or_body"
                ev.add("input", symbol, symbol["start_line"], note="Handler parameter bound from the request by FastAPI conventions", parameter=name, source=source, evidence=name)
    return ev.facts
