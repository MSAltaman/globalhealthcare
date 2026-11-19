-- Balance per country: claims in the what_works and problems sections, and
-- claims marked as strengths or weaknesses anywhere in the profile.
SELECT
  c.iso3, c.name,
  COUNTIF(cl.section = 'what_works') AS what_works_claims,
  COUNTIF(cl.section = 'problems') AS problems_claims,
  COUNTIF(cl.valence = 'strength') AS strength_claims,
  COUNTIF(cl.valence = 'weakness') AS weakness_claims,
  COUNTIF(cl.valence = 'neutral') AS neutral_claims,
  COUNT(DISTINCT IF(cl.section = 'what_works', cl.source_id, NULL)) AS what_works_sources,
  COUNT(DISTINCT IF(cl.section = 'problems', cl.source_id, NULL)) AS problems_sources
FROM {{countries}} AS c
JOIN {{claims}} AS cl USING (iso3)
GROUP BY c.iso3, c.name
