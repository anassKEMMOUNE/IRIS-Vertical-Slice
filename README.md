# IRIS local vertical slice

A deliberately small, synthetic prospecting pilot implementing IRIS-CAND-30. Python adapters → immutable raw staging → explicit validation → transactional validated snapshot → PostGIS candidate views → two two-page PDFs and a JSON provenance manifest. No production credentials, real ownership information, external datasets, web application or private IRIS services are used.

## Reproduce

Prerequisites: Docker Engine/Desktop running, Docker Compose v2, internet for initial image/package download. Docker provides Python 3.12.9, PostgreSQL 16 and PostGIS 3.4. Run from this repository root:

```sh
docker compose run --build --rm app
```

Compose starts the database, waits for health, builds the app, applies migrations, loads fixtures, validates/promotes, queries candidates and produces reports. On Apple Silicon Docker may use emulation for the PostGIS image. The command prints the run UUID and output directory. Expected outputs:

```text
outputs/<run-uuid>/bess.pdf
outputs/<run-uuid>/peatland.pdf
outputs/<run-uuid>/manifest.json
```

Each report has exactly two pages. Failures exit nonzero. Invalid demonstration rows are expected, recorded rejections, not stage failures. Unexpected SQL/adapter/report errors fail the run. No candidate is an error. If a required dataset has no valid records, promotion fails without changing business entities. Failed runs may leave partial files; only a success-status database run with its manifest is a completed run.

Individual stages and lifecycle:

```sh
docker compose up -d db
docker compose build app
docker compose run --rm app iris migrate
docker compose run --rm app iris load
# Substitute the UUID printed by load:
docker compose run --rm app iris promote --run-id <uuid>
docker compose run --rm app iris candidates
docker compose run --rm app iris report --run-id <uuid>
docker compose run --rm app pytest -q
docker compose down
# Destructive: reset only this project's disposable database:
docker compose down -v
```

Outputs remain on disk after resetting the database. Integration tests replace the validated snapshot and create audit runs/reports in this disposable database. Run the demo again after tests to leave a successful demo snapshot. To remove old output folders, delete only runs you no longer need.

