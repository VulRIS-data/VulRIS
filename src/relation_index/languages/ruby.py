"""Ruby frontend (tree-sitter-ruby)."""

from .treesitter import TreeSitterFrontend, field, simple_type, strings_in, text

REQUIRE_CALLS = {"require", "require_relative", "load", "autoload"}


class RubyFrontend(TreeSitterFrontend):
    name = "ruby"
    extensions = (".rb", ".gemspec", ".rake")
    VERSION = "ruby-syntax-v2-ts0.25-ruby0.23"
    RULES_VERSION = "ruby-rules-v2"
    grammar = ("tree_sitter_ruby", "language")
    separator = "::"
    member_separator = "#"
    module_prefix = False
    implicit_receiver = True
    self_names = frozenset({"self"})
    constructor_names = frozenset({"initialize"})
    containers = {"class": "class", "module": "namespace"}
    callables = {"method": "method", "singleton_method": "method"}
    call_nodes = frozenset({"call"})

    def parameter(self, node):
        kind = node.type
        if kind == "identifier":
            return {"name": text(node), "type": "", "default": "", "variadic": False, "receiver": False, "annotations": []}
        if kind in {"optional_parameter", "keyword_parameter"}:
            value = text(field(node, "value"))
            return {"name": text(field(node, "name")), "type": "", "default": value or ("" if kind == "keyword_parameter" else "nil"), "variadic": False, "receiver": False, "annotations": []}
        if kind in {"splat_parameter", "hash_splat_parameter"}:
            return {"name": text(field(node, "name")) or "*", "type": "", "default": "", "variadic": True, "receiver": False, "annotations": []}
        if kind == "block_parameter":
            return {"name": text(field(node, "name")) or "&", "type": "", "default": "&", "variadic": False, "receiver": False, "annotations": []}
        return None

    def bases(self, node):
        superclass = field(node, "superclass")
        if superclass is None:
            return []
        target = superclass.named_children[0] if superclass.named_children else None
        return [{"type": text(target), "kind": "EXTENDS"}] if target is not None else []

    def call_info(self, node):
        method = field(node, "method")
        if method is None:
            return None
        arguments = field(node, "arguments")
        args = [text(item) for item in arguments.named_children if item.type != "comment"] if arguments else []
        receiver = text(field(node, "receiver"))
        name = text(method)
        kind = "constructor" if name == "new" and receiver else ("method" if receiver else "function")
        return {"name": name, "receiver": receiver, "args": args, "kind": kind}

    def import_call(self, call, node):
        if call["name"] not in REQUIRE_CALLS or call["receiver"] or not call["args"]:
            return []
        values = strings_in(call["args"][0])
        if not values:
            return []
        return [{"module": values[0], "names": [], "alias": "", "name": values[0], "line": node.start_point.row + 1, "kind": call["name"], "raw": text(node)}]

    def _constructed(self, value):
        if value is not None and value.type == "call" and text(field(value, "method")) == "new":
            return simple_type(text(field(value, "receiver")))
        return ""

    def binding(self, node):
        if node.type == "assignment":
            left = field(node, "left")
            if left is not None and left.type == "identifier":
                return text(left), self._constructed(field(node, "right"))
        return None

    def field_binding(self, node):
        if node.type == "assignment":
            left = field(node, "left")
            if left is not None and left.type == "instance_variable":
                value = self._constructed(field(node, "right"))
                return [(text(left), value)] if value else []
        return []


frontend = RubyFrontend()
