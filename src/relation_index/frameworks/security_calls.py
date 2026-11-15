"""Name-based sensitive-call hints for the non-Java languages.

A hint only says that a call uses a name commonly associated with process
execution, SQL, deserialization, file or network access. It does not prove
that the call reaches that API, that input is attacker controlled, or that
anything is exploitable. Java keeps the original Spring-era name table.
"""

from __future__ import annotations

import re

from ..storage import digest

VERSION = "security-call-rules-v2"

# language -> {call name: (category, receiver pattern or None)}
RULES = {
    "python": {
        "eval": ("code", None), "exec": ("code", None), "compile": ("code", r"^$"),
        "system": ("process", r"^os$"), "popen": ("process", r"^os$"), "Popen": ("process", r"subprocess"),
        "run": ("process", r"^subprocess$"), "call": ("process", r"^subprocess$"), "check_output": ("process", r"^subprocess$"),
        "loads": ("deserialization", r"^(pickle|cPickle|marshal|dill|shelve)$"), "load": ("deserialization", r"^(pickle|yaml|marshal|dill)$"),
        "execute": ("sql", None), "executemany": ("sql", None), "raw": ("sql", None), "executescript": ("sql", None),
        "open": ("file", r"^$"), "send_file": ("file", None), "urlopen": ("network", None), "redirect": ("redirect", r"^$"),
    },
    "javascript": {
        "eval": ("code", r"^$"), "Function": ("code", r"^$"), "exec": ("process", r"child_process|^cp$|^$"), "execSync": ("process", None),
        "spawn": ("process", None), "query": ("sql", None), "raw": ("sql", None), "readFile": ("file", r"fs"), "readFileSync": ("file", r"fs"),
        "writeFile": ("file", r"fs"), "redirect": ("redirect", r"res"), "deserialize": ("deserialization", None), "unserialize": ("deserialization", None),
    },
    "go": {
        "Command": ("process", r"^exec$"), "CommandContext": ("process", r"^exec$"), "Query": ("sql", r"(?i)db|tx|conn|stmt"),
        "QueryRow": ("sql", r"(?i)db|tx|conn"), "Exec": ("sql", r"(?i)db|tx|conn|stmt"), "Open": ("file", r"^os$"), "ReadFile": ("file", r"^(os|ioutil)$"),
        "Redirect": ("redirect", r"^http$"), "Get": ("network", r"^http$"),
    },
    "csharp": {
        "Start": ("process", r"Process"), "Deserialize": ("deserialization", None), "ExecuteReader": ("sql", None), "ExecuteNonQuery": ("sql", None),
        "ExecuteScalar": ("sql", None), "FromSqlRaw": ("sql", None), "ExecuteSqlRaw": ("sql", None), "ReadAllText": ("file", r"File"), "Redirect": ("redirect", None),
    },
    "c": {
        "system": ("process", None), "popen": ("process", None), "execl": ("process", None), "execv": ("process", None), "execvp": ("process", None),
        "strcpy": ("memory", None), "strcat": ("memory", None), "sprintf": ("memory", None), "gets": ("memory", None), "memcpy": ("memory", None),
        "scanf": ("memory", None), "fopen": ("file", None),
    },
    "rust": {
        "new": ("process", r"Command$"), "execute": ("sql", None), "query": ("sql", None), "query_as": ("sql", None), "read_to_string": ("file", r"fs$"),
        "from_str": ("deserialization", r"serde_json|serde_yaml"), "transmute": ("memory", r"mem$"),
    },
    "php": {
        "eval": ("code", r"^$"), "exec": ("process", r"^$"), "system": ("process", r"^$"), "shell_exec": ("process", r"^$"), "passthru": ("process", r"^$"),
        "proc_open": ("process", r"^$"), "popen": ("process", r"^$"), "unserialize": ("deserialization", r"^$"), "query": ("sql", None),
        "raw": ("sql", None), "statement": ("sql", r"DB"), "file_get_contents": ("file", r"^$"), "include": ("file", r"^$"), "header": ("redirect", r"^$"),
    },
    "ruby": {
        "eval": ("code", None), "instance_eval": ("code", None), "system": ("process", r"^$"), "exec": ("process", r"^$"), "spawn": ("process", None),
        "constantize": ("code", None), "send": ("code", None), "load": ("deserialization", r"Marshal|YAML"), "find_by_sql": ("sql", None),
        "execute": ("sql", None), "redirect_to": ("redirect", r"^$"), "read": ("file", r"File|IO"),
    },
    "kotlin": {
        "exec": ("process", None), "executeQuery": ("sql", None), "execute": ("sql_or_process", None), "readObject": ("deserialization", None),
        "readText": ("file", None), "sendRedirect": ("redirect", None),
    },
    "swift": {
        "run": ("process", r"(?i)process|task"), "launch": ("process", None), "evaluateJavaScript": ("code", None), "unarchiveObject": ("deserialization", None),
        "contentsOfFile": ("file", None),
    },
}
RULES["typescript"] = RULES["javascript"]
RULES["cpp"] = RULES["c"]


def extract(entry, content):
    rules = RULES.get(entry.get("language"), {})
    facts = []
    for call in entry.get("calls", []):
        rule = rules.get(call.get("name"))
        if rule is None:
            continue
        category, receiver = rule
        if receiver is not None and not re.search(receiver, call.get("receiver", "")):
            continue
        facts.append({
            "id": digest([call["path"], call["id"], "security_call", call["name"]])[:24],
            "path": call["path"], "symbol_id": call.get("caller_id"),
            "kind": "security_call", "start_line": call["start_line"],
            "end_line": call.get("end_line", call["start_line"]), "status": "candidate",
            "framework": "security_calls", "language": entry.get("language"), "provenance": VERSION,
            "category": category, "name": call["name"], "call_id": call["id"], "expression": call["expression"][:200],
            "note": "Name-based navigation hint; reachability and exploitability are unverified",
        })
    return facts
