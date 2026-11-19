-- Who pays for health care in each country: OECD revenue segments grouped into
-- five channels, as a share of total current health spending.
-- Table names in double braces are filled in by scripts/load_bigquery.py.
SELECT
  iso3,
  ANY_VALUE(year) AS year,
  ANY_VALUE(total_pct_gdp) AS health_spending_pct_gdp,
  SUM(IF(segment_id = 'taxes', share_of_total, 0)) AS share_taxes,
  SUM(IF(segment_id IN ('payroll_employer', 'payroll_worker', 'payroll_other'), share_of_total, 0)) AS share_social_insurance,
  SUM(IF(segment_id IN ('mandated_employer', 'mandated_individual', 'voluntary'), share_of_total, 0)) AS share_insurance_premiums,
  SUM(IF(segment_id = 'households', share_of_total, 0)) AS share_out_of_pocket,
  SUM(IF(segment_id IN ('other', 'private_unsplit'), share_of_total, 0)) AS share_other,
  LOGICAL_OR(segment_id = 'private_unsplit' AND pct_gdp > 0) AS private_not_broken_down
FROM {{financing_revenue}}
GROUP BY iso3
