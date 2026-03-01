"""
One-time Postgres setup for the_main_quest.

Creates the app role, the production and test databases, and applies the
todoist snapshot schema to both. All values are read from config — nothing
is hardcoded here.

Reads from [admin.postgres] in the secrets TOML:
    dsn          superuser DSN (news_drift)
    new_user     role to create
    new_password role password
    prod_db      production database name
    test_db      test database name

Run as:
    poetry run python -m runs.setup_postgres
"""

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

SCHEMA = Path(__file__).resolve().parents[1] / "migrations" / "todoist_snapshot_schema.sql"


def main():
    os.environ["ENV_FOR_DYNACONF"] = "admin"
    from the_main_quest.omniconf import config

    admin_dsn = config.postgres.dsn
    new_user = config.postgres.new_user
    new_password = config.postgres.new_password
    db_name = config.postgres.db_name
    test_db_name = config.postgres.test_db_name
    databases = [db_name, test_db_name]

    admin_parsed = urlparse(admin_dsn)

    # --- create role and databases ---
    conn = psycopg2.connect(admin_dsn)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (new_user,))
        if cur.fetchone():
            print(f"role '{new_user}' already exists")
        else:
            cur.execute(f"CREATE USER {new_user} WITH PASSWORD %s", (new_password,))
            print(f"created role '{new_user}'")

        for db in databases:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
            if cur.fetchone():
                print(f"database '{db}' already exists")
            else:
                cur.execute(f'CREATE DATABASE "{db}" OWNER {new_user}')
                print(f"created database '{db}'")
    conn.close()

    # --- apply schema to each database ---
    schema_sql = SCHEMA.read_text()
    for db in databases:
        db_dsn = urlunparse(admin_parsed._replace(
            netloc=f"{new_user}:{new_password}@{admin_parsed.hostname}:{admin_parsed.port or 5432}",
            path=f"/{db}",
        ))
        conn = psycopg2.connect(db_dsn)
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        conn.close()
        print(f"schema applied to '{db}'")

    host = admin_parsed.hostname
    port = admin_parsed.port
    print(f"\nSetup complete.")
    for db in databases:
        print(f"  postgresql://{new_user}:***@{host}:{port}/{db}")


if __name__ == "__main__":
    main()
