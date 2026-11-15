"""Python frontend (tree-sitter-python)."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, text


def _callee_type(node) -> str:
    if node is not None and node.type == "call":
        return simple_type(text(field(node, "function")))
    return ""


class PythonFrontend(TreeSitterFrontend):
    name = "python"
    extensions = (".py", ".pyi")
    VERSION = "python-syntax-v2-ts0.25-python0.25"
    RULES_VERSION = "python-rules-v2"
    grammar = ("tree_sitter_python", "language")
    self_names = frozenset({"self", "cls"})
    constructor_names = frozenset({"__init__"})
    containers = {"class_definition": "class"}
    callables = {"function_definition": "function"}
    call_nodes = frozenset({"call"})
    import_nodes = frozenset({"import_statement", "import_from_statement"})

    def parameter(self, node):
        kind = node.type
        if kind in {"keyword_separator", "positional_separator", "comment"}:
            return None
        variadic = kind in {"list_splat_pattern", "dictionary_splat_pattern"}
        if kind == "identifier":
            name_node = node
        elif kind in {"default_parameter", "typed_default_parameter"}:
            name_node = field(node, "name")
        else:
            name_node = child_of_type(node, "identifier") or field(node, "name")
            if name_node is not None and name_node.type in {"list_splat_pattern", "dictionary_splat_pattern"}:
                variadic = True
                name_node = child_of_type(name_node, "identifier")
        return {
            "name": text(name_node),
            "type": text(field(node, "type")),
            "default": text(field(node, "value")),
            "variadic": variadic,
            "receiver": False,
            "annotations": [],
        }

    def parameters(self, node):
        values = super().parameters(node)
        if values and values[0]["name"] in self.self_names:
            values[0]["receiver"] = True
        return values

    def bases(self, node):
        values = []
        for item in (field(node, "superclasses").named_children if field(node, "superclasses") else []):
            if item.type in {"identifier", "attribute", "subscript"}:
                values.append({"type": text(item), "kind": "INHERITS"})
        return values

    def call_info(self, node):
        function = field(node, "function")
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type != "comment"] if arguments else []
        if function is None:
            return None
        if function.type == "attribute":
            return {"name": text(field(function, "attribute")), "receiver": text(field(function, "object")), "args": args, "kind": "method"}
        if function.type == "identifier":
            return {"name": text(function), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        line, raw = node.start_point.row + 1, text(node)
        entries = []
        if node.type == "import_statement":
            for item in node.children_by_field_name("name"):
                module = text(field(item, "name")) if item.type == "aliased_import" else text(item)
                alias = text(field(item, "alias")) if item.type == "aliased_import" else ""
                entries.append({"module": module, "names": [], "alias": alias, "name": module.split(".")[-1], "line": line, "kind": node.type, "raw": raw})
            return entries
        module = text(field(node, "module_name"))
        names = []
        for item in node.children_by_field_name("name"):
            if item.type == "aliased_import":
                names.append({"name": text(field(item, "name")), "alias": text(field(item, "alias"))})
            else:
                names.append({"name": text(item), "alias": ""})
        if child_of_type(node, "wildcard_import") is not None:
            names.append({"name": "*", "alias": ""})
        return [{"module": module, "names": names, "alias": "", "name": names[0]["name"] if names else "", "line": line, "kind": node.type, "raw": raw}]

    def binding(self, node):
        if node.type != "assignment":
            return None
        left, right = field(node, "left"), field(node, "right")
        if left is None or left.type != "identifier":
            return None
        declared = simple_type(text(field(node, "type")))
        return text(left), declared or _callee_type(right)

    def field_binding(self, node):
        if node.type != "assignment":
            return []
        left, right = field(node, "left"), field(node, "right")
        if left is not None and left.type == "attribute" and text(field(left, "object")) in self.self_names:
            value = simple_type(text(field(node, "type"))) or _callee_type(right)
            return [("self." + text(field(left, "attribute")), value)] if value else []
        if left is not None and left.type == "identifier" and node.parent is not None and node.parent.parent is not None and node.parent.parent.type == "block" and node.parent.parent.parent is not None and node.parent.parent.parent.type == "class_definition":
            value = simple_type(text(field(node, "type"))) or _callee_type(right)
            return [("self." + text(left), value)] if value else []
        return []


frontend = PythonFrontend()
