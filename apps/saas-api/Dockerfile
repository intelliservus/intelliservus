FROM python:3.12-slim AS build

RUN pip install --no-cache-dir uv==0.11.17
WORKDIR /app

COPY apps/saas-api/pyproject.toml apps/saas-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/saas-api/src ./src
COPY apps/saas-api/migrations ./migrations
COPY apps/saas-api/scripts ./scripts

RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
COPY --from=build /app/migrations /app/migrations
COPY --from=build /app/scripts /app/scripts

EXPOSE 3000

CMD ["uvicorn", "saas_api.main:app", "--host", "0.0.0.0", "--port", "3000"]
