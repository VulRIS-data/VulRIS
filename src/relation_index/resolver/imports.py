"""Deterministic, syntax-only import resolution.

Each import is matched against files and declarations of the same snapshot.
Imports that name a package outside the snapshot are reported as external and
never matched by name to unrelated project code.
"""

from __future__ import annotations

import posixpath
from collections import defaultdict

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".d.ts")
QUALIFIED_SEPARATORS = {"php": "\\", "rust": "::", "cpp": "::", "ruby": "::"}


def _dir(path):
    return posixpath.dirname(path)


def _strip_ext(path):
    root, ext = posixpath.splitext(path)
    return root if ext else path


def rust_module_key(path):
    parts = _strip_ext(path).split("/")
    if "src" in parts:
        parts = parts[len(parts) - parts[::-1].index("src"):]
    if parts and parts[-1] in {"mod", "lib", "main"}:
        parts = parts[:-1]
    return "::".join(parts)


class ImportIndex:
    """Lookup tables shared by all files of one language family."""

    def __init__(self, entries, symbols):
        self.entries = {entry["path"]: entry for entry in entries}
        self.paths = sorted(self.entries)
        self.modules = {}
        self.by_qualified = defaultdict(list)
        self.top_level = defaultdict(lambda: defaultdict(list))
        self.dirs = defaultdict(list)
        by_id = {symbol["id"]: symbol for symbol in symbols}
        for symbol in symbols:
            if symbol["kind"] == "module":
                self.modules[symbol["path"]] = symbol
            else:
                self.by_qualified[symbol["qualified_name"]].append(symbol)
                owner = by_id.get(symbol.get("owner_id"))
                if owner is not None and owner["kind"] in {"module", "namespace"}:
                    self.top_level[symbol["path"]][symbol["name"]].append(symbol)
        for path in self.paths:
            self.dirs[_dir(path)].append(path)
        self.dotted = defaultdict(list)
        self.suffixes = defaultdict(list)
        self.rust = defaultdict(list)
        for path, module in self.modules.items():
            key = module["qualified_name"]
            self.dotted[key].append(path)
            parts = key.split(".")
            for index in range(1, len(parts)):
                self.suffixes[".".join(parts[index:])].append(path)
            self.rust[rust_module_key(path)].append(path)

    def dotted_paths(self, dotted):
        """Match ``a.b.c`` to a module, allowing the snapshot root to sit
        above (``src/a/b/c.py``) or inside (``b/c.py`` for ``a.b.c``) the
        package root. At least two components must match in the second case."""
        found = self.dotted.get(dotted) or self.suffixes.get(dotted)
        if not found:
            parts = dotted.split(".")
            for index in range(1, len(parts) - 1):
                key = ".".join(parts[index:])
                found = self.dotted.get(key)
                if found:
                    break
        return sorted(set(found or []))

    def existing(self, candidates):
        return [path for path in candidates if path in self.entries]


class Scope:
    def __init__(self):
        self.aliases = defaultdict(list)
        self.external = set()
        self.modules = set()
        self.prefixes = set()

    def bind(self, name, kind, value):
        if name and (kind, value["id"]) not in {(item[0], item[1]["id"]) for item in self.aliases[name]}:
            self.aliases[name].append((kind, value))


def _module_targets(index, paths):
    return [index.modules[path] for path in sorted(set(paths)) if path in index.modules]


def _named(index, paths, name):
    return [symbol for path in sorted(set(paths)) for symbol in index.top_level[path].get(name, [])]


