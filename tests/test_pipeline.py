import json
from copy import deepcopy
import pytest
from pypdf import PdfReader
from iris.adapters import ParcelAdapter
from iris.config import ROOT, DISCLAIMER
from iris.db import connect, migrate
from iris.pipeline import load, promote, candidates, reports
from iris.validation import validate


@pytest.fixture
def db():
    with connect() as conn:
        conn.execute("SELECT pg_advisory_lock(730030)")
        migrate(conn)
        run = load(conn)
        promote(conn, run)
        yield conn, run
        conn.rollback()


def test_adapters_and_qa():
    records = list(ParcelAdapter().read(ROOT / "fixtures/parcels.json"))
    r = records[0][1]
    assert validate(r, "parcels") == ([], [])
    for field, value in [
        ("source_id", None),
        ("country_code", None),
        ("crs", None),
        ("units", "degrees"),
        ("source_date", None),
        ("geom", "POINT(500000 5700000)"),
        ("unknown_date", "false"),
    ]:
        bad = deepcopy(r)
        bad[field] = value
        assert validate(bad, "parcels")[0], field
    unknown = deepcopy(r)
    unknown.update(source_date=None, unknown_date=True)
    assert validate(unknown, "parcels") == ([], ["source date unknown"])
    assert validate(r, "parcels", True)[0]
    invalid = next(r for _, r in records if r["source_id"] == "BAD-GEOM")
    assert validate(invalid, "parcels")[0]


def test_known_spatial_results(db):
    conn, _ = db
    c = candidates(conn)
    assert [r["parcel_id"] for r in c["bess"]] == ["BESS-EXACT"]
    b = c["bess"][0]
    assert b["area_m2"] == pytest.approx(20000, abs=1e-6)
    assert b["area_ha"] == 2
    assert b["distance_m"] == pytest.approx(1000, abs=1e-6)
    assert b["voltage_kv"] == 110 and b["substation_id"] == "GRID-A"
    assert [r["parcel_id"] for r in c["peatland"]] == ["PEAT-EXACT"]
    p = c["peatland"][0]
    assert p["area_m2"] == 30000
    assert p["overlap_m2"] == pytest.approx(20000, abs=1e-6)
    assert p["eco_points"] == 160000
    assert p["overlap_percent"] == pytest.approx(200 / 3)
    assert p["peat_ids"] == ["PEAT-A", "PEAT-B", "PEAT-COPY"]


def test_threshold_neighbors(db):
    conn, _ = db
    conn.execute(
        "UPDATE entities SET geom=ST_Translate(geom,-500,0) WHERE source_id='GRID-B'"
    )
    nearest = candidates(conn)["bess"]
    assert len(nearest) == 1
    assert nearest[0]["substation_id"] == "GRID-B"
    assert nearest[0]["distance_m"] == 500
    conn.rollback()
    # Move both boundary substations 1 cm beyond the maximum distance.
    conn.execute(
        "UPDATE entities SET geom=ST_Translate(geom,0.01,0) WHERE source_id IN ('GRID-A','GRID-B')"
    )
    assert not candidates(conn)["bess"]
    conn.rollback()
    conn.execute(
        "UPDATE entities SET voltage_kv=109.99 WHERE source_id IN ('GRID-A','GRID-B')"
    )
    assert not candidates(conn)["bess"]
    conn.rollback()
    conn.execute(
        "UPDATE entities SET geom=ST_Translate(geom,-0.01,0) WHERE source_id IN ('GRID-A','GRID-B')"
    )
    assert candidates(conn)["bess"][0]["distance_m"] == pytest.approx(999.99)
    conn.rollback()
    # Slightly smaller peat parcel must disappear even though coverage remains.
    conn.execute(
        "UPDATE entities SET geom=ST_GeomFromText('POLYGON((540000 5700000,540299.99 5700000,540299.99 5700100,540000 5700100,540000 5700000))',25832) WHERE source_id='PEAT-EXACT'"
    )
    assert not candidates(conn)["peatland"]


