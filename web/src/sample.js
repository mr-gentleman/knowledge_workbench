// Sample canon from the mockup. Only candidates are live in this spike (one real read, one real write);
// canon/PI reads would follow the same API pattern against metric_core / metric_calc.
const NRR_MONTHLY = `-- Annualized NRR, AC accounts on core plans, last full month
SELECT
    date,
    POWER(
        1 + (
            (COALESCE(SUM(churn_mrr), 0)
           + COALESCE(SUM(contraction_mrr), 0)
           + COALESCE(SUM(reactivation_mrr), 0)
           + COALESCE(SUM(expansion_mrr), 0))
          / NULLIFZERO(COALESCE(SUM(starting_mrr), 0))
        ), 12
    ) AS annualized_nrr
FROM AC.conformed_dimensions.cohort_account_monthly_consolidation
WHERE UPPER(account_type) = 'AC'
  AND plan_name_bop IN ('Enterprise', 'Plus', 'Professional', 'Starter')
  AND date = DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE()))
GROUP BY date;`;
const NRR_DAILY = `-- Month-to-date NRR pacing (example)
SELECT
    DATE_TRUNC('month', date) AS month,
    1 + (SUM(churn_mrr) + SUM(contraction_mrr)
       + SUM(reactivation_mrr) + SUM(expansion_mrr))
      / NULLIFZERO(SUM(CASE WHEN date = DATE_TRUNC('month', date)
                            THEN starting_mrr END)) AS mtd_nrr
FROM AC.conformed_dimensions.cohort_account_daily_consolidation
WHERE UPPER(account_type) = 'AC'
  AND date >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY 1;`;
const fmt = s =>
  s
    .replace(/ (FROM|WHERE|GROUP BY|AND) /g, '\n$1 ')
    .replace(/^SELECT /, 'SELECT\n    ')
    .replace(/, (SUM|COUNT|ABS|POWER)/g, ',\n    $1');

export const FACT = {
  'AC.conformed_dimensions.cohort_account_monthly_consolidation': 'Monthly',
  'AC.conformed_dimensions.cohort_account_daily_consolidation': 'Daily',
  'AC.finance.ssa_daily_mrr_consolidation_rollup': 'Daily',
  'AC.acdb.csat': 'Response',
  'AC.acdb.nps_accountid_best_match': 'Response',
  'AC.conformed_dimensions.account_extension': 'Account (current)',
};

export const COLS = {
  cohort_account_monthly_consolidation: [
    'date',
    'account_id',
    'account_type',
    'plan_name_bop',
    'starting_mrr',
    'churn_mrr',
    'contraction_mrr',
    'expansion_mrr',
    'reactivation_mrr',
    'total_mrr',
  ],
  cohort_account_daily_consolidation: [
    'date',
    'account_id',
    'account_type',
    'account_convert_date',
    'starting_mrr',
    'churn_mrr',
    'contraction_mrr',
    'expansion_mrr',
    'reactivation_mrr',
  ],
  ssa_daily_mrr_consolidation_rollup: ['date_cst', 'accountid', 'mrr_type', 'inferred_mrr', 'exists_in_fact_daily_mrr_tiers'],
  account_extension: ['account_id', 'plan_name', 'is_paid_plan', 'created_date'],
  csat: ['tstamp', 'id', 'type', 'rating'],
  nps_accountid_best_match: ['cdate', 'accountid', 'score'],
};

const pi = (id, table, sql, o = {}) => ({
  id,
  table,
  sql,
  disambig: '',
  validatedRev: 3,
  rev: 3,
  served: 3,
  check: 'passed',
  checkMsg: '',
  source: 'auto-gen',
  ...o,
});

