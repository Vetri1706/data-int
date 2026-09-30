# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
WORKDIR /app/services/scrapling
COPY services/scrapling/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
RUN scrapling install && chmod -R a+rX /opt/browsers
COPY services/source_policy.py /app/services/source_policy.py
COPY services/scrapling/ ./
RUN useradd --system --uid 10001 --create-home app
USER app
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
