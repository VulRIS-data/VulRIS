"""Gin and net/http route, middleware and request accessor candidates."""

from .base import AUTH_RE, Evidence, literal

VERSION = "gin-rules-v2"
GIN_VERBS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "Any"}
GIN_INPUTS = {
    "Param", "Query", "DefaultQuery", "QueryArray", "QueryMap", "GetQuery", "PostForm", "DefaultPostForm",
    "PostFormArray", "GetPostForm", "GetHeader", "Cookie", "FormFile", "MultipartForm", "GetRawData",
    "ShouldBind", "ShouldBindJSON", "ShouldBindQuery", "ShouldBindUri", "ShouldBindHeader", "Bind", "BindJSON", "BindQuery", "BindUri",
}


def extract(entry, content):
    facts = []
    gin = Evidence(entry, content, "gin", VERSION)
    if gin.imports("github.com/gin-gonic/gin"):
        for call in gin.calls:
            caller = gin.by_id.get(call["caller_id"])
            if call["name"] in GIN_VERBS and call["arguments"]:
                path = literal(call["arguments"][0])
                if path is None:
                    continue
                gin.add("route", caller, call["start_line"], call["end_line"], note="Gin route registration; group prefixes are not resolved",
                        http_method="ANY" if call["name"] == "Any" else call["name"], paths=[path], handler=call["arguments"][-1][:200], path_resolution="literal", evidence=call["expression"][:200])
                for item in call["arguments"][1:-1]:
                    if AUTH_RE.search(item):
                        gin.add("guard", caller, call["start_line"], note="Route middleware with an authentication-like name; enforcement unverified", middleware=item[:120], evidence=item[:200])
            elif call["name"] == "Use" and any(AUTH_RE.search(item) for item in call["arguments"]):
                gin.add("guard", caller, call["start_line"], note="Router middleware with an authentication-like name; order and enforcement unverified", evidence=call["expression"][:200])
            elif call["name"] in GIN_INPUTS and call.get("receiver"):
                gin.add("input", caller, call["start_line"], note="gin.Context request accessor", source=call["name"], evidence=call["expression"][:200])
        facts.extend(gin.facts)
    std = Evidence(entry, content, "net/http", VERSION)
    if std.imports("net/http"):
        for call in std.calls:
            if call["name"] in {"HandleFunc", "Handle"} and call["arguments"]:
                path = literal(call["arguments"][0])
                if path is not None:
                    std.add("route", std.by_id.get(call["caller_id"]), call["start_line"], call["end_line"], note="net/http handler registration; method patterns are recorded as written",
                            http_method="ANY", paths=[path], handler=call["arguments"][-1][:200], path_resolution="literal", evidence=call["expression"][:200])
        std.scan("input", r"\b\w+\.(URL\.Query|FormValue|PostFormValue|Header\.Get|Cookie|PathValue|ParseForm|ParseMultipartForm)\b", "net/http request accessor")
        facts.extend(std.facts)
    return facts
