"""C frontend (tree-sitter-c); the C++ frontend extends it."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, strings_in, text, walk

NAME_NODES = {"identifier", "field_identifier", "qualified_identifier", "destructor_name", "operator_name", "template_function", "operator_cast"}


def function_declarator(node):
    current = field(node, "declarator")
    while current is not None and current.type != "function_declarator":
        current = field(current, "declarator")
    return current


class CFrontend(TreeSitterFrontend):
    name = "c"
    extensions = (".c", ".h")
    VERSION = "c-syntax-v2-ts0.25-c0.24"
    RULES_VERSION = "c-rules-v2"
    grammar = ("tree_sitter_c", "language")
    module_prefix = False
    module_keeps_extension = True
    containers = {"struct_specifier": "struct", "enum_specifier": "enum", "union_specifier": "struct"}
    callables = {"function_definition": "function"}
    call_nodes = frozenset({"call_expression"})
    import_nodes = frozenset({"preproc_include"})

    def classify(self, node):
        if node.type in self.containers and field(node, "body") is None:
            return None
        return super().classify(node)

    def _declarator_name(self, node):
        declarator = function_declarator(node)
        target = field(declarator, "declarator") if declarator is not None else None
        return text(target).strip()

    def symbol_name(self, node, kind):
        if node.type == "function_definition":
            value = self._declarator_name(node)
            return value.rsplit("::", 1)[-1] if value else ""
        return text(field(node, "name")).strip()

    def parameter(self, node):
        if node.type == "variadic_parameter":
            return {"name": "...", "type": "", "default": "", "variadic": True, "receiver": False, "annotations": []}
        if node.type not in {"parameter_declaration", "optional_parameter_declaration", "variadic_parameter_declaration"}:
            return None
        declarator = field(node, "declarator")
        identifiers = [item for item in walk(declarator) if item.type == "identifier"] if declarator is not None else []
        type_text = text(field(node, "type"))
        if type_text == "void" and declarator is None:
            return None
        return {
            "name": text(identifiers[0]) if identifiers else "_",
            "type": type_text, "default": text(field(node, "default_value")),
            "variadic": node.type == "variadic_parameter_declaration",
            "receiver": False, "annotations": [],
        }

    def parameter_container(self, node):
        declarator = function_declarator(node)
        return field(declarator, "parameters") if declarator is not None else None

    def call_info(self, node):
        function = field(node, "function")
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type != "comment"] if arguments else []
        if function is None:
            return None
        if function.type == "field_expression":
            return {"name": text(field(function, "field")), "receiver": text(field(function, "argument")), "args": args, "kind": "method"}
        if function.type == "qualified_identifier":
            value = text(function)
            scope, _, name = value.rpartition("::")
            return {"name": simple_type(name) or name, "receiver": scope, "args": args, "kind": "method"}
        if function.type == "template_function":
            return {"name": text(field(function, "name")), "receiver": "", "args": args, "kind": "function"}
        if function.type == "identifier":
            return {"name": text(function), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        path = field(node, "path")
        if path is None:
            return []
        system = path.type == "system_lib_string"
        value = text(path).strip('<>"')
        return [{"module": value, "names": [], "alias": "", "name": value, "line": node.start_point.row + 1, "kind": "system_include" if system else "include", "raw": text(node)}]

    def binding(self, node):
        if node.type != "declaration":
            return None
        declarator = field(node, "declarator")
        if declarator is not None and declarator.type == "init_declarator":
            declarator = field(declarator, "declarator")
        while declarator is not None and declarator.type in {"pointer_declarator", "reference_declarator"}:
            declarator = field(declarator, "declarator") or child_of_type(declarator, "identifier")
        if declarator is None or declarator.type != "identifier":
            return None
        return text(declarator), simple_type(text(field(node, "type")))

    def field_binding(self, node):
        if node.type != "field_declaration":
            return []
        declarator = field(node, "declarator")
        while declarator is not None and declarator.type in {"pointer_declarator", "reference_declarator"}:
            declarator = field(declarator, "declarator")
        if declarator is None or declarator.type != "field_identifier":
            return []
        value = simple_type(text(field(node, "type")))
        return [(text(declarator), value)] if value else []


frontend = CFrontend()
