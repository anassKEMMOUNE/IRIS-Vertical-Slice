import argparse
import json
import sys
from iris.db import connect, migrate
from iris.pipeline import load, promote, candidates, reports


def main():
    parser = argparse.ArgumentParser(description="Synthetic IRIS PostGIS pilot")
    parser.add_argument(
        "command", choices=["migrate", "load", "promote", "candidates", "report", "run"]
    )
    parser.add_argument(
        "--run-id", help="Run returned by load; required for promote/report"
    )
    args = parser.parse_args()
    run_id = args.run_id
    try:
        with connect() as conn:
            # Serialize snapshot replacement and report generation across CLI processes.
            conn.execute("SELECT pg_advisory_lock(730030)")
            try:
                if args.command in ("migrate", "run"):
                    migrate(conn)
                if args.command in ("load", "run"):
                    run_id = load(conn)
                    print(f"Run: {run_id}")
                if args.command in ("promote", "run"):
                    if not run_id:
                        raise ValueError("--run-id is required")
                    promote(conn, run_id)
                if args.command == "candidates":
                    print(json.dumps(candidates(conn), indent=2, default=str))
                if args.command in ("report", "run"):
                    if not run_id:
                        raise ValueError("--run-id is required")
                    print(f"Success: {reports(conn,run_id)}")
            except Exception as exc:
                conn.rollback()
                if run_id:
                    conn.execute(
                        "UPDATE runs SET status='failed',error=%s WHERE run_id=%s AND status<>'success'",
                        (str(exc), run_id),
                    )
                    conn.commit()
                raise
    except Exception as exc:
        print(f"IRIS failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
