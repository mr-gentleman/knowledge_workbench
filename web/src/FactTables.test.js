import { describe, expect, it } from 'vitest';
import { FIELDS, changedFields, fromRow, matchesTable, saveBody } from './FactTables.jsx';
import { outcome } from './metricSave.js';

const row = {
  table_name: 'AC.FINANCE.MRR',
  grain: 'One row per account per day',
  status: 'active',
  department: 'Finance',
  description: null,
  revision_no: 3,
  updated_by: 'ALICE',
};

describe('fact table drafts', () => {
  it('maps an API row, blanks as empty strings', () => {
    const t = fromRow(row);
    expect([t.key, t.name, t.rev, t.description, t.grain]).toEqual(['t:AC.FINANCE.MRR', 'AC.FINANCE.MRR', 3, '', row.grain]);
  });

  it('sends every field, so fields the form hides keep their value', () => {
    const t = fromRow(row);
    const body = saveBody({ ...t, grain: 'weekly' }, t);
    expect(Object.keys(body.table.fields)).toEqual(FIELDS);
    expect(body.table).toMatchObject({ table_name: 'AC.FINANCE.MRR', expected_revision: 3 });
    expect(body.table.fields).toMatchObject({ grain: 'weekly', department: 'Finance' });
  });

  it('a draft with no saved baseline is a create', () => {
    expect(saveBody(fromRow(row), undefined).table.expected_revision).toBeNull();
  });

  it('lists changed fields; a new draft lists what it filled in', () => {
    const t = fromRow(row);
    expect(changedFields({ ...t, gotchas: 'x', status: 'retired' }, t)).toEqual(['gotchas', 'status']);
    expect(changedFields({ ...t, description: '' }, undefined)).toEqual(['grain', 'department']);
  });

  it('search matches name, definition and grain, ignoring case', () => {
    const t = fromRow(row);
    expect(['mrr', 'PER ACCOUNT', '', 'nope'].map(q => matchesTable(t, q))).toEqual([true, true, true, false]);
  });

  it('a fact-table reply sets the revision from revision_no', () => {
    const t = fromRow(row);
    expect(outcome({ status: 'saved', revision_no: 4 }, t, 'BOB').saved).toMatchObject({ rev: 4, updatedBy: 'BOB' });
  });
});
