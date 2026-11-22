# Atlas method 0.2-draft (archived 20 Nov 2026)

The scoring method before financial protection changed to method 0.3.

- Git tag `method-v0.2` holds the full repository (code, config, data) at that point:
  `git checkout method-v0.2`.
- `scoring.json`: the 0.2 scoring configuration. Financial protection scored the
  out-of-pocket share of health spending (weight 2) plus WHO's three household
  measures: catastrophic spending over 10% and 25% of the household budget, and
  impoverishment by health costs (weight 1 each).
- `reference.json`: the worldwide benchmark values used for scaling.
- `scores-all-countries.json`: 0.2 scores for all 45 ranked countries, computed
  from every research branch on 20 Nov 2026.

Why it changed: WHO's household measures were missing or older than the 10-year
rule for 19 to 21 of 45 countries (Sweden 1996, Norway 1998, Germany 2010, none
for France, the Netherlands or New Zealand), so countries were scored on
different measures. Method 0.3 scores every country on the same current measures.
