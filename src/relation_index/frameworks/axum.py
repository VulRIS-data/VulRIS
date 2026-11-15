"""Axum and Actix Web route, extractor and middleware candidates."""

import re

from .base import AUTH_RE, Evidence, literal, short

VERSION = "axum-actix-rules-v2"
ACTIX_ATTRIBUTES = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH", "head": "HEAD", "route": "ANY"}
EXTRACTORS = {"Path": "path", "Query": "query", "Json": "body", "Form": "form", "Multipart": "file", "HeaderMap": "header", "TypedHeader": "header", "HttpRequest": "request", "RawQuery": "query", "Bytes": "body"}


def extract(entry, content):
    axum = Evidence(entry, content, "axum", VERSION)
    actix = Evidence(entry, content, "actix", VERSION)
    use_axum, use_actix = axum.imports("axum"), actix.imports("actix_web", "actix-web")
    if not (use_axum or use_actix):
        return []
    ev = actix if use_actix and not use_axum else axum
    for symbol in ev.callables():
        for decorator in symbol.get("decorators", []):
            name = short(decorator["name"])
            if use_actix and name in ACTIX_ATTRIBUTES and decorator["args"]:
                path = literal(decorator["args"][0])
                actix.add("route", symbol, decorator["line"], symbol["end_line"], note="Actix route attribute; scopes are not resolved",
                          http_method=ACTIX_ATTRIBUTES[name], paths=[path] if path else [], path_resolution="literal" if path else "unresolved", evidence=decorator["text"][:200])
        for parameter in symbol.get("parameters", []):
            head = short(re.split(r"<", parameter.get("type", ""))[0])
            if head in EXTRACTORS:
                ev.add("input", symbol, symbol["start_line"], note="Request extractor parameter", parameter=parameter["name"], source=EXTRACTORS[head], evidence=parameter.get("type", "")[:200])
            elif parameter.get("type") and AUTH_RE.search(parameter.get("type", "")):
                ev.add("guard", symbol, symbol["start_line"], note="Extractor type with an authentication-like name; enforcement unverified", parameter=parameter["name"], evidence=parameter["type"][:200])
    for call in ev.calls:
        caller = ev.by_id.get(call["caller_id"])
        if call["name"] == "route" and len(call["arguments"]) >= 2:
            path = literal(call["arguments"][0])
            if path is None:
                continue
            methods = sorted({value.upper() for value in re.findall(r"\b(get|post|put|delete|patch|head|options)\s*\(", call["arguments"][1])}) or ["ANY"]
            ev.add("route", caller, call["start_line"], call["end_line"], note="Router registration; nested routers are not resolved",
                   http_method=",".join(methods), paths=[path], handler=call["arguments"][1][:200], path_resolution="literal", evidence=call["expression"][:200])
        elif call["name"] == "resource" and call["arguments"]:
            path = literal(call["arguments"][0])
            if path is not None:
                ev.add("route", caller, call["start_line"], call["end_line"], note="Actix resource registration", http_method="ANY", paths=[path], path_resolution="literal", evidence=call["expression"][:200])
        elif call["name"] in {"layer", "route_layer", "wrap", "wrap_fn"} and any(AUTH_RE.search(item) for item in call["arguments"]):
            ev.add("guard", caller, call["start_line"], note="Middleware layer with an authentication-like name; order and enforcement unverified", evidence=call["expression"][:200])
    return axum.facts + actix.facts
