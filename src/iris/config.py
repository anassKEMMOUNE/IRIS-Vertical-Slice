import os
from pathlib import Path

ROOT = Path(os.environ.get("IRIS_ROOT", "."))
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://iris:iris-local-demo@localhost:55432/iris"
)
VERSION = "0.1.0"
RULES = {
    "version": "iris-screening-1.0",
    "bess_min_area_m2": 20000,
    "min_voltage_kv": 110,
    "max_distance_m": 1000,
    "peat_min_parcel_m2": 30000,
    "eco_points_per_m2": 8,
}
ASSUMPTIONS = [
    "Synthetic German pilot; no ownership, planning or grid availability claims.",
    "Internal IRIS specifications unavailable; contracts in README are local assumptions.",
    "EPSG:25832 (ETRS89 / UTM zone 32N), planar grid metres; suitable only for this pilot region.",
    "Distance is shortest parcel boundary/interior to substation point distance.",
    "Unknown source dates are allowed only with an explicit true unknown_date flag.",
    "Full fixture snapshot replaces validated entities transactionally; raw history is retained.",
    "Overlap tolerance is 0.000001 m2; no rounding is used for eligibility.",
    "Ownership, planning, environmental eligibility and transferability are unverified.",
]
DISCLAIMER = "Preliminary prospecting material. Figures, eco-point estimates and site suitability are indicative and based on available source data and commercial screening assumptions. The 8 eco-points/m2 factor is the current commercial baseline, not certified compensation. Ownership, planning, grid capacity, environmental eligibility and transferability remain subject to project-specific verification. No permit, reservation or construction readiness is represented."
