# Data analysis pilot report

> Scope: synthetic sample only. This report does not describe production data or current product performance.

## Source and quality gate

- Source: `tests/fixtures/data-analysis/weekly-metrics.csv`
- Snapshot date: `2026-08-24`
- Intended grain: one row per `week_start × channel`
- Rows / periods / channels: `8 / 4 / 2`
- Null or blank required values: `0`
- Duplicate grain rows: `0`
- Invalid funnel rows (`paid_conversions <= signups <= sessions`): `0`
- Freshness lag from latest week to snapshot: `7 days`
- Quality gate: **PASS for this synthetic descriptive pilot**

## Observations

| Period | Sessions | Paid conversions | Paid conversion rate |
|---|---:|---:|---:|
| 2026-08-10 | 2,100 | 138 | 6.57% |
| 2026-08-17 | 2,250 | 130 | 5.78% |

The aggregate paid conversion rate changed by **-0.79 pp** (-12.08% relative).

| Channel | Prior rate | Current rate | Change |
|---|---:|---:|---:|
| organic | 8.00% | 8.00% | +0.00 pp |
| ads | 4.67% | 3.00% | -1.67 pp |

## Calculations

- Prior aggregate rate: `138 / 2100 = 6.57%`
- Current aggregate rate: `130 / 2250 = 5.78%`
- Current-period counterfactual at prior channel rates: `6.52%`
- Channel-mix effect: `-0.05 pp`
- Within-channel rate effect: `-0.74 pp`
- Share of the observed drop associated with the within-channel rate effect: `93.33%`

## Inferences

- Organic remained at 8.00%; the visible deterioration is concentrated in the ads segment.
- Under this descriptive decomposition, the within-channel rate effect accounts for 93.33% of the aggregate decline.
- This decomposition does not establish causality. Campaign mix, attribution, landing-page changes, and late-arriving events were not observed.

## Recommendations

1. Validate ads tracking completeness and late-arriving conversions before acting on the decline.
2. Compare campaign, creative, audience, device, and landing-page mix for the two latest weeks.
3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.

## Unknowns

- Campaign-level composition and spend
- Attribution-window or tracking-definition changes
- Whether recent conversion events are complete
- Production metric definitions and business thresholds

## Publication boundary

Only this synthetic aggregate report is approved for repository publication. Raw production rows, identifiers, credentials, connector details, and unpublished business metrics remain outside scope.
