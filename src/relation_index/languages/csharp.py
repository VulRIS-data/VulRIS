"""C# frontend (tree-sitter-c-sharp)."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, text


class CSharpFrontend(TreeSitterFrontend):
    name = "csharp"
    extensions = (".cs",)
    VERSION = "csharp-syntax-v2-ts0.25-csharp0.23"
    RULES_VERSION = "csharp-rules-v2"
    grammar = ("tree_sitter_c_sharp", "language")
    module_prefix = False
    implicit_receiver = True
    self_names = frozenset({"this", "base"})
    containers = {
        "namespace_declaration": "namespace", "file_scoped_namespace_declaration": "namespace",
        "class_declaration": "class", "record_declaration": "class", "interface_declaration": "interface",
        "struct_declaration": "struct", "record_struct_declaration": "struct", "enum_declaration": "enum",
    }
    callables = {"method_declaration": "method", "constructor_declaration": "constructor", "local_function_statement": "function"}
    call_nodes = frozenset({"invocation_expression", "object_creation_expression"})
    import_nodes = frozenset({"using_directive"})
    namespace_statements = frozenset({"file_scoped_namespace_declaration"})

    def parameter(self, node):
        if node.type != "parameter":
            return None
        raw = text(node)
        clause = child_of_type(node, "equals_value_clause")
        default = text(field(node, "default_value")) or (text(clause) if clause is not None else "")
        return {
            "name": text(field(node, "name")), "type": text(field(node, "type")), "default": default,
            "variadic": raw.lstrip().startswith("params") or "params " in raw.split("]")[-1][:8],
            "receiver": False, "annotations": self.annotations(node),
        }

    def bases(self, node):
        clause = child_of_type(node, "base_list")
        values = []
        for item in clause.named_children if clause is not None else []:
            target = child_of_type(item, "identifier", "qualified_name", "generic_name") if item.type == "primary_constructor_base_type" else item
            if target is not None and target.type in {"identifier", "qualified_name", "generic_name", "predefined_type"}:
                values.append({"type": text(target), "kind": "INHERITS"})
        return values

    def call_info(self, node):
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type == "argument"] if arguments else []
        if node.type == "object_creation_expression":
            name = simple_type(text(field(node, "type")))
            return {"name": name, "receiver": "", "args": args, "kind": "constructor"} if name else None
        function = field(node, "function")
        if function is None:
            return None
        if function.type == "member_access_expression":
            return {"name": simple_type(text(field(function, "name"))), "receiver": text(field(function, "expression")), "args": args, "kind": "method"}
        if function.type in {"identifier", "generic_name"}:
            return {"name": simple_type(text(function)), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        alias = text(field(node, "name"))
        target = child_of_type(node, "qualified_name", "identifier")
        if alias and target is not None and target.id == field(node, "name").id:
            named = [item for item in node.named_children if item.id != target.id]
            target = named[-1] if named else None
        module = text(target)
        if not module:
            return []
        return [{"module": module, "names": [], "alias": alias, "name": module.split(".")[-1], "line": node.start_point.row + 1, "kind": node.type, "raw": text(node)}]

    def binding(self, node):
        if node.type != "variable_declaration" or (node.parent is not None and node.parent.type == "field_declaration"):
            return None
        declarator = child_of_type(node, "variable_declarator")
        if declarator is None:
            return None
        declared = text(field(node, "type"))
        if declared == "var":
            created = child_of_type(declarator, "object_creation_expression")
            declared = text(field(created, "type")) if created is not None else ""
        return text(field(declarator, "name")), simple_type(declared)

    def field_binding(self, node):
        if node.type == "field_declaration":
            declaration = child_of_type(node, "variable_declaration")
            value = simple_type(text(field(declaration, "type")))
            names = [text(field(item, "name")) for item in (declaration.named_children if declaration else []) if item.type == "variable_declarator"]
            return [(name, value) for name in names] if value else []
        if node.type == "property_declaration":
            value = simple_type(text(field(node, "type")))
            return [(text(field(node, "name")), value)] if value else []
        return []


frontend = CSharpFrontend()
