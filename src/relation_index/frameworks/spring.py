from ..storage import digest
from .base import Evidence, join_paths, literal, short

VERSION = "spring-rules-v4"
CONFIGURATION = {"Configuration", "EnableWebSecurity", "EnableMethodSecurity", "Bean"}
INJECTION = {"Autowired", "Inject", "Resource", "Value"}

ROUTES = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT", "DeleteMapping": "DELETE", "PatchMapping": "PATCH", "RequestMapping": "ANY"}
GUARDS = {"PreAuthorize", "PostAuthorize", "Secured", "RolesAllowed"}
INPUTS = {"PathVariable", "RequestParam", "RequestBody", "RequestHeader", "CookieValue"}
ROLE_NAMES = {"exec": "process", "start": "process", "execute": "sql_or_process", "executeQuery": "sql", "query": "sql", "openConnection": "network", "send": "network", "readObject": "deserialization", "readAllBytes": "file", "write": "output", "flush": "output", "sendRedirect": "redirect", "checkPermission": "guard", "hasRole": "guard", "isAuthorized": "guard"}


def java_facts(entry, parser_version):
    """Reconstruct the legacy Java fact rows from syntax data and anchors."""
    path = next((symbol["path"] for symbol in entry.get("symbols", [])), "")
    symbols = entry.get("symbols", [])
    by_id = {symbol["id"]: symbol for symbol in symbols}
    anchors = entry.get("anchors", {})
    result = []

    def add(kind, symbol, start_line, end_line, details, anchor_id=None):
        start_byte = anchors.get(anchor_id or symbol["id"], 0)
        result.append({"id": digest([path, symbol["id"], start_byte, kind, details])[:24], "symbol_id": symbol["id"], "path": path, "kind": kind, "start_line": start_line, "end_line": end_line, "status": "candidate", "provenance": parser_version, **details})

    for symbol in symbols:
        for ann in symbol.get("annotations", []):
            short = ann["name"].split(".")[-1]
            if short in ROUTES:
                owner = by_id.get(symbol.get("owner_id"))
                bases = []
                for base_ann in owner.get("annotations", []) if owner and symbol["kind"] != "class" else []:
                    if base_ann["name"].split(".")[-1] == "RequestMapping":
                        bases.extend(base_ann["values"].get("path", base_ann["values"].get("value", {})).get("strings", []))
                value = ann["values"].get("path", ann["values"].get("value", {}))
                routes = value.get("strings", [])
                paths = ["/" + (left.strip("/") + "/" + right.strip("/")).strip("/") for left in (bases or [""]) for right in (routes or [""])]
                add("route", symbol, symbol["start_line"], symbol["end_line"], {"http_method": ROUTES[short], "paths": paths, "annotation": ann["text"], "path_resolution": "literal" if not ann["values"] or value.get("literal") else "unresolved", "note": "Annotation-name match; runtime mapping and profiles unverified"})
            if short in GUARDS:
                add("guard", symbol, symbol["start_line"], symbol["end_line"], {"annotation": ann["text"], "note": "Method-security activation and actual enforcement unverified"})
            if short in {"Test", "ParameterizedTest", "RepeatedTest"}:
                add("test", symbol, symbol["start_line"], symbol["end_line"], {"annotation": ann["text"]})
            if short in {"Configuration", "EnableWebSecurity", "EnableMethodSecurity", "Bean"}:
                add("configuration", symbol, symbol["start_line"], symbol["end_line"], {"annotation": ann["text"]})
        for parameter in symbol.get("parameters", []):
            for ann in parameter.get("annotations", []):
                if ann["name"].split(".")[-1] in INPUTS:
                    add("input", symbol, symbol["start_line"], symbol["end_line"], {"parameter": parameter["name"], "annotation": ann["text"]})
        if symbol.get("kind") == "field":
            for ann in symbol.get("annotations", []):
                if ann["name"].split(".")[-1] in {"Autowired", "Inject", "Resource", "Value"}:
                    add("injection", symbol, symbol["start_line"], symbol["end_line"], {"annotation": ann["text"], "declared_type": symbol["type"]})
    for call in entry.get("calls", []):
        if call["name"] in ROLE_NAMES:
            method = by_id[call["caller_id"]]
            add("security_call", method, call["start_line"], call["end_line"], {"category": ROLE_NAMES[call["name"]], "call_id": call["id"], "expression": call["expression"], "note": "Name-based navigation hint, not a verified API or vulnerability"}, call["id"])
    return result


def kotlin_facts(entry, content):
    """Spring annotations on Kotlin declarations, read from the common format."""
    ev = Evidence(entry, content, "spring", VERSION)
    for symbol in ev.symbols:
        owner = ev.owner(symbol)
        prefixes = [
            literal(item["args"][0]) or ""
            for item in (owner or {}).get("decorators", [])
            if short(item["name"]) == "RequestMapping" and item["args"]
        ] if symbol["kind"] != "class" else []
        for decorator in symbol.get("decorators", []):
            name = short(decorator["name"])
            if name in ROUTES:
                routes = [value for value in (literal(item.split("=", 1)[-1]) for item in decorator["args"][:1]) if value is not None]
                paths = [join_paths(left, right) for left in (prefixes or [""]) for right in (routes or [""])]
                ev.add("route", symbol, decorator["line"], symbol["end_line"], note="Annotation-name match; runtime mapping and profiles unverified",
                       http_method=ROUTES[name], paths=paths, path_resolution="literal" if routes or not decorator["args"] else "unresolved", evidence=decorator["text"][:200])
            elif name in GUARDS:
                ev.add("guard", symbol, decorator["line"], note="Method-security activation and actual enforcement unverified", evidence=decorator["text"][:200])
            elif name in CONFIGURATION:
                ev.add("configuration", symbol, decorator["line"], note="Spring configuration annotation", evidence=decorator["text"][:200])
            elif name in INJECTION:
                ev.add("injection", symbol, decorator["line"], note="Spring injection annotation", evidence=decorator["text"][:200])
        for parameter in symbol.get("parameters", []):
            for annotation in parameter.get("annotations", []):
                if short(annotation["name"]) in INPUTS:
                    ev.add("input", symbol, annotation["line"], note="Spring request parameter annotation", parameter=parameter["name"], evidence=annotation["text"][:200])
    return ev.facts


def extract(entry, content):
    if entry.get("language") == "java":
        return java_facts(entry, entry.get("parser_version", "java-syntax-v3-ts0.25-java0.23"))
    return kotlin_facts(entry, content)
