FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir 'psycopg[binary]>=3.2,<4'
COPY migrations/ /migrations/
COPY infra/docker/migrate.py /migrate.py
USER 10001
CMD ["python", "/migrate.py"]
