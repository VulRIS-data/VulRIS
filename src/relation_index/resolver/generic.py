"""Syntax-level candidate linking for the non-Java frontends.

Calls are narrowed in this order: constructor syntax, the current object
(``self``/``this``), a receiver whose type is known from a declaration or a
constructor expression, a type or module name used as receiver, then the
caller's scope (same file, imports, same directory). Only when none of these
apply is a name and argument-count match across the language family used.
Every result is a candidate. ``status`` is ``candidate`` for exactly one
target, ``ambiguous`` for several and ``unresolved`` for none.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict

from ..languages.base import CALLABLE_KINDS, TYPE_KINDS
from ..storage import digest
from .imports import ImportIndex, resolve_imports

VERSION = "generic-resolver-v2"
MAX_TARGETS = 20
IMPLICIT_RECEIVER = {"csharp", "cpp", "kotlin", "swift", "ruby"}
SELF_NAMES = {
    "python": {"self", "cls"}, "javascript": {"this"}, "typescript": {"this"},
    "csharp": {"this"}, "cpp": {"this", "(*this)"}, "rust": {"self", "Self"},
    "php": {"$this", "self", "static"}, "ruby": {"self"}, "kotlin": {"this"}, "swift": {"self", "Self"},
}
SUPER_NAMES = {"super", "base", "parent", "super()"}
SELF_PREFIX = re.compile(r"^(?:this\.|self\.|\$this->|this->|@)")
CONSTRUCTED = [
    re.compile(r"^\(?\s*new\s+([\w.:\\]+)"),
    re.compile(r"^([\w:]+)::(?:new|default|from)\s*\("),
    re.compile(r"^([\w:]+)\.new\b"),
    re.compile(r"^&?([A-Z][\w.]*)\s*[({]"),
]


def _last(value: str) -> str:
    value = re.sub(r"<.*>|\[.*\]", "", value or "")
    parts = [part for part in re.split(r"[.:\\]+", value.strip(" *&?!()")) if part]
    return parts[-1] if parts else ""


def _arity_ok(symbol, count):
    limits = symbol.get("arity") or {}
    low, high = limits.get("min", 0), limits.get("max")
    return low <= count and (high is None or count <= high)


def link(parsed_files, checkpoint=lambda: None, on_progress=None):
    symbols = [symbol for entry in parsed_files for symbol in entry.get("symbols", [])]
    calls = [call for entry in parsed_files for call in entry.get("calls", [])]
    by_id = {symbol["id"]: symbol for symbol in symbols}
    entries = {entry["path"]: entry for entry in parsed_files}
    types_by_name = defaultdict(list)
    callables_by_name = defaultdict(list)
    members = defaultdict(list)
    for symbol in symbols:
        if symbol["kind"] in TYPE_KINDS:
            types_by_name[symbol["name"]].append(symbol)
        elif symbol["kind"] in CALLABLE_KINDS:
            callables_by_name[symbol["name"]].append(symbol)
    edges, edge_ids = [], set()

    def add_edge(src, dst, kind, evidence, language, status="candidate"):
        edge_id = digest([src, dst, kind, evidence])[:24]
        if edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edges.append({
            "id": edge_id, "src_id": src, "dst_id": dst, "kind": kind,
            "status": status, "evidence": evidence, "provenance": VERSION, "language": language,
        })

    # Imports first: they decide which declarations a file can see.
    index = ImportIndex(parsed_files, symbols)
    scopes, unresolved_imports, external_imports = {}, defaultdict(int), defaultdict(int)
    for path in sorted(entries):
        entry = entries[path]
        scope, results = resolve_imports(entry, index)
        scopes[path] = scope
        module = index.modules.get(path)
        for item, targets, external in results:
            if external:
                external_imports[entry["language"]] += 1
            elif not targets:
                unresolved_imports[entry["language"]] += 1
            for target in targets[:MAX_TARGETS]:
                if module is not None and target["id"] != module["id"]:
                    add_edge(module["id"], target["id"], "IMPORTS", {"path": path, "start_line": item.get("line", 1), "import": item.get("raw", item.get("module", ""))[:300]}, entry["language"])

    alias_ids = {
        path: {value["id"] for values in scope.aliases.values() for _, value in values}
        for path, scope in scopes.items()
    }

    def rank(candidate, path):
        scope = scopes.get(path)
        if candidate["path"] == path:
            return 0
        if scope is not None:
            if candidate["id"] in alias_ids[path]:
                return 1
            if candidate["path"] in scope.modules:
                return 1
            if any(candidate["qualified_name"].startswith(prefix) for prefix in scope.prefixes if prefix):
                return 1
        if posixpath.dirname(candidate["path"]) == posixpath.dirname(path):
            return 2
        return 3

    def best(candidates, path):
        if not candidates:
            return []
        ranked = sorted(candidates, key=lambda item: (rank(item, path), item["qualified_name"], item["id"]))
        top = rank(ranked[0], path)
        return [item for item in ranked if rank(item, path) == top]

    def lookup_type(name, path):
        simple = _last(name)
        scope = scopes.get(path)
        if scope is not None and simple in scope.aliases:
            aliased = [value for kind, value in scope.aliases[simple] if value["kind"] in TYPE_KINDS]
            if aliased:
                return aliased
        return best(types_by_name.get(simple, []), path)

    # Members declared outside their type body (Go receivers, C++ Type::method,
    # Rust impl blocks, Swift extensions) are attached to a uniquely named type.
    for symbol in symbols:
        declared = symbol.get("declared_owner")
        if declared:
            found = lookup_type(declared, symbol["path"])
            if len(found) == 1:
                symbol["owner_id"] = found[0]["id"]
                symbol["owner_resolution"] = "candidate"
            else:
                symbol["owner_resolution"] = "ambiguous" if found else "unresolved"
        if symbol.get("owner_id"):
            members[symbol["owner_id"]].append(symbol)

    total = len(symbols) + len(calls)
    parents = defaultdict(list)
    for current, symbol in enumerate(symbols, start=1):
        checkpoint()
        if on_progress:
            on_progress(current, total, symbol["path"])
        evidence = {"path": symbol["path"], "start_line": symbol["start_line"]}
        if symbol.get("owner_id"):
            if symbol.get("owner_resolution") == "candidate":
                add_edge(symbol["owner_id"], symbol["id"], "CONTAINS", {**evidence, "strategy": "declared_owner"}, symbol["language"], "candidate")
            else:
                add_edge(symbol["owner_id"], symbol["id"], "CONTAINS", evidence, symbol["language"], "syntax")
        for base in symbol.get("bases", []):
            targets = [target for target in lookup_type(base.get("type", ""), symbol["path"]) if target["id"] != symbol["id"]]
            status = "candidate" if len(targets) == 1 else "ambiguous"
            for target in targets[:MAX_TARGETS]:
                relation = "IMPLEMENTS" if target["kind"] == "interface" and symbol["kind"] != "interface" else ("EXTENDS" if base.get("kind") in {"INHERITS", None} else base["kind"])
                parents[symbol["id"]].append(target["id"])
                add_edge(symbol["id"], target["id"], relation, {**evidence, "base": base.get("type", "")}, symbol["language"], status)
    for entry in parsed_files:
        for relation in entry.get("relations", []):
            owners = lookup_type(relation["type"], entry["path"])
            bases = lookup_type(relation["base"], entry["path"])
            for owner in owners[:1] if len(owners) == 1 else []:
                for base in bases[:MAX_TARGETS]:
                    kind = "IMPLEMENTS" if base["kind"] == "interface" else "EXTENDS"
                    parents[owner["id"]].append(base["id"])
                    add_edge(owner["id"], base["id"], kind, {"path": entry["path"], "start_line": relation["line"], "strategy": "impl_block"}, entry["language"], "candidate" if len(bases) == 1 else "ambiguous")

    def enclosing_type(symbol):
        seen = set()
        while symbol is not None and symbol["id"] not in seen:
            seen.add(symbol["id"])
            if symbol["kind"] in TYPE_KINDS:
                return symbol
            symbol = by_id.get(symbol.get("owner_id"))
        return None

    def methods_of(type_symbols, name, count):
        """Closest declarations named ``name`` in the types or their ancestors."""
        frontier, seen = [item["id"] for item in type_symbols], set()
        for _ in range(8):
            level_named, next_frontier = [], []
            for type_id in frontier:
                if type_id in seen:
                    continue
                seen.add(type_id)
                level_named.extend(member for member in members.get(type_id, []) if member["name"] == name and member["kind"] in CALLABLE_KINDS)
                next_frontier.extend(parents.get(type_id, []))
            if level_named:
                matching = [member for member in level_named if _arity_ok(member, count)]
                return matching or level_named, not matching
            frontier = next_frontier
            if not frontier:
                break
        return [], False

    def bindings(symbol):
        return {SELF_PREFIX.sub("", key): value for key, value in (symbol or {}).get("bindings", {}).items()}

    def constructors(type_symbols, count):
        found = [member for item in type_symbols for member in members.get(item["id"], []) if member["kind"] == "constructor"]
        matching = [member for member in found if _arity_ok(member, count)]
        return matching or found or list(type_symbols)

    def scoped_functions(name, path, count, language):
        """Plain function calls: same file, imported names, same directory, then the family."""
        scope = scopes.get(path)
        pools = []
        local = [item for item in callables_by_name.get(name, []) if item["path"] == path and item["kind"] == "function"]
        pools.append(("same_file", local))
        if scope is not None and name in scope.aliases:
            pools.append(("import", [value for kind, value in scope.aliases[name] if value["kind"] in CALLABLE_KINDS]))
        if scope is not None and scope.modules:
            pools.append(("import", [item for item in callables_by_name.get(name, []) if item["path"] in scope.modules and item["kind"] == "function"]))
        directory = posixpath.dirname(path)
        pools.append(("same_package", [item for item in callables_by_name.get(name, []) if posixpath.dirname(item["path"]) == directory and item["kind"] == "function"]))
        if scope is not None and name in scope.external:
            return [], "external_import", False
        pools.append(("name_arity", [item for item in callables_by_name.get(name, []) if item["kind"] == "function"]))
        for strategy, pool in pools:
            if pool:
                matching = [item for item in pool if _arity_ok(item, count)]
                return matching or pool, strategy, not matching
        return [], "name_arity", False

    def resolve_call(call):
        caller = by_id.get(call.get("caller_id"))
        path, language = call["path"], call["language"]
        name, count = call["name"], call.get("arg_count", len(call.get("arguments", [])))
        receiver = (call.get("receiver") or "").strip()
        owner = enclosing_type(caller)
        self_names = SELF_NAMES.get(language, set()) | set((caller or {}).get("self_names", []))
        scope = scopes.get(path)

        if call.get("kind") == "constructor":
            type_name = receiver if receiver and name == "new" else name
            found = lookup_type(type_name, path)
            return (constructors(found, count), "constructor", False) if found else ([], "external_type", False)

        if not receiver:
            if language in IMPLICIT_RECEIVER and owner is not None:
                found, relaxed = methods_of([owner], name, count)
                if found:
                    return found, "implicit_receiver", relaxed
            if name in types_by_name and name not in callables_by_name:
                found = lookup_type(name, path)
                if found:
                    return constructors(found, count), "constructor", False
            return scoped_functions(name, path, count, language)

        type_symbols, strategy = None, ""
        bare = receiver.removeprefix("(").removesuffix(")")
        if bare in self_names or (caller and bare in caller.get("self_names", [])):
            type_symbols, strategy = ([owner] if owner else []), "self"
        elif bare in SUPER_NAMES:
            type_symbols = [by_id[item] for item in parents.get(owner["id"], [])] if owner else []
            strategy = "super"
        else:
            for pattern in CONSTRUCTED:
                match = pattern.match(bare)
                if match and _last(match.group(1)) in types_by_name:
                    type_symbols, strategy = lookup_type(match.group(1), path), "constructed_receiver"
                    break
        if type_symbols is None:
            key = SELF_PREFIX.sub("", bare).lstrip("$")
            declared = ""
            if not SELF_PREFIX.match(bare):
                declared = bindings(caller).get(key, "")
            if not declared and owner is not None:
                declared = bindings(owner).get(key, "")
            if declared:
                found = lookup_type(declared, path)
                if not found:
                    return [], "external_type", False
                type_symbols, strategy = found, "receiver_type"
        if type_symbols is None and scope is not None and bare in scope.aliases:
            modules = [value for kind, value in scope.aliases[bare] if kind == "module"]
            typed = [value for kind, value in scope.aliases[bare] if value["kind"] in TYPE_KINDS]
            if modules:
                module_paths = {item["path"] for item in modules}
                found = [item for item in callables_by_name.get(name, []) if item["path"] in module_paths and by_id.get(item.get("owner_id"), {}).get("kind") in {"module", "namespace"}]
                if language == "go":
                    directories = {posixpath.dirname(item) for item in module_paths}
                    found = [item for item in callables_by_name.get(name, []) if posixpath.dirname(item["path"]) in directories and item["kind"] == "function"]
                matching = [item for item in found if _arity_ok(item, count)]
                return matching or found, "module_alias", bool(found) and not matching
            if typed:
                type_symbols, strategy = typed, "static_type"
        if type_symbols is None and scope is not None and bare.split(".")[0].split("::")[0] in scope.external:
            return [], "external_receiver", False
        if type_symbols is None:
            simple = _last(bare)
            if simple and simple == bare.split("::")[-1].split(".")[-1] and simple in types_by_name and (simple[:1].isupper() or "::" in bare):
                type_symbols, strategy = lookup_type(bare, path), "static_type"
        if type_symbols is None and language == "rust" and "::" in bare:
            module_name = bare.split("::")[-1]
            if scope is not None and module_name in scope.aliases:
                module_paths = {value["path"] for kind, value in scope.aliases[module_name] if kind == "module"}
                found = [item for item in callables_by_name.get(name, []) if item["path"] in module_paths]
                return found, "module_alias", False
        if type_symbols is not None:
            if not type_symbols:
                return [], strategy or "receiver_type", False
            found, relaxed = methods_of(type_symbols, name, count)
            return found, strategy if found else strategy + "_no_member", relaxed
        candidates = [item for item in callables_by_name.get(name, []) if item["kind"] in {"method", "function"}]
        matching = [item for item in candidates if _arity_ok(item, count)]
        return matching, "name_arity", False

    for current, call in enumerate(calls, start=len(symbols) + 1):
        checkpoint()
        if on_progress:
            on_progress(current, total, call["path"])
        found, strategy, relaxed = resolve_call(call)
        unique = {item["id"]: item for item in found}
        ordered = sorted(unique.values(), key=lambda item: (rank(item, call["path"]), item["qualified_name"], item["id"]))
        call["targets"] = [item["id"] for item in ordered[:MAX_TARGETS]]
        call["target_count"] = len(ordered)
        call["status"] = "candidate" if len(ordered) == 1 else "ambiguous" if ordered else "unresolved"
        call["strategy"] = strategy
        if relaxed:
            call["arity_relaxed"] = True
        for target_id in call["targets"]:
            add_edge(call["caller_id"], target_id, "CALLS", {"path": call["path"], "start_line": call["start_line"], "call_id": call["id"]}, call["language"], call["status"])

    for edge in [item for item in edges if item["kind"] in {"EXTENDS", "IMPLEMENTS"}]:
        for child in members.get(edge["src_id"], []):
            if child["kind"] not in CALLABLE_KINDS or child["kind"] == "constructor":
                continue
            for parent in members.get(edge["dst_id"], []):
                if parent["kind"] in CALLABLE_KINDS and parent["name"] == child["name"] and parent.get("arity") == child.get("arity"):
                    add_edge(child["id"], parent["id"], "OVERRIDES", {"path": child["path"], "start_line": child["start_line"]}, child["language"])
    return symbols, calls, edges, {"unresolved": dict(unresolved_imports), "external": dict(external_imports)}
