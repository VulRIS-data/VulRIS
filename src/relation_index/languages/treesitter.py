"""Shared tree-sitter extraction for the non-Java frontends.

Each language module subclasses :class:`TreeSitterFrontend` and overrides a few
hooks (names, parameters, calls, imports, bases, type bindings). The output is
syntax only: declarations, source spans, call expressions and declared types.
Cross-file linking happens later in ``relation_index.resolver``.
"""

from __future__ import annotations

import importlib
import re
from pathlib import PurePosixPath
from typing import Any

from tree_sitter import Language, Parser

from ..storage import digest
from .base import CALLABLE_KINDS, TYPE_KINDS

STRING_RE = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`([^`$\\]*)`')
IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
ANNOTATION_NODES = {"decorator", "annotation", "marker_annotation", "attribute", "attribute_item"}
ANNOTATION_GROUPS = {"modifiers", "attribute_list", "attribute_group", "attributes"}
ANONYMOUS_PARENTS = {
    "variable_declarator", "assignment", "assignment_expression", "pair",
    "property_declaration", "let_declaration", "short_var_declaration",
}


def walk(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def field(node, *names):
    if node is None:
        return None
    for name in names:
        value = node.child_by_field_name(name)
        if value is not None:
            return value
    return None


def child_of_type(node, *types):
    if node is None:
        return None
    return next((child for child in node.named_children if child.type in types), None)


def strings_in(value: str) -> list[str]:
    return [next(group for group in match.groups() if group is not None) for match in STRING_RE.finditer(value)]


def split_arguments(inner: str) -> list[str]:
    """Split ``a, f(b, c), "x,y"`` at top-level commas."""
    parts, depth, current, quote = [], 0, [], ""
    for char in inner:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "\"'`":
            quote = char
        elif char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return parts


def simple_type(value: str) -> str:
    """Return the last identifier of a declared type, without generics or pointers."""
    value = re.sub(r"<.*>|\[.*\]|\(.*\)", "", value or "")
    value = re.sub(r"\b(const|mut|struct|class|enum|ref|out|in|dyn|impl|readonly|volatile|unsigned|signed)\b", " ", value)
    value = value.strip(" \t*&?!:;=")
    segments = [segment for segment in re.split(r"[.:\\/\s]+", value) if segment]
    last = segments[-1] if segments else ""
    return last if IDENT_RE.fullmatch(last) else ""


def module_name(path: str) -> str:
    value = PurePosixPath(path)
    parts = list(value.with_suffix("").parts)
    if parts and parts[-1] in {"__init__", "index", "mod"}:
        parts = parts[:-1]
    return ".".join(parts) or value.stem


