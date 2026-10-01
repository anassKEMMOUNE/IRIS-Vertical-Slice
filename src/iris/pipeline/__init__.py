import hashlib
import json
from collections import Counter
from uuid import uuid4
from psycopg.types.json import Jsonb
from iris.config import ROOT, RULES, VERSION, ASSUMPTIONS
from iris.adapters import ADAPTERS
from iris.validation import validate


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(conn):
    run_id = str(uuid4())
    inputs = []
    conn.execute("INSERT INTO runs(run_id,status) VALUES (%s,'started')", (run_id,))
    for adapter in ADAPTERS:
        path = ROOT / "fixtures" / f"{adapter.dataset}.json"
        inputs.append({"filename": str(path), "sha256": checksum(path)})
        for ordinal, payload in adapter.read(path):
            conn.execute(
                "INSERT INTO staging(run_id,dataset,source_file,ordinal,payload) VALUES (%s,%s,%s,%s,%s)",
                (run_id, adapter.dataset, str(path), ordinal, Jsonb(payload)),
            )
    conn.execute(
        "UPDATE runs SET status='loaded',inputs=%s WHERE run_id=%s",
        (Jsonb(inputs), run_id),
    )
    conn.commit()
    return run_id


def promote(conn, run_id):
    run = conn.execute(
        "SELECT * FROM runs WHERE run_id=%s FOR UPDATE", (run_id,)
    ).fetchone()
    if not run or run["status"] not in ("loaded", "promoted"):
        raise ValueError("Promotion requires a loaded or promoted run")
    rows = conn.execute(
        "SELECT * FROM staging WHERE run_id=%s ORDER BY stage_id", (run_id,)
    ).fetchall()

    def key(row):
        r = row["payload"]
        # JSON encoding also supports malformed unhashable source values for rejection.
        return json.dumps(
            [row["dataset"], r.get("country_code"), r.get("source_id")], sort_keys=True
        )

    counts = Counter(key(row) for row in rows)
    accepted = []
    for row in rows:
        errors, warnings = validate(
            row["payload"], row["dataset"], counts[key(row)] > 1
        )
        conn.execute(
            "INSERT INTO validation_results VALUES (%s,%s,%s,%s) ON CONFLICT(stage_id) DO UPDATE SET accepted=excluded.accepted,errors=excluded.errors,warnings=excluded.warnings",
            (row["stage_id"], not errors, Jsonb(errors), Jsonb(warnings)),
        )
        if not errors:
            accepted.append(row)
    # QA evidence survives a failed promotion. Business snapshot changes atomically below.
    conn.commit()
    if {r["dataset"] for r in accepted} != {"parcels", "peat", "substations"}:
        raise ValueError(
            "No valid records in at least one required dataset; promotion blocked"
        )
    conn.execute("DELETE FROM entities")
    for row in accepted:
        r = row["payload"]
        conn.execute(
            "INSERT INTO entities VALUES (%s,%s,%s,%s,%s,ST_GeomFromText(%s,25832),%s,%s)",
            (
                r["country_code"],
                row["dataset"],
                r["source_id"],
                r.get("source_date"),
                r["unknown_date"],
                r["geom"],
                r.get("voltage_kv") if row["dataset"] == "substations" else None,
                row["stage_id"],
            ),
        )
    conn.execute("UPDATE runs SET status='promoted' WHERE run_id=%s", (run_id,))
    conn.commit()


def candidates(conn):
    result = {
        name: conn.execute(
            f'SELECT * FROM {name}_candidates ORDER BY country_code COLLATE "C",parcel_id COLLATE "C"'
        ).fetchall()
        for name in ("bess", "peatland")
    }
    for row in result["peatland"]:
        if row["overlap_m2"] > row["area_m2"] + 1e-6:
            raise ValueError("Peat overlap exceeds parcel area")
    return result


def reports(conn, run_id):
    from iris.reporting import make_report

    run = conn.execute("SELECT * FROM runs WHERE run_id=%s", (run_id,)).fetchone()
    if not run or run["status"] != "promoted":
        raise ValueError("Reports require a promoted run")
    stale = conn.execute(
        "SELECT count(*) AS n FROM entities e JOIN staging s USING(stage_id) WHERE s.run_id<>%s",
        (run_id,),
    ).fetchone()["n"]
    if stale:
        raise ValueError(
            "Validated snapshot belongs to another run; promote this run first"
        )
    all_candidates = candidates(conn)
    if any(not rows for rows in all_candidates.values()):
        raise ValueError(
            "No qualifying BESS or peatland candidate; no reports generated"
        )
    evidence = conn.execute(
        "SELECT s.*,v.accepted,v.errors,v.warnings FROM staging s JOIN validation_results v USING(stage_id) WHERE run_id=%s ORDER BY stage_id",
        (run_id,),
    ).fetchall()
    out = ROOT / "outputs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for kind, rows in all_candidates.items():
        selected = rows[0]
        path = out / f"{kind}.pdf"
        sources = [
            r
            for r in evidence
            if r["accepted"]
            and r["payload"]["country_code"] == selected["country_code"]
            and (
                (
                    r["dataset"] == "parcels"
                    and r["payload"]["source_id"] == selected["parcel_id"]
                )
                or (
                    kind == "bess"
                    and r["dataset"] == "substations"
                    and r["payload"]["source_id"] == selected["substation_id"]
                )
                or (
                    kind == "peatland"
                    and r["dataset"] == "peat"
                    and r["payload"]["source_id"] in selected["peat_ids"]
                )
            )
        ]
        make_report(path, kind, selected, sources, run_id)
        files.append(
            {
                "path": str(path),
                "sha256": checksum(path),
                "candidate": selected,
                "source_stage_ids": [s["stage_id"] for s in sources],
            }
        )
    manifest = {
        "run_id": run_id,
        "timestamp": run["started_at"],
        "software_version": VERSION,
        "rules": RULES,
        "calculation_sql": {
            "filename": "sql/candidates.sql",
            "sha256": checksum(ROOT / "sql/candidates.sql"),
        },
        "runtime": conn.execute(
            "SELECT version() AS postgres, postgis_full_version() AS postgis"
        ).fetchone(),
        "inputs": run["inputs"],
        "spatial_conventions": {
            "source_crs": "EPSG:25832",
            "analysis_crs": "EPSG:25832",
            "area_units": ["m2", "ha"],
            "distance_units": "m",
        },
        "validation": {
            "staged": len(evidence),
            "accepted": sum(r["accepted"] for r in evidence),
            "promoted": sum(r["accepted"] for r in evidence),
            "rejected": sum(not r["accepted"] for r in evidence),
            "warnings": sum(bool(r["warnings"]) for r in evidence),
        },
        "rejection_summary": dict(
            Counter(reason for r in evidence for reason in r["errors"])
        ),
        "warning_summary": dict(
            Counter(reason for r in evidence for reason in r["warnings"])
        ),
        "sources_and_validation": evidence,
        "candidates": all_candidates,
        "outputs": files,
        "assumptions": ASSUMPTIONS,
    }
    temporary = out / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    temporary.replace(out / "manifest.json")
    conn.execute("UPDATE runs SET status='success' WHERE run_id=%s", (run_id,))
    conn.commit()
    return out
