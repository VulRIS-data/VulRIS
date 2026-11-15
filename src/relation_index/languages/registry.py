"""Lazy frontend registry; one missing grammar never disables other languages."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

LANGUAGE_MODULES = {
    "java": "java", "python": "python", "javascript": "javascript",
    "typescript": "typescript", "go": "go", "csharp": "csharp", "c": "c",
    "cpp": "cpp", "rust": "rust", "php": "php", "ruby": "ruby",
    "kotlin": "kotlin", "swift": "swift",
}


@dataclass
class UnavailableFrontend:
    name: str
    error: str
    extensions: tuple[str, ...] = ()
    VERSION: str = "unavailable"
    RULES_VERSION: str = "unavailable"

    def available(self):
        return False

    def unavailable_reason(self):
        return self.error

    def extract(self, path, content):
        raise RuntimeError(self.error)


class Registry:
    def __init__(self, overrides=None):
        self._overrides = overrides or {}
        self._loaded = {}

    def get(self, language):
        if language in self._overrides:
            return self._overrides[language]
        if language not in LANGUAGE_MODULES:
            return None
        if language not in self._loaded:
            try:
                module = importlib.import_module(f"{__package__}.{LANGUAGE_MODULES[language]}")
                self._loaded[language] = getattr(module, "frontend", module)
            except Exception as exc:
                self._loaded[language] = UnavailableFrontend(
                    language, f"{type(exc).__name__}: {exc}"
                )
        return self._loaded[language]

    def all(self):
        return {name: self.get(name) for name in LANGUAGE_MODULES}


default_registry = Registry()
