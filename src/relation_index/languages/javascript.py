"""JavaScript frontend (tree-sitter-javascript); TypeScript extends it."""

from .treesitter import TreeSitterFrontend, child_of_type, field, simple_type, strings_in, text, walk


class EcmaScriptFrontend(TreeSitterFrontend):
    self_names = frozenset({"this"})
    constructor_names = frozenset({"constructor"})
    containers = {"class_declaration": "class", "class": "class"}
    callables = {
        "function_declaration": "function", "generator_function_declaration": "function",
        "function_expression": "function", "function": "function", "arrow_function": "function",
        "method_definition": "method",
    }
    call_nodes = frozenset({"call_expression", "new_expression"})
    import_nodes = frozenset({"import_statement"})

    def parameter(self, node):
        kind = node.type
        if kind in {"comment", "decorator"}:
            return None
        default, variadic, type_text = "", False, ""
        target = node
        if kind in {"required_parameter", "optional_parameter"}:
            target = field(node, "pattern")
            type_text = text(field(node, "type")).lstrip(": ")
            default = text(field(node, "value")) or ("?" if kind == "optional_parameter" else "")
        if target is not None and target.type == "assignment_pattern":
            default = text(field(target, "right"))
            target = field(target, "left")
        if target is not None and target.type == "rest_pattern":
            variadic = True
            target = child_of_type(target, "identifier") or target
        name = text(target) if target is not None and target.type == "identifier" else ("{destructured}" if target is not None else "")
        return {"name": name, "type": type_text, "default": default, "variadic": variadic, "receiver": False, "annotations": self.annotations(node)}

    def bases(self, node):
        values = []
        heritage = child_of_type(node, "class_heritage")
        if heritage is None:
            return values
        clauses = heritage.named_children
        for clause in clauses:
            if clause.type == "extends_clause":
                value = field(clause, "value") or (clause.named_children[0] if clause.named_children else None)
                values.append({"type": text(value), "kind": "EXTENDS"})
            elif clause.type == "implements_clause":
                for item in clause.named_children:
                    values.append({"type": text(item), "kind": "IMPLEMENTS"})
            elif clause.type in {"identifier", "member_expression", "call_expression"}:
                values.append({"type": text(clause), "kind": "EXTENDS"})
        return values

    def call_info(self, node):
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type != "comment"] if arguments else []
        if node.type == "new_expression":
            name = simple_type(text(field(node, "constructor")))
            return {"name": name, "receiver": "", "args": args, "kind": "constructor"} if name else None
        function = field(node, "function")
        if function is None:
            return None
        if function.type == "member_expression":
            return {"name": text(field(function, "property")), "receiver": text(field(function, "object")), "args": args, "kind": "method"}
        if function.type == "identifier":
            return {"name": text(function), "receiver": "", "args": args, "kind": "function"}
        return None

    def import_call(self, call, node):
        if call["name"] != "require" or call["receiver"] or not call["args"]:
            return []
        values = strings_in(call["args"][0])
        if not values:
            return []
        alias, names = "", []
        parent = node.parent
        if parent is not None and parent.type == "variable_declarator":
            target = field(parent, "name")
            if target is not None and target.type == "identifier":
                alias = text(target)
            elif target is not None:
                names = [{"name": text(item), "alias": ""} for item in walk(target) if item.type in {"shorthand_property_identifier_pattern", "identifier"}]
        return [{"module": values[0], "names": names, "alias": alias, "name": alias, "line": node.start_point.row + 1, "kind": "require", "raw": text(node)}]

    def import_entries(self, node):
        source = strings_in(text(field(node, "source")))
        if not source:
            return []
        names, alias = [], ""
        clause = child_of_type(node, "import_clause")
        for item in clause.named_children if clause is not None else []:
            if item.type == "identifier":
                names.append({"name": "default", "alias": text(item)})
            elif item.type == "namespace_import":
                alias = text(child_of_type(item, "identifier"))
            elif item.type == "named_imports":
                for spec in item.named_children:
                    if spec.type == "import_specifier":
                        names.append({"name": text(field(spec, "name")), "alias": text(field(spec, "alias"))})
        return [{"module": source[0], "names": names, "alias": alias, "name": names[0]["name"] if names else alias, "line": node.start_point.row + 1, "kind": node.type, "raw": text(node)}]

    def _constructed(self, value):
        if value is not None and value.type == "new_expression":
            return simple_type(text(field(value, "constructor")))
        return ""

    def binding(self, node):
        if node.type != "variable_declarator":
            return None
        name = field(node, "name")
        if name is None or name.type != "identifier":
            return None
        declared = simple_type(text(field(node, "type")))
        return text(name), declared or self._constructed(field(node, "value"))

    def field_binding(self, node):
        if node.type in {"public_field_definition", "field_definition"}:
            name = field(node, "name", "property")
            value = simple_type(text(field(node, "type"))) or self._constructed(field(node, "value"))
            return [("this." + text(name), value)] if name is not None and value else []
        if node.type == "required_parameter" and child_of_type(node, "accessibility_modifier", "override_modifier") is not None:
            name = field(node, "pattern")
            value = simple_type(text(field(node, "type")))
            return [("this." + text(name), value)] if name is not None and value else []
        if node.type == "assignment_expression":
            left = field(node, "left")
            if left is not None and left.type == "member_expression" and text(field(left, "object")) == "this":
                value = self._constructed(field(node, "right"))
                return [("this." + text(field(left, "property")), value)] if value else []
        return []


class JavaScriptFrontend(EcmaScriptFrontend):
    name = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    VERSION = "javascript-syntax-v2-ts0.25-javascript0.25"
    RULES_VERSION = "javascript-rules-v2"
    grammar = ("tree_sitter_javascript", "language")


frontend = JavaScriptFrontend()
