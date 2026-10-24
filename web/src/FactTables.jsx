// The Fact tables screen (rail → Fact tables, UX-04): browse, create and edit the registry PIs point at.
// Saves use the metric save machinery (optimistic, Retry with the same op_id, closed-tab restore).
import { useEffect, useState } from 'react';
import './FactTables.css';
import { getFactTable, listFactTables, saveFactTable } from './api.js';
import { readStored, restoredBaseline, useMetricSave } from './metricSave.js';
import { FACT } from './sample.js';

// Every field the save writes (services.FACT_EDITABLE). All are sent, so fields the form doesn't show keep their values.
export const FIELDS = [
  'display_name',
  'description',
  'disambig',
  'gotchas',
  'required_filter',
  'grain',
  'primary_key',
  'time_dimension',
  'department',
  'status',
];
// The form and read view, in order: [field, label, placeholder, rows (1 = single line)].
const FORM = [
  ['description', 'Definition', 'What is in this table?', 2],
  ['disambig', 'When to use', 'When to use this table instead of a similar one.', 2],
  ['grain', 'Grain', 'e.g. One row per ACCOUNTID per DATE_CST per MRR_TYPE', 1],
  ['primary_key', 'Key', 'The columns that enforce the grain, e.g. ACCOUNTID, DATE_CST, MRR_TYPE', 1],
  ['time_dimension', 'Time field', 'e.g. DATE_CST', 1],
  ['required_filter', 'Required filters', 'Filters every query must apply, e.g. EXISTS_IN_FACT_DAILY_MRR_TIERS = 1', 2],
  ['gotchas', 'Gotchas', 'How you get a wrong number from it.', 3],
];
const MONO = ['primary_key', 'time_dimension']; // column names
const keyOf = name => 't:' + name;
const blank = Object.fromEntries(FIELDS.map(f => [f, '']));

// An API row (lower-case keys) → the screen's shape. Blank fields are '' so inputs stay controlled.
export const fromRow = r => ({
  ...blank,
  ...Object.fromEntries(FIELDS.map(f => [f, r[f] ?? ''])),
  key: keyOf(r.table_name),
  name: r.table_name,
  live: true,
  rev: r.revision_no,
  source: r.source,
  author: r.original_author || '—',
  updatedBy: r.updated_by,
});

const sampleTables = () =>
  Object.entries(FACT).map(([name, grain]) => ({
    ...blank,
    grain,
    status: 'active',
    key: keyOf(name),
    name,
    live: false,
    rev: 1,
    source: 'sample',
    author: '—',
    updatedBy: '—',
  }));

// The request for saving draft `t`; no saved baseline = create. A new op_id per save; Retry reuses it.
export const saveBody = (t, orig) => ({
  op_id: crypto.randomUUID(),
  table: { table_name: t.name, expected_revision: orig ? orig.rev : null, fields: Object.fromEntries(FIELDS.map(f => [f, t[f]])) },
});

export const changedFields = (t, orig) => FIELDS.filter(f => (orig ? t[f] !== orig[f] : t[f] && f !== 'status'));

export const matchesTable = (t, q) =>
  !q || [t.name, t.display_name, t.description, t.grain].join(' ').toLowerCase().includes(q.trim().toLowerCase());

const split = name => {
  const parts = name.split('.');
  return { schema: parts.slice(0, -1).join('.'), table: parts.at(-1) };
};

