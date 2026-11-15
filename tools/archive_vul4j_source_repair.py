"""Archive corrected B0/P1 inputs for Vul4J 57, 69, 70 and 71.

The original 75-case archive is untouched. The database is opened read-only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from archive_vul4j_inputs import archive_relations, archive_source, save_json
from audit_vul4j_source_inputs import audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--blobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-free-gib", type=float, default=2.0)
    parser.add_argument("--cases", nargs="*", choices=["VUL4J-57", "VUL4J-69", "VUL4J-70", "VUL4J-71"])
    args = parser.parse_args()

    checked = audit(args.database)
    if any(row["status"] != "ready" for row in checked["cases"]):
        raise SystemExit("A corrected source input failed the source-only audit")
    args.output.mkdir(parents=True, exist_ok=True)
    for row in checked["cases"]:
        case_id, snapshot_id = row["case_id"], row["snapshot_id"]
        if args.cases and case_id not in args.cases:
            continue
        if shutil.disk_usage(args.output).free < args.min_free_gib * (1024 ** 3):
            raise SystemExit(f"Insufficient free space before {case_id}; prior exports are preserved")
        case_dir = args.output / case_id
        with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            source = archive_source(
                db, snapshot_id, args.blobs, case_dir / "B0" / "source.zip",
            )
        relation = archive_relations(
            args.database, snapshot_id,
            case_dir / "P1" / f"relations-{snapshot_id[:12]}.sqlite3",
        )
        # Keep the publication record portable. Archive helpers return local
        # absolute paths, but case records are rooted at the supplement folder.
        source["archive"] = f"{case_id}/B0/source.zip"
        relation["archive"] = f"{case_id}/P1/relations-{snapshot_id[:12]}.sqlite3"
        record = {
            "case_id": case_id,
            "source_snapshot_id": snapshot_id,
            "collector_version": row["collector_version"],
            "source": source,
            "relation_data": relation,
            "source_audit": row,
            "input_contract": "B0=source.zip source/; P1=the same source plus relation_data",
        }
        save_json(case_dir / "case.json", record)
        completed = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(args.output.glob("VUL4J-*/case.json"))
        ]
        save_json(args.output / "cohort-supplement.json", {
            "schema_version": 1,
            "case_count": len(completed),
            "cases": completed,
            "note": "Supplement to the frozen 75-case archive; no model outputs or labels",
        })
        print(f"{case_id}: {source['files']} source files; relation data saved", flush=True)


if __name__ == "__main__":
    main()
