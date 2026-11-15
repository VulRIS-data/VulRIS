from pathlib import PurePosixPath
from ..storage import digest

VERSION = "config-rules-v2"
EXACT = {"package.json", "tsconfig.json", "pyproject.toml", "setup.cfg", "Pipfile", "go.mod", "Cargo.toml", "composer.json", "Gemfile", "CMakeLists.txt", "compile_commands.json", "Package.swift", "settings.gradle", "settings.gradle.kts"}


def ecosystem(name):
    lower = name.lower()
    if lower in {"package.json", "tsconfig.json"}: return "javascript"
    if lower in {"pyproject.toml", "setup.cfg", "pipfile"} or lower.startswith("requirements"): return "python"
    if lower == "go.mod": return "go"
    if lower.endswith(".csproj") or lower.startswith("appsettings"): return "dotnet"
    if lower == "cargo.toml": return "rust"
    if lower == "composer.json": return "php"
    if lower == "gemfile" or lower.endswith(".gemspec"): return "ruby"
    if lower in {"cmakelists.txt", "compile_commands.json"}: return "cpp"
    if lower == "package.swift": return "swift"
    return "build"


def extract(file):
    path = file["path"]
    name = PurePosixPath(path).name
    legacy = name.startswith(("application.", "application-", "pom.xml", "build.gradle"))
    lower = name.lower()
    selected = legacy or name in EXACT or lower.startswith("requirements") and lower.endswith(".txt") or lower.endswith((".csproj", ".gemspec")) or lower.startswith("appsettings") and lower.endswith(".json")
    if not selected:
        return []
    fact = {"id": digest([path, "config"])[:24], "path": path, "symbol_id": None, "kind": "config_file", "start_line": 1, "end_line": file["line_count"], "status": "candidate", "note": "Related configuration file; active profile unverified"}
    if not legacy:
        fact.update({"ecosystem": ecosystem(name), "framework": "config_files", "language": file.get("language"), "provenance": VERSION})
    return [fact]