def test_country_scoping(db):
    conn, _ = db
    # Synthetic isolation test only; same coordinates and IDs, separate namespace.
    conn.execute(
        "INSERT INTO entities SELECT 'FR',dataset,source_id,source_date,unknown_date,geom,voltage_kv,stage_id FROM entities WHERE source_id IN ('BESS-EXACT','PEAT-EXACT')"
    )
    assert all(
        r["country_code"] == "DE" for rows in candidates(conn).values() for r in rows
    )
    conn.execute(
        "INSERT INTO entities SELECT 'FR',dataset,source_id,source_date,unknown_date,geom,voltage_kv,stage_id FROM entities WHERE country_code='DE' AND source_id IN ('GRID-A','PEAT-A')"
    )
    c = candidates(conn)
    assert len(c["bess"]) == 2 and len(c["peatland"]) == 2
    assert (
        next(r for r in c["peatland"] if r["country_code"] == "FR")["overlap_m2"]
        == 15000
    )


def test_rejections_repeatability_and_outputs(db):
    conn, run = db
    count = conn.execute("SELECT count(*) AS n FROM entities").fetchone()["n"]
    assert count == 18
    rejected = conn.execute(
        "SELECT payload,errors FROM rejected_records WHERE run_id=%s", (run,)
    ).fetchall()
    assert len(rejected) == 5 + 1
    assert not conn.execute(
        "SELECT 1 FROM entities WHERE source_id IN ('BAD-GEOM','BAD-CRS','DUPLICATE','BAD-COUNTRY','GRID-MISSING')"
    ).fetchone()
    promote(conn, run)
    run2 = load(conn)
    promote(conn, run2)
    assert conn.execute("SELECT count(*) AS n FROM entities").fetchone()["n"] == count
    out = reports(conn, run2)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["validation"]["accepted"] == count
    assert len(manifest["outputs"]) == 2
    from iris.pipeline import checksum

    for output in manifest["outputs"]:
        path = ROOT / output["path"]
        assert checksum(path) == output["sha256"]
        pdf = PdfReader(path)
        assert len(pdf.pages) == 2
        # Guard against a zero-height diagram overlapping the summary table.
        positions = {}

        def capture(text, cm, tm, font, size):
            for label in (
                "Qualifying rule",
                "EPSG:25832 |",
                "Why this candidate qualifies",
            ):
                if label in text:
                    positions[label] = cm[5] + tm[5]

        pdf.pages[0].extract_text(visitor_text=capture)
        assert (
            positions["Qualifying rule"]
            > positions["EPSG:25832 |"]
            > positions["Why this candidate qualifies"]
        )
        assert DISCLAIMER in " ".join(
            " ".join(p.extract_text().split()) for p in pdf.pages
        )
    assert (
        conn.execute("SELECT status FROM runs WHERE run_id=%s", (run2,)).fetchone()[
            "status"
        ]
        == "success"
    )


def test_missing_candidate_errors(db):
    conn, run = db
    conn.execute("DELETE FROM entities WHERE dataset='substations'")
    with pytest.raises(ValueError, match="No qualifying"):
        reports(conn, run)


def test_failed_promotion_preserves_snapshot_and_evidence(db):

    conn, _ = db
    before = candidates(conn)
    run = load(conn)
    conn.execute(
        "UPDATE staging SET payload=payload - 'crs' WHERE run_id=%s AND dataset='peat'",
        (run,),
    )
    conn.commit()
    with pytest.raises(ValueError, match="promotion blocked"):
        promote(conn, run)
    conn.rollback()
    assert candidates(conn) == before
    assert (
        conn.execute(
            "SELECT count(*) AS n FROM rejected_records WHERE run_id=%s", (run,)
        ).fetchone()["n"]
        == 11
    )


def test_substation_contract():
    from iris.adapters import SubstationAdapter

    r = next(SubstationAdapter().read(ROOT / "fixtures/substations.json"))[1]
    for field, value in [
        ("voltage_kv", None),
        ("voltage_kv", float("nan")),
        ("voltage_kv", True),
        ("voltage_kv", -1),
        ("voltage_units", "V"),
        ("source_date", "2026-02-30"),
    ]:
        bad = deepcopy(r)
        bad[field] = value
        assert validate(bad, "substations")[0]


def test_database_geometry_and_country_constraints(db):
    import psycopg

    conn, _ = db
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "UPDATE entities SET geom=ST_GeomFromText('POINT(500000 5700000)',25832) WHERE source_id='BESS-EXACT'"
            )
    with pytest.raises(psycopg.errors.NotNullViolation):
        with conn.transaction():
            conn.execute(
                "UPDATE entities SET country_code=NULL WHERE source_id='BESS-EXACT'"
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute("UPDATE entities SET voltage_kv=NULL WHERE source_id='GRID-A'")
