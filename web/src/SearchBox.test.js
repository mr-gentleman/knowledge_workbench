import { describe, expect, it } from 'vitest';
import { hitParts, hitWhere, rank, search } from './SearchBox.jsx';

const m = (key, o) => ({ key, kind: 'canon', id: 1, dept: 'Finance', category: '', description: '', disambig: '', pis: [], ...o });
const nrr = m('nrr', { name: 'NRR', category: 'Retention', disambig: 'Not logo-based: see Logo Churn Count.' });
const churn = m('churn', { name: 'Logo Churn Count', kind: 'cand', dept: 'Customer' });
const arpa = m('arpa', { name: 'ARPA', pis: [{ table: 'AC.finance.ssa_daily_mrr', sql: 'SELECT SUM(churn_mrr)' }] });
const data = [nrr, arpa, churn];

describe('search', () => {
  it('ranks a name hit above a definition hit above a SQL hit', () => {
    expect(search(data, 'churn', 'all').map(x => x.key)).toEqual(['churn', 'nrr', 'arpa']);
  });
  it('needs every word to hit somewhere', () => {
    expect(search(data, 'nrr retention', 'all').map(x => x.key)).toEqual(['nrr']);
    expect(search(data, 'nrr daily', 'all')).toEqual([]);
  });
  it('matches category and department', () => {
    expect(search(data, 'customer', 'all').map(x => x.key)).toEqual(['churn']);
  });
  it('keeps list order with no query, and applies the kind filter', () => {
    expect(search(data, '  ', 'all')).toEqual(data);
    expect(search(data, 'churn', 'canon').map(x => x.key)).toEqual(['nrr', 'arpa']);
  });
  it('scores a name prefix above a name infix', () => {
    expect(rank(m('a', { name: 'Net ARR' }), 'net')).toBeGreaterThan(rank(m('b', { name: 'Logo Net Count' }), 'net'));
  });
});

describe('hitWhere', () => {
  it('names the field when the name does not match', () => {
    expect(hitWhere(nrr, 'churn')).toBe('definition');
    expect(hitWhere(arpa, 'churn')).toBe('SQL');
    expect(hitWhere(churn, 'churn')).toBe(null);
  });
});

describe('hitParts', () => {
  it('marks each query word, case-insensitively, and escapes regex characters', () => {
    expect(hitParts('Logo Churn Count', 'churn logo')).toEqual([
      ['Logo', true],
      [' ', false],
      ['Churn', true],
      [' Count', false],
    ]);
    expect(hitParts('NRR (YoY)', '(yoy')).toEqual([
      ['NRR ', false],
      ['(YoY', true],
      [')', false],
    ]);
    expect(hitParts('NRR', '')).toEqual([['NRR', false]]);
  });
});
