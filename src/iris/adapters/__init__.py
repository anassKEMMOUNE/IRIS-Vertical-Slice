"""Parsing only: preserve values, including invalid values, for auditable QA."""

import json
from pathlib import Path


class JsonAdapter:
    dataset: str

    def read(self, path: Path):
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError(f"{path}: expected a JSON array")
        for ordinal, record in enumerate(data, 1):
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{ordinal}: expected a record object")
            yield ordinal, dict(record)


class ParcelAdapter(JsonAdapter):
    dataset = "parcels"


class PeatAdapter(JsonAdapter):
    dataset = "peat"


class SubstationAdapter(JsonAdapter):
    dataset = "substations"


ADAPTERS = (ParcelAdapter(), PeatAdapter(), SubstationAdapter())
