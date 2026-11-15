"""End-to-end checks for the packaged command and read-only tool interface."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from relation_index.cli import main
from relation_index.tool_api import definitions


class CLITest(unittest.TestCase):
    @staticmethod
    def command(*args: str) -> object:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(list(args))
        return json.loads(output.getvalue())

    def test_build_and_read_only_queries(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            data = str(Path(folder) / "index")
            project = str(ROOT / "tests" / "fixture")
            prefix = ("--data-dir", data, "--project", project)

            result = self.command(*prefix, "build")
            self.assertEqual(result["metrics"]["java_files"], 2)
            self.assertTrue(result["snapshot_id"])

            overview = self.command(*prefix, "call", "get_source_scope", "{}")
            self.assertEqual(overview["metrics"]["symbols"], 5)
            found = self.command(*prefix, "call", "find_symbols", '{"query":"Service"}')
            self.assertGreater(found["total"], 0)
            files = self.command(*prefix, "call", "list_files", '{"limit":1}')
            self.assertEqual(files["total"], 2)
            self.assertTrue(files["truncated"])
            facts = self.command(*prefix, "call", "search_relation_facts", '{"limit":1}')
            self.assertEqual(facts["total"], 2)
            matches = self.command(*prefix, "call", "search_code", '{"query":"find"}')
            self.assertGreater(matches["total"], 0)
            read = self.command(*prefix, "call", "read_file", '{"path":"Service.java"}')
            self.assertEqual(read["path"], "Service.java")
            job = self.command("--data-dir", data, "job", result["job_id"])
            self.assertEqual(job["status"], "completed")

            with self.assertRaises(SystemExit):
                self.command(*prefix, "call", "read_file", '{"path":"../secret"}')
            with self.assertRaises(SystemExit):
                self.command(*prefix, "call", "unknown", "{}")
            with self.assertRaises(SystemExit):
                self.command(*prefix, "call", "read_file", '{"path":"Service.java","execute":true}')
            with self.assertRaises(SystemExit):
                self.command(*prefix, "call", "read_file", "{}")
            with self.assertRaises(SystemExit):
                self.command(*prefix, "call", "find_symbols", '{"limit":"10"}')

    def test_tool_catalog_is_read_only(self) -> None:
        names = {item["name"] for item in definitions()}
        self.assertIn("trace_relations", names)
        self.assertNotIn("build", names)
        self.assertTrue(all(item["read_only"] for item in definitions()))
        read_tool = next(item for item in definitions() if item["name"] == "read_file")
        self.assertEqual(read_tool["parameters"]["required"], ["path"])

    def test_query_does_not_create_missing_index(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "absent"
            with self.assertRaises(FileNotFoundError):
                self.command(
                    "--data-dir", str(missing),
                    "--project", str(ROOT / "tests" / "fixture"),
                    "overview",
                )
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
