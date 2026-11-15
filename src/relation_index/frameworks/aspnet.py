"""ASP.NET Core attribute routing, minimal API, authorization and binding candidates."""

import re

from .base import Evidence, join_paths, literal, short

VERSION = "aspnet-rules-v2"
VERBS = {"HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT", "HttpDelete": "DELETE", "HttpPatch": "PATCH", "HttpHead": "HEAD", "HttpOptions": "OPTIONS"}
INPUTS = {"FromBody": "body", "FromQuery": "query", "FromRoute": "path", "FromHeader": "header", "FromForm": "form"}
MAP_CALLS = {"MapGet": "GET", "MapPost": "POST", "MapPut": "PUT", "MapDelete": "DELETE", "MapPatch": "PATCH", "MapMethods": "ANY", "Map": "ANY"}
CONFIG_CALLS = {"AddAuthentication", "AddAuthorization", "UseAuthentication", "UseAuthorization", "AddCors", "UseCors", "AddAntiforgery", "UseAntiforgery", "AddJwtBearer", "AddCookie"}


def _short(name):
    return short(name).removesuffix("Attribute")


def extract(entry, content):
    ev = Evidence(entry, content, "aspnet", VERSION)
    names = {_short(item["name"]) for symbol in ev.symbols for item in symbol.get("decorators", [])}
    if not (ev.imports("Microsoft.AspNetCore") or names & (set(VERBS) | {"ApiController", "Route", "Authorize"})):
        return []
    for symbol in ev.symbols:
        owner = ev.owner(symbol)
        prefix = next((literal(item["args"][0]) or "" for item in (owner or {}).get("decorators", []) if _short(item["name"]) == "Route" and item["args"]), "")
        verbs = []
        for decorator in symbol.get("decorators", []):
            name = _short(decorator["name"])
            path = literal(decorator["args"][0]) if decorator["args"] else ""
            if name in VERBS and symbol["kind"] in {"method", "function"}:
                verbs.append((VERBS[name], path, decorator))
            elif name == "Route" and symbol["kind"] in {"method", "function"}:
                verbs.append(("ANY", path, decorator))
            elif name == "Authorize":
                ev.add("guard", symbol, decorator["line"], note="Authorization attribute; policies and middleware order unverified", evidence=decorator["text"][:200])
            elif name == "AllowAnonymous":
                ev.add("guard", symbol, decorator["line"], note="AllowAnonymous attribute; this marks an exemption, not a check", effect="allow_anonymous", evidence=decorator["text"][:200])
            elif name in {"IgnoreAntiforgeryToken"}:
                ev.add("configuration", symbol, decorator["line"], note="Antiforgery validation is disabled by attribute", evidence=decorator["text"][:200])
        for method, path, decorator in verbs:
            full = join_paths(prefix, path or "") if not (path or "").startswith("/") else path
            ev.add("route", symbol, decorator["line"], symbol["end_line"], note="Attribute route; conventional routes and [controller] tokens are not expanded",
                   http_method=method, paths=[full], path_resolution="template" if "[" in full else "literal", evidence=decorator["text"][:200])
        for parameter in symbol.get("parameters", []):
            attributes = [_short(item["name"]) for item in parameter.get("annotations", [])]
            source = next((INPUTS[item] for item in attributes if item in INPUTS), None)
            if source:
                ev.add("input", symbol, symbol["start_line"], note="Model binding attribute", parameter=parameter["name"], source=source, evidence=parameter["name"])
            elif verbs and "FromServices" not in attributes:
                ev.add("input", symbol, symbol["start_line"], note="Action parameter bound by ASP.NET conventions", parameter=parameter["name"], source="model_binding", evidence=parameter["name"])
            if symbol["kind"] == "constructor" and owner is not None and owner["name"].endswith("Controller") and parameter.get("type"):
                ev.add("injection", symbol, symbol["start_line"], note="Constructor dependency resolved by the DI container at runtime", parameter=parameter["name"], declared_type=parameter["type"], evidence=parameter["name"])
    for call in ev.calls:
        caller = ev.by_id.get(call["caller_id"])
        if call["name"] in MAP_CALLS and call["arguments"]:
            path = literal(call["arguments"][0])
            if path is not None:
                ev.add("route", caller, call["start_line"], call["end_line"], note="Minimal API endpoint; route groups are not resolved", http_method=MAP_CALLS[call["name"]], paths=[path], path_resolution="literal", evidence=call["expression"][:200])
        elif call["name"] in {"RequireAuthorization", "AllowAnonymous"}:
            ev.add("guard", caller, call["start_line"], note="Endpoint authorization call; enforcement unverified", evidence=call["expression"][:200])
        elif call["name"] in CONFIG_CALLS:
            ev.add("configuration", caller, call["start_line"], note="Security middleware or service registration", call=call["name"], evidence=call["expression"][:200])
    ev.scan("input", r"\bRequest\.(Query|Form|Headers|Cookies|Body|RouteValues)\b", "HttpRequest accessor")
    return ev.facts
