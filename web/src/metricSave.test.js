// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { outcome, readStored, restoredBaseline, saveBody, useMetricSave } from './metricSave.js';
import { saveBody as factSaveBody } from './FactTables.jsx';
import { saveMetric } from './api.js';
import replayConflicts from '../../tests/fixtures/replay-conflicts.json';

vi.mock('./api.js', () => ({ saveMetric: vi.fn() }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// Node's own (file-less) localStorage shadows jsdom's; use an in-memory one.
const mem = new Map();
vi.stubGlobal('localStorage', {
  getItem: k => mem.get(k) ?? null,
  setItem: (k, v) => mem.set(k, String(v)),
  clear: () => mem.clear(),
});

const snap = {
  key: 'c7',
  mid: 7,
  name: 'NRR',
  description: 'd',
  disambig: '',
  deptRaw: 'finance',
  category: 'Retention',
  rev: 3,
  updatedBy: 'OLD',
  pis: [],
};

describe('outcome', () => {
  it('treats conflict and invalid as nothing written', () => {
    expect(outcome({ status: 'conflict', message: 'changed' }, snap, 'ME').failed).toBe('conflict');
    expect(outcome({ status: 'invalid', message: 'bad' }, snap, 'ME').failed).toBe('conflict');
  });
  it('keeps the draft on a failed save', () => {
    expect(outcome({ status: 'failed', message: 'x' }, snap, 'ME')).toMatchObject({ failed: 'failed' });
  });
  it('advances the revision and author on a write', () => {
    expect(outcome({ status: 'saved', metric_revision: 4 }, snap, 'ME')).toEqual({
      saved: { ...snap, rev: 4, updatedBy: 'ME' },
      wrote: true,
    });
    expect(outcome({ status: 'replayed', metric_revision: 4 }, snap, 'ME').wrote).toBe(true);
  });
  it('lists every problem of an invalid save', () => {
    const out = { status: 'invalid', message: 'Nothing was saved.', problems: [{ message: 'Add SQL to save.' }] };
    expect(outcome(out, snap, 'ME').msg).toBe('NRR: Nothing was saved. Add SQL to save.');
  });
  it('moves saved PIs to their new revisions; a check survives unless the SQL changed', () => {
    const pis = [
      { id: 5, rev: 2, validatedRev: 2 },
      { id: 6, rev: 4, validatedRev: 4 },
      { id: 9, rev: 1, validatedRev: null },
    ];
    const out = { status: 'saved', metric_revision: 4, calc_revisions: { 5: 3, 6: 5 }, checks_due: [6] };
    expect(outcome(out, { ...snap, pis }, 'ME').saved.pis).toEqual([
      { id: 5, rev: 3, validatedRev: 3 },
      { id: 6, rev: 5, validatedRev: 4 },
      { id: 9, rev: 1, validatedRev: null },
    ]);
  });
  it('keeps the author on a no-op save', () => {
    expect(outcome({ status: 'unchanged', metric_revision: 3 }, snap, 'ME')).toEqual({
      saved: { ...snap, updatedBy: 'OLD' },
      wrote: false,
    });
  });
});

describe('saveBody', () => {
  it('checks against the last saved revision, not the draft', () => {
    const b = saveBody({ ...snap, rev: 9 }, { rev: 3, pis: [] });
    expect(b.metric).toMatchObject({ id: 7, expected_revision: 3 });
    expect(saveBody(snap, snap).op_id).not.toBe(b.op_id);
  });

  it('never takes a fresh server revision as the baseline of a restored draft', () => {
    const draft = { ...snap, description: 'Mine' };
    const stored = { snap: draft, body: saveBody(draft, snap), baseline: snap };
    const baseline = restoredBaseline({ ...snap, description: 'Theirs', rev: 5 }, stored);
    expect(saveBody(draft, baseline).metric.expected_revision).toBe(3);
    expect(baseline.description).toBe(snap.description);
    const table = { name: 'AC.FINANCE.MRR', grain: 'weekly', rev: 3 };
    const tableBaseline = restoredBaseline({ ...table, grain: 'daily', rev: 5 }, { baseline: table });
    expect(factSaveBody(table, tableBaseline).table.expected_revision).toBe(3);
  });

  it('refuses to adopt the current revision for legacy recovery data without a baseline', () => {
    const row = { ...snap, rev: 5 };
    expect(restoredBaseline(row)).toBe(row);
    expect(restoredBaseline(row, { snap, body: saveBody(snap, snap) }).rev).toBeNull();
  });
});

// Renders the hook and exposes its latest return value.
function mount(props) {
  const out = {};
  const Probe = () => {
    Object.assign(out, useMetricSave(props));
    return null;
  };
  act(() => createRoot(document.createElement('div')).render(createElement(Probe)));
  return out;
}
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
};

describe('useMetricSave', () => {
  beforeEach(() => {
    localStorage.clear();
    saveMetric.mockReset();
  });

  it.each(Object.entries(replayConflicts))(
    'preserves the %s draft and baseline after a lost response and intervening edit',
    async (kind, response) => {
      // api.test_api asserts these exact responses from the real API/service code.
      const onSaved = vi.fn();
      const save = vi.fn().mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce({ data: response, ms: 50 });
      const h = mount({ user: 'ME', onSaved, flash: vi.fn(), save });
      const draft =
        kind === 'metric'
          ? { ...snap, pis: [{ id: 5, sql: 'SELECT mine', rev: 2, validatedRev: 2, check: 'passed' }] }
          : { key: 't:AC.FINANCE.MRR', name: 'AC.FINANCE.MRR', grain: 'My edit', rev: 3 };
      const body =
        kind === 'metric'
          ? saveBody(draft, { ...draft, pis: [] })
          : { op_id: crypto.randomUUID(), table: { table_name: draft.name, expected_revision: 3, fields: { grain: draft.grain } } };
      const baseline = { ...draft, rev: 3 };
      await act(() => h.send(draft.key, { snap: draft, body, baseline }));
      await act(() => h.send(draft.key, h.pending[draft.key]));
      expect(save.mock.calls[1][0]).toBe(body);
      expect(onSaved).not.toHaveBeenCalled();
      expect(h.pending[draft.key]).toMatchObject({ state: 'conflict', snap: draft, body });
      expect(h.pending[draft.key].msg).toContain('earlier save went through');
      expect(h.justSaved[draft.key]).toBeUndefined();
      expect(readStored()[draft.key]).toEqual({ snap: draft, body, baseline });
      const recovered = restoredBaseline({ ...draft, rev: 5 }, readStored()[draft.key]);
      expect(recovered.rev).toBe(3);
      expect(draft.rev).toBe(3);
      if (kind === 'metric') expect(draft.pis[0]).toMatchObject({ rev: 2, validatedRev: 2 });
    },
  );

  it('keeps the draft stored until the server confirms', async () => {
    const onSaved = vi.fn();
    const h = mount({ user: 'ME', onSaved, flash: vi.fn() });
    const reply = deferred();
    saveMetric.mockReturnValue(reply.promise);
    const body = saveBody(snap, snap);
    let sent;
    act(() => {
      sent = h.send('c7', { snap, body });
    });
    expect(h.pending.c7.state).toBe('saving');
    expect(readStored().c7.body.op_id).toBe(body.op_id);
    await act(async () => {
      reply.resolve({ data: { status: 'saved', metric_revision: 4 }, ms: 900 });
      await sent;
    });
    expect(onSaved).toHaveBeenCalledWith('c7', snap, expect.objectContaining({ rev: 4 }));
    expect(h.pending.c7).toBeUndefined();
    expect(h.justSaved.c7).toEqual({ rev: 4, ms: 900 });
    expect(readStored().c7).toBeUndefined();
  });

  it('marks a network error retryable and retry reuses the op_id', async () => {
    const h = mount({ user: 'ME', onSaved: vi.fn(), flash: vi.fn() });
    const body = saveBody(snap, snap);
    saveMetric.mockRejectedValueOnce(new Error('timeout'));
    await act(() => h.send('c7', { snap, body }));
    expect(h.pending.c7.state).toBe('failed');
    expect(readStored().c7).toBeDefined();
    saveMetric.mockResolvedValueOnce({ data: { status: 'replayed', metric_revision: 4 }, ms: 50 });
    await act(() => h.send('c7', h.pending.c7));
    expect(saveMetric.mock.calls[1][0].op_id).toBe(body.op_id);
    expect(h.pending.c7).toBeUndefined();
  });

  it('ignores a late reply to a superseded save', async () => {
    const h = mount({ user: 'ME', onSaved: vi.fn(), flash: vi.fn() });
    const first = deferred();
    saveMetric.mockReturnValueOnce(first.promise).mockReturnValueOnce(new Promise(() => {}));
    let p1;
    act(() => {
      p1 = h.send('c7', { snap, body: saveBody(snap, snap) });
    });
    const second = saveBody(snap, snap);
    act(() => {
      h.send('c7', { snap, body: second });
    });
    await act(async () => {
      first.resolve({ data: { status: 'failed', message: 'x' }, ms: 1 });
      await p1;
    });
    expect(h.pending.c7).toMatchObject({ state: 'saving', body: second });
  });

  it('keeps the draft on a conflict', async () => {
    const onSaved = vi.fn();
    const h = mount({ user: 'ME', onSaved, flash: vi.fn() });
    saveMetric.mockResolvedValueOnce({ data: { status: 'conflict', message: 'changed' }, ms: 1 });
    await act(() => h.send('c7', { snap, body: saveBody(snap, snap) }));
    expect(h.pending.c7.state).toBe('conflict');
    expect(onSaved).not.toHaveBeenCalled();
  });
});
