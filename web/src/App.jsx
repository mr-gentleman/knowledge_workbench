import { useEffect, useState } from 'react';
import DefinitionSection from './DefinitionSection.jsx';
import Explorer from './Explorer.jsx';
import FactTables from './FactTables.jsx';
import PiSection from './PiSection.jsx';
import SearchBox, { matches } from './SearchBox.jsx';
import { SAMPLE_CANON } from './sample.js';
import { getCandidate, getMe, listCandidates } from './api.js';
import { readStored, saveBody, useMetricSave } from './metricSave.js';

const DEPT_LABEL = d => (d ? d[0].toUpperCase() + d.slice(1) : 'Unassigned');

// A live metric_candidate row → the editor's shape. Detail fields arrive on open (getCandidate).
const fromRow = r => ({
  key: `c${r.CANDIDATE_ID}`,
  cid: r.CANDIDATE_ID,
  id: `C-${r.CANDIDATE_ID}`,
  kind: 'cand',
  live: true,
  dept: DEPT_LABEL(r.DEPARTMENT),
  deptRaw: r.DEPARTMENT,
  name: r.FULL_NAME,
  category: r.CATEGORY || '',
  status: r.STATUS,
  rev: r.REVISION_NO,
  source: r.SOURCE,
  author: r.ORIGINAL_AUTHOR || '—',
  updatedBy: r.UPDATED_BY,
  description: '',
  disambig: '',
  pis: [],
  loaded: false,
});

const Icon = {
  metrics: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
    </svg>
  ),
  tables: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M9 10v10" />
    </svg>
  ),
  queue: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M4 6h16M4 12h10M4 18h7" />
      <circle cx="19" cy="16" r="3" />
    </svg>
  ),
};

