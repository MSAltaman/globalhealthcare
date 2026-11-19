-- Every country's value for every statistic next to the United States' value.
-- difference = country minus US, in the indicator's own unit.
WITH us AS (
  SELECT indicator_id, value AS us_value, year AS us_year
  FROM {{indicators}}
  WHERE iso3 = 'USA'
)
SELECT
  i.iso3, c.name, i.indicator_id, i.label, i.unit, i.indicator_group,
  i.value, i.year, us.us_value, us.us_year,
  i.value - us.us_value AS difference,
  SAFE_DIVIDE(i.value, us.us_value) AS ratio_to_us
FROM {{indicators}} AS i
JOIN us USING (indicator_id)
LEFT JOIN {{countries}} AS c USING (iso3)
WHERE i.iso3 != 'USA'
