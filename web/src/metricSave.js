// The metric save (DEC-020): one optimistic, retryable save per metric. The fact-table screen
// reuses it with its own `save` call (UX-04); `snap.name` labels messages either way.
// The page shows the submitted values at once; "Saved" appears only after the server commits.
import { useEffect, useState } from 'react';
import { saveMetric } from './api.js';
import { calcsBody } from './pis.js';

// Unconfirmed saves survive a closed tab: { [key]: { snap, body } } until the server confirms.
const PENDING = 'kw.pendingSaves';
export const readStored = () => {
  try {
    return JSON.parse(localStorage.getItem(PENDING)) || {};
  } catch {
    return {};
  }
};
const store = (key, v) => {
  try {
    const all = readStored();
    if (v) all[key] = v;
    else delete all[key];
    localStorage.setItem(PENDING, JSON.stringify(all));
  } catch {
    /* storage blocked: the draft lives only in memory */
  }
};

// The request for saving draft `m` against its last saved revision. A new op_id per save; Retry reuses it.
export const saveBody = (m, orig) => ({
  op_id: crypto.randomUUID(),
  metric: {
    id: m.mid,
    expected_revision: orig.rev,
    fields: { full_name: m.name, description: m.description, disambig: m.disambig, department: m.deptRaw, category: m.category },
  },
  calcs: calcsBody(m.pis, orig.pis),
});

// The new revision: metric replies carry metric_revision, fact-table replies revision_no.
const revOf = out => out.metric_revision ?? out.revision_no;

// What a server reply means for the submitted snapshot `snap`.
// → { failed: 'conflict' | 'failed', msg }   nothing was written (or unknown); keep the draft
// → { saved: metric, wrote }                 committed; wrote = false for a no-op save
export function outcome(out, snap, user) {
  if (out.status === 'conflict' || out.status === 'invalid')
    return { failed: 'conflict', msg: [`${snap.name}: ${out.message}`, ...(out.problems || []).map(p => p.message)].join(' ') };
  if (out.status === 'failed') return { failed: 'failed', msg: `Couldn't save ${snap.name}. Your edits are kept. ${out.message}` };
  const wrote = out.status === 'saved' || out.status === 'replayed';
  // A check stays valid until the SQL changes (sql/008): PIs not in checks_due carry it to their new revision.
  // Fact-table snapshots have no PIs.
  const pis = snap.pis?.map(p => {
    const rev = out.calc_revisions?.[p.id] ?? p.rev;
    const keep = p.validatedRev === p.rev && !(out.checks_due || []).includes(p.id);
    return { ...p, rev, validatedRev: keep ? rev : p.validatedRev };
  });
  return { saved: { ...snap, ...(pis && { pis }), rev: revOf(out), updatedBy: wrote ? user : snap.updatedBy }, wrote };
}

const without = (o, key) => {
  const { [key]: _, ...rest } = o;
  return rest;
};

// pending[key] = { snap, body, state: 'saving' | 'failed' | 'conflict', msg }: the submitted snapshot.
// justSaved[key] = { rev, ms }: the header's ✓ Saved pill, until the next Edit.
// onSaved(key, snap, saved) is called once the server commits `snap` as `saved`.
export function useMetricSave({ user, onSaved, flash, save = saveMetric }) {
  const [pending, setPending] = useState({});
  const [justSaved, setJustSaved] = useState({});
  const inFlight = Object.values(pending).some(p => p.state === 'saving');

  useEffect(() => {
    if (!inFlight) return;
    const warn = e => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [inFlight]);

  // One in-flight save per metric (Edit is disabled meanwhile). Retry resends the same body, so the same op_id.
  const send = async (key, { snap, body }) => {
    const settle = patch => setPending(p => (p[key]?.body.op_id === body.op_id ? patch(p) : p)); // ignore stale replies
    const fail = (state, msg) => settle(p => ({ ...p, [key]: { snap, body, state, msg } }));
    setPending(p => ({ ...p, [key]: { snap, body, state: 'saving' } }));
    store(key, { snap, body });
    let reply;
    try {
      reply = await save(body);
    } catch (e) {
      // Timeout or network error: the save may have landed. Retry with the same op_id finds out.
      return fail(
        'failed',
        `Couldn't save ${snap.name}. Your edits are kept. (${e.status ? e.message : 'No answer from the server; Retry is safe.'})`,
      );
    }
    const { data: out, ms } = reply;
    const r = outcome(out, snap, user);
    if (r.failed) return fail(r.failed, r.msg);
    onSaved(key, snap, r.saved);
    settle(p => without(p, key));
    store(key, null);
    if (r.wrote) setJustSaved(j => ({ ...j, [key]: { rev: revOf(out), ms } }));
    else flash(`No changes · ${ms} ms`);
    if (out.warnings?.length) flash(out.warnings.join(' '));
  };

  return {
    pending,
    justSaved,
    send,
    // Saves a closed tab left unconfirmed come back as failed, ready to Retry with the same op_id.
    restore: setPending,
    // Reopening a metric for editing clears its save banner and pill.
    dismiss: key => {
      setPending(p => without(p, key));
      setJustSaved(j => without(j, key));
    },
    discard: key => store(key, null),
  };
}
