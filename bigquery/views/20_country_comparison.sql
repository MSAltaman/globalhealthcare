-- One row per country in scope: atlas scores, key statistics and the financing mix.
WITH ind AS (
  SELECT
    iso3,
    MAX(IF(indicator_id = 'SP.DYN.LE00.IN', value, NULL)) AS life_expectancy,
    MAX(IF(indicator_id = 'OECD_TREATABLE_MORT', value, NULL)) AS treatable_mortality_per_100k,
    MAX(IF(indicator_id = 'SP.DYN.IMRT.IN', value, NULL)) AS infant_mortality_per_1000,
    MAX(IF(indicator_id = 'SH.XPD.CHEX.PP.CD', value, NULL)) AS health_spending_per_person_ppp,
    MAX(IF(indicator_id = 'SH.XPD.CHEX.GD.ZS', value, NULL)) AS health_spending_pct_gdp,
    MAX(IF(indicator_id = 'SH.XPD.OOPC.CH.ZS', value, NULL)) AS out_of_pocket_share_pct,
    MAX(IF(indicator_id = 'UHC_INDEX_REPORTED', value, NULL)) AS uhc_service_coverage_index,
    MAX(IF(indicator_id = 'FINPROTECTION_CATA_TOT_10_POP', value, NULL)) AS households_over_10pct_on_health
  FROM {{indicators}}
  GROUP BY iso3
),
dom AS (
  SELECT
    iso3,
    MAX(IF(domain = 'coverage', score, NULL)) AS coverage_score,
    MAX(IF(domain = 'financial_protection', score, NULL)) AS financial_protection_score,
    MAX(IF(domain = 'outcomes', score, NULL)) AS outcomes_score,
    MAX(IF(domain = 'outcomes', position, NULL)) AS outcomes_position
  FROM {{score_domains}}
  GROUP BY iso3
)
SELECT
  c.iso3, c.name, c.wave, c.is_baseline, c.has_profile, c.status, c.model_label,
  s.rank, s.overall, s.rank_low, s.rank_high,
  dom.coverage_score, dom.financial_protection_score, dom.outcomes_score, dom.outcomes_position,
  ind.* EXCEPT (iso3),
  fm.share_taxes, fm.share_social_insurance, fm.share_insurance_premiums, fm.share_out_of_pocket,
  c.claim_count, c.source_count
FROM {{countries}} AS c
LEFT JOIN {{scores}} AS s USING (iso3)
LEFT JOIN dom USING (iso3)
LEFT JOIN ind USING (iso3)
LEFT JOIN {{financing_mix}} AS fm USING (iso3)
