CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS runs (
 run_id uuid PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL CHECK(status IN ('started','loaded','promoted','success','failed')),
 inputs jsonb NOT NULL DEFAULT '[]', error text
);
CREATE TABLE IF NOT EXISTS staging (
 stage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES runs, dataset text NOT NULL,
 source_file text NOT NULL, ordinal integer NOT NULL, payload jsonb NOT NULL,
 UNIQUE(run_id,dataset,source_file,ordinal)
);
CREATE TABLE IF NOT EXISTS validation_results (
 stage_id bigint PRIMARY KEY REFERENCES staging, accepted boolean NOT NULL,
 errors jsonb NOT NULL, warnings jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
 country_code text NOT NULL CHECK(country_code ~ '^[A-Z]{2}$'),
 dataset text NOT NULL CHECK(dataset IN ('parcels','peat','substations')),
 source_id text NOT NULL CHECK(length(source_id)>0),
 source_date date, unknown_date boolean NOT NULL,
 geom geometry(Geometry,25832) NOT NULL,
 voltage_kv double precision,
 stage_id bigint NOT NULL REFERENCES staging,
 PRIMARY KEY(country_code,dataset,source_id),
 CHECK ((source_date IS NULL) = unknown_date),
 CHECK (NOT ST_IsEmpty(geom) AND ST_IsValid(geom)),
 CHECK ((dataset='substations' AND GeometryType(geom)='POINT' AND voltage_kv IS NOT NULL AND voltage_kv>0 AND voltage_kv<'Infinity'::float8)
 OR (dataset IN ('parcels','peat') AND GeometryType(geom) IN ('POLYGON','MULTIPOLYGON') AND voltage_kv IS NULL))
);
CREATE INDEX IF NOT EXISTS entities_geom_idx ON entities USING gist(geom);
CREATE INDEX IF NOT EXISTS staging_run_idx ON staging(run_id);
CREATE OR REPLACE VIEW rejected_records AS
 SELECT s.*,v.errors,v.warnings FROM staging s JOIN validation_results v USING(stage_id) WHERE NOT v.accepted;
