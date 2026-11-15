"""PHP frontend (tree-sitter-php, PHP grammar with HTML)."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, strings_in, text


class PhpFrontend(TreeSitterFrontend):
    name = "php"
    extensions = (".php",)
    VERSION = "php-syntax-v2-ts0.25-php0.25"
    RULES_VERSION = "php-rules-v2"
    grammar = ("tree_sitter_php", "language_php")
    separator = "\\"
    member_separator = "::"
    module_prefix = False
    self_names = frozenset({"$this", "self", "static", "parent"})
    constructor_names = frozenset({"__construct"})
    containers = {
        "namespace_definition": "namespace", "class_declaration": "class", "trait_declaration": "class",
        "interface_declaration": "interface", "enum_declaration": "enum",
    }
    callables = {
        "function_definition": "function", "method_declaration": "method",
        "anonymous_function": "function", "arrow_function": "function",
    }
    call_nodes = frozenset({
        "function_call_expression", "member_call_expression", "nullsafe_member_call_expression",
        "scoped_call_expression", "object_creation_expression",
    })
    import_nodes = frozenset({
        "namespace_use_declaration", "include_expression", "include_once_expression",
        "require_expression", "require_once_expression",
    })
    namespace_statements = frozenset({"namespace_definition"})

    def parameter(self, node):
        if node.type not in {"simple_parameter", "variadic_parameter", "property_promotion_parameter"}:
            return None
        return {
            "name": text(field(node, "name")).lstrip("$"), "type": text(field(node, "type")),
            "default": text(field(node, "default_value")), "variadic": node.type == "variadic_parameter",
            "receiver": False, "annotations": self.annotations(node),
        }

    def bases(self, node):
        values = []
        for clause_type, kind in (("base_clause", "EXTENDS"), ("class_interface_clause", "IMPLEMENTS")):
            clause = child_of_type(node, clause_type)
            for item in clause.named_children if clause is not None else []:
                if item.type in {"name", "qualified_name"}:
                    values.append({"type": text(item), "kind": kind})
        return values

    def call_info(self, node):
        arguments = field(node, "arguments") or child_of_type(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type == "argument"] if arguments else []
        if node.type == "object_creation_expression":
            target = child_of_type(node, "name", "qualified_name")
            name = simple_type(text(target))
            return {"name": name, "receiver": "", "args": args, "kind": "constructor"} if name else None
        if node.type in {"member_call_expression", "nullsafe_member_call_expression"}:
            return {"name": text(field(node, "name")), "receiver": text(field(node, "object")), "args": args, "kind": "method"}
        if node.type == "scoped_call_expression":
            return {"name": text(field(node, "name")), "receiver": text(field(node, "scope")), "args": args, "kind": "method"}
        function = field(node, "function")
        if function is not None and function.type in {"name", "qualified_name"}:
            return {"name": simple_type(text(function)), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_entries(self, node):
        line, raw = node.start_point.row + 1, text(node)
        if node.type != "namespace_use_declaration":
            values = strings_in(raw)
            return [{"module": values[0], "names": [], "alias": "", "name": values[0], "line": line, "kind": node.type, "raw": raw}] if values else []
        entries = []
        prefix = text(child_of_type(node, "namespace_name"))
        clauses = [item for item in node.named_children if item.type == "namespace_use_clause"]
        group = child_of_type(node, "namespace_use_group")
        if group is not None:
            clauses.extend(item for item in group.named_children if item.type == "namespace_use_clause")
        for clause in clauses:
            target = child_of_type(clause, "qualified_name", "name")
            full = "\\".join(filter(None, [prefix, text(target)])).lstrip("\\")
            module, _, name = full.rpartition("\\")
            entries.append({"module": module, "names": [{"name": name, "alias": text(field(clause, "alias"))}], "alias": "", "name": name, "line": line, "kind": node.type, "raw": raw})
        return entries

    def binding(self, node):
        if node.type != "assignment_expression":
            return None
        left, right = field(node, "left"), field(node, "right")
        if left is None or left.type != "variable_name" or right is None or right.type != "object_creation_expression":
            return None
        return text(left).lstrip("$"), simple_type(text(child_of_type(right, "name", "qualified_name")))

    def field_binding(self, node):
        if node.type == "property_promotion_parameter":
            value = simple_type(text(field(node, "type")))
            return [("$this->" + text(field(node, "name")).lstrip("$"), value)] if value else []
        if node.type == "property_declaration":
            value = simple_type(text(field(node, "type")))
            names = [text(child_of_type(item, "variable_name")).lstrip("$") for item in node.named_children if item.type == "property_element"]
            return [("$this->" + name, value) for name in names] if value else []
        if node.type == "assignment_expression":
            left, right = field(node, "left"), field(node, "right")
            if left is not None and left.type == "member_access_expression" and text(field(left, "object")) == "$this" and right is not None and right.type == "object_creation_expression":
                return [("$this->" + text(field(left, "name")), simple_type(text(child_of_type(right, "name", "qualified_name"))))]
        return []


frontend = PhpFrontend()
