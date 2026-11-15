"""C++ frontend (tree-sitter-cpp)."""

from .c import CFrontend
from .treesitter import child_of_type, field, simple_type, text


class CppFrontend(CFrontend):
    name = "cpp"
    extensions = (".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".h")
    VERSION = "cpp-syntax-v2-ts0.25-cpp0.23"
    RULES_VERSION = "cpp-rules-v2"
    grammar = ("tree_sitter_cpp", "language")
    separator = "::"
    implicit_receiver = True
    self_names = frozenset({"this"})
    containers = {
        "struct_specifier": "struct", "union_specifier": "struct", "enum_specifier": "enum",
        "class_specifier": "class", "namespace_definition": "namespace",
    }
    call_nodes = frozenset({"call_expression", "new_expression"})

    def classify(self, node):
        if node.type == "namespace_definition":
            return "namespace"
        return super().classify(node)

    def symbol_name(self, node, kind):
        if node.type == "namespace_definition":
            return text(field(node, "name")).strip() or "<anonymous namespace>"
        return super().symbol_name(node, kind)

    def declared_owner(self, node, kind):
        if node.type != "function_definition":
            return None
        value = self._declarator_name(node)
        if "::" not in value:
            return None
        return simple_type(value.rpartition("::")[0]) or None

    def refine_kind(self, kind, name, owner, declared_owner):
        kind = super().refine_kind(kind, name, owner, declared_owner)
        if kind == "method" and declared_owner and name == declared_owner:
            return "constructor"
        return kind

    def bases(self, node):
        clause = child_of_type(node, "base_class_clause")
        values = []
        for item in clause.named_children if clause is not None else []:
            if item.type in {"type_identifier", "qualified_identifier", "template_type"}:
                values.append({"type": text(item), "kind": "INHERITS"})
        return values

    def call_info(self, node):
        if node.type == "new_expression":
            arguments = field(node, "arguments")
            args = [text(item) for item in arguments.named_children] if arguments else []
            name = simple_type(text(field(node, "type")))
            return {"name": name, "receiver": "", "args": args, "kind": "constructor"} if name else None
        return super().call_info(node)


frontend = CppFrontend()
