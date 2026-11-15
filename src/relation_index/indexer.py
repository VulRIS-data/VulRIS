"""Build immutable, multi-language relation-index snapshots."""

import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from .frameworks import VERSIONS as FRAMEWORK_VERSIONS
from .frameworks import extract as extract_frameworks
from .frameworks.config_files import VERSION as CONFIG_RULES_VERSION
from .frameworks.config_files import extract as extract_config
from .languages import default_registry
from .resolver import VERSION as RESOLVER_VERSION
from .resolver import resolve
from .snapshot import collect
from .storage import Cancelled, atomic_write, digest, encode


def _analysis_signature(manifest, registry):
    languages = []
    for name in sorted({item["language"] for item in manifest["files"]}):
        frontend = registry.get(name)
        if frontend is not None:
            languages.append((name, frontend.VERSION if frontend.available() else "unavailable", frontend.RULES_VERSION))
    return {"languages": languages, "frameworks": sorted({**FRAMEWORK_VERSIONS, "config_files": CONFIG_RULES_VERSION}.items()), "resolver": RESOLVER_VERSION}


def _capabilities(registry, parsed_counts):
    languages = {}
    for name, frontend in registry.all().items():
        available = frontend.available()
        languages[name] = {
            "status": "available" if available else "unavailable",
            "parser_version": frontend.VERSION if available else "unavailable",
            "rules_version": frontend.RULES_VERSION,
            "extracted": parsed_counts.get(name, 0),
            "resolution": "syntax_candidates", "semantic": "not_available",
            "limits": "No runtime dispatch, data flow, or control-flow proof",
            "error": frontend.unavailable_reason(),
        }
    return {
        "syntax": "Declarations, imports and call sites for supported language parsers",
        "relations": "Syntax containment plus name, type and arity candidate relations",
        "semantic_resolution": "not_implemented", "data_flow": "not_implemented",
        "control_flow": "not_implemented",
        "spring": "Annotation-name candidates; runtime DI, profiles and security enforcement unverified",
        "incremental": "Unchanged files reuse syntax cache; cross-file candidates are rebuilt",
        "parser_version": registry.get("java").VERSION, "languages": languages,
        "frameworks": {name: {"rules_version": version, "status": "candidate_evidence"} for name, version in sorted({**FRAMEWORK_VERSIONS, "config_files": CONFIG_RULES_VERSION}.items())},
        "resolver_version": RESOLVER_VERSION,
    }


