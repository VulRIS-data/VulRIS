"""Django URLconf, request accessor and access-control candidates."""

from .base import Evidence, literal, short

VERSION = "django-rules-v2"
GUARDS = {"login_required", "permission_required", "user_passes_test", "staff_member_required", "superuser_required"}
MIXINS = {"LoginRequiredMixin", "PermissionRequiredMixin", "UserPassesTestMixin", "AccessMixin"}


def extract(entry, content):
    ev = Evidence(entry, content, "django", VERSION)
    if not (ev.imports("django", "rest_framework") or ev.path.endswith("urls.py")):
        return []
    for call in ev.calls:
        if call["name"] in {"path", "re_path", "url"} and not call.get("receiver") and len(call["arguments"]) >= 2:
            route = literal(call["arguments"][0])
            if route is None:
                continue
            symbol = ev.by_id.get(call["caller_id"])
            ev.add("route", symbol, call["start_line"], call["end_line"], note="URLconf entry; include() prefixes are not resolved",
                   http_method="ANY", paths=["/" + route.lstrip("^/")], handler=call["arguments"][1][:200], path_resolution="literal", evidence=call["expression"][:200])
    for symbol in ev.symbols:
        for decorator in symbol.get("decorators", []):
            name = short(decorator["name"])
            if name in GUARDS:
                ev.add("guard", symbol, decorator["line"], note="Django access decorator; enforcement unverified", evidence=decorator["text"][:200])
            elif name == "csrf_exempt":
                ev.add("configuration", symbol, decorator["line"], note="CSRF protection is disabled for this view by decorator", evidence=decorator["text"][:200])
        for base in symbol.get("bases", []):
            if short(base["type"]) in MIXINS:
                ev.add("guard", symbol, symbol["start_line"], note="Django access mixin; enforcement unverified", evidence=base["type"])
    ev.scan("guard", r"\bpermission_classes\s*=\s*[\[(]([^\])]*)", "DRF permission classes; enforcement unverified")
    ev.scan("input", r"\brequest\.(GET|POST|FILES|COOKIES|META|body|headers|data|query_params)\b", "Django request accessor")
    return ev.facts
