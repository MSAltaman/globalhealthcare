-- Each claim with the source it cites.
SELECT
  cl.claim_id, cl.iso3, c.name AS country, cl.section, cl.position, cl.statement, cl.valence,
  cl.data_year, cl.historical,
  cl.locator_page, cl.locator_section, cl.locator_table, cl.locator_figure,
  cl.passage_found, cl.supports, cl.checked_on,
  s.source_id, s.title AS source_title, s.publisher, s.year AS source_year, s.tier, s.type AS source_type,
  s.url AS source_url, s.doi, s.funding_note
FROM {{claims}} AS cl
LEFT JOIN {{sources}} AS s ON s.iso3 = cl.iso3 AND s.source_id = cl.source_id
LEFT JOIN {{countries}} AS c ON c.iso3 = cl.iso3
