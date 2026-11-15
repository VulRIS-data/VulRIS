from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from relation_index.config import Settings
from relation_index.frameworks import extract as framework_extract
from relation_index.indexer import build_index
from relation_index.languages import Registry, default_registry
from relation_index.languages.registry import UnavailableFrontend
from relation_index.queries import Queries
from relation_index.storage import Store

LANGUAGES = ("python", "javascript", "typescript", "go", "csharp", "c", "cpp", "rust", "php", "ruby", "kotlin", "swift")

# language -> (caller, callee, inheritance edges, fact kinds, framework, route path)
EXPECTED = {
    "python": ("app.main.read_user", "app.service.UserService.find", [("EXTENDS", "app.service.UserService", "app.service.BaseService")], {"route", "input", "guard", "injection", "security_call"}, "fastapi", "/users/{user_id}"),
    "javascript": ("app.<anonymous@8>", "service.UserService.find", [("EXTENDS", "service.UserService", "service.BaseService")], {"route", "input", "guard"}, "express", "/users/:id"),
    "typescript": ("user.controller.UserController.get", "user.service.UserService.find", [("IMPLEMENTS", "user.service.UserService", "user.service.Finder")], {"route", "input", "guard", "injection"}, "nestjs", "/users/:id"),
    "go": ("main.main.<anonymous@13>", "service.Base.Find", [("EXTENDS", "service.UserService", "service.Base")], {"route", "input", "guard"}, "gin", "/users/:id"),
    "csharp": ("Demo.Api.UsersController.Get", "Demo.Services.UserService.Find", [("IMPLEMENTS", "Demo.Services.UserService", "Demo.Services.IFinder")], {"route", "input", "guard", "injection"}, "aspnet", "/api/users/{id}"),
    "c": ("main", "find_user", [], {"security_call"}, "security_calls", None),
    "cpp": ("main", "UserService::find", [("EXTENDS", "UserService", "BaseService")], {"security_call"}, "security_calls", None),
    "rust": ("show_user", "UserService::find", [("IMPLEMENTS", "UserService", "Finder")], {"route", "input", "guard"}, "axum", "/users/:id"),
    "php": ("App\\Http\\Controllers\\UserController::show", "App\\Services\\UserService::find", [("IMPLEMENTS", "App\\Services\\UserService", "App\\Services\\Finder")], {"route", "input", "guard"}, "laravel", "/users/{id}"),
    "ruby": ("UsersController#show", "UserService#find", [("EXTENDS", "UserService", "BaseService")], {"route", "input", "guard"}, "rails", "/users/:id"),
    "kotlin": ("demo.web.UserController.show", "demo.service.UserService.find", [("EXTENDS", "demo.service.UserService", "demo.service.BaseService")], {"route", "input", "guard"}, "spring", "/users/{id}"),
    "swift": ("showUser", "UserService.find", [("EXTENDS", "UserService", "BaseService"), ("IMPLEMENTS", "UserService", "Finder")], {"security_call"}, "security_calls", None),
}


def run_build(source: Path, data: Path, registry=default_registry, project_id=None):
    store = Store(Settings(data))
    project_id = project_id or uuid.uuid5(uuid.NAMESPACE_URL, str(source)).hex
    with store.connect() as db:
        db.execute("INSERT OR IGNORE INTO projects(id,name,root,created_at) VALUES(?,?,?,?)", (project_id, source.name, str(source), time.time()))
    job = store.enqueue(project_id, "index", {})
    store.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
    return store, build_index(store, job, registry)


def rows(store, snapshot_id):
    return {
        table: sorted(row["data"] for row in store.all(f"SELECT data FROM {table} WHERE snapshot_id=?", (snapshot_id,)))
        for table in ("symbols", "calls", "edges", "facts")
    }


