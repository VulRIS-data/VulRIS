"""Rails routes, controller filters and parameter accessor candidates."""

import re

from .base import AUTH_RE, Evidence, literal

VERSION = "rails-rules-v2"
ROUTE_CALLS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "delete": "DELETE", "match": "ANY", "root": "GET"}
FILTERS = {"before_action", "prepend_before_action", "before_filter", "around_action"}


def extract(entry, content):
    ev = Evidence(entry, content, "rails", VERSION)
    is_routes = ev.path.endswith("config/routes.rb")
    is_controller = "app/controllers/" in ev.path or any(base["type"].endswith("Controller") for symbol in ev.types() for base in symbol.get("bases", []))
    if not (is_routes or is_controller):
        return []
    for call in ev.calls:
        caller = ev.by_id.get(call["caller_id"])
        args = call["arguments"]
        if is_routes and not call.get("receiver") and call["name"] in ROUTE_CALLS and args:
            path = "/" if call["name"] == "root" else literal(args[0])
            if path is None:
                continue
            target = next((value for item in args[1:] for value in re.findall(r"(?:to:|=>)\s*['\"]([^'\"]+)", item)), "")
            if call["name"] == "root":
                target = literal(args[0]) or target
            ev.add("route", caller, call["start_line"], call["end_line"], note="Rails route; scopes and namespaces are not resolved",
                   http_method=ROUTE_CALLS[call["name"]], paths=["/" + path.lstrip("/")], handler=target, path_resolution="literal", evidence=call["expression"][:200])
        elif is_routes and not call.get("receiver") and call["name"] in {"resources", "resource"} and args:
            name = literal(args[0])
            if name:
                ev.add("route", caller, call["start_line"], call["end_line"], note="Rails resource routes; generated actions are not expanded",
                       http_method="RESOURCES", paths=["/" + name], path_resolution="literal", evidence=call["expression"][:200])
        elif is_controller and call["name"] in FILTERS and any(AUTH_RE.search(item) for item in args):
            ev.add("guard", caller, call["start_line"], note="Controller filter with an authentication-like name; enforcement unverified", evidence=call["expression"][:200])
        elif is_controller and call["name"] in {"skip_before_action", "skip_forgery_protection"} and any("authenticity" in item or "auth" in item for item in args + [call["name"]]):
            ev.add("configuration", caller, call["start_line"], note="A protection filter is skipped for some actions", evidence=call["expression"][:200])
        elif is_controller and call["name"] in {"authorize", "authorize!", "can?", "cannot?", "policy_scope", "authenticate_user!"}:
            ev.add("guard", caller, call["start_line"], note="Authorization call; enforcement unverified", evidence=call["expression"][:200])
    if is_controller:
        ev.scan("input", r"\b(params(?:\[|\.require|\.permit|\.fetch)|request\.(?:headers|body|raw_post|query_parameters|request_parameters)|cookies\[)", "Rails request accessor")
    return ev.facts
