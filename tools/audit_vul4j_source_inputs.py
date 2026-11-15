"""Check that the four repaired Vul4J source snapshots retain their Java packages.

This is a source-only, read-only audit. It does not execute static scanners or LLMs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

EXPECTED_PACKAGES = {
    57: ["src/main/java/org/jenkinsci/plugins/workflow/support/steps/build"],
    69: [
        "spring-aop/src/main/java/org/springframework/aop/framework/autoproxy/target",
        "spring-aop/src/main/java/org/springframework/aop/target",
        "spring-orm-hibernate4/src/main/java/org/springframework/orm/jpa/vendor",
        "spring-orm/src/main/java/org/springframework/orm/jpa/vendor",
    ],
    70: [
        "spring-aop/src/main/java/org/springframework/aop/framework/autoproxy/target",
        "spring-aop/src/main/java/org/springframework/aop/target",
        "spring-orm/src/main/java/org/springframework/orm/jpa/vendor",
    ],
    71: [
        "spring-aop/src/main/java/org/springframework/aop/framework/autoproxy/target",
        "spring-aop/src/main/java/org/springframework/aop/target",
        "spring-orm-hibernate4/src/main/java/org/springframework/orm/jpa/vendor",
        "spring-orm/src/main/java/org/springframework/orm/jpa/vendor",
    ],
}


def blind_name(number: int, seed: int) -> str:
    value = f"blind-v2:{seed}:VUL4J-{number}:vulnerable"
    return "sample-blind-v2-" + hashlib.sha256(value.encode()).hexdigest()[:16]


def audit(database: Path, seed: int = 20260921) -> dict:
    results = []
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for number, expected in EXPECTED_PACKAGES.items():
            project = db.execute(
                "SELECT active_snapshot FROM projects WHERE name=? "
                "ORDER BY created_at DESC LIMIT 1",
                (blind_name(number, seed),),
            ).fetchone()
            snapshot_id = project["active_snapshot"] if project else None
            row = db.execute(
                "SELECT manifest,metrics FROM snapshots WHERE id=?", (snapshot_id,)
            ).fetchone() if snapshot_id else None
            if row is None:
                results.append({"case_id": f"VUL4J-{number}", "status": "missing_snapshot"})
                continue
            manifest = json.loads(row["manifest"])
            metrics = json.loads(row["metrics"])
            omitted = {
                entry.get("path") for entry in manifest.get("omitted", [])
                if entry.get("reason") == "excluded"
            }
            package_files = {
                prefix: db.execute(
                    "SELECT count(*) FROM files WHERE snapshot_id=? AND path LIKE ?",
                    (snapshot_id, prefix + "/%"),
                ).fetchone()[0]
                for prefix in expected
            }
            actual_files = db.execute(
                "SELECT count(*) FROM files WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()[0]
            problems = []
            if manifest.get("collector_version") != "snapshot-v7":
                problems.append("unexpected_collector_version")
            if metrics.get("java_files", 0) <= 0:
                problems.append("no_java_files")
            if actual_files != metrics.get("files"):
                problems.append("file_count_mismatch")
            for prefix, count in package_files.items():
                if prefix in omitted or count == 0:
                    problems.append("missing_source_package:" + prefix)
            results.append({
                "case_id": f"VUL4J-{number}",
                "status": "ready" if not problems else "invalid",
                "snapshot_id": snapshot_id,
                "collector_version": manifest.get("collector_version"),
                "java_files": metrics.get("java_files"),
                "source_files": actual_files,
                "required_package_file_counts": package_files,
                "problems": problems,
            })
    return {"schema_version": 1, "case_count": 4, "cases": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.database)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({row["case_id"]: row["status"] for row in report["cases"]}, ensure_ascii=False))
    if any(row["status"] != "ready" for row in report["cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
