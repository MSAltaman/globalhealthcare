-- How much of the atlas rests on each publisher.
SELECT
  publisher,
  MIN(tier) AS best_tier,
  COUNT(DISTINCT source_id) AS sources,
  COUNT(DISTINCT iso3) AS countries,
  SUM(claim_count) AS claims_citing
FROM {{sources}}
GROUP BY publisher
ORDER BY claims_citing DESC
