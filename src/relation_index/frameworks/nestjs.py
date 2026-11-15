"""NestJS controller, guard, parameter and injection candidates."""

from .base import Evidence, join_paths, literal, short

VERSION = "nestjs-rules-v2"
ROUTES = {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE", "Patch": "PATCH", "Options": "OPTIONS", "Head": "HEAD", "All": "ANY"}
INPUTS = {"Param": "path", "Query": "query", "Body": "body", "Headers": "header", "Req": "request", "Request": "request", "UploadedFile": "file", "UploadedFiles": "file", "Cookies": "cookie", "Session": "session", "Ip": "ip"}
GUARDS = {"UseGuards", "Roles", "Public", "SetMetadata", "Auth"}


def extract(entry, content):
    ev = Evidence(entry, content, "nestjs", VERSION)
    if not ev.imports("@nestjs"):
        return []
    for symbol in ev.symbols:
        owner = ev.owner(symbol)
        prefix = ""
        for decorator in (owner or {}).get("decorators", []):
            if short(decorator["name"]) == "Controller" and decorator["args"]:
                prefix = literal(decorator["args"][0]) or ""
        for decorator in symbol.get("decorators", []):
            name = short(decorator["name"])
            if name in ROUTES and symbol["kind"] in {"method", "function"}:
                path = literal(decorator["args"][0]) if decorator["args"] else ""
                ev.add("route", symbol, decorator["line"], symbol["end_line"], note="NestJS route decorator; global prefixes and versioning are not resolved",
                       http_method=ROUTES[name], paths=[join_paths(prefix, path or "")], path_resolution="literal" if path is not None else "unresolved", evidence=decorator["text"][:200])
            if name in GUARDS:
                ev.add("guard", symbol, decorator["line"], note="NestJS guard or role metadata; enforcement unverified", evidence=decorator["text"][:200])
        for parameter in symbol.get("parameters", []):
            for annotation in parameter.get("annotations", []):
                name = short(annotation["name"])
                if name in INPUTS:
                    ev.add("input", symbol, annotation["line"], note="NestJS request parameter decorator", parameter=parameter["name"], source=INPUTS[name], evidence=annotation["text"][:200])
            if symbol["kind"] == "constructor" and parameter.get("type"):
                ev.add("injection", symbol, symbol["start_line"], note="Constructor parameter resolved by the NestJS container at runtime", parameter=parameter["name"], declared_type=parameter["type"], evidence=parameter["name"])
    return ev.facts
