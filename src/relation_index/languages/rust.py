"""Rust frontend (tree-sitter-rust)."""

from .treesitter import TreeSitterFrontend, field, simple_type, text


class RustFrontend(TreeSitterFrontend):
    name = "rust"
    extensions = (".rs",)
    VERSION = "rust-syntax-v2-ts0.25-rust0.24"
    RULES_VERSION = "rust-rules-v2"
    grammar = ("tree_sitter_rust", "language")
    separator = "::"
    module_prefix = False
    self_names = frozenset({"self", "Self"})
    containers = {
        "struct_item": "struct", "union_item": "struct", "enum_item": "enum",
        "trait_item": "interface", "mod_item": "namespace",
    }
    callables = {"function_item": "function", "function_signature_item": "method"}
    call_nodes = frozenset({"call_expression"})
    import_nodes = frozenset({"use_declaration", "mod_item"})

    def classify(self, node):
        if node.type == "mod_item" and field(node, "body") is None:
            return None
        return super().classify(node)

    def transparent(self, node):
        if node.type != "impl_item":
            return None
        owner = simple_type(text(field(node, "type")))
        trait = simple_type(text(field(node, "trait")))
        return (owner, [trait] if trait else []) if owner else None

    def refine_kind(self, kind, name, owner, declared_owner):
        if kind == "function" and (declared_owner or owner["kind"] == "interface"):
            return "method"
        return kind

    def parameter(self, node):
        if node.type == "self_parameter":
            return {"name": "self", "type": "Self", "default": "", "variadic": False, "receiver": True, "annotations": []}
        if node.type == "variadic_parameter":
            return {"name": "...", "type": "", "default": "", "variadic": True, "receiver": False, "annotations": []}
        if node.type != "parameter":
            return None
        pattern = field(node, "pattern")
        name = text(pattern) if pattern is not None and pattern.type == "identifier" else text(pattern)
        return {"name": name.removeprefix("mut ").strip(), "type": text(field(node, "type")), "default": "", "variadic": False, "receiver": False, "annotations": []}

    def bases(self, node):
        if node.type != "trait_item":
            return []
        bounds = field(node, "bounds")
        return [{"type": text(item), "kind": "EXTENDS"} for item in (bounds.named_children if bounds is not None else [])]

    def call_info(self, node):
        function = field(node, "function")
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type not in {"line_comment", "block_comment"}] if arguments else []
        if function is not None and function.type == "generic_function":
            function = field(function, "function")
        if function is None:
            return None
        if function.type == "field_expression":
            return {"name": text(field(function, "field")), "receiver": text(field(function, "value")), "args": args, "kind": "method"}
        if function.type == "scoped_identifier":
            return {"name": text(field(function, "name")), "receiver": text(field(function, "path")), "args": args, "kind": "method"}
        if function.type == "identifier":
            return {"name": text(function), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        line, raw = node.start_point.row + 1, text(node)
        if node.type == "mod_item":
            if field(node, "body") is not None:
                return []
            name = text(field(node, "name"))
            return [{"module": "self::" + name, "names": [], "alias": name, "name": name, "line": line, "kind": "mod", "raw": raw}]
        entries = []

        def expand(item, prefix):
            if item is None:
                return
            if item.type in {"scoped_identifier", "identifier", "crate", "self", "super"}:
                path = "::".join(filter(None, [prefix, text(item)]))
                module, _, name = path.rpartition("::")
                entries.append({"module": module, "names": [{"name": name, "alias": ""}], "alias": "", "name": name, "line": line, "kind": "use", "raw": raw})
            elif item.type == "use_as_clause":
                path = "::".join(filter(None, [prefix, text(field(item, "path"))]))
                module, _, name = path.rpartition("::")
                entries.append({"module": module, "names": [{"name": name, "alias": text(field(item, "alias"))}], "alias": "", "name": name, "line": line, "kind": "use", "raw": raw})
            elif item.type == "scoped_use_list":
                base = "::".join(filter(None, [prefix, text(field(item, "path"))]))
                for child in (field(item, "list").named_children if field(item, "list") is not None else []):
                    expand(child, base)
            elif item.type == "use_list":
                for child in item.named_children:
                    expand(child, prefix)
            elif item.type == "use_wildcard":
                path = "::".join(filter(None, [prefix, text(item).removesuffix("::*")]))
                entries.append({"module": path, "names": [{"name": "*", "alias": ""}], "alias": "", "name": "*", "line": line, "kind": "use", "raw": raw})

        expand(field(node, "argument"), "")
        return entries

    def _value_type(self, value):
        if value is None:
            return ""
        if value.type == "call_expression":
            function = field(value, "function")
            if function is not None and function.type == "scoped_identifier":
                return simple_type(text(field(function, "path")))
        if value.type == "struct_expression":
            return simple_type(text(field(value, "name")))
        return ""

    def binding(self, node):
        if node.type != "let_declaration":
            return None
        pattern = field(node, "pattern")
        if pattern is None or pattern.type != "identifier":
            return None
        return text(pattern), simple_type(text(field(node, "type"))) or self._value_type(field(node, "value"))

    def field_binding(self, node):
        if node.type == "field_declaration" and field(node, "name") is not None:
            value = simple_type(text(field(node, "type")))
            return [("self." + text(field(node, "name")), value)] if value else []
        return []


frontend = RustFrontend()