export default function FactTables({ user, flash }) {
  const [tables, setTables] = useState([]); // drafts, as shown
  const [saved, setSaved] = useState([]); // last saved revision of each
  const [sel, setSel] = useState(null);
  const [q, setQ] = useState('');
  const [editing, setEditing] = useState(false);
  const [live, setLive] = useState({ state: 'loading' });
  const [error, setError] = useState('');

  const replace = (list, nt) => list.map(x => (x.key === nt.key ? nt : x));
  // Replace the draft only if it is still the submitted snapshot — never mark newer edits saved.
  const onSaved = (key, snap, nt) => {
    const done = { ...nt, isNew: false };
    setTables(d => d.map(x => (x.key === key && x === snap ? done : x)));
    setSaved(s => (s.some(x => x.key === key) ? replace(s, done) : [...s, done]));
  };
  const { pending, justSaved, send, restore, dismiss, discard } = useMetricSave({ user, onSaved, flash, save: saveFactTable });

  useEffect(() => {
    listFactTables()
      .then(({ data: rows, ms }) => {
        const list = rows.map(fromRow);
        // Saves a closed tab left unconfirmed come back as drafts, ready to Retry with the same op_id.
        const stored = Object.entries(readStored()).filter(([k]) => k.startsWith('t:'));
        const restored = Object.fromEntries(
          stored.map(([k, v]) => [
            k,
            { ...v, state: 'failed', msg: `Couldn't confirm the save of ${v.snap.name} before the page closed. Your edits are kept.` },
          ]),
        );
        const drafts = list.map(t => (restored[t.key] ? restored[t.key].snap : t));
        const creates = stored.filter(([k]) => !list.some(t => t.key === k)).map(([, v]) => v.snap);
        setTables([...creates, ...drafts]);
        setSaved(list.map(t => restoredBaseline(t, restored[t.key])));
        setSel([...creates, ...drafts][0]?.key ?? null);
        restore(restored);
        setLive({ state: 'ok', n: list.length, ms });
      })
      .catch(e => {
        const s = sampleTables();
        setTables(s);
        setSaved(s);
        setSel(s[0].key);
        setLive({ state: 'error', msg: e.message });
      });
  }, [restore]); // restore is setState: stable, so this runs once

  const t = tables.find(x => x.key === sel);
  const orig = saved.find(x => x.key === sel);
  const pend = t && pending[t.key];
  const dirty = t ? changedFields(t, orig) : [];
  const setT = patch => setTables(d => d.map(x => (x.key === sel ? { ...x, ...patch } : x)));
  const changed = f => (t && (orig ? t[f] !== orig[f] : false) ? ' changed' : '');

  // A fresh baseline on open: its revision is what the save is checked against.
  const reload = k => {
    const x = tables.find(y => y.key === k);
    getFactTable(x.name)
      .then(({ data }) => {
        const nt = fromRow(data);
        setTables(d => replace(d, nt));
        setSaved(s => replace(s, nt));
      })
      .catch(e => setError(`Couldn't load ${x.name}: ${e.message}`));
  };
  const pick = k => {
    setSel(k);
    setEditing(false);
    setError('');
    const x = tables.find(y => y.key === k);
    if (x.live && !x.isNew && !pending[k]) reload(k); // a refresh would overwrite an unconfirmed draft
  };
  const startNew = () => {
    const nt = { ...blank, status: 'active', key: 'new', name: '', isNew: true, live: live.state === 'ok', rev: null, source: 'sme' };
    setTables(d => [nt, ...d.filter(x => x.key !== 'new')]);
    setSel('new');
    setEditing(true);
    setError('');
  };
  const openDraft = k => {
    dismiss(k);
    setSel(k);
    setEditing(true);
    setError('');
  };
  // After a conflict: drop my draft and show what was saved meanwhile.
  const discardDraft = k => {
    dismiss(k);
    discard(k);
    const o = saved.find(x => x.key === k);
    setTables(d => (o ? replace(d, o) : d.filter(x => x.key !== k)));
    if (o?.live) reload(k);
    else if (!o) setSel(saved[0]?.key ?? null);
  };
  const cancel = () => {
    discard(sel);
    setEditing(false);
    setError('');
    if (orig) return setTables(d => replace(d, orig));
    setTables(d => d.filter(x => x.key !== sel));
    setSel(saved[0]?.key ?? null);
  };

  const save = () => {
    let snap = t;
    if (t.isNew) {
      // The server stores names upper case (AC.SCHEMA.TABLE); key the draft the same way.
      const name = t.name.trim().toUpperCase();
      if (saved.some(x => x.key === keyOf(name))) return setError(`${name} is already registered — open it from the list instead.`);
      snap = { ...t, name, key: keyOf(name) };
      if (t.key !== snap.key) discard(t.key); // a failed create renamed in its draft: drop the old key's stored copy
      setTables(d => d.map(x => (x.key === t.key ? snap : x)));
      setSel(snap.key);
    }
    setEditing(false);
    setError('');
    if (!snap.live) {
      onSaved(snap.key, snap, { ...snap, rev: (snap.rev || 0) + 1 });
      return flash(`Saved ${snap.name} (sample, not persisted)`);
    }
    // Optimistic: read mode with the submitted values now; "Saved" only once the server commits.
    send(snap.key, { snap, body: saveBody(snap, orig), baseline: orig });
  };

  const visible = tables.filter(x => matchesTable(x, q));
  const nActive = saved.filter(x => x.status === 'active').length;
  const label = f => FORM.find(([k]) => k === f)?.[1].toLowerCase() || f.replace('_', ' ');

  return (
    <div className="ft">
      <aside className="ftlist" aria-label="Fact tables">
        <div className="exhead">
          <h2>Fact tables</h2>
          <input className="search" placeholder="Search names, definitions, grain" value={q} onChange={e => setQ(e.target.value)} />
          <span className="ftcount">
            {live.state === 'loading'
              ? 'Loading…'
              : live.state === 'error'
                ? `Sample data — couldn't reach the API (${live.msg})`
                : `${nActive} active · ${saved.length - nActive} retired · ${live.ms} ms`}
          </span>
          <button className="btn" onClick={startNew} disabled={editing}>
            + New fact table
          </button>
        </div>
        <div className="tree">
          {visible.map(x => {
            const { schema, table } = split(x.name || 'New fact table');
            return (
              <button
                key={x.key}
                className={'ftitem' + (x.key === sel ? ' on' : '') + (x.status === 'retired' ? ' retired' : '')}
                onClick={() => pick(x.key)}
                disabled={editing && x.key !== sel}
              >
                <span className="nm">{x.display_name || table}</span>
                <span className="sub">
                  {schema}
                  {x.grain ? ` · ${x.grain}` : ''}
                </span>
              </button>
            );
          })}
          {!visible.length && live.state !== 'loading' && (
            <div className="empty ftempty">{q ? `No fact tables match “${q}”.` : 'No fact tables registered yet.'}</div>
          )}
        </div>
      </aside>

      <div className="ftdetail">
        {t ? (
          <div className="page">
            {Object.entries(pending)
              .filter(([k, p]) => k.startsWith('t:') && p.state !== 'saving')
              .map(([k, p]) => (
                <div key={k} className="error savefail" role="alert">
                  <span>{p.msg}</span>
                  {p.state === 'failed' && (
                    <button className="btn" onClick={() => send(k, p)}>
                      Retry
                    </button>
                  )}
                  <button className="btn" onClick={() => openDraft(k)}>
                    Open my draft
                  </button>
                  {p.state === 'conflict' && (
                    <button className="btn ghost" onClick={() => discardDraft(k)}>
                      Discard my draft
                    </button>
                  )}
                </div>
              ))}
            <div className="crumbs">Fact tables / {t.name ? split(t.name).schema : 'New'}</div>
            <div className="title">
              <h1 className="fttitle">{t.isNew && editing ? 'New fact table' : t.display_name || split(t.name).table}</h1>
              {t.isNew && !editing && <span className="badge warn">Not saved</span>}
              {!t.isNew && (
                <span className={'badge ' + (t.status === 'active' ? 'ok' : 'plain')}>{t.status === 'active' ? 'Active' : 'Retired'}</span>
              )}
              {pend?.state === 'saving' && (
                <span className="saving" role="status">
                  Saving
                  <span className="dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                </span>
              )}
              {justSaved[t.key] && (
                <span className="savedpill" role="status">
                  <span className="check">✓</span> Saved · rev {justSaved[t.key].rev} · {(justSaved[t.key].ms / 1000).toFixed(1)} s
                </span>
              )}
              {!editing && (
                <span className="titleactions">
                  <button className="btn primary" onClick={() => openDraft(t.key)} disabled={pend?.state === 'saving'}>
                    Edit
                  </button>
                </span>
              )}
            </div>
            {!t.isNew && (
              <div className="meta">
                <span className="ftname">{t.name}</span>
                <span>
                  Revision <b>{t.rev}</b>
                </span>
                <span>
                  Source <b>{t.source}</b>
                </span>
                {t.department && (
                  <span>
                    Department <b>{t.department}</b>
                  </span>
                )}
                <span>
                  Last saved by <b>{t.updatedBy}</b>
                </span>
              </div>
            )}
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}

            <section className="section">
              {editing ? (
                <div className="ftform">
                  {t.isNew ? (
                    <div className="field">
                      <label htmlFor="ft-name">Table</label>
                      <input
                        id="ft-name"
                        className="input mono"
                        value={t.name}
                        placeholder="AC.SCHEMA.TABLE"
                        autoFocus
                        onChange={e => setT({ name: e.target.value })}
                      />
                      <span className="hint">The full three-part name the SQL uses. It can't be changed after saving.</span>
                    </div>
                  ) : null}
                  <div className="grid2">
                    <div className="field">
                      <label htmlFor="ft-display_name">Display name</label>
                      <input
                        id="ft-display_name"
                        className={'input' + changed('display_name')}
                        value={t.display_name}
                        placeholder="e.g. MRR Rollup"
                        onChange={e => setT({ display_name: e.target.value })}
                      />
                    </div>
                    {!t.isNew && (
                      <div className="field">
                        <label htmlFor="ft-status">Status</label>
                        <select
                          id="ft-status"
                          className={'select' + changed('status')}
                          value={t.status}
                          onChange={e => setT({ status: e.target.value })}
                        >
                          <option value="active">Active</option>
                          <option value="retired">Retired — PIs shouldn't use it</option>
                        </select>
                      </div>
                    )}
                  </div>
                  {FORM.map(([f, lbl, ph, rows]) => (
                    <div className="field" key={f}>
                      <label htmlFor={'ft-' + f}>{lbl}</label>
                      {rows === 1 ? (
                        <input
                          id={'ft-' + f}
                          className={'input' + (MONO.includes(f) ? ' mono' : '') + changed(f)}
                          value={t[f]}
                          placeholder={ph}
                          onChange={e => setT({ [f]: e.target.value })}
                        />
                      ) : (
                        <textarea
                          id={'ft-' + f}
                          className={'ta' + changed(f)}
                          rows={rows}
                          value={t[f]}
                          placeholder={ph}
                          onChange={e => setT({ [f]: e.target.value })}
                        />
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <dl className="ftread">
                  {FORM.map(([f, lbl]) => (
                    <div key={f}>
                      <dt>{lbl}</dt>
                      <dd className={t[f] && MONO.includes(f) ? 'mono' : ''}>{t[f] || <span className="muted">Not written yet.</span>}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>
          </div>
        ) : (
          <div className="page">
            <div className="empty">{live.state === 'loading' ? 'Loading fact tables…' : 'Pick a fact table, or add one.'}</div>
          </div>
        )}
        {t && editing && (
          <div className="savebar">
            <span className="what">
              {dirty.length ? (
                <>
                  {t.isNew ? 'New fact table' : 'Editing'} · unsaved changes in <b>{dirty.map(label).join(', ')}</b>
                </>
              ) : (
                <>{t.isNew ? 'New fact table · not saved yet' : 'Editing · no changes yet'}</>
              )}
            </span>
            <button className="btn ghost" onClick={cancel}>
              Cancel
            </button>
            <button className="btn primary" onClick={save} disabled={t.isNew && !t.name.trim()}>
              {t.isNew ? 'Add fact table' : 'Save changes'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
