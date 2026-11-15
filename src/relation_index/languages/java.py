"""Java frontend adapter that preserves the legacy row data byte for byte.

Java keeps its original extractor and linker (``relation_index.java``) so that
symbol, call, edge and fact IDs and their ``data`` JSON stay identical to the
research implementation. Spring evidence is produced by ``frameworks.spring``.
"""

from .. import java as legacy

name = "java"
extensions = (".java",)
VERSION = legacy.VERSION
RULES_VERSION = "java-rules-v3"


def available():
    return True


def unavailable_reason():
    return None


def extract(path, content):
    entry = legacy.extract(path, content, with_facts=False)
    entry.update({"language": name, "parser_version": VERSION, "rules_version": RULES_VERSION, "path": path, "module": entry.get("package", "")})
    return entry


def link(parsed_files, checkpoint=lambda: None, on_progress=None):
    return legacy.link(parsed_files, checkpoint, on_progress)
