"""Read-only structural and optional SHA-256 checks for archived research inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vul4j", type=Path, required=True,
                        help="Directory containing cohort.json and VUL4J-* subdirectories")
    parser.add_argument("--spring", type=Path, required=True,
                        help="Spring Boot directory containing experiment input archive")
    parser.add_argument("--full-hash", action="store_true")
    args = parser.parse_args()
    cohort = json.loads((args.vul4j / "cohort.json").read_text(encoding="utf-8"))
    cases = cohort["cases"]
    if (cohort["case_count"], cohort["selected_runs"], len(cases)) != (75, 450, 75):
        raise ValueError("Vul4J cohort size is incomplete")
    if set(cohort["excluded_case_ids"]) != {"VUL4J-57", "VUL4J-69", "VUL4J-70", "VUL4J-71"}:
        raise ValueError("Unexpected excluded Vul4J cases")
    seen = set()
    index_count = 0
    for case in cases:
        case_id = case["case_id"]
        if case_id in seen:
            raise ValueError(f"Duplicate case: {case_id}")
        seen.add(case_id)
        local = args.vul4j / case_id
        record = json.loads((local / "case.json").read_text(encoding="utf-8"))
        if record != case:
            raise ValueError(f"Cohort and case manifest differ: {case_id}")
        source = local / "B0" / "source.zip"
        with zipfile.ZipFile(source) as bundle:
            members = bundle.namelist()
            if len(members) != case["source"]["files"] + 4:
                raise ValueError(f"Source member count mismatch: {case_id}")
            listing = bundle.read("snapshot/files.jsonl").splitlines()
            if len(listing) != case["source"]["files"]:
                raise ValueError(f"Source manifest count mismatch: {case_id}")
        if args.full_hash and sha256(source) != case["source"]["sha256"]:
            raise ValueError(f"Source ZIP hash mismatch: {case_id}")
        for relation in case["relation_indexes"]:
            path = local / "P1" / f"relations-{relation['snapshot_id'][:12]}.sqlite3"
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                row = db.execute("SELECT id FROM snapshots").fetchone()
                if row is None or row[0] != relation["snapshot_id"]:
                    raise ValueError(f"Snapshot mismatch: {path}")
                for table, expected in relation["counts"].items():
                    if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] != expected:
                        raise ValueError(f"Table count mismatch: {path} {table}")
            if args.full_hash and sha256(path) != relation["sha256"]:
                raise ValueError(f"Relation database hash mismatch: {path}")
            index_count += 1
    if index_count != 80:
        raise ValueError(f"Expected 80 Vul4J relation indices, found {index_count}")

    spring = json.loads((args.spring / "실험입력" / "archive-manifest.json").read_text(encoding="utf-8"))
    spring_zip = args.spring / "실험입력" / "B0" / "source.zip"
    with zipfile.ZipFile(spring_zip) as bundle:
        if len(bundle.namelist()) != spring["tracked_files"] or spring["tracked_files"] != 11923:
            raise ValueError("Spring source count mismatch")
    spring_db = args.spring / "실험입력" / "P1" / "relations.sqlite3"
    with sqlite3.connect(spring_db.as_uri() + "?mode=ro", uri=True) as db:
        snapshot_id = json.loads((args.spring / "실험입력" / "experiment.json")
                                 .read_text(encoding="utf-8"))["index_snapshot"]
        for table, expected in spring["P1_relation_database"]["counts"].items():
            if db.execute(f"SELECT count(*) FROM {table} WHERE snapshot_id=?",
                          (snapshot_id,)).fetchone()[0] != expected:
                raise ValueError(f"Spring relation count mismatch: {table}")
    if args.full_hash:
        if sha256(spring_zip) != spring["B0_source_archive"]["sha256"]:
            raise ValueError("Spring source ZIP hash mismatch")
        if sha256(spring_db) != spring["P1_relation_database"]["sha256"]:
            raise ValueError("Spring relation database hash mismatch")
    print(json.dumps({"vul4j_cases": len(cases), "vul4j_snapshots": index_count,
                      "spring_files": spring["tracked_files"], "full_hash": args.full_hash}))


if __name__ == "__main__":
    main()
