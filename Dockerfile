FROM python:3.14-slim-bookworm AS compile-image
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY bot ./bot
COPY data ./data
RUN uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm AS run-image
COPY --from=compile-image /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY bot ./bot
COPY data ./data
CMD ["python", "-m", "bot"]
