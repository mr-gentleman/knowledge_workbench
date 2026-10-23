import React, { useEffect, useState } from 'react';
import SqlEditor from './SqlEditor.jsx';
import { FACT, SAMPLE_CANON, pi } from './sample.js';
import { getCandidate, getMe, listCandidates, saveMetric } from './api.js';

const DEPT_LABEL = d => (d ? d[0].toUpperCase() + d.slice(1) : 'Unassigned');

// A live metric_candidate row → the editor's shape. Detail fields arrive on open (getCandidate).
const fromRow = r => ({
  key: `c${r.CANDIDATE_ID}`, cid: r.CANDIDATE_ID, id: `C-${r.CANDIDATE_ID}`, kind: 'cand', live: true,
  dept: DEPT_LABEL(r.DEPARTMENT), deptRaw: r.DEPARTMENT, name: r.FULL_NAME, category: r.CATEGORY || '',
  status: r.STATUS, rev: r.REVISION_NO, source: r.SOURCE, author: r.ORIGINAL_AUTHOR || '—',
  updatedBy: r.UPDATED_BY, description: '', disambig: '', pis: [], loaded: false,
});

const Icon = {
  metrics: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 19V9M10 19V5M16 19v-7M22 19H2" /></svg>,
  tables: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" /></svg>,
  queue: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 6h16M4 12h10M4 18h7" /><circle cx="19" cy="16" r="3" /></svg>,
};

function piStatus(p) {
  if (p.status === 'bad') return <span className="badge bad">✗ Failed · rev {p.validatedRev}</span>;
  if (p.status === 'stale' || p.rev > p.validatedRev) return <span className="badge warn">Edited since check</span>;
  return <span className="badge ok">✓ Passed · rev {p.validatedRev}</span>;
}

