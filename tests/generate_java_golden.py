"""Generate the frozen Java extractor/linker output used by regression tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from relation_index import java


def snapshot(folder: Path) -> dict:
    parsed = [
        java.extract(path.relative_to(folder).as_posix(), path.read_bytes())
        for path in sorted(folder.rglob("*.java"))
    ]
    symbols, calls, edges = java.link(parsed)
    facts = [fact for entry in parsed for fact in entry["facts"]]
    return {
        "version": java.VERSION,
        "symbols": sorted(symbols, key=lambda item: item["id"]),
        "calls": sorted(calls, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: item["id"]),
        "facts": sorted(facts, key=lambda item: item["id"]),
        "parse_errors": sorted(
            path.relative_to(folder).as_posix()
            for path, entry in zip(sorted(folder.rglob("*.java")), parsed)
            if entry["parse_error"]
        ),
    }


def main() -> None:
    output = ROOT / "tests" / "golden"
    output.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "java_minimal.json": ROOT / "tests" / "fixture",
        "java_spring.json": ROOT / "tests" / "fixtures" / "java_spring",
    }
    for name, folder in fixtures.items():
        content = json.dumps(snapshot(folder), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        (output / name).write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
