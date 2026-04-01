FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Report generation dependencies (reportlab image/font support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
COPY frontend /app/frontend
COPY billingfiles /app/billingfiles
COPY .env.example /app/.env.example

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir . && \
    ln -s /app/frontend "$(python -c "import audit_engine, pathlib; print(pathlib.Path(audit_engine.__file__).resolve().parents[2] / 'frontend')")"

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "audit_engine.api:app", "--host", "0.0.0.0", "--port", "8001"]