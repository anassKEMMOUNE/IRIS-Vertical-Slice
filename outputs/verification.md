# Execution evidence - 2026-10-01

Final reviewed run: `915f80e1-01e8-4ef4-b734-791d783b0ff3`.

- Read both pages of IRIS-CAND-30 before implementation.
- Built and executed `docker compose run --build --rm app` successfully against the initially empty local application schema.
- Runtime: Python 3.12.9, PostgreSQL 16.4, PostGIS 3.4; database full build details are recorded in the manifest.
- Final test command: `docker compose run --build --rm app pytest -q` — **9 passed in 2.19 seconds**.
- Final demonstration: `docker compose run --rm app` — success.
- Compared separate complete runs: identical candidate records/calculations, input checksums, rules, query checksum and validation counts.
- 24 staged records; 18 accepted/promoted; 6 rejected; 1 record with an explicit unknown-date warning.
- BESS: DE/BESS-EXACT, 20,000 m², 2 ha, GRID-A, 110 kV, 1,000 m.
- Peatland: DE/PEAT-EXACT, 30,000 m² parcel, 20,000 m² unioned peat overlap, 66.6666667%, 160,000 indicative eco-points.
- Both final PDFs have exactly two pages and the exact required uncertainty wording. Output SHA-256 checksums were independently checked against the manifest.
- Rendered all four final pages with Poppler and visually inspected them. Tables, diagrams, source references and disclaimers are readable, with no clipping or overlap. A zero-height map layout defect found during the first visual review was fixed and covered by a PDF text-position regression check before final delivery.
- `explain.txt` contains actual EXPLAIN ANALYZE/BUFFERS evidence for both queries on the fixture-sized database. These plans do not establish production performance.
- Python syntax and formatting checks passed.

No core assessment checks remain unverified in this local Docker environment. Other host architectures, production data scale, real source accuracy, external systems and environmental/grid/ownership claims are not validated. There is no second-country geographic fixture; country isolation is exercised by integration tests that deliberately reuse identifiers and coordinates in a separate namespace.

Initial package downloads timed out or were incomplete; checksum validation rejected the incomplete download. A cached retry succeeded without disabling verification. The local Poppler renderer needed a temporary writable font-cache configuration; this did not require changes to the generated PDFs or application runtime.

The submission zip contains only the final reviewed report pair and its manifest, plus this evidence and the source. Earlier local output runs are development/test artifacts, not the submitted report pair. UUIDs, timestamps, staging IDs and PDF metadata vary between runs; numeric outcomes are deterministic.
