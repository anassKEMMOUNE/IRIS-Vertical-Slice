# Synthetic demonstration fixtures

All records in this directory are invented for deterministic engineering tests. They do not represent actual cadastre, ownership, planning status, environmental eligibility, grid capacity or connection permission. IDs and dates are synthetic. WKT coordinates are explicitly EPSG:25832, in metres, near a German UTM32 pilot location.

`parcels.json`, `peat.json` and `substations.json` each contain an array of records under the contracts in the root README. Intentionally invalid records must stay invalid to exercise rejection evidence. Do not correct them to make every row promote. See the root README table for dimensions, thresholds and independently known outcomes.