def build_index(store, job, registry=default_registry):
    job_id = job["id"]
    project = store.one("SELECT * FROM projects WHERE id=?", (job["project_id"],))
    started, cpu = time.monotonic(), time.process_time()
    store.phase(job_id, "collecting", "원본 파일을 수집하고 버전별 사본을 보관합니다.")
    manifest = collect(Path(project["root"]), store, lambda: store.checkpoint(job_id), on_file=lambda current, total, path: store.progress(job_id, current, total, path))
    signature = _analysis_signature(manifest, registry)
    manifest["analysis_signature"] = signature
    snapshot_id = digest([project["id"], manifest["content_hash"], signature])
    if store.all("SELECT id FROM snapshots WHERE id=?", (snapshot_id,)):
        store.checkpoint(job_id)
        with store.connect() as db:
            if db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()[0]:
                raise Cancelled()
            db.execute("UPDATE projects SET active_snapshot=? WHERE id=?", (snapshot_id, project["id"]))
        return {"snapshot_id": snapshot_id, "reused": True}

    store.phase(job_id, "parsing", "지원 언어의 선언, import와 호출 위치를 추출합니다.")
    parsed, facts, errors = [], [], []
    hits, misses, parsed_counts = 0, Counter(), Counter()
    unavailable = defaultdict(lambda: {"files": 0, "reason": ""})
    failures = []
    error_languages = defaultdict(list)
    for current, file in enumerate(manifest["files"], start=1):
        store.checkpoint(job_id)
        path, blob_hash, language = file["path"], file["hash"], file["language"]
        store.progress(job_id, current, len(manifest["files"]), path)
        facts.extend(extract_config(file))
        frontend = registry.get(language)
        if frontend is None:
            continue
        if not frontend.available():
            unavailable[language]["files"] += 1
            unavailable[language]["reason"] = frontend.unavailable_reason()
            continue
        content = store.get_blob(blob_hash)
        cache = store.settings.data_dir / "parse_cache" / (digest([path, blob_hash, language, frontend.VERSION, frontend.RULES_VERSION]) + ".json")
        try:
            entry = None
            if cache.exists():
                try:
                    candidate = json.loads(cache.read_text(encoding="utf-8"))
                    if isinstance(candidate, dict) and {"symbols", "calls", "facts", "parse_error", "language", "anchors"} <= candidate.keys():
                        entry, hits = candidate, hits + 1
                except (OSError, UnicodeError, ValueError):
                    entry = None
            if entry is None:
                entry = frontend.extract(path, content)
                atomic_write(cache, encode(entry).encode("utf-8"))
                misses[language] += 1
            facts.extend(extract_frameworks(entry, content))
            parsed.append(entry)
            parsed_counts[language] += 1
            if entry["parse_error"]:
                errors.append(path)
                error_languages[language].append(path)
        except Exception as exc:
            failures.append({"path": path, "language": language, "error": f"{type(exc).__name__}: {exc}"})

    store.phase(job_id, "resolving", "호출, import와 상속 후보를 연결하고 불확실성을 기록합니다.")
    java_entries = [entry for entry in parsed if entry["language"] == "java"]
    other_entries = [entry for entry in parsed if entry["language"] != "java"]
    symbols, calls, edges, import_counts = [], [], [], {"unresolved": {}, "external": {}}
    if java_entries:
        part_symbols, part_calls, part_edges = registry.get("java").link(java_entries, lambda: store.checkpoint(job_id), lambda current, total, path: store.progress(job_id, current, total, path))
        symbols.extend(part_symbols); calls.extend(part_calls); edges.extend(part_edges)
    if other_entries:
        part_symbols, part_calls, part_edges, import_counts = resolve(other_entries, lambda: store.checkpoint(job_id), lambda current, total, path: store.progress(job_id, current, total, path))
        symbols.extend(part_symbols); calls.extend(part_calls); edges.extend(part_edges)

    files_by_language = Counter(item["language"] for item in manifest["files"])
    symbols_by_language = Counter(symbol.get("language", "java") for symbol in symbols)
    calls_by_language = Counter(call.get("language", "java") for call in calls)
    call_status, call_strategy = defaultdict(Counter), defaultdict(Counter)
    for call in calls:
        call_status[call.get("language", "java")][call.get("status", "unresolved")] += 1
        call_strategy[call.get("language", "java")][call.get("strategy", "java_legacy")] += 1
    fact_frameworks = Counter(fact.get("framework") or ("config_files" if fact["kind"] == "config_file" else "spring") for fact in facts)
    metrics = {
        "files": len(manifest["files"]), "java_files": parsed_counts.get("java", 0),
        "symbols": len(symbols), "calls": len(calls), "edges": len(edges), "facts": len(facts),
        "unresolved_calls": sum(not call.get("targets") for call in calls),
        "parse_errors": errors, "cache_hits": hits, "parsed_files": sum(misses.values()),
        "source_bytes": sum(item["size"] for item in manifest["files"]), "omitted_files": len(manifest["omitted"]),
        "files_by_language": dict(sorted(files_by_language.items())),
        "parsed_files_by_language": dict(sorted(parsed_counts.items())),
        "cache_misses_by_language": dict(sorted(misses.items())),
        "symbols_by_language": dict(sorted(symbols_by_language.items())),
        "calls_by_language": dict(sorted(calls_by_language.items())),
        "call_status_by_language": {name: dict(sorted(counts.items())) for name, counts in sorted(call_status.items())},
        "call_strategy_by_language": {name: dict(sorted(counts.items())) for name, counts in sorted(call_strategy.items())},
        "unresolved_calls_by_language": {name: sum(1 for call in calls if call.get("language", "java") == name and not call.get("targets")) for name in sorted(calls_by_language)},
        "parse_errors_by_language": {name: error_languages.get(name, []) for name in sorted(parsed_counts)},
        "parser_unavailable": dict(sorted(unavailable.items())), "extraction_failures": failures,
        "unresolved_imports_by_language": import_counts["unresolved"],
        "external_imports_by_language": import_counts["external"],
        "edges_by_kind": dict(sorted(Counter(edge["kind"] for edge in edges).items())),
        "facts_by_framework": dict(sorted(fact_frameworks.items())),
        "build_seconds": round(time.monotonic() - started, 4), "cpu_seconds": round(time.process_time() - cpu, 4),
    }
    capabilities = _capabilities(registry, parsed_counts)
    store.phase(job_id, "indexing", "검색 인덱스를 저장하고 새 버전을 활성화합니다.")
    published = False
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()[0]:
            raise Cancelled()
        if not db.execute("SELECT 1 FROM snapshots WHERE id=?", (snapshot_id,)).fetchone():
            db.execute("INSERT INTO snapshots(id,project_id,created_at,manifest,metrics,capabilities) VALUES(?,?,?,?,?,?)", (snapshot_id, project["id"], time.time(), encode(manifest), encode(metrics), encode(capabilities)))
            published = True
        for file in manifest["files"] if published else []:
            db.execute("INSERT INTO files(snapshot_id,path,hash,size,language,line_count) VALUES(?,?,?,?,?,?)", (snapshot_id, file["path"], file["hash"], file["size"], file["language"], file["line_count"]))
            db.execute("INSERT INTO file_search(snapshot_id,path,content) VALUES(?,?,?)", (snapshot_id, file["path"], store.get_blob(file["hash"]).decode("utf-8")))
        for symbol in symbols if published else []:
            language = symbol.get("language", "java")
            provenance = symbol.get("provenance") or registry.get(language).VERSION
            db.execute("INSERT INTO symbols(snapshot_id,id,path,kind,name,qualified_name,owner_id,signature,start_line,end_line,language,provenance,data) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (snapshot_id, symbol["id"], symbol["path"], symbol["kind"], symbol["name"], symbol["qualified_name"], symbol.get("owner_id"), symbol["signature"], symbol["start_line"], symbol["end_line"], language, provenance, encode(symbol)))
        for call in calls if published else []:
            language = call.get("language", "java")
            provenance = call.get("provenance") or registry.get(language).VERSION
            db.execute("INSERT INTO calls(snapshot_id,id,caller_id,path,start_line,language,provenance,data) VALUES(?,?,?,?,?,?,?,?)", (snapshot_id, call["id"], call.get("caller_id"), call["path"], call["start_line"], language, provenance, encode(call)))
        for edge in edges if published else []:
            language = edge.get("language", "java" if edge.get("provenance", "").startswith("java-") else None)
            db.execute("INSERT INTO edges(snapshot_id,id,src_id,dst_id,kind,language,provenance,data) VALUES(?,?,?,?,?,?,?,?)", (snapshot_id, edge["id"], edge["src_id"], edge["dst_id"], edge["kind"], language, edge.get("provenance"), encode(edge)))
        for fact in facts if published else []:
            language = fact.get("language")
            if language is None and fact.get("kind") != "config_file": language = "java"
            db.execute("INSERT INTO facts(snapshot_id,id,symbol_id,path,kind,language,provenance,data) VALUES(?,?,?,?,?,?,?,?)", (snapshot_id, fact["id"], fact.get("symbol_id"), fact["path"], fact["kind"], language, fact.get("provenance"), encode(fact)))
        db.execute("UPDATE projects SET active_snapshot=? WHERE id=?", (snapshot_id, project["id"]))
    if not published:
        return {"snapshot_id": snapshot_id, "reused": True}
    metrics["build_seconds"] = round(time.monotonic() - started, 4)
    metrics["cpu_seconds"] = round(time.process_time() - cpu, 4)
    store.execute("UPDATE snapshots SET metrics=? WHERE id=?", (encode(metrics), snapshot_id))
    return {"snapshot_id": snapshot_id, "reused": False, "metrics": metrics}
