"""Archive the pinned Spring Boot B0 source and P1 relation data, read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
import zipfile
from pathlib import Path


def io_path(path: Path) -> str:
    absolute = os.path.abspath(os.fspath(path))
    if os.name == "nt" and not absolute.startswith("\\\\?\\"):
        return "\\\\?\\" + absolute
    return absolute


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(io_path(path), "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    output = args.output.resolve()
    metadata = json.loads((experiment / "experiment.json").read_text(encoding="utf-8"))
    inventory = json.loads((experiment / "B0" / "file-inventory.json").read_text(encoding="utf-8"))
    if len(inventory) != metadata["tracked_files"]:
        raise ValueError("Inventory count does not match experiment metadata")
    canonical = hashlib.sha256(json.dumps(inventory, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if canonical != metadata["file_inventory_sha256"]:
        raise ValueError("Canonical inventory digest does not match experiment metadata")

    source = experiment / "B0" / "source"
    p1_source = experiment / "P1" / "source"
    archive = output / "실험입력" / "B0" / "source.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_name(archive.name + ".building-" + uuid.uuid4().hex)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as bundle:
            for number, item in enumerate(inventory, 1):
                relative = item["path"]
                if relative.startswith("/") or ".." in Path(relative).parts or ":" in relative:
                    raise ValueError(f"Unsafe source path: {relative}")
                original = source / relative
                p1_copy = p1_source / relative
                if digest_file(original) != item["sha256"] or os.stat(io_path(original)).st_size != item["bytes"]:
                    raise ValueError(f"B0 source mismatch: {relative}")
                if digest_file(p1_copy) != item["sha256"]:
                    raise ValueError(f"P1 source mismatch: {relative}")
                with open(io_path(original), "rb") as stream:
                    bundle.writestr("source/" + relative.replace("\\", "/"), stream.read())
                if number % 2000 == 0:
                    print(f"verified and archived {number}/{len(inventory)} files", flush=True)
        os.replace(temporary, archive)

    relation_source = experiment / "P1" / "relations" / "relations.sqlite3"
    relation_target = output / "실험입력" / "P1" / "relations.sqlite3"
    relation_target.parent.mkdir(parents=True, exist_ok=True)
    if not relation_target.exists():
        temporary = relation_target.with_name(relation_target.name + ".building-" + uuid.uuid4().hex)
        shutil.copyfile(io_path(relation_source), io_path(temporary))
        os.replace(temporary, relation_target)
    with sqlite3.connect(relation_target.as_uri() + "?mode=ro", uri=True) as db:
        counts = {table: db.execute(f"SELECT count(*) FROM {table} WHERE snapshot_id=?",
                                    (metadata["index_snapshot"],)).fetchone()[0]
                  for table in ("files", "symbols", "calls", "edges", "facts")}
    if counts != metadata["index_counts"]:
        raise ValueError(f"P1 relation counts mismatch: {counts}")
    for side in ("B0", "P1"):
        target = output / "실험입력" / side
        target.mkdir(parents=True, exist_ok=True)
        for name in ("INPUT.json", "file-inventory.json", "task-prompt.md"):
            shutil.copyfile(experiment / side / name, target / name)
    for name in ("experiment.json", "common-protocol.md"):
        shutil.copyfile(experiment / name, output / "실험입력" / name)
    for name in ("README.md", "index-metadata.json", "relation_query.py"):
        shutil.copyfile(experiment / "P1" / "relations" / name,
                        output / "실험입력" / "P1" / name)
    result = {
        "source_commit": metadata["source_commit"],
        "tracked_files": len(inventory),
        "B0_source_archive": {"path": str(archive), "sha256": digest_file(archive)},
        "P1_relation_database": {"path": str(relation_target),
                                 "sha256": digest_file(relation_target), "counts": counts},
        "P1_source": "B0/source.zip contains the same verified source files as the P1 input; add P1/relations.sqlite3",
        "input_inventory_canonical_sha256": canonical,
    }
    (output / "실험입력" / "archive-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
