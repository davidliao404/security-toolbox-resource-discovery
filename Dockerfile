FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples
COPY config ./config
COPY alembic.ini ./
COPY migrations ./migrations
COPY tests/fixtures ./tests/fixtures
COPY scripts ./scripts

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "resource_discovery.http_app:app", "--host", "0.0.0.0", "--port", "8000"]
