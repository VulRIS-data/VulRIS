# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.11.3 AS uv

FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="VulRIS" \
      org.opencontainers.image.description="Multi-language structured source-code relation index" \
      org.opencontainers.image.source="https://github.com/VulRIS-data/VulRIS"

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

RUN groupadd --gid 10001 vulris \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin vulris \
    && mkdir -p /data /workspace \
    && chown -R vulris:vulris /data /workspace

ENV PATH="/app/.venv/bin:${PATH}"
WORKDIR /workspace
USER 10001:10001
VOLUME ["/data"]

ENTRYPOINT ["vulris"]
CMD ["--help"]
