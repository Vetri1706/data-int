"""Idempotent schema initialization; never resets an existing database."""
import os
from pathlib import Path

import psycopg

with psycopg.connect(
    host="postgres", port=5432, dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
    connect_timeout=10,
) as conn:
    conn.execute("SELECT pg_advisory_xact_lock(684701247)")
    if conn.execute("SELECT to_regclass('public.users')").fetchone()[0] is None:
        if conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:
            raise RuntimeError("Database contains unrelated tables; refusing to initialize.")
        conn.execute(Path("/migrations/001_initial_schema.sql").read_text())
    conn.execute(Path("/migrations/002_trust_and_workflow.sql").read_text())
print("Database migrations are current.")
