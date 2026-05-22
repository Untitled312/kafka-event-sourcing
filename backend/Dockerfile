FROM python:3.11-slim

RUN useradd -m -u 1000 appuser && mkdir -p /app /tmp/loki-cache && chown -R appuser:appuser /app /tmp/loki-cache

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser ./app ./app

USER appuser

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-level", "info", \
     "--access-log", \
     "--loop", "uvloop", \
     "--http", "httptools"]