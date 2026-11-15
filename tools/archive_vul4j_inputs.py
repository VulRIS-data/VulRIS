"""Archive the exact vulnerable-source and relationship-index inputs used in the 75-case study.

The input database is opened read-only. The output contains no model responses,
ground-truth patches, or static-scan results; those belong in separate records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import uuid
import zipfile
from collections import defaultdict
from contextlib import closing
from pathlib import Path, PurePosixPath

TABLES = ("files", "symbols", "calls", "edges", "facts")
EXPECTED = {"files": "files", "symbols": "symbols", "calls": "calls", "edges": "edges", "facts": "facts"}


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".building-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def safe_member(relative: str) -> str:
    path = PurePosixPath(relative.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError(f"Unsafe source path: {relative}")
    return "source/" + path.as_posix()


def source_rows(db: sqlite3.Connection, snapshot_id: str) -> list[tuple]:
    return db.execute(
        "SELECT path,hash,size,language,line_count FROM files WHERE snapshot_id=? ORDER BY path",
        (snapshot_id,),
    ).fetchall()


def content_identity(rows: list[tuple]) -> str:
    value = hashlib.sha256()
    for path, blob_hash, *_ in rows:
        value.update(path.encode("utf-8"))
        value.update(b"\0")
        value.update(blob_hash.encode("ascii"))
        value.update(b"\n")
    return value.hexdigest()


def archive_source(db: sqlite3.Connection, snapshot_id: str, blobs: Path, output: Path) -> dict:
    rows = source_rows(db, snapshot_id)
    snapshot = db.execute(
        "SELECT manifest,metrics,capabilities FROM snapshots WHERE id=?", (snapshot_id,)
    ).fetchone()
    if snapshot is None:
        raise ValueError(f"Missing snapshot: {snapshot_id}")
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".building-" + uuid.uuid4().hex)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as archive:
                archive.writestr("snapshot/manifest.json", snapshot[0] + "\n")
                archive.writestr("snapshot/metrics.json", snapshot[1] + "\n")
                archive.writestr("snapshot/capabilities.json", snapshot[2] + "\n")
                archive.writestr(
                    "snapshot/files.jsonl",
                    "".join(json.dumps({"path": path, "sha256": blob_hash, "bytes": size,
                                         "language": language, "line_count": lines},
                                        ensure_ascii=False) + "\n"
                            for path, blob_hash, size, language, lines in rows),
                )
                for path, blob_hash, size, _, _ in rows:
                    blob = blobs / blob_hash
                    content = blob.read_bytes()
                    if len(content) != size or hashlib.sha256(content).hexdigest() != blob_hash:
                        raise ValueError(f"Blob integrity failure: {snapshot_id} {path}")
                    archive.writestr(safe_member(path), content)
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {"archive": str(output), "sha256": sha256_file(output),
            "files": len(rows), "source_identity_sha256": content_identity(rows)}


def archive_relations(source_db: Path, snapshot_id: str, output: Path) -> dict:
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".building-" + uuid.uuid4().hex)
        source_uri = source_db.as_uri() + "?mode=ro"
        try:
            with closing(sqlite3.connect(temporary, uri=True)) as exported:
                exported.execute("ATTACH DATABASE ? AS origin", (source_uri,))
                exported.execute(
                    "CREATE TABLE snapshots AS SELECT * FROM origin.snapshots WHERE id=?",
                    (snapshot_id,),
                )
                for table in TABLES:
                    exported.execute(
                        f"CREATE TABLE {table} AS SELECT * FROM origin.{table} WHERE snapshot_id=?",
                        (snapshot_id,),
                    )
                exported.execute("CREATE INDEX symbol_name ON symbols(name)")
                exported.execute("CREATE INDEX symbol_owner ON symbols(owner_id)")
                exported.execute("CREATE INDEX edge_source ON edges(src_id)")
                exported.execute("CREATE INDEX edge_target ON edges(dst_id)")
                exported.execute("CREATE INDEX files_path ON files(path)")
                exported.execute("CREATE INDEX facts_kind ON facts(kind)")
                counts = {table: exported.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                          for table in TABLES}
                snapshot = exported.execute("SELECT metrics FROM snapshots").fetchone()
                if snapshot is None:
                    raise ValueError(f"Missing snapshot: {snapshot_id}")
                metrics = json.loads(snapshot[0])
                mismatches = {table: (counts[table], metrics.get(metric))
                              for table, metric in EXPECTED.items()
                              if counts[table] != metrics.get(metric)}
                if mismatches:
                    raise ValueError(f"Index row-count mismatch {snapshot_id}: {mismatches}")
                exported.commit()
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
    with sqlite3.connect(output.as_uri() + "?mode=ro", uri=True) as check:
        counts = {table: check.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in TABLES}
        ident = check.execute("SELECT id FROM snapshots").fetchone()
        if ident is None or ident[0] != snapshot_id:
            raise ValueError(f"Index identity mismatch: {output}")
    return {"archive": str(output), "sha256": sha256_file(output), "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--blobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="*", help="Optional case IDs for a pilot or resume")
    args = parser.parse_args()
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    selected = [row for row in runs if row["condition"] in {"B0", "P1"}
                and row["settings"].get("snapshot_role") == "vulnerable"]
    if len(selected) != 450 or len({row["case_id"] for row in selected}) != 75:
        raise SystemExit("Expected exactly 450 selected B0/P1 runs from 75 vulnerable cases")
    cases: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in selected:
        cases[row["case_id"]][row["snapshot_id"]].add(row["label"] + "/" + row["condition"])
    wanted = set(args.cases or cases)
    unknown = wanted - cases.keys()
    if unknown:
        raise SystemExit(f"Unknown cases: {sorted(unknown)}")
    args.output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.database.as_uri() + "?mode=ro", uri=True)
    cohort = {"schema_version": 1, "source": str(args.runs),
              "selected_runs": len(selected), "case_count": len(cases),
              "actual_snapshot_count": len({r["snapshot_id"] for r in selected}),
              "excluded_case_ids": [f"VUL4J-{i}" for i in range(1, 80)
                                    if f"VUL4J-{i}" not in cases], "cases": []}
    for case_id in sorted(cases, key=lambda value: int(value.split("-")[1])):
        variants = cases[case_id]
        if case_id not in wanted:
            continue
        canonical = next(row["snapshot_id"] for row in selected
                         if row["case_id"] == case_id and row["label"] == "flash_high"
                         and row["condition"] == "B0")
        identity = content_identity(source_rows(db, canonical))
        for snapshot_id in variants:
            if content_identity(source_rows(db, snapshot_id)) != identity:
                raise ValueError(f"Source content differs between runs of {case_id}")
        case_dir = args.output / case_id
        source = archive_source(db, canonical, args.blobs, case_dir / "B0" / "source.zip")
        indexes = []
        for snapshot_id in sorted(variants):
            result = archive_relations(
                args.database, snapshot_id,
                case_dir / "P1" / f"relations-{snapshot_id[:12]}.sqlite3",
            )
            indexes.append({"snapshot_id": snapshot_id, "used_by": sorted(variants[snapshot_id]),
                            **result})
        case_record = {"case_id": case_id, "source_snapshot_id": canonical,
                       "source": source, "relation_indexes": indexes}
        save_json(case_dir / "case.json", case_record)
        cohort["cases"].append(case_record)
        print(f"{case_id}: source {source['files']} files; {len(indexes)} P1 index(es)", flush=True)
    save_json(args.output / "cohort.json", cohort)
    print(f"Archived {len(cohort['cases'])} cases to {args.output}", flush=True)


if __name__ == "__main__":
    main()
