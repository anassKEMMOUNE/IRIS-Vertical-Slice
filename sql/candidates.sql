CREATE OR REPLACE VIEW bess_candidates AS
SELECT p.country_code,p.source_id AS parcel_id,ST_Area(p.geom) AS area_m2,
 ST_Area(p.geom)/10000 AS area_ha,s.source_id AS substation_id,s.voltage_kv,
 ST_Distance(p.geom,s.geom) AS distance_m,p.source_date AS parcel_date,s.source_date AS substation_date,
 p.unknown_date OR s.unknown_date AS unknown_date,'iris-screening-1.0'::text AS rule_version,
 true AS grid_capacity_unverified,true AS connection_permission_unverified,true AS ownership_unverified,true AS planning_unverified,true AS source_accuracy_unverified
FROM entities p
CROSS JOIN LATERAL (
 SELECT s.* FROM entities s WHERE s.dataset='substations' AND s.country_code=p.country_code
 AND s.voltage_kv>=110 AND ST_DWithin(p.geom,s.geom,1000)
 ORDER BY ST_Distance(p.geom,s.geom),s.source_id COLLATE "C" LIMIT 1
) s
WHERE p.dataset='parcels' AND ST_Area(p.geom)>=20000;
CREATE OR REPLACE VIEW peatland_candidates AS
SELECT p.country_code,p.source_id AS parcel_id,ST_Area(p.geom) AS area_m2,
 ST_Area(p.geom)/10000 AS area_ha,q.overlap_m2,
 q.overlap_m2/ST_Area(p.geom)*100 AS overlap_percent,q.overlap_m2*8 AS eco_points,
 q.peat_ids,q.peat_dates,p.source_date AS parcel_date,p.unknown_date OR q.unknown_date AS unknown_date,
 'iris-screening-1.0'::text AS rule_version,true AS environmental_eligibility_unverified,true AS ownership_unverified,true AS planning_unverified,true AS transferability_unverified,true AS source_accuracy_unverified
FROM entities p
CROSS JOIN LATERAL (
 SELECT ST_Area(ST_Intersection(p.geom,ST_UnaryUnion(ST_Collect(t.geom)))) AS overlap_m2,
 array_agg(t.source_id ORDER BY t.source_id COLLATE "C") AS peat_ids,
 jsonb_object_agg(t.source_id,t.source_date) AS peat_dates,bool_or(t.unknown_date) AS unknown_date
 FROM entities t WHERE t.dataset='peat' AND t.country_code=p.country_code
 AND ST_Intersects(p.geom,t.geom) AND ST_Area(ST_Intersection(p.geom,t.geom))>0
) q
WHERE p.dataset='parcels' AND ST_Area(p.geom)>=30000 AND q.overlap_m2>0;