export const SAMPLE_CANON = [
  {
    key: 'nrr',
    id: 10,
    kind: 'canon',
    dept: 'Finance',
    name: 'NRR',
    category: 'Retention',
    rev: 5,
    source: 'auto-gen',
    author: 'chris',
    description:
      'Net Revenue Retention; the primary revenue-retention KPI. Starting-MRR cohort is gated; reactivations count in the numerator.',
    disambig:
      'Use for revenue retention including expansion. For retention without expansion, use GRR. Not logo-based: see Logo Churn Count.',
    pis: [
      pi(1, 'AC.conformed_dimensions.cohort_account_monthly_consolidation', NRR_MONTHLY, {
        disambig: 'Default. Closed months; matches the board-reported number.',
        validatedRev: 4,
        rev: 4,
        served: 4,
        source: 'sme',
      }),
      pi(2, 'AC.conformed_dimensions.cohort_account_daily_consolidation', NRR_DAILY, {
        disambig: 'Intra-month pacing only. Not annualized; never compare to the monthly number.',
        validatedRev: 1,
        rev: 2,
        served: 1,
        source: 'sme',
      }),
    ],
  },
  {
    key: 'grr',
    id: 11,
    kind: 'canon',
    dept: 'Finance',
    name: 'GRR',
    category: 'Retention',
    rev: 3,
    source: 'auto-gen',
    author: 'chris',
    description: 'Gross Revenue Retention; retention excluding the benefit of expansion.',
    disambig: 'Use when expansion should not offset losses. Compare with NRR.',
    pis: [
      pi(
        3,
        'AC.conformed_dimensions.cohort_account_monthly_consolidation',
        "SELECT date, POWER(1 + ((COALESCE(SUM(churn_mrr),0) + COALESCE(SUM(contraction_mrr),0)) / NULLIFZERO(COALESCE(SUM(starting_mrr),0))), 12) AS annualized_grr FROM AC.conformed_dimensions.cohort_account_monthly_consolidation WHERE UPPER(account_type) = 'AC' AND date = DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE())) GROUP BY date;",
      ),
    ],
  },
  {
    key: 'net_arr',
    id: 3,
    kind: 'canon',
    dept: 'Finance',
    name: 'Net ARR',
    category: 'Core Financial',
    rev: 2,
    source: 'auto-gen',
    author: 'chris',
    description: 'Net ARR change over a period after positive and negative movement types are combined.',
    disambig: '',
    pis: [
      pi(
        4,
        'AC.finance.ssa_daily_mrr_consolidation_rollup',
        "SELECT date_cst, SUM(inferred_mrr)*12 AS net_arr FROM AC.finance.ssa_daily_mrr_consolidation_rollup WHERE exists_in_fact_daily_mrr_tiers = 1 AND mrr_type IN ('new_biz','churn','expansion','contraction','reactivation') GROUP BY date_cst;",
      ),
    ],
  },
  {
    key: 'arpa',
    id: 13,
    kind: 'canon',
    dept: 'Finance',
    name: 'ARPA',
    category: 'Growth & Accounts',
    rev: 2,
    source: 'auto-gen',
    author: 'chris',
    description: 'Average revenue per account; used with ARR and customer count to track mix and monetization.',
    disambig: '',
    pis: [
      pi(
        5,
        'AC.conformed_dimensions.cohort_account_monthly_consolidation',
        "SELECT date, SUM(total_mrr)*12 / NULLIFZERO(COUNT(DISTINCT account_id)) AS arpa FROM AC.conformed_dimensions.cohort_account_monthly_consolidation WHERE UPPER(account_type) = 'AC' AND total_mrr > 0 GROUP BY date;",
      ),
    ],
  },
  {
    key: 'logo',
    id: 23,
    kind: 'canon',
    dept: 'Finance',
    name: 'Logo Churn Count',
    category: 'Retention',
    rev: 1,
    source: 'auto-gen',
    author: 'chris',
    description: 'Count-based churn at the account/logo level rather than ARR-weighted churn.',
    disambig: 'Counts accounts, not dollars. For dollar churn see Churn ARR.',
    pis: [
      pi(
        6,
        'AC.conformed_dimensions.cohort_account_monthly_consolidation',
        "SELECT date, COUNT(DISTINCT CASE WHEN churn_mrr < 0 THEN account_id END) AS logo_churn_count FROM AC.conformed_dimensions.cohort_account_monthly_consolidation WHERE UPPER(account_type) = 'AC' GROUP BY date;",
      ),
    ],
  },
  {
    key: 'csat',
    id: 90001,
    kind: 'canon',
    dept: 'Customer',
    name: 'CSAT',
    category: 'Support',
    rev: 1,
    source: 'sme',
    author: 'cx team',
    description: 'Customer satisfaction score across support channels, scaled 0–1.',
    disambig: '',
    pis: [
      pi(
        8,
        'AC.acdb.csat',
        "SELECT DATE_TRUNC('month', TSTAMP) AS month, SUM(RATING) / NULLIF(COUNT(DISTINCT ID) * 10, 0) AS csat_score FROM AC.ACDB.CSAT WHERE TSTAMP >= DATEADD('month', -12, CURRENT_DATE) GROUP BY ALL",
        { source: 'sme' },
      ),
    ],
  },
  {
    key: 'nps',
    id: 90002,
    kind: 'canon',
    dept: 'Customer',
    name: 'NPS',
    category: 'Support',
    rev: 1,
    source: 'sme',
    author: 'cx team',
    description: 'Net Promoter Score: promoters minus detractors, as a percent of responses.',
    disambig: '',
    pis: [
      pi(
        9,
        'AC.acdb.nps_accountid_best_match',
        "SELECT DATE_TRUNC('month', CDATE) AS month, (SUM(IFF(SCORE >= 9,1,0)) - SUM(IFF(SCORE <= 6,1,0))) / NULLIFZERO(COUNT(*)) * 100 AS nps_score FROM AC.ACDB.NPS_ACCOUNTID_BEST_MATCH GROUP BY ALL",
        { source: 'sme' },
      ),
    ],
  },
].map(m => ({ ...m, pis: m.pis.map(p => ({ ...p, sql: p.sql.includes('\n') ? p.sql : fmt(p.sql) })) }));
