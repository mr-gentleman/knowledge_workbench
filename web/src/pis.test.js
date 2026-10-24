import { describe, expect, it } from 'vitest';
import { calcsBody, followTable, fromCalc, piTitle, runState, sqlTables } from './pis.js';

const saved = fromCalc({
  CALC_ID: 5,
  SOURCE_TABLE: 'AC.acdb.csat',
  SQL_TEXT: 'SELECT 1',
  DISAMBIG: 'Survey month\nmore detail',
  REVISION_NO: 3,
  VALIDATED_REVISION_NO: 3,
  VALIDATION_STATUS: 'passed',
  SOURCE: 'sme',
});

describe('runState', () => {
  it('reports a result only for the revision it checked', () => {
    expect(runState(saved, saved).label).toBe('✓ Runs · rev 3');
    expect(runState({ ...saved, check: 'failed' }, saved).label).toBe('✗ SQL failed · rev 3');
    expect(runState({ ...saved, rev: 4 }, { ...saved, rev: 4 }).label).toBe('Not run');
  });
  it('treats edited or unsaved SQL as not run', () => {
    expect(runState({ ...saved, sql: 'SELECT 2' }, saved).label).toBe('Not run');
    expect(runState(saved, undefined).label).toBe('Not run');
    expect(runState({ ...saved, disambig: 'x' }, saved).tone).toBe('ok');
  });
});

describe('piTitle', () => {
  it('names one PI by its table and several by their first label line', () => {
    expect(piTitle(saved, false)).toBe('csat');
    expect(piTitle(saved, true)).toBe('Survey month');
    expect(piTitle({ ...saved, disambig: ' ' }, true)).toBe('csat');
    expect(piTitle({ ...saved, table: '', disambig: '' }, true)).toBe('New implementation');
  });
});

describe('calcsBody', () => {
  const fields = { sql_text: 'SELECT 1', source_table: 'AC.acdb.csat', disambig: 'Survey month\nmore detail' };
  it('sends new, changed and removed PIs; leaves untouched ones out', () => {
    const other = { ...saved, id: 6, rev: 1 };
    const fresh = { ...saved, id: 7, sql: 'SELECT 7' };
    expect(calcsBody([{ ...saved, table: '' }, fresh], [saved, other])).toEqual([
      { calc_id: 5, expected_revision: 3, fields: { ...fields, source_table: '' } },
      { calc_id: 7, expected_revision: null, fields: { ...fields, sql_text: 'SELECT 7' } },
      { calc_id: 6, expected_revision: 1, retire: true, fields },
    ]);
    expect(calcsBody([saved], [saved])).toEqual([]);
  });
});

describe('sqlTables / followTable', () => {
  const sql = `-- FROM AC.x.commented
WITH m AS (SELECT * FROM AC.finance.mrr)
SELECT 'FROM AC.x.quoted' FROM m JOIN ac.acdb.csat c ON true LEFT JOIN AC.finance.MRR r ON true`;
  it('lists three-part tables in order, once, skipping comments, strings and CTEs', () => {
    expect(sqlTables(sql)).toEqual(['AC.finance.mrr', 'ac.acdb.csat']);
  });
  it('follows the SQL until the SME types a different table', () => {
    const p = { sql: 'SELECT 1 FROM AC.a.one', table: '' };
    expect(followTable(p, 'SELECT 1 FROM AC.a.two')).toBe('AC.a.two');
    expect(followTable({ ...p, table: 'AC.a.one' }, 'SELECT 1 FROM AC.a.two')).toBe('AC.a.two');
    expect(followTable({ ...p, table: 'AC.z.mine' }, 'SELECT 1 FROM AC.a.two')).toBe('AC.z.mine');
  });
});