export default function App() {
  const [data, setData] = useState(SAMPLE_CANON);
  const [saved, setSaved] = useState(SAMPLE_CANON);
  const [sel, setSel] = useState('nrr');
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [openPi, setOpenPi] = useState(1);
  const [toast, setToast] = useState('');
  const [nav, setNav] = useState('metrics');
  const [me, setMe] = useState(null);
  const [live, setLive] = useState({ state: 'loading' });
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false); // DEC-020: read mode until Edit; one session per page

  const flash = msg => {
    setToast(msg);
    setTimeout(() => setToast(''), 2600);
  };
  const replace = (list, nm) => list.map(x => (x.key === nm.key ? nm : x));
  // Replace the draft only if it is still the submitted snapshot — never mark newer edits saved.
  const onSaved = (key, snap, nm) => {
    setData(d => d.map(x => (x.key === key && x === snap ? nm : x)));
    setSaved(s => replace(s, nm));
  };
  const { pending, justSaved, send, restore, dismiss, discard } = useMetricSave({ user: me?.user, onSaved, flash });
  useEffect(() => {
    getMe()
      .then(r => setMe(r.data))
      .catch(e => setMe({ error: e.message }));
    listCandidates()
      .then(({ data: rows, ms }) => {
        // DEC-011: closed candidates are hidden by default.
        const cands = rows.filter(r => r.STATUS === 'open').map(fromRow);
        // A save left unconfirmed by a closed tab comes back as its draft, ready to Retry with the same op_id.
        const stored = readStored(),
          restored = {};
        const drafts = cands.map(c => {
          if (!stored[c.key]) return c;
          restored[c.key] = {
            ...stored[c.key],
            state: 'failed',
            msg: `Couldn't confirm the save of ${c.name} before the page closed. Your edits are kept.`,
          };
          return stored[c.key].snap;
        });
        setData(d => [...d, ...drafts]);
        setSaved(s => [...s, ...cands]);
        restore(restored);
        setLive({ state: 'ok', n: cands.length, ms });
      })
      .catch(e => setLive({ state: 'error', msg: e.message }));
  }, [restore]); // restore is setState: stable, so this runs once

  const m = data.find(x => x.key === sel);
  const pend = m && pending[m.key];
  const orig = saved.find(x => x.key === sel);
  const visible = data.filter(x => matches(x, q, filter));
  const depts = [...new Set(data.map(x => x.dept))];

  const setM = patch => setData(d => d.map(x => (x.key === sel ? { ...x, ...patch } : x)));

  const dirty = [];
  if (m && orig) {
    if (['name', 'category', 'description', 'disambig'].some(k => m[k] !== orig[k])) dirty.push('definition');
    m.pis.forEach((p, i) => {
      const o = orig.pis.find(x => x.id === p.id);
      if (!o || o.sql !== p.sql || o.table !== p.table || o.disambig !== p.disambig || o.isDefault !== p.isDefault)
        dirty.push('implementation ' + (i + 1));
    });
    const removed = orig.pis.filter(o => !m.pis.some(p => p.id === o.id)).length;
    if (removed) dirty.push(`${removed} removed implementation${removed > 1 ? 's' : ''}`);
  }
  const changed = k => (orig && m[k] !== orig[k] ? ' changed' : '');

  // Opening a live candidate loads a fresh baseline (its revision is what the save is checked against).
  const pick = k => {
    setSel(k);
    setError('');
    setEditing(false);
    const t = data.find(x => x.key === k);
    setOpenPi(t.pis[0]?.id ?? null);
    if (!t.live || pending[k]) return; // a refresh would overwrite the unconfirmed draft
    getCandidate(t.cid)
      .then(({ data: r, ms }) => {
        const nm = { ...fromRow(r), description: r.DESCRIPTION || '', disambig: r.DISAMBIG || '', loaded: true, loadMs: ms };
        setData(d => replace(d, nm));
        setSaved(s => replace(s, nm));
      })
      .catch(e => setError(`Couldn't load ${t.id}: ${e.message}`));
  };

  const save = async () => {
    if (!m.live) {
      const nm = { ...m, rev: m.rev + 1 };
      setData(d => replace(d, nm));
      setSaved(s => replace(s, nm));
      setEditing(false);
      return flash(`Saved ${m.name} · revision ${nm.rev} (sample, not persisted)`);
    }
    // Optimistic: back to read mode with the submitted values now; "Saved" only once the server commits.
    setEditing(false);
    setError('');
    send(m.key, { snap: m, body: saveBody(m, orig) });
  };
  const openDraft = key => {
    dismiss(key);
    setNav('metrics');
    setSel(key);
    setEditing(true);
    setError('');
  };
  const cancel = () => {
    setData(d => d.map(x => (x.key === sel ? orig : x)));
    setEditing(false);
    setError('');
    discard(sel);
  };
  const missing =
    m && m.kind === 'cand'
      ? [
          !m.pis.length && 'at least one implementation that passes validation',
          m.pis.length && !m.pis.some(p => p.status === 'ok') && 'a passing implementation',
        ].filter(Boolean)
      : [];
  // PIs on live candidates aren't wired in the spike — editing them would look saved when it isn't.
  const piDirtyLive = m?.live && dirty.some(d => d.startsWith('implementation'));

  return (
    <div className="app">
      <nav className="rail" aria-label="Sections">
        <div className="logo" title="Knowledge Workbench">
          Kw
        </div>
        {[
          ['metrics', 'Metrics'],
          ['tables', 'Fact tables'],
          ['queue', 'Queue'],
        ].map(([k, l]) => (
          <button key={k} className={'railbtn' + (nav === k ? ' on' : '')} onClick={() => setNav(k)}>
            {Icon[k]}
            {l}
          </button>
        ))}
      </nav>
      {nav !== 'tables' && (
        <Explorer
          search={<SearchBox q={q} setQ={setQ} filter={filter} setFilter={setFilter} />}
          visible={visible}
          depts={depts}
          q={q}
          sel={sel}
          pick={pick}
        />
      )}
      <main className={'main' + (nav === 'tables' ? ' wide' : '')}>
        <div className={'banner' + (live.state === 'ok' ? ' live' : '')}>
          <span>
            {live.state === 'ok'
              ? `Candidates are live from AI_PLATFORM.WORKBENCH (${live.n} open, ${live.ms} ms). Canon is sample data.`
              : live.state === 'error'
                ? `Couldn't reach the API: ${live.msg}. Showing sample data only.`
                : 'Loading candidates…'}
          </span>
          <span className="r">{me?.user ? `signed in as ${me.user}` : me?.error ? `identity: ${me.error}` : ''}</span>
        </div>
        {nav === 'tables' ? (
          <FactTables user={me?.user} flash={flash} />
        ) : nav !== 'metrics' ? (
          <div className="page">
            <div className="empty">Review queue would open here. The spike only covers the metric editor.</div>
          </div>
        ) : (
          m && (
            <div className="page">
              <div className="crumbs">
                {m.dept} / {m.category || 'Uncategorized'}
              </div>
              <div className="title">
                <h1>{m.name}</h1>
                {m.kind === 'canon' ? (
                  <span className="badge canon">Canon · #{m.id}</span>
                ) : (
                  <span className="badge cand">Candidate · {m.id}</span>
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
                {justSaved[m.key] && (
                  <span className="savedpill" role="status">
                    <span className="check">✓</span> Saved · rev {justSaved[m.key].rev} · {(justSaved[m.key].ms / 1000).toFixed(1)} s
                  </span>
                )}
                {!editing && (
                  <span className="titleactions">
                    {m.kind === 'cand' ? (
                      <button className="btn" disabled={missing.length > 0 || !!pend}>
                        Promote to canon
                      </button>
                    ) : null}
                    <button
                      className="btn primary"
                      onClick={() => openDraft(m.key)}
                      disabled={(m.live && !m.loaded) || pend?.state === 'saving'}
                    >
                      Edit
                    </button>
                  </span>
                )}
              </div>
              <div className="meta">
                <span>
                  Revision <b>{m.rev}</b>
                </span>
                <span>
                  Source <b>{m.source}</b>
                </span>
                <span>
                  Original author <b>{m.author}</b>
                </span>
                {m.live ? (
                  <span>
                    Last saved by <b>{m.updatedBy}</b>
                  </span>
                ) : (
                  <span>
                    Slug <b>{m.key}</b>
                  </span>
                )}
                {m.loadMs ? (
                  <span>
                    Loaded in <b>{m.loadMs} ms</b>
                  </span>
                ) : null}
              </div>
              {Object.entries(pending)
                .filter(([, p]) => p.state !== 'saving')
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
                  </div>
                ))}
              {error && (
                <div className="error" role="alert">
                  {error}
                </div>
              )}
              {missing.length ? <div className="missing">Can't promote to canon yet. Still needs {missing.join(' and ')}.</div> : null}

              <DefinitionSection m={m} editing={editing} setM={setM} changed={changed} />

              <PiSection m={m} orig={orig} editing={editing} setM={setM} openPi={openPi} setOpenPi={setOpenPi} />
            </div>
          )
        )}
        {nav === 'metrics' && m && editing && (
          <div className="savebar">
            <span className="what">
              {piDirtyLive ? (
                'The spike UI saves only the definition of a live candidate; the API accepts implementations, but this page does not send them yet.'
              ) : dirty.length ? (
                <>
                  Editing · unsaved changes in <b>{dirty.join(', ')}</b>
                </>
              ) : (
                'Editing · no changes yet'
              )}
            </span>
            <button className="btn ghost" onClick={cancel}>
              Cancel
            </button>
            <button className="btn primary" onClick={save} disabled={piDirtyLive}>
              Save changes
            </button>
          </div>
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
