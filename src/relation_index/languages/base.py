"""Contract shared by every language frontend."""

from __future__ import annotations

from typing import Any, Protocol

TYPE_KINDS = frozenset({"class", "interface", "struct", "enum"})
SCOPE_KINDS = TYPE_KINDS | {"module", "namespace"}
CALLABLE_KINDS = frozenset({"function", "method", "constructor"})


class LanguageFrontend(Protocol):
    """A frontend turns one source file into the common intermediate format.

    ``extract`` returns a dict with ``language``, ``parser_version``,
    ``rules_version``, ``path``, ``module``, ``imports``, ``symbols``, ``calls``,
    ``facts`` (filled later by framework rules), ``parse_error`` and ``anchors``.
    """

    name: str
    extensions: tuple[str, ...]
    VERSION: str
    RULES_VERSION: str

    def available(self) -> bool: ...

    def unavailable_reason(self) -> str | None: ...

    def extract(self, path: str, content: bytes) -> dict[str, Any]: ...
