"""Kotlin frontend (tree-sitter-kotlin 1.x grammar)."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, text, walk

TYPE_NODES = {"user_type", "nullable_type", "function_type", "type"}


def _identifier(node):
    return child_of_type(node, "identifier", "simple_identifier")


class KotlinFrontend(TreeSitterFrontend):
    name = "kotlin"
    extensions = (".kt", ".kts")
    VERSION = "kotlin-syntax-v2-ts0.25-kotlin1.1"
    RULES_VERSION = "kotlin-rules-v2"
    grammar = ("tree_sitter_kotlin", "language")
    module_prefix = False
    implicit_receiver = True
    self_names = frozenset({"this", "super"})
    containers = {"class_declaration": "class", "object_declaration": "class"}
    callables = {"function_declaration": "function", "secondary_constructor": "constructor", "anonymous_function": "function"}
    call_nodes = frozenset({"call_expression"})
    import_nodes = frozenset({"import", "import_header"})

    def package_name(self, root):
        header = child_of_type(root, "package_header")
        target = child_of_type(header, "qualified_identifier", "identifier") if header is not None else None
        return text(target)

    def classify(self, node):
        if node.type == "class_declaration":
            keywords = {child.type for child in node.children if not child.is_named}
            modifiers = text(child_of_type(node, "modifiers"))
            if "interface" in keywords:
                return "interface"
            if "enum" in modifiers.split():
                return "enum"
        return super().classify(node)

    def symbol_name(self, node, kind):
        if node.type == "secondary_constructor":
            return "constructor"
        return text(field(node, "name") or _identifier(node))

    def parameter_container(self, node):
        return child_of_type(node, "function_value_parameters", "parameters")

    def parameters(self, node):
        container = self.parameter_container(node)
        values = []
        for child in container.named_children if container is not None else []:
            if child.type == "parameter":
                type_node = child_of_type(child, *TYPE_NODES)
                values.append({"name": text(_identifier(child)), "type": text(type_node), "default": "", "variadic": False, "receiver": False, "annotations": self.annotations(child)})
            elif child.type == "parameter_modifiers" or (child.type == "modifiers" and "vararg" in text(child)):
                values.append({"name": "", "type": "", "default": "", "variadic": "vararg" in text(child), "receiver": False, "annotations": self.annotations(child), "_pending": True})
            elif values and child.type not in {"comment", "line_comment"}:
                values[-1]["default"] = text(child)
        merged, pending = [], None
        for item in values:
            if item.pop("_pending", False):
                pending = item
                continue
            if pending is not None:
                item["variadic"] = item["variadic"] or pending["variadic"]
                item["annotations"] = pending["annotations"] + item["annotations"]
                pending = None
            merged.append(item)
        return merged

    def bases(self, node):
        values = []
        clause = child_of_type(node, "delegation_specifiers")
        for item in clause.named_children if clause is not None else []:
            invocation = child_of_type(item, "constructor_invocation")
            target = child_of_type(invocation or item, "user_type")
            if target is not None:
                values.append({"type": text(target), "kind": "EXTENDS" if invocation is not None else "INHERITS"})
        return values

    def call_info(self, node):
        callee = node.named_children[0] if node.named_children else None
        arguments = child_of_type(node, "value_arguments")
        args = [text(item) for item in arguments.named_children if item.type == "value_argument"] if arguments else []
        if child_of_type(node, "annotated_lambda", "lambda_literal") is not None:
            args.append("{lambda}")
        if callee is None:
            return None
        if callee.type == "navigation_expression":
            parts = callee.named_children
            name_node = parts[-1] if parts else None
            if name_node is not None and name_node.type == "navigation_suffix":
                name_node = _identifier(name_node)
            receiver = text(parts[0]) if len(parts) > 1 else ""
            return {"name": text(name_node), "receiver": receiver, "args": args, "kind": "method"}
        if callee.type in {"identifier", "simple_identifier"}:
            return {"name": text(callee), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        target = child_of_type(node, "qualified_identifier", "identifier")
        value = text(target)
        if not value:
            return []
        alias_node = child_of_type(node, "import_alias")
        alias = text(_identifier(alias_node)) if alias_node is not None else ""
        module, _, name = value.rpartition(".")
        wildcard = text(node).rstrip().endswith("*")
        if wildcard:
            module, name = value, "*"
        return [{"module": module, "names": [{"name": name, "alias": alias}], "alias": "", "name": name, "line": node.start_point.row + 1, "kind": "import", "raw": text(node)}]

    def _value_type(self, node):
        call = child_of_type(node, "call_expression")
        callee = call.named_children[0] if call is not None and call.named_children else None
        if callee is not None and callee.type in {"identifier", "simple_identifier"} and text(callee)[:1].isupper():
            return text(callee)
        return ""

    def binding(self, node):
        if node.type != "property_declaration":
            return None
        declaration = child_of_type(node, "variable_declaration")
        if declaration is None:
            return None
        return text(_identifier(declaration)), simple_type(text(child_of_type(declaration, *TYPE_NODES))) or self._value_type(node)

    def field_binding(self, node):
        if node.type == "class_parameter" and any(child.type in {"val", "var"} or text(child) in {"val", "var"} for child in node.children):
            value = simple_type(text(child_of_type(node, *TYPE_NODES)))
            return [(text(_identifier(node)), value)] if value else []
        if node.type == "property_declaration" and node.parent is not None and node.parent.type == "class_body":
            found = self.binding(node)
            return [found] if found and found[1] else []
        return []


frontend = KotlinFrontend()
