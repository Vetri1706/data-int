# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/services/intelligence
COPY services/intelligence/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY services/source_policy.py /app/services/source_policy.py
COPY services/intelligence/ ./
RUN useradd --system --uid 10001 --create-home app
USER app
EXPOSE 7000
# A single worker owns in-process workflow tasks and cancellation state.
CMD ["python", "-m", "uvicorn", "graph:app", "--host", "0.0.0.0", "--port", "7000", "--workers", "1"]
