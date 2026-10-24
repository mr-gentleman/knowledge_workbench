// Physical implementations (PIs) on the metric page: shape, run status, titles and what a save sends.
// Rules: DEC-019 (default, labels, run status), DEC-020 (one save for the whole page).

// A metric_calc row (GET /api/candidates/{id} → CALCS) → the page's PI.
export const fromCalc = c => ({
  id: c.CALC_ID,
  table: c.SOURCE_TABLE || '',
  sql: c.SQL_TEXT || '',
  disambig: c.DISAMBIG || '',
  rev: c.REVISION_NO,
  validatedRev: c.VALIDATED_REVISION_NO,
  check: c.VALIDATION_STATUS, // passed | failed | null (never checked)
  checkMsg: c.VALIDATION_MESSAGE || '',
  served: c.SERVED_REVISION_NO,
  source: c.SOURCE,
});

const EDITABLE = ['sql', 'table', 'disambig'];
export const piChanged = (p, o) => !o || EDITABLE.some(k => p[k] !== o[k]);

// Mirrors services.validation_state: a result counts only for the revision it checked; edited SQL is "Not run".
// p = the draft PI, o = the same PI as saved (undefined while new).
export function runState(p, o) {
  if (!o || p.sql !== o.sql || !p.check || p.validatedRev !== p.rev) return { tone: 'warn', label: 'Not run' };
  return p.check === 'passed' ? { tone: 'ok', label: `✓ Runs · rev ${p.rev}` } : { tone: 'bad', label: `✗ SQL failed · rev ${p.rev}` };
}

// One PI is titled by its fact table. With several, each is titled by the first line of its "When to use".
export function piTitle(p, several) {
  const label = p.disambig.trim().split('\n')[0];
  if (several && label) return label;
  return p.table ? p.table.split('.').pop() : 'New implementation';
}

// The PIs a save sends (docs/plans/metric-save-contract.md): new, changed and removed ones.
// The server decides the default: the oldest active PI (DEC-019).
export function calcsBody(pis, origPis) {
  const fields = p => ({ sql_text: p.sql, source_table: p.table, disambig: p.disambig });
  const before = new Map(origPis.map(o => [o.id, o]));
  const touched = pis
    .filter(p => piChanged(p, before.get(p.id)))
    .map(p => ({ calc_id: p.id, expected_revision: before.get(p.id)?.rev ?? null, fields: fields(p) }));
  const removed = origPis
    .filter(o => !pis.some(p => p.id === o.id))
    .map(o => ({ calc_id: o.id, expected_revision: o.rev, retire: true, fields: fields(o) }));
  return [...touched, ...removed];
}

// Fully qualified tables the SQL reads (FROM / JOIN db.schema.table), in order, without repeats.
// Comments and string literals are ignored; CTE names never match because they aren't three-part.
export function sqlTables(sql) {
  const code = sql.replace(/--[^\n]*|\/\*[\s\S]*?\*\/|'(?:[^']|'')*'/g, ' ');
  const seen = new Map();
  for (const [, t] of code.matchAll(/\b(?:FROM|JOIN)\s+([A-Za-z_][\w$]*\.[A-Za-z_][\w$]*\.[A-Za-z_][\w$]*)/gi))
    if (!seen.has(t.toLowerCase())) seen.set(t.toLowerCase(), t);
  return [...seen.values()];
}

// The fact table follows the SQL's first table while the SME hasn't typed a different one.
export function followTable(p, sql) {
  const before = sqlTables(p.sql)[0] || '';
  if (p.table && p.table.toLowerCase() !== before.toLowerCase()) return p.table;
  return sqlTables(sql)[0] || '';
}
