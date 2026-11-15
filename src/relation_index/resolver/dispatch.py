"""Resolve candidates only within compatible language families."""

from collections import defaultdict

from .generic import link

FAMILY = {"javascript": "js_ts", "typescript": "js_ts", "c": "c_cpp", "cpp": "c_cpp"}


def resolve(parsed_files, checkpoint=lambda: None, on_progress=None):
    groups = defaultdict(list)
    for entry in parsed_files:
        language = entry["language"]
        groups[FAMILY.get(language, language)].append(entry)
    symbols, calls, edges = [], [], []
    imports = {"unresolved": defaultdict(int), "external": defaultdict(int)}
    for family in sorted(groups):
        group_symbols, group_calls, group_edges, counts = link(groups[family], checkpoint, on_progress)
        symbols.extend(group_symbols)
        calls.extend(group_calls)
        edges.extend(group_edges)
        for key in imports:
            for language, count in counts[key].items():
                imports[key][language] += count
    return symbols, calls, edges, {key: dict(sorted(value.items())) for key, value in imports.items()}
