"""Swift frontend (tree-sitter-swift)."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, text

TYPE_NODES = {"user_type", "optional_type", "array_type", "dictionary_type", "function_type", "tuple_type"}
DECLARATION_KINDS = {"class": "class", "struct": "struct", "enum": "enum", "actor": "class"}


def _keyword(node):
    return next((child.type for child in node.children if not child.is_named and child.type in set(DECLARATION_KINDS) | {"extension"}), "")


class SwiftFrontend(TreeSitterFrontend):
    name = "swift"
    extensions = (".swift",)
    VERSION = "swift-syntax-v2-ts0.25-swift0.7"
    RULES_VERSION = "swift-rules-v2"
    grammar = ("tree_sitter_swift", "language")
    module_prefix = False
    implicit_receiver = True
    self_names = frozenset({"self", "super", "Self"})
    constructor_names = frozenset({"init"})
    containers = {"class_declaration": "class", "protocol_declaration": "interface"}
    callables = {"function_declaration": "function", "init_declaration": "constructor", "protocol_function_declaration": "method"}
    call_nodes = frozenset({"call_expression"})
    import_nodes = frozenset({"import_declaration"})

    def classify(self, node):
        if node.type == "class_declaration":
            return DECLARATION_KINDS.get(_keyword(node), "class")
        return super().classify(node)

    def transparent(self, node):
        if node.type != "class_declaration" or _keyword(node) != "extension":
            return None
        owner = simple_type(text(field(node, "name")))
        return (owner, [text(item) for item in self._inherited(node)]) if owner else None

    def _inherited(self, node):
        values = []
        for item in node.named_children:
            if item.type == "inheritance_specifier":
                target = field(item, "inherits_from") or child_of_type(item, "user_type")
                if target is not None:
                    values.append(target)
        return values

    def symbol_name(self, node, kind):
        if node.type == "init_declaration":
            return "init"
        return text(field(node, "name"))

    def parameters(self, node):
        values = []
        for child in node.named_children:
            if child.type == "parameter":
                name_node = next((item for index, item in enumerate(child.children) if child.field_name_for_child(index) == "name" and item.type == "simple_identifier"), None)
                type_node = child_of_type(child, *TYPE_NODES)
                raw = text(child)
                values.append({"name": text(name_node), "type": text(type_node), "default": "", "variadic": raw.rstrip().endswith("..."), "receiver": False, "annotations": []})
            elif values and node.field_name_for_child(next(index for index, item in enumerate(node.children) if item.id == child.id)) == "default_value":
                values[-1]["default"] = text(child)
        return values

    def bases(self, node):
        return [{"type": text(item), "kind": "INHERITS"} for item in self._inherited(node)]

    def call_info(self, node):
        callee = node.named_children[0] if node.named_children else None
        suffix = child_of_type(node, "call_suffix")
        arguments = child_of_type(suffix, "value_arguments") if suffix is not None else None
        args = [text(item) for item in arguments.named_children if item.type == "value_argument"] if arguments else []
        if suffix is not None and child_of_type(suffix, "lambda_literal") is not None:
            args.append("{closure}")
        if callee is None:
            return None
        if callee.type == "navigation_expression":
            suffix_node = field(callee, "suffix")
            name = text(field(suffix_node, "suffix")) if suffix_node is not None else ""
            return {"name": name, "receiver": text(field(callee, "target")), "args": args, "kind": "method"}
        if callee.type == "simple_identifier":
            return {"name": text(callee), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        value = text(child_of_type(node, "identifier"))
        return [{"module": value, "names": [], "alias": "", "name": value, "line": node.start_point.row + 1, "kind": node.type, "raw": text(node)}] if value else []

    def binding(self, node):
        if node.type != "property_declaration":
            return None
        pattern = field(node, "name")
        name = text(field(pattern, "bound_identifier")) if pattern is not None else ""
        annotation = child_of_type(node, "type_annotation")
        declared = simple_type(text(child_of_type(annotation, *TYPE_NODES))) if annotation is not None else ""
        value = field(node, "value")
        if not declared and value is not None and value.type == "call_expression":
            callee = value.named_children[0] if value.named_children else None
            if callee is not None and callee.type == "simple_identifier" and text(callee)[:1].isupper():
                declared = text(callee)
        return (name, declared) if name else None

    def field_binding(self, node):
        if node.type == "property_declaration" and node.parent is not None and node.parent.type == "class_body":
            found = self.binding(node)
            return [found] if found and found[1] else []
        return []


frontend = SwiftFrontend()