Optional host execution (Python 3.12; pinned binary packages target this version):

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps --no-build-isolation .
docker compose up -d db
export DATABASE_URL=postgresql://iris:iris-local-demo@localhost:55432/iris
iris run
pytest -q
```

`.env.example` contains disposable local defaults, not production secrets. `.env` is ignored. The database port binds only to localhost. No production configuration is claimed. Direct and transitive Python dependencies are pinned in `requirements.lock`, and the Python patch image is pinned. PostgreSQL/PostGIS image tags can change across rebuilds; the manifest records the actual database versions. Numeric reproducibility is the goal, not bit-identical container rebuilds.

## Design and contracts

- `src/iris/adapters`: three reusable JSON adapters parse records without filling missing values; validation and persistence are separate.
- `validation`: blocking checks and explicit warnings. JSON format errors fail ingestion; record errors remain available in staging.
- `pipeline`: orchestrates audit runs, ingestion, QA, promotion, selection and manifest creation.
- `reporting`: ReportLab layout and geographic diagrams; pypdf checks two pages and exact uncertainty wording.
- `migrations/001_schema.sql`: schema, constraints and spatial index; applied once through `schema_migrations`.
- `sql/candidates.sql`: reproducible candidate views, recreated by migrate.
- CLI database advisory lock serializes snapshot writers and report creation. Direct library callers must hold this same lock if concurrent.

`staging` preserves raw JSON, fixture path, ordinal and run. Invalid country values are raw evidence, not business entities. `validation_results` records errors/warnings per staging record; `rejected_records` exposes rejected payloads. `entities` is a small unified validated table differentiated by dataset, with a composite primary key `(country_code, dataset, source_id)`, canonical `geom`, required country, source date/unknown flag, and a staging foreign key. There are no identifier-only business joins: every spatial join includes country. The staging foreign key references globally unique evidence IDs, not country-scoped source IDs. `runs` records timestamps/status/inputs/errors. Audit metadata and malformed raw payloads are not business entities.

All JSON records require `source_id`, uppercase two-letter `country_code`, `crs`, `units`, `geom`, `source_date` or explicit `unknown_date=true`. IDs are preserved verbatim. Country syntax is checked; an ISO registry is deliberately not maintained. Source date is an ISO calendar date (no timezone); known dates require `unknown_date=false`. Explicit unknown dates warn but can promote. No missing voltage or CRS is inferred. Substations additionally require finite positive numeric `voltage_kv` and `voltage_units="kV"`. Parcels/peat require nonempty valid 2D Polygon or MultiPolygon WKT; substations require Point WKT. Self-intersections, wrong types, Z coordinates, empty geometries, unparseable WKT, missing fields, invalid dates, inconsistent flags and incorrect units block promotion. Duplicate source IDs within country/dataset reject **all** copies. No geometry repair occurs.

The pilot uses **EPSG:25832**, ETRS89 / UTM zone 32N, for both declared source and analysis coordinates. Synthetic geometries lie near easting 500,000/northing 5,700,000 in Germany. Grid metres give area in m² (hectares = m² / 10,000) and distance in metres. Validation checks the pilot envelope (200,000–800,000 east; 5,200,000–6,200,000 north) to catch obvious mislabeling; this cannot prove source accuracy. This projection is not suitable globally. Another region requires an explicit adapter transformation and suitable CRS/geography design. There is no longitude/latitude metric arithmetic.

Promotion replaces the complete validated snapshot in one transaction after QA evidence is committed. Accepted records from each of the three datasets are required. Repeated promotion/ingestion does not accumulate business duplicates; run/staging history deliberately accumulates. Candidate views describe the current snapshot. A report command rejects a superseded snapshot; manifests preserve historical inputs and calculations even after the snapshot changes.

## Fixtures and expected results

All `fixtures/*.json` are **synthetic demonstration data**, with no implied ownership, planning status, connection rights or available capacity. Rectangular coordinates support independently known measurements:

| Case | Expected result |
|---|---|
| BESS-EXACT, 200 × 100 m | 20,000 m² / 2 ha; eligible GRID-A exactly 1,000 m away, 110 kV |
| GRID-B at identical position, 220 kV | Tie resolved to GRID-A; one parcel result |
| BESS-SMALL, 199.99 × 100 m | 19,999 m²; rejected by screening |
| BESS-FAR | Closest eligible grid 1,000.01 m away; no candidate |
| BESS-LOW-VOLTAGE | Nearby 109.99 kV substation; no candidate |
| PEAT-EXACT, 300 × 100 m | 30,000 m² / 3 ha; union overlap 20,000 m²; 66.6667%; 160,000 eco-points |
| PEAT-A/B/COPY | 15,000 + 10,000 + repeated 15,000 m² footprints union to 20,000 m² |
| PEAT-SMALL | 29,999 m², covered but below parcel threshold |
| PEAT-NONE | Coverage only touches boundary; zero overlap, no candidate |
| BAD-GEOM / BAD-CRS / BAD-COUNTRY | Blocking QA failures |
| DUPLICATE (two copies) / GRID-MISSING | Both duplicate rows and missing voltage rejected |
| UNKNOWN-DATE | Explicitly unknown date; warning, accepted |

There are 24 staged records, 18 accepted, 6 rejected and one warning-bearing record. Dates are synthetic 2026-01-15 except the explicit unknown example.

## Rules and uncertainty

`iris-screening-1.0` uses inclusive BESS thresholds: parcel ≥20,000 m², substation ≥110 kV, shortest distance from parcel geometry to point ≤1,000 m (a point inside the parcel has distance zero). A lateral nearest qualifying substation selection returns one row per parcel; exact ties use identifier with C collation. Candidate columns include source dates, metric calculations, country, rule version, unknown-date and grid/connection-unverified flags.

Peatland requires parcel ≥30,000 m² and positive area intersection. Relevant same-country coverage is unioned before intersection/area measurement, deduplicating overlapping coverage even under different source IDs. Eco-points = overlap m² × 8, **not total parcel area × 8**. Coverage percentage, contributing IDs/dates and unknown flags are exposed. The pipeline asserts overlap ≤ parcel area + 0.000001 m²; thresholds themselves use unrounded values without an eligibility tolerance. Fixtures use planar exact rectangles; test comparisons allow floating error where appropriate.

Reports select the first candidate by country/parcel with C collation, show measurement tables and labeled geographic diagrams, source evidence, rules and required wording. Diagram coordinates use uniform scaling and north-up orientation; they are not cadastral maps. All ownership, planning, source accuracy, environmental eligibility, transferability and connection claims remain unverified.

> Preliminary prospecting material. Figures, eco-point estimates and site suitability are indicative and based on available source data and commercial screening assumptions. The 8 eco-points/m2 factor is the current commercial baseline, not certified compensation. Ownership, planning, grid capacity, environmental eligibility and transferability remain subject to project-specific verification. No permit, reservation or construction readiness is represented.

## Provenance and reproducibility

Each manifest contains UUID, database start timestamp, software version, rule version/thresholds, input filenames/SHA-256, complete raw source evidence with country/date/unknown flags, validation reasons and counts, CRS/units, the candidate SQL checksum, all candidate calculations, selected report candidates and their evidence IDs, output paths/SHA-256 and assumptions. Report evidence references the original fixture record ordinal and staging ID. The manifest itself is not self-hashed. QA counts equal promotion counts because every accepted row is inserted transactionally; any insert failure rolls back promotion.

Same inputs give identical candidate selection and numeric results. UUIDs, timestamps, staging IDs and PDF metadata vary; output files are intentionally not byte-identical between runs. Numeric formatting in PDFs rounds for display only. Full-precision values remain in JSON. Input content is preserved in the audit trail and manifest. PDF checksums identify the exact run artifacts.

## Tests and review

`docker compose run --rm app pytest -q` runs actual PostGIS integration tests, not spatial mocks. It checks exact and adjacent thresholds, independently known area/distance/union/eco-point results, multiple grids without inflation, country isolation with reused IDs, invalid geometry/missing attributes, rejected records excluded from business tables, repeated ingestion/promotion, and both two-page PDFs with exact disclaimer, diagram placement and output checksums. The FR rows in country-isolation tests deliberately reuse German coordinates: they test namespace isolation only, not a second-country geographic pilot.

For database inspection:

```sh
docker compose exec db psql -U iris -d iris -c 'SELECT * FROM rejected_records;'
docker compose exec db psql -U iris -d iris -c 'SELECT * FROM bess_candidates;'
docker compose exec db psql -U iris -d iris -c 'SELECT * FROM peatland_candidates;'
docker compose exec db psql -U iris -d iris -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM bess_candidates;'
docker compose exec db psql -U iris -d iris -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM peatland_candidates;'
```

GiST geometry indexing supports proximity/intersection filtering; tiny fixtures may correctly favor sequential scans. No performance claim is based on this sample size.

## Assumptions, simplifications and evolution

The PDF references internal IRIS-002/003/007/etc. that were not supplied. Their contents are not invented. This repository defines a minimum local contract, rule version, source-date policy and diagram/report layout. It uses a unified validated entity table and JSON/WKT adapters for a single projected-region snapshot, rather than an ingestion framework. Real integrations would add authenticated adapters, durable source snapshots, CRS transformation policies, verified metadata, incremental country-partitioned promotion, migration checksums, immutable run-specific candidate snapshots, coverage QA, formal uncertainty models, structured operational logs and transactionally coordinated artifact publication. No certified compensation, planning diligence or grid study is performed. Commercial eco-points remain indicative.

## Assessment acceptance checklist

- [x] One documented Compose command reproduces the local pipeline and outputs.
- [x] BESS ≥2 ha, ≥110 kV, ≤1,000 m, area/distance shown.
- [x] Peatland ≥3 ha, unioned overlap and overlap-based 8 eco-points/m².
- [x] Required country, dates/unknowns, geometry QA and exact standard wording.
- [x] Country-scoped joins, deterministic single BESS row, no fabricated claims.
- [x] Repository/runtime config, migration, reusable adapters and tests, candidate SQL.
- [x] Two two-page reports, machine-readable manifest, reviewer README.

See `outputs/verification.md` for the execution evidence and any environment-specific limitations from the implementation session.