def resolve_imports(entry, index):
    """Return (scope, [(import item, target symbols, external flag)])."""
    scope = Scope()
    results = []
    language, path = entry["language"], entry["path"]
    current_dir = _dir(path)
    for item in entry.get("imports", []):
        module = item.get("module", "")
        names = item.get("names", [])
        alias = item.get("alias", "")
        paths, targets, external = [], [], False
        if language == "python":
            level = len(module) - len(module.lstrip("."))
            rest = module.lstrip(".")
            if level:
                base = current_dir.split("/") if current_dir else []
                base = base[: len(base) - (level - 1)] if level > 1 else base
                dotted = ".".join(filter(None, base + ([rest] if rest else [])))
            else:
                dotted = rest
            paths = index.dotted_paths(dotted) if dotted else []
            if item.get("kind") == "import_statement":
                local = alias or dotted.split(".")[0]
                for module_symbol in _module_targets(index, paths):
                    scope.bind(alias or dotted, "module", module_symbol)
                    if not alias:
                        scope.bind(local, "module", module_symbol)
                targets = _module_targets(index, paths)
                external = not paths
                if external:
                    scope.external.update({alias or local, dotted})
            else:
                for spec in names:
                    name, local = spec["name"], spec.get("alias") or spec["name"]
                    if name == "*":
                        scope.modules.update(paths)
                        continue
                    sub = index.dotted_paths(dotted + "." + name if dotted else name)
                    found = _module_targets(index, sub) or _named(index, paths, name)
                    for symbol in found:
                        scope.bind(local, "module" if symbol["kind"] == "module" else "symbol", symbol)
                    targets.extend(found)
                    if not found and not paths:
                        scope.external.add(local)
                external = not paths and not targets
        elif language in {"javascript", "typescript"}:
            if module.startswith("."):
                base = posixpath.normpath(posixpath.join(current_dir, module))
                stem = _strip_ext(base) if base.endswith((".js", ".jsx", ".mjs", ".cjs")) else base
                candidates = [base, *(stem + ext for ext in JS_EXTENSIONS), *(stem + "/index" + ext for ext in JS_EXTENSIONS)]
                found = index.existing(candidates)
                paths = found[:1]
            external = not paths
            module_symbols = _module_targets(index, paths)
            if alias:
                for symbol in module_symbols:
                    scope.bind(alias, "module", symbol)
                if external:
                    scope.external.add(alias)
            for spec in names:
                local = spec.get("alias") or spec["name"]
                found = _named(index, paths, spec["name"]) if spec["name"] != "default" else []
                for symbol in found or module_symbols:
                    scope.bind(local, "symbol" if found else "module", symbol)
                targets.extend(found)
                if external:
                    scope.external.add(local)
            targets = targets or module_symbols
        elif language == "go":
            for directory, files in index.dirs.items():
                if directory and (module == directory or module.endswith("/" + directory)) and any(index.entries[p]["language"] == "go" for p in files):
                    paths.extend(files)
            external = not paths
            local = alias or module.rsplit("/", 1)[-1]
            for symbol in _module_targets(index, paths):
                scope.bind(local, "module", symbol)
            if external:
                scope.external.add(local)
            targets = _module_targets(index, paths)
        elif language in {"c", "cpp"}:
            if item.get("kind") == "include":
                local_path = posixpath.normpath(posixpath.join(current_dir, module))
                paths = index.existing([local_path]) or [p for p in index.paths if p == module or p.endswith("/" + module)]
            external = not paths
            scope.modules.update(paths)
            targets = _module_targets(index, paths)
        elif language == "ruby":
            if item.get("kind") == "require_relative":
                base = posixpath.normpath(posixpath.join(current_dir, module))
                paths = index.existing([base, base + ".rb"])
            else:
                wanted = module if module.endswith(".rb") else module + ".rb"
                paths = [p for p in index.paths if p == wanted or p.endswith("/" + wanted)]
            external = not paths
            scope.modules.update(paths)
            targets = _module_targets(index, paths)
        elif language == "rust":
            parts = [part for part in module.split("::") if part]
            key_parts = rust_module_key(path).split("::") if rust_module_key(path) else []
            if parts and parts[0] == "crate":
                parts = parts[1:]
            elif parts and parts[0] in {"self", "super"}:
                # ``self`` is the current module, each ``super`` goes one level up.
                base = list(key_parts)
                while parts and parts[0] in {"self", "super"}:
                    if parts[0] == "super" and base:
                        base.pop()
                    parts = parts[1:]
                parts = base + parts
            key = "::".join(filter(None, parts))
            paths = list(index.rust.get(key, []))
            for spec in names:
                name, local = spec["name"], spec.get("alias") or spec["name"]
                if name == "*":
                    scope.modules.update(paths)
                    continue
                sub = list(index.rust.get("::".join(filter(None, [key, name])), []))
                found = _module_targets(index, sub) or _named(index, paths, name)
                for symbol in found:
                    scope.bind(local, "module" if symbol["kind"] == "module" else "symbol", symbol)
                targets.extend(found)
                if not found and not paths:
                    scope.external.add(local)
            if item.get("kind") == "mod":
                for symbol in _module_targets(index, paths):
                    scope.bind(item.get("alias", ""), "module", symbol)
                targets = _module_targets(index, paths)
            external = not paths and not targets
        elif language in {"csharp", "kotlin", "php", "swift"}:
            separator = QUALIFIED_SEPARATORS.get(language, ".")
            if names:
                for spec in names:
                    name, local = spec["name"], spec.get("alias") or spec["name"]
                    if name == "*":
                        scope.prefixes.add(module)
                        continue
                    found = index.by_qualified.get(separator.join(filter(None, [module, name])), [])
                    for symbol in found:
                        scope.bind(local, "symbol", symbol)
                    targets.extend(found)
                    if not found:
                        scope.external.add(local)
            else:
                scope.prefixes.add(module)
                targets = [symbol for symbol in index.by_qualified.get(module, []) if symbol["kind"] == "namespace"]
            external = not targets and not any(
                key == module or key.startswith(module + separator) for key in index.by_qualified
            )
        unique = {symbol["id"]: symbol for symbol in targets}
        scope.modules.update(path for path in paths)
        results.append((item, [unique[key] for key in sorted(unique)], external))
    return scope, results