function PiRow({ p, open, onToggle, onChange, onDefault, onRemove, showDefault, orig, editing }) {
  const grain = FACT[p.table] || '—';
  const [check, setCheck] = useState(null);
  const short = p.table.split('.').slice(-1)[0];
  const validate = () => {
    setCheck({ state: 'run' });
    setTimeout(() => {
      const okish = /\bFROM\b/i.test(p.sql);
      onChange({ status: okish ? 'ok' : 'bad', validatedRev: p.rev, msg: okish ? '' : 'No FROM clause' });
      setCheck({ state: okish ? 'ok' : 'bad', ms: 900 + Math.round(Math.random() * 700) });
    }, 650);
  };
  const changed = k => (orig && orig[k] !== p[k] ? ' changed' : '');
  return (
    <div className={'pi' + (open ? ' open' : '')}>
      <button className="pirow" onClick={onToggle} aria-expanded={open}>
        <span className={'caret' + (open ? ' open' : '')}>▸</span>
        <span className="grain">{grain}</span><span className="tbl">{short}</span>
        <span className="right">{p.isDefault && showDefault ? <span className="badge plain">Default</span> : null}{piStatus(p)}</span>
      </button>
      {open && !editing && (
        <div className="pibody">
          {p.disambig ? <p className="readtext">{p.disambig}</p> : null}
          <pre className="sqlread">{p.sql}</pre>
          <span className="served">{p.served ? `Agent uses rev ${p.served}` : 'Not served yet'} · Source: {p.source === 'sme' ? 'SME' : 'Auto-generated'}</span>
        </div>
      )}
      {open && editing && (
        <div className="pibody">
          <SqlEditor id={'sql-' + p.id} fileName={short + '.sql'} value={p.sql}
            onChange={v => onChange({ sql: v, rev: orig && v !== orig.sql ? orig.rev + 1 : p.rev, status: orig && v !== orig.sql ? 'stale' : p.status })} />
          <div className="edbar">
            <button className="btn" onClick={validate} disabled={check && check.state === 'run'}>{check && check.state === 'run' ? 'Running…' : 'Validate SQL'}</button>
            {check && check.state === 'ok' ? <span className="valmsg ok">Ran in {(check.ms / 1000).toFixed(1)}s · 1 row · passed on rev {p.rev}</span>
              : (check && check.state === 'bad') || p.status === 'bad' ? <span className="valmsg bad">{p.msg || 'Query failed'}. Fix the SQL and validate again.</span>
                : <span className="valmsg">Checks that it runs. It doesn't prove the number is right.</span>}
          </div>
          <div className="grid2">
            <div className="field">
              <label htmlFor={'tbl-' + p.id}>Fact table</label>
              <select id={'tbl-' + p.id} className={'select' + changed('table')} value={p.table} onChange={e => onChange({ table: e.target.value })}>
                {Object.keys(FACT).map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <span className="hint">Grain comes from the fact table: {grain}.</span>
            </div>
            <div className="field">
              <label htmlFor={'dis-' + p.id}>When to use</label>
              <textarea id={'dis-' + p.id} className={'ta' + changed('disambig')} rows="2" value={p.disambig}
                placeholder={showDefault ? 'Required when a metric has more than one implementation' : 'Optional with one implementation'}
                onChange={e => onChange({ disambig: e.target.value })} />
            </div>
          </div>
          <div className="edbar">
            {showDefault ? <label className="radio"><input type="radio" name="default-pi" checked={p.isDefault} onChange={onDefault} /> Default implementation</label> : null}
            <span className="served">{p.served ? <>Agent uses <b>rev {p.served}</b>{p.rev !== p.served ? ` · you're editing rev ${p.rev}` : null}</> : 'Not served yet'}</span>
            <button className="btn ghost" style={{ marginLeft: 'auto' }} onClick={onRemove}>Remove implementation</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(SAMPLE_CANON);
  const [saved, setSaved] = useState(SAMPLE_CANON);
  const [sel, setSel] = useState('nrr');
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [openDept, setOpenDept] = useState({ Finance: true });
  const [openPi, setOpenPi] = useState(1);
  const [toast, setToast] = useState('');
  const [nav, setNav] = useState('metrics');
  const [me, setMe] = useState(null);
  const [live, setLive] = useState({ state: 'loading' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false); // DEC-020: read mode until Edit; one session per page

  const flash = msg => { setToast(msg); setTimeout(() => setToast(''), 2600); };

  useEffect(() => {
    getMe().then(r => setMe(r.data)).catch(e => setMe({ error: e.message }));
    listCandidates()
      .then(({ data: rows, ms }) => {
        // DEC-011: closed candidates are hidden by default.
        const cands = rows.filter(r => r.STATUS === 'open').map(fromRow);
        setData(d => [...d, ...cands]); setSaved(s => [...s, ...cands]);
        setLive({ state: 'ok', n: cands.length, ms });
      })
      .catch(e => setLive({ state: 'error', msg: e.message }));
  }, []);

  const m = data.find(x => x.key === sel);
  const orig = saved.find(x => x.key === sel);
  const visible = data.filter(x => (filter === 'all' || x.kind === filter)
    && (!q || (x.name + ' ' + x.description + ' ' + x.disambig).toLowerCase().includes(q.toLowerCase())));
  const depts = [...new Set(data.map(x => x.dept))];

  const replace = (list, nm) => list.map(x => (x.key === nm.key ? nm : x));
  const setM = patch => setData(d => d.map(x => (x.key === sel ? { ...x, ...patch } : x)));
  const setPi = (id, patch) => setM({ pis: m.pis.map(p => (p.id === id ? { ...p, ...patch } : p)) });

  const dirty = [];
  if (m && orig) {
    if (['name', 'category', 'description', 'disambig'].some(k => m[k] !== orig[k])) dirty.push('definition');
    m.pis.forEach((p, i) => {
      const o = orig.pis.find(x => x.id === p.id);
      if (!o || o.sql !== p.sql || o.table !== p.table || o.disambig !== p.disambig || o.isDefault !== p.isDefault) dirty.push('implementation ' + (i + 1));
    });
    const removed = orig.pis.filter(o => !m.pis.some(p => p.id === o.id)).length;
    if (removed) dirty.push(`${removed} removed implementation${removed > 1 ? 's' : ''}`);
  }
  const changed = k => (orig && m[k] !== orig[k] ? ' changed' : '');

  // Opening a live candidate loads a fresh baseline (its revision is what the save is checked against).
  const pick = k => {
    setSel(k); setError(''); setEditing(false);
    const t = data.find(x => x.key === k);
    setOpenPi(t.pis[0]?.id ?? null);
    if (!t.live) return;
    getCandidate(t.cid).then(({ data: r, ms }) => {
      const nm = { ...fromRow(r), description: r.DESCRIPTION || '', disambig: r.DISAMBIG || '', loaded: true, loadMs: ms };
      setData(d => replace(d, nm)); setSaved(s => replace(s, nm));
    }).catch(e => setError(`Couldn't load ${t.id}: ${e.message}`));
  };

  const save = async () => {
    if (!m.live) {
      const nm = { ...m, rev: m.rev + 1 };
      setData(d => replace(d, nm)); setSaved(s => replace(s, nm)); setEditing(false);
      return flash(`Saved ${m.name} · revision ${nm.rev} (sample, not persisted)`);
    }
    setBusy(true); setError('');
    try {
      const fields = { full_name: m.name, description: m.description, disambig: m.disambig, department: m.deptRaw, category: m.category };
      const { data: out, ms } = await saveMetric({ id: m.cid, expected_revision: orig.rev, fields });
      // conflict / invalid: nothing was written; stay in Edit with the draft intact.
      if (out.status !== 'saved' && out.status !== 'no_change') { setError(out.message); return; }
      const nm = { ...m, rev: out.candidate_revision, updatedBy: out.status === 'saved' ? me?.user : m.updatedBy };
      setData(d => replace(d, nm)); setSaved(s => replace(s, nm)); setEditing(false);
      flash(out.status === 'saved' ? `Saved ${m.id} · revision ${out.candidate_revision} · ${ms} ms` : `No changes · ${ms} ms`);
      if (out.warnings?.length) setError(out.warnings.join(' '));
    } catch (e) {
      setError(`Save failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };
  const cancel = () => { setData(d => d.map(x => (x.key === sel ? orig : x))); setEditing(false); setError(''); };
  const addPi = () => {
    const id = Date.now();
    setM({ pis: [...m.pis, pi(id, 'AC.conformed_dimensions.cohort_account_monthly_consolidation', '-- New implementation\nSELECT\n    \nFROM AC.\nWHERE ', { isDefault: m.pis.length === 0, validatedRev: 0, rev: 1, served: null, status: 'stale', source: 'sme' })] });
    setOpenPi(id);
  };
  const missing = m && m.kind === 'cand'
    ? [!m.pis.length && 'at least one implementation that passes validation', m.pis.length && !m.pis.some(p => p.status === 'ok') && 'a passing implementation'].filter(Boolean)
    : [];
  // PIs on live candidates aren't wired in the spike — editing them would look saved when it isn't.
  const piDirtyLive = m?.live && dirty.some(d => d.startsWith('implementation'));

  return (
    <div className="app">
      <nav className="rail" aria-label="Sections">
        <div className="logo" title="Knowledge Workbench">Kw</div>
        {[['metrics', 'Metrics'], ['tables', 'Fact tables'], ['queue', 'Queue']].map(([k, l]) => (
          <button key={k} className={'railbtn' + (nav === k ? ' on' : '')} onClick={() => setNav(k)}>{Icon[k]}{l}</button>
        ))}
      </nav>
      <aside className="explorer" aria-label="Metric explorer">
        <div className="exhead">
          <h2>Metrics</h2>
          <input className="search" id="search" placeholder="Search names, definitions, when-to-use" value={q} onChange={e => setQ(e.target.value)} />
          <div className="chips">{[['all', 'All'], ['canon', 'Canon'], ['cand', 'Candidates']].map(([k, l]) => (
            <button key={k} className={'chip' + (filter === k ? ' on' : '')} onClick={() => setFilter(k)}>{l}</button>
          ))}</div>
        </div>
        <div className="tree">
          {depts.map(dp => {
            const items = visible.filter(x => x.dept === dp);
            const open = openDept[dp] || !!q;
            return (
              <div key={dp}>
                <button className="folder" onClick={() => setOpenDept(o => ({ ...o, [dp]: !o[dp] }))} aria-expanded={open}>
                  <span className={'caret' + (open ? ' open' : '')}>▸</span>{dp}<span className="count">{items.length}</span>
                </button>
                {open && items.map(x => (
                  <button key={x.key} className={'item' + (x.key === sel ? ' on' : '')} onClick={() => pick(x.key)}>
                    <span className={'dot ' + x.kind} /><span className="nm">{x.name}</span>{x.live && <span className="live">live</span>}
                  </button>
                ))}
              </div>
            );
          })}
          {!visible.length && <div className="empty" style={{ padding: '20px 8px' }}>No metrics match “{q}”.</div>}
        </div>
      </aside>
      <main className="main">
        <div className={'banner' + (live.state === 'ok' ? ' live' : '')}>
          <span>{live.state === 'ok' ? `Candidates are live from AI_PLATFORM.WORKBENCH (${live.n} open, ${live.ms} ms). Canon is sample data.`
            : live.state === 'error' ? `Couldn't reach the API: ${live.msg}. Showing sample data only.` : 'Loading candidates…'}</span>
          <span className="r">{me?.user ? `signed in as ${me.user}` : me?.error ? `identity: ${me.error}` : ''}</span>
        </div>
        {nav !== 'metrics' ? (
          <div className="page"><div className="empty">{nav === 'tables' ? 'Fact tables' : 'Review queue'} would open here. The spike only covers the metric editor.</div></div>
        ) : m && (
          <div className="page">
            <div className="crumbs">{m.dept} / {m.category || 'Uncategorized'}</div>
            <div className="title">
              <h1>{m.name}</h1>{m.kind === 'canon' ? <span className="badge canon">Canon · #{m.id}</span> : <span className="badge cand">Candidate · {m.id}</span>}
              {!editing && (
                <span className="titleactions">
                  {m.kind === 'cand' ? <button className="btn" disabled={missing.length > 0}>Promote to canon</button> : null}
                  <button className="btn primary" onClick={() => setEditing(true)} disabled={m.live && !m.loaded}>Edit</button>
                </span>
              )}
            </div>
            <div className="meta">
              <span>Revision <b>{m.rev}</b></span><span>Source <b>{m.source}</b></span><span>Original author <b>{m.author}</b></span>
              {m.live ? <span>Last saved by <b>{m.updatedBy}</b></span> : <span>Slug <b>{m.key}</b></span>}
              {m.loadMs ? <span>Loaded in <b>{m.loadMs} ms</b></span> : null}
            </div>
            {error && <div className="error" role="alert">{error}</div>}
            {missing.length ? <div className="missing">Can't promote to canon yet. Still needs {missing.join(' and ')}.</div> : null}

            <section className="section">
              <div className="sechead"><h3>Definition</h3><div className="rule" /></div>
              {editing ? (<>
                <div className="grid2">
                  <div className="field"><label htmlFor="f-name">Full name</label><input id="f-name" className={'input' + changed('name')} value={m.name} onChange={e => setM({ name: e.target.value })} /></div>
                  <div className="field"><label htmlFor="f-cat">Category</label><input id="f-cat" className={'input' + changed('category')} value={m.category} onChange={e => setM({ category: e.target.value })} /></div>
                </div>
                <div className="field"><label htmlFor="f-desc">Description</label><textarea id="f-desc" className={'ta' + changed('description')} rows="2" value={m.description} onChange={e => setM({ description: e.target.value })} /></div>
                <div className="field"><label htmlFor="f-dis">When to use · how it differs</label><textarea id="f-dis" className={'ta' + changed('disambig')} rows="2" value={m.disambig} placeholder="e.g. Use for revenue retention including expansion; for logo counts see Logo Churn Count." onChange={e => setM({ disambig: e.target.value })} /></div>
              </>) : (<>
                <div className="field"><label>Description</label><p className="readtext">{m.description || <span className="muted">No description yet.</span>}</p></div>
                <div className="field"><label>When to use · how it differs</label><p className="readtext">{m.disambig || <span className="muted">Not written yet.</span>}</p></div>
              </>)}
            </section>

            <section className="section">
              <div className="sechead"><h3>Implementations · {m.pis.length}</h3><div className="rule" /></div>
              <div className="pis">
                {m.pis.map(p => (
                  <PiRow key={p.id} p={p} orig={orig.pis.find(o => o.id === p.id)} open={openPi === p.id} showDefault={m.pis.length > 1} editing={editing}
                    onToggle={() => setOpenPi(openPi === p.id ? null : p.id)} onChange={patch => setPi(p.id, patch)}
                    onRemove={() => setM({ pis: m.pis.filter(x => x.id !== p.id) })}
                    onDefault={() => setM({ pis: m.pis.map(x => ({ ...x, isDefault: x.id === p.id })) })} />
                ))}
                {!m.pis.length && <div className="empty" style={{ padding: '16px 14px' }}>No implementations yet.{editing ? ' Add the SQL that computes this metric.' : ''}</div>}
                {editing && <button className="addpi" onClick={addPi}>+ Add implementation</button>}
              </div>
            </section>
          </div>
        )}
        {nav === 'metrics' && m && editing && (
          <div className="savebar">
            <span className="what">{piDirtyLive ? 'The spike UI saves only the definition of a live candidate; the API accepts implementations, but this page does not send them yet.'
              : dirty.length ? <>Editing · unsaved changes in <b>{dirty.join(', ')}</b></> : 'Editing · no changes yet'}</span>
            <button className="btn ghost" onClick={cancel} disabled={busy}>Cancel</button>
            <button className="btn primary" onClick={save} disabled={busy || piDirtyLive}>{busy ? 'Saving…' : 'Save changes'}</button>
          </div>
        )}
      </main>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