class MultiLanguageTest(unittest.TestCase):
    def test_java_golden_rows_remain_identical(self):
        frontend = default_registry.get("java")
        for name, folder in (("java_minimal.json", "fixture"), ("java_spring.json", "fixtures/java_spring")):
            expected = json.loads((ROOT / "tests/golden" / name).read_text(encoding="utf-8"))
            entries, facts = [], []
            for path in sorted((ROOT / "tests" / folder).rglob("*.java")):
                entry = frontend.extract(path.relative_to(ROOT / "tests" / folder).as_posix(), path.read_bytes())
                facts.extend(framework_extract(entry, path.read_bytes()))
                entries.append(entry)
            symbols, calls, edges = frontend.link(entries)
            self.assertEqual(sorted(symbols, key=lambda item: item["id"]), expected["symbols"])
            self.assertEqual(sorted(calls, key=lambda item: item["id"]), expected["calls"])
            self.assertEqual(sorted(edges, key=lambda item: item["id"]), expected["edges"])
            self.assertEqual(sorted(facts, key=lambda item: item["id"]), expected["facts"])

    def test_each_language_links_cross_file_calls_inheritance_and_facts(self):
        for language in LANGUAGES:
            with self.subTest(language=language), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                shutil.copytree(ROOT / "tests/fixtures" / language, root / "source")
                store, result = run_build(root / "source", root / "data")
                metrics = result["metrics"]
                self.assertEqual(metrics["parse_errors"], [])
                self.assertEqual(metrics["extraction_failures"], [])
                snapshot = result["snapshot_id"]
                symbols = {row["id"]: row for row in store.all("SELECT * FROM symbols WHERE snapshot_id=?", (snapshot,))}
                self.assertTrue(all(row["language"] in {language, "c", "cpp"} for row in symbols.values()))
                name = lambda key: symbols[key]["qualified_name"]
                edges = [json.loads(row["data"]) for row in store.all("SELECT data FROM edges WHERE snapshot_id=?", (snapshot,))]
                found = {(edge["kind"], name(edge["src_id"]), name(edge["dst_id"]), edge["status"]) for edge in edges}
                caller, callee, inheritance, kinds, framework, route = EXPECTED[language]
                self.assertIn(("CALLS", caller, callee, "candidate"), found)
                for kind, child, parent in inheritance:
                    self.assertIn((kind, child, parent, "candidate"), found)
                facts = [json.loads(row["data"]) for row in store.all("SELECT data FROM facts WHERE snapshot_id=? AND kind<>'config_file'", (snapshot,))]
                self.assertTrue(kinds <= {fact["kind"] for fact in facts}, {fact["kind"] for fact in facts})
                self.assertIn(framework, {fact.get("framework") for fact in facts})
                self.assertTrue(all(fact["status"] == "candidate" for fact in facts))
                if route:
                    paths = {path for fact in facts if fact["kind"] == "route" for path in fact.get("paths", [])}
                    self.assertIn(route, paths)

    def test_mixed_repository_is_deterministic_and_filterable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            for language in ("java_spring", "python", "typescript", "go", "rust"):
                shutil.copytree(ROOT / "tests/fixtures" / language, source / language)
            first_store, first = run_build(source, root / "first", project_id="fixed")
            second_store, second = run_build(source, root / "second", project_id="fixed")
            self.assertEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertEqual(rows(first_store, first["snapshot_id"]), rows(second_store, second["snapshot_id"]))
            _, reused = run_build(source, root / "first", project_id="fixed")
            self.assertTrue(reused["reused"])
            query = Queries(first_store, first["snapshot_id"])
            self.assertTrue(query.files(language="python")["items"])
            self.assertEqual({item["path"].split("/")[0] for item in query.symbols(language="typescript", limit=100)["items"]}, {"typescript"})
            self.assertEqual(set(first["metrics"]["symbols_by_language"]), {"java", "python", "typescript", "go", "rust"})

    def test_parse_cache_is_reused_for_java_and_other_languages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            shutil.copytree(ROOT / "tests/fixtures/java_spring", source / "java")
            shutil.copytree(ROOT / "tests/fixtures/python", source / "python")
            shutil.copytree(source, root / "copy")
            store, first = run_build(source, root / "data", project_id="one")
            _, second = run_build(root / "copy", root / "data", project_id="two")
            self.assertEqual(second["metrics"]["parsed_files"], 0)
            self.assertEqual(second["metrics"]["cache_hits"], first["metrics"]["parsed_files"])
            first_rows, second_rows = rows(store, first["snapshot_id"]), rows(store, second["snapshot_id"])
            self.assertEqual(first_rows, second_rows)

    def test_every_language_supports_core_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            for fixture in (ROOT / "tests/fixtures").iterdir():
                if fixture.is_dir():
                    shutil.copytree(fixture, source / fixture.name)
            store, result = run_build(source, root / "data")
            query = Queries(store, result["snapshot_id"])
            for language in ("java", *LANGUAGES):
                with self.subTest(language=language):
                    files = query.files(language=language)
                    symbols = query.symbols(language=language)
                    self.assertTrue(files["items"])
                    self.assertTrue(symbols["items"])
                    readable = next(item for item in files["items"] if item["line_count"])
                    self.assertTrue(query.read(readable["path"])["lines"])
                    symbol_id = symbols["items"][0]["id"]
                    self.assertIn("items", query.relations(symbol_id))
                    self.assertEqual(query.context(symbol_id)["symbol"]["id"], symbol_id)
            fact_kinds = {fact["kind"] for fact in query.facts(limit=100)["items"]}
            self.assertTrue({"route", "input", "guard", "config_file"} <= fact_kinds)

    def test_external_imports_are_not_matched_to_project_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            (source / "util.py").write_text("def join(a, b):\n    return a + b\n", encoding="utf-8")
            (source / "main.py").write_text("import os\n\ndef run(a, b):\n    return os.path.join(a, b)\n", encoding="utf-8")
            store, result = run_build(source, root / "data")
            calls = [json.loads(row["data"]) for row in store.all("SELECT data FROM calls WHERE snapshot_id=?", (result["snapshot_id"],))]
            join = next(call for call in calls if call["name"] == "join")
            self.assertEqual(join["status"], "unresolved")
            self.assertEqual(join["strategy"], "external_receiver")
            self.assertEqual(result["metrics"]["external_imports_by_language"], {"python": 1})

    def test_parse_error_and_header_language_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            (source / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            (source / "shared.h").write_text("int shared();\n", encoding="utf-8")
            (source / "main.cpp").write_text("int main() { return shared(); }\n", encoding="utf-8")
            store, result = run_build(source, root / "data")
            self.assertIn("broken.py", result["metrics"]["parse_errors"])
            self.assertEqual(result["metrics"]["parse_errors_by_language"]["python"], ["broken.py"])
            files = Queries(store, result["snapshot_id"]).files(language="cpp", limit=100)["items"]
            self.assertEqual({item["path"] for item in files}, {"main.cpp", "shared.h"})

    def test_unavailable_parser_does_not_stop_other_languages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            shutil.copytree(ROOT / "tests/fixtures/python", source / "python")
            shutil.copytree(ROOT / "tests/fixtures/go", source / "go")
            registry = Registry({"python": UnavailableFrontend("python", "test parser missing")})
            store, result = run_build(source, root / "data", registry)
            self.assertEqual(result["metrics"]["parser_unavailable"]["python"]["files"], 3)
            self.assertGreater(result["metrics"]["symbols_by_language"]["go"], 0)
            capabilities = Queries(store, result["snapshot_id"]).overview()["capabilities"]
            self.assertEqual(capabilities["languages"]["python"]["status"], "unavailable")

    def test_v1_schema_migrates_to_language_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            db_path = data / "relations.sqlite3"
            db = sqlite3.connect(db_path)
            db.executescript(
                "CREATE TABLE symbols(snapshot_id TEXT,id TEXT,path TEXT,kind TEXT,name TEXT,qualified_name TEXT,owner_id TEXT,signature TEXT,start_line INTEGER,end_line INTEGER,data TEXT,PRIMARY KEY(snapshot_id,id));"
                "CREATE TABLE calls(snapshot_id TEXT,id TEXT,caller_id TEXT,path TEXT,start_line INTEGER,data TEXT,PRIMARY KEY(snapshot_id,id));"
                "CREATE TABLE edges(snapshot_id TEXT,id TEXT,src_id TEXT,dst_id TEXT,kind TEXT,data TEXT,PRIMARY KEY(snapshot_id,id));"
                "CREATE TABLE facts(snapshot_id TEXT,id TEXT,symbol_id TEXT,path TEXT,kind TEXT,data TEXT,PRIMARY KEY(snapshot_id,id));"
                "INSERT INTO symbols VALUES('s','a','A.java','class','A','A',NULL,'class A',1,1,'{\"provenance\":\"java-syntax-v3-ts0.25-java0.23\"}');"
                "INSERT INTO facts VALUES('s','f',NULL,'pom.xml','config_file','{}');"
                "PRAGMA user_version=1;"
            )
            db.commit()
            db.close()
            Store(Settings(data))
            db = sqlite3.connect(db_path)
            try:
                for table in ("symbols", "calls", "edges", "facts"):
                    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                    self.assertTrue({"language", "provenance"} <= columns)
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT language,provenance FROM symbols").fetchone(), ("java", "java-syntax-v3-ts0.25-java0.23"))
                self.assertEqual(db.execute("SELECT language FROM facts").fetchone(), (None,))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