class TreeSitterFrontend:
    name = ""
    extensions: tuple[str, ...] = ()
    VERSION = ""
    RULES_VERSION = ""
    grammar = ("", "language")
    separator = "."
    member_separator: str | None = None
    module_prefix = True
    module_keeps_extension = False
    implicit_receiver = False
    self_names: frozenset[str] = frozenset()
    constructor_names: frozenset[str] = frozenset()
    containers: dict[str, str] = {}
    callables: dict[str, str] = {}
    call_nodes: frozenset[str] = frozenset()
    import_nodes: frozenset[str] = frozenset()
    namespace_statements: frozenset[str] = frozenset()
    parameter_containers = frozenset({
        "parameters", "formal_parameters", "parameter_list", "method_parameters",
        "function_value_parameters", "lambda_parameters", "value_parameters",
    })

    def __init__(self):
        self._language = None
        self._error: str | None = None
        try:
            module = importlib.import_module(self.grammar[0])
            self._language = Language(getattr(module, self.grammar[1])())
        except Exception as exc:  # a missing grammar must not stop other languages
            self._error = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ status
    def available(self) -> bool:
        return self._language is not None

    def unavailable_reason(self) -> str | None:
        return self._error

    def language_for(self, path: str):
        return self._language

    # ------------------------------------------------------------------ hooks
    def classify(self, node) -> str | None:
        return self.containers.get(node.type) or self.callables.get(node.type)

    def refine_kind(self, kind: str, name: str, owner: dict, declared_owner: str | None) -> str:
        if kind == "function" and (owner["kind"] in TYPE_KINDS or declared_owner):
            kind = "method"
        if kind == "method" and (name in self.constructor_names or (owner["kind"] in TYPE_KINDS and name == owner["name"])):
            kind = "constructor"
        return kind

    def symbol_name(self, node, kind: str) -> str:
        return text(field(node, "name")).strip()

    def anonymous_name(self, node) -> str:
        parent = node.parent
        if parent is not None and parent.type in ANONYMOUS_PARENTS:
            target = field(parent, "name", "left", "key", "pattern")
            if target is not None and target.id != node.id:
                value = text(target).strip()
                if IDENT_RE.fullmatch(value.lstrip("$")):
                    return value.lstrip("$")
        return f"<anonymous@{node.start_point.row + 1}>"

    def declared_owner(self, node, kind: str) -> str | None:
        return None

    def transparent(self, node) -> tuple[str, list[str]] | None:
        """Blocks such as Rust ``impl`` or Swift ``extension`` add members to a type."""
        return None

    def package_name(self, root) -> str:
        return ""

    def parameter_container(self, node):
        container = field(node, "parameters")
        if container is None:
            container = child_of_type(node, *self.parameter_containers)
        return container

    def parameter(self, node) -> dict[str, Any] | None:
        if not node.is_named or node.type in {"comment", "attribute_list", "decorator"}:
            return None
        name_node = field(node, "name", "pattern") or node
        name = text(name_node).strip()
        if not IDENT_RE.fullmatch(name.lstrip("$*&.")):
            identifiers = [part for part in walk(name_node) if part.type in {"identifier", "simple_identifier", "variable_name"}]
            name = text(identifiers[0]) if identifiers else ""
        raw = text(node)
        return {
            "name": name.lstrip("$*&."),
            "type": text(field(node, "type")).lstrip(": ").strip(),
            "default": text(field(node, "value", "default_value", "default")),
            "variadic": raw.lstrip().startswith(("*", "...")) or "..." in raw.split(":")[0],
            "receiver": False,
            "annotations": self.annotations(node),
        }

    def parameters(self, node) -> list[dict[str, Any]]:
        container = self.parameter_container(node)
        values = []
        for child in container.named_children if container is not None else []:
            item = self.parameter(child)
            if item and item["name"]:
                values.append(item)
        return values

    def bases(self, node) -> list[dict[str, str]]:
        return []

    def call_info(self, node) -> dict[str, Any] | None:
        return None

    def import_entries(self, node) -> list[dict[str, Any]]:
        return []

    def import_call(self, call: dict[str, Any], node) -> list[dict[str, Any]]:
        """Calls such as ``require("x")`` that act as imports."""
        return []

    def binding(self, node) -> tuple[str, str] | None:
        """A local declaration ``name -> declared or constructed type``."""
        return None

    def field_binding(self, node) -> list[tuple[str, str]]:
        return []

    def body(self, node):
        return field(node, "body")

    def extra_relations(self, node) -> list[dict[str, Any]]:
        return []

    # ------------------------------------------------------------------ helpers
    def annotation_nodes(self, node) -> list:
        found = []

        def collect(item):
            if item.type in ANNOTATION_NODES:
                found.append(item)
            elif item.type in ANNOTATION_GROUPS:
                for child in item.named_children:
                    collect(child)

        for child in node.named_children:
            collect(child)
        sibling = node.prev_named_sibling
        while sibling is not None and (sibling.type in ANNOTATION_NODES or sibling.type in {"attribute_list", "comment"}):
            if sibling.type != "comment":
                collect(sibling)
            sibling = sibling.prev_named_sibling
        parent = node.parent
        if parent is not None and parent.type in {"decorated_definition", "export_statement"}:
            for child in parent.named_children:
                if child.id != node.id:
                    collect(child)
        return sorted(found, key=lambda item: item.start_byte)

    def annotations(self, node) -> list[dict[str, Any]]:
        result = []
        for item in self.annotation_nodes(node):
            raw = text(item).strip()
            body = raw.lstrip("@#![ \t").rstrip("] \t")
            match = re.match(r"([\w.:\\$]+)", body)
            name = match.group(1) if match else ""
            inner = ""
            if "(" in body:
                inner = body[body.index("(") + 1 : body.rindex(")") if ")" in body else len(body)]
            result.append({
                "name": name,
                "text": raw,
                "args": split_arguments(inner),
                "strings": strings_in(inner),
                "line": item.start_point.row + 1,
            })
        return result

    def bindings_in(self, node) -> dict[str, str]:
        values = {}
        if node is None:
            return values
        for item in walk(node):
            found = self.binding(item)
            if found and found[0] and found[1] and found[0] not in values:
                values[found[0]] = found[1]
        return values

    # ------------------------------------------------------------------ extract
    def extract(self, path: str, content: bytes) -> dict[str, Any]:
        if self._language is None:
            raise RuntimeError(self._error or f"{self.name} parser unavailable")
        root = Parser(self.language_for(path)).parse(content).root_node
        module = path if self.module_keeps_extension else module_name(path)
        package = self.package_name(root)
        symbols: list[dict[str, Any]] = []
        calls: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        anchors: dict[str, int] = {}
        member_separator = self.member_separator or self.separator
        module_id = digest([self.name, path, "module", module])[:24]
        module_symbol = {
            "id": module_id, "path": path, "kind": "module",
            "name": PurePosixPath(path).name if self.module_keeps_extension else module.split(".")[-1],
            "qualified_name": module, "owner_id": None,
            "signature": path, "start_line": 1, "end_line": max(1, content.count(b"\n") + 1),
            "language": self.name, "provenance": self.VERSION, "package": package,
            "parameters": [], "decorators": [], "bases": [], "arity": {"min": 0, "max": 0},
            "self_names": [], "bindings": {},
        }
        symbols.append(module_symbol)
        anchors[module_id] = 0

        def sid(node, kind, name):
            return digest([self.name, path, node.start_byte, node.end_byte, kind, name])[:24]

        def qualify(owner, declared, name):
            if owner["kind"] == "module":
                prefix = module if self.module_prefix else package
                parts = [prefix, declared] if declared else [prefix]
                head = self.separator.join(filter(None, parts))
                sep = member_separator if declared else self.separator
            else:
                head = owner["qualified_name"]
                if declared:
                    head = head + self.separator + declared
                sep = member_separator if (owner["kind"] in TYPE_KINDS or declared) else self.separator
            return sep.join(filter(None, [head, name])) if head else name

        def make_symbol(node, kind, owner, declared):
            name = self.symbol_name(node, kind)
            if not name and kind in CALLABLE_KINDS:
                name = self.anonymous_name(node)
            if not name:
                return None
            declared = self.declared_owner(node, kind) or declared
            kind = self.refine_kind(kind, name, owner, declared)
            body = self.body(node)
            params = self.parameters(node) if kind in CALLABLE_KINDS else []
            counted = [item for item in params if not item["receiver"]]
            variadic = any(item["variadic"] for item in counted)
            signature_end = body.start_byte if body is not None and body.start_byte > node.start_byte else node.end_byte
            symbol = {
                "id": sid(node, kind, name), "path": path, "kind": kind, "name": name,
                "qualified_name": qualify(owner, declared, name), "owner_id": owner["id"],
                "signature": " ".join(content[node.start_byte:signature_end].decode("utf-8", errors="replace").split())[:500],
                "start_line": node.start_point.row + 1, "end_line": node.end_point.row + 1,
                "language": self.name, "provenance": self.VERSION,
                "parameters": [{key: value for key, value in item.items()} for item in params],
                "decorators": self.annotations(node),
                "bases": self.bases(node) if kind in TYPE_KINDS else [],
                "arity": {
                    "min": len([item for item in counted if not item["default"] and not item["variadic"]]),
                    "max": None if variadic else len(counted),
                },
                "self_names": [item["name"] for item in params if item["receiver"]],
                "bindings": {},
            }
            if declared:
                symbol["declared_owner"] = declared
            if kind in CALLABLE_KINDS:
                bindings = {item["name"]: item["type"] for item in counted if item["type"]}
                for key, value in self.bindings_in(body).items():
                    bindings.setdefault(key, value)
                symbol["bindings"] = bindings
            elif kind in TYPE_KINDS:
                values = {}
                for item in walk(node):
                    for key, value in self.field_binding(item):
                        values.setdefault(key, value)
                symbol["bindings"] = values
            symbols.append(symbol)
            anchors[symbol["id"]] = node.start_byte
            return symbol

        def visit(node, owner, current, declared):
            created = None
            child_owner, child_current, child_declared = owner, current, declared
            transparent = self.transparent(node)
            if transparent:
                child_declared = transparent[0]
                for trait in transparent[1]:
                    relations.append({"type": transparent[0], "base": trait, "kind": "IMPLEMENTS", "line": node.start_point.row + 1})
            kind = None if transparent else self.classify(node)
            if kind:
                scope = current if (current is not None and kind in CALLABLE_KINDS) else owner
                created = make_symbol(node, kind, scope, declared if scope is owner else None)
                if created is not None:
                    if created["kind"] in CALLABLE_KINDS:
                        child_owner, child_current, child_declared = created, created, None
                    else:
                        child_owner, child_current, child_declared = created, None, None
            relations.extend(self.extra_relations(node))
            if node.type in self.import_nodes:
                imports.extend(self.import_entries(node))
            if node.type in self.call_nodes:
                info = self.call_info(node)
                if info and info.get("name"):
                    linked = self.import_call(info, node)
                    if linked:
                        imports.extend(linked)
                    else:
                        caller = current or module_symbol
                        call_id = sid(node, "call", info["name"])
                        args = info.get("args", [])
                        calls.append({
                            "id": call_id, "caller_id": caller["id"], "path": path,
                            "start_line": node.start_point.row + 1, "end_line": node.end_point.row + 1,
                            "column": node.start_point.column, "name": info["name"],
                            "receiver": info.get("receiver", ""), "expression": text(node)[:500],
                            "arguments": [value[:200] for value in args], "arg_count": len(args),
                            "kind": info.get("kind") or ("method" if info.get("receiver") else "function"),
                            "status": "unresolved", "targets": [], "target_count": 0,
                            "strategy": "syntax", "language": self.name, "provenance": self.VERSION,
                        })
                        anchors[call_id] = node.start_byte
            for child in node.named_children:
                result = visit(child, child_owner, child_current, child_declared)
                if (
                    result is not None and result["kind"] == "namespace"
                    and child.type in self.namespace_statements and field(child, "body") is None
                ):
                    child_owner = result
            return created

        visit(root, module_symbol, None, None)
        return {
            "language": self.name, "parser_version": self.VERSION, "rules_version": self.RULES_VERSION,
            "path": path, "module": module, "package": package, "imports": imports,
            "symbols": symbols, "calls": calls, "relations": relations, "facts": [],
            "parse_error": root.has_error, "anchors": anchors,
        }
