import time
import psycopg
from psycopg.rows import dict_row
from iris.config import DATABASE_URL, ROOT


def connect():
    for attempt in range(30):
        try:
            return psycopg.connect(DATABASE_URL, row_factory=dict_row)
        except psycopg.OperationalError:
            if attempt == 29:
                raise RuntimeError(
                    "Database unavailable after 60 seconds; start Docker Compose db."
                )
            time.sleep(2)


def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY)")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if not conn.execute(
            "SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)
        ).fetchone():
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))
    server_version = int(
        conn.execute("SHOW server_version_num").fetchone()["server_version_num"]
    )
    postgis_version = conn.execute(
        "SELECT postgis_lib_version() AS version"
    ).fetchone()["version"]
    if server_version < 160000 or tuple(map(int, postgis_version.split(".")[:2])) < (
        3,
        4,
    ):
        raise RuntimeError("IRIS requires PostgreSQL 16+ and PostGIS 3.4+")
    conn.execute((ROOT / "sql/candidates.sql").read_text())
    conn.commit()
