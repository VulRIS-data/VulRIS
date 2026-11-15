"""Framework evidence dispatcher, separate from language parsing."""

from . import aspnet, axum, django, express, fastapi, flask, gin, laravel, nestjs, rails, security_calls, spring

VERSIONS = {
    "spring": spring.VERSION, "fastapi": fastapi.VERSION, "django": django.VERSION,
    "flask": flask.VERSION, "express": express.VERSION, "nestjs": nestjs.VERSION,
    "aspnet": aspnet.VERSION, "gin": gin.VERSION, "rails": rails.VERSION,
    "laravel": laravel.VERSION, "axum_actix": axum.VERSION,
    "security_calls": security_calls.VERSION,
}

BY_LANGUAGE = {
    "java": (spring,), "kotlin": (spring,),
    "python": (fastapi, django, flask),
    "javascript": (express, nestjs), "typescript": (express, nestjs),
    "csharp": (aspnet,), "go": (gin,), "ruby": (rails,), "php": (laravel,),
    "rust": (axum,),
}


def extract(entry, content):
    facts = []
    for module in BY_LANGUAGE.get(entry.get("language"), ()):
        facts.extend(module.extract(entry, content))
    if entry.get("language") != "java":
        facts.extend(security_calls.extract(entry, content))
    unique = {fact["id"]: fact for fact in facts}
    return [unique[key] for key in sorted(unique)]
