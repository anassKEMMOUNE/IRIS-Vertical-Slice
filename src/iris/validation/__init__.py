from datetime import date
import math
import re
from shapely import wkt
from shapely.validation import explain_validity


def validate(record, dataset, duplicate=False):
    errors, warnings = [], []
    if not isinstance(record.get("source_id"), str) or not record["source_id"].strip():
        errors.append("source_id must be a nonempty string")
    if not isinstance(record.get("country_code"), str) or not re.fullmatch(
        "[A-Z]{2}", record["country_code"]
    ):
        errors.append("country_code must be two uppercase letters")
    if record.get("crs") != "EPSG:25832":
        errors.append("crs must explicitly be EPSG:25832 for this pilot")
    if record.get("units") != "m":
        errors.append("geometry units must explicitly be m")
    if type(record.get("unknown_date")) is not bool:
        errors.append("unknown_date must be boolean")
    if record.get("source_date") is None:
        if record.get("unknown_date") is not True:
            errors.append("missing source_date without explicit unknown flag")
        else:
            warnings.append("source date unknown")
    else:
        try:
            value = record["source_date"]
            if not isinstance(value, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", value
            ):
                raise ValueError()
            date.fromisoformat(value)
            if record.get("unknown_date") is not False:
                errors.append("known source_date conflicts with unknown_date")
        except (ValueError, TypeError):
            errors.append("source_date must be an ISO calendar date")
    try:
        geom = wkt.loads(record.get("geom", ""))
        expected = (
            ("Point",) if dataset == "substations" else ("Polygon", "MultiPolygon")
        )
        if (
            geom.is_empty
            or not geom.is_valid
            or geom.geom_type not in expected
            or geom.has_z
        ):
            errors.append(
                "invalid/empty/wrong type or non-2D geometry: " + explain_validity(geom)
            )
        if not all(math.isfinite(x) for x in geom.bounds):
            errors.append("nonfinite geometry")
        # Restrict analysis to the declared German UTM32 pilot envelope.
        if geom.bounds and not (
            200000 <= geom.bounds[0] <= geom.bounds[2] <= 800000
            and 5200000 <= geom.bounds[1] <= geom.bounds[3] <= 6200000
        ):
            errors.append("geometry outside pilot CRS envelope")
    except Exception:
        errors.append("missing or unparseable WKT geometry")
    if dataset == "substations":
        voltage = record.get("voltage_kv")
        if (
            type(voltage) not in (int, float)
            or not math.isfinite(voltage)
            or voltage <= 0
        ):
            errors.append("voltage_kv must be a finite positive number")
        if record.get("voltage_units") != "kV":
            errors.append("voltage_units must explicitly be kV")
    if duplicate:
        errors.append(
            "duplicate source_id within country and dataset; all copies rejected"
        )
    return errors, warnings
