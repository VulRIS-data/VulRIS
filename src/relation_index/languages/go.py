"""Go frontend (tree-sitter-go)."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, strings_in, text


class GoFrontend(TreeSitterFrontend):
    name = "go"
    extensions = (".go",)
    VERSION = "go-syntax-v2-ts0.25-go0.25"
    RULES_VERSION = "go-rules-v2"
    grammar = ("tree_sitter_go", "language")
    module_prefix = False
    containers = {"type_spec": "struct"}
    callables = {"function_declaration": "function", "method_declaration": "method", "func_literal": "function"}
    call_nodes = frozenset({"call_expression"})
    import_nodes = frozenset({"import_spec"})

    def package_name(self, root):
        clause = child_of_type(root, "package_clause")
        return text(child_of_type(clause, "package_identifier")) if clause is not None else ""

    def classify(self, node):
        if node.type == "type_spec":
            kind = (field(node, "type").type if field(node, "type") is not None else "")
            return {"struct_type": "struct", "interface_type": "interface"}.get(kind)
        return super().classify(node)

    def declared_owner(self, node, kind):
        if node.type != "method_declaration":
            return None
        receiver = field(node, "receiver")
        declaration = child_of_type(receiver, "parameter_declaration")
        return simple_type(text(field(declaration, "type"))) or None

    def _declarations(self, container, receiver=False):
        values = []
        for item in container.named_children if container is not None else []:
            if item.type not in {"parameter_declaration", "variadic_parameter_declaration"}:
                continue
            type_text = text(field(item, "type"))
            names = item.children_by_field_name("name") or [None]
            for name in names:
                values.append({
                    "name": text(name) if name is not None else "_",
                    "type": type_text, "default": "",
                    "variadic": item.type == "variadic_parameter_declaration",
                    "receiver": receiver, "annotations": [],
                })
        return values

    def parameters(self, node):
        values = []
        if node.type == "method_declaration":
            values.extend(self._declarations(field(node, "receiver"), receiver=True))
        values.extend(self._declarations(field(node, "parameters")))
        return values

    def bases(self, node):
        values = []
        struct = field(node, "type")
        fields = child_of_type(struct, "field_declaration_list")
        for item in fields.named_children if fields is not None else []:
            if item.type == "field_declaration" and field(item, "name") is None:
                values.append({"type": text(field(item, "type")).lstrip("*"), "kind": "EXTENDS", "note": "struct embedding"})
        return values

    def call_info(self, node):
        function = field(node, "function")
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type != "comment"] if arguments else []
        if function is None:
            return None
        if function.type == "selector_expression":
            return {"name": text(field(function, "field")), "receiver": text(field(function, "operand")), "args": args, "kind": "method"}
        if function.type == "identifier":
            return {"name": text(function), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        path = strings_in(text(field(node, "path")))
        if not path:
            return []
        alias = text(field(node, "name"))
        return [{"module": path[0], "names": [], "alias": alias or path[0].rsplit("/", 1)[-1], "name": path[0].rsplit("/", 1)[-1], "line": node.start_point.row + 1, "kind": node.type, "raw": text(node)}]

    def _value_type(self, value):
        if value is None:
            return ""
        if value.type == "unary_expression":
            value = field(value, "operand")
        if value is not None and value.type == "composite_literal":
            return simple_type(text(field(value, "type")))
        return ""

    def binding(self, node):
        if node.type == "short_var_declaration":
            left, right = field(node, "left"), field(node, "right")
            if left is not None and right is not None and len(left.named_children) == 1 and len(right.named_children) == 1:
                return text(left.named_children[0]), self._value_type(right.named_children[0])
        if node.type == "var_spec":
            name = field(node, "name")
            return text(name), simple_type(text(field(node, "type")))
        if node.type == "parameter_declaration" and field(node, "name") is not None:
            return text(field(node, "name")), simple_type(text(field(node, "type")))
        return None

    def field_binding(self, node):
        if node.type == "field_declaration" and field(node, "name") is not None:
            value = simple_type(text(field(node, "type")))
            return [(text(name), value) for name in node.children_by_field_name("name")] if value else []
        return []


frontend = GoFrontend()
