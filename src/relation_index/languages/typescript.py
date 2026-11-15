"""TypeScript frontend (tree-sitter-typescript, TS and TSX grammars)."""

import importlib

from tree_sitter import Language

from .javascript import EcmaScriptFrontend
from .treesitter import child_of_type, text


class TypeScriptFrontend(EcmaScriptFrontend):
    name = "typescript"
    extensions = (".ts", ".tsx", ".mts", ".cts")
    VERSION = "typescript-syntax-v2-ts0.25-typescript0.23"
    RULES_VERSION = "typescript-rules-v2"
    grammar = ("tree_sitter_typescript", "language_typescript")
    containers = {
        **EcmaScriptFrontend.containers,
        "abstract_class_declaration": "class", "interface_declaration": "interface",
        "enum_declaration": "enum", "internal_module": "namespace", "module": "namespace",
    }
    callables = {
        **EcmaScriptFrontend.callables,
        "method_signature": "method", "abstract_method_signature": "method",
    }

    def __init__(self):
        super().__init__()
        self._tsx = None
        if self._language is not None:
            try:
                self._tsx = Language(importlib.import_module("tree_sitter_typescript").language_tsx())
            except Exception:
                self._tsx = None

    def language_for(self, path):
        if path.lower().endswith(".tsx") and self._tsx is not None:
            return self._tsx
        return self._language

    def bases(self, node):
        if node.type == "interface_declaration":
            clause = child_of_type(node, "extends_type_clause")
            return [{"type": text(item), "kind": "EXTENDS"} for item in (clause.named_children if clause else [])]
        return super().bases(node)


frontend = TypeScriptFrontend()
