import { useState } from 'react';
import SqlEditor from './SqlEditor.jsx';
import { FACT } from './sample.js';
import { followTable, piChanged, piTitle, runState, sqlTables } from './pis.js';
import './PiSection.css';

const STARTER = '-- New implementation\nSELECT\n    \nFROM AC.\nWHERE ';

// Run check for one PI. It runs the SQL as saved (read-only, on Snowflake), so it's offered only without unsaved edits.
// `check(id, rev)` resolves to the API's CheckOutcome; null on sample data.
function CheckBar({ p, o, check }) {
  const [res, setRes] = useState(null);
  const saved = !piChanged(p, o);
  const run = async () => {
    setRes({ status: 'run' });
    try {
      setRes(await check(p.id, p.rev));
    } catch (e) {
      setRes({ status: 'unavailable', message: `Couldn't run the check: ${e.message}` });
    }
  };
  let msg = <span className="valmsg">Runs the saved SQL read-only. It doesn't prove the number is right.</span>;
  if (!check) msg = <span className="valmsg">Sample data: checks run on live metrics only.</span>;
  else if (!saved) msg = <span className="valmsg">Save first: a check runs the saved version.</span>;
  else if (res?.status === 'run') msg = <span className="valmsg">Running on Snowflake, read-only, up to 30 s…</span>;
  else if (res?.status === 'passed')
    msg = (
      <span className="valmsg ok">
        {res.message} · {res.row_count}
        {res.truncated ? '+' : ''} rows · {(res.ms / 1000).toFixed(1)} s
      </span>
    );
  else if (res?.status === 'failed') msg = <span className="valmsg bad">{`${res.message}: ${res.error}`}</span>;
  else if (res) msg = <span className="valmsg bad">{res.message}</span>;
  else if (runState(p, o).tone === 'bad') msg = <span className="valmsg bad">{p.checkMsg}</span>;
  return (
    <>
      <div className="edbar">
        <button className="btn" onClick={run} disabled={!check || !saved || res?.status === 'run'}>
          {res?.status === 'run' ? 'Running…' : 'Run check'}
        </button>
        {msg}
      </div>
      {saved && res?.status === 'passed' && res.rows.length > 0 && (
        <div className="checkrows">
          <table>
            <thead>
              <tr>
                {res.columns.map(c => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {res.rows.map((r, i) => (
                <tr key={i}>
                  {r.map((v, j) => (
                    <td key={j}>{v ?? 'NULL'}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function PiRow({ p, o, isDefault, several, open, editing, check, onToggle, onChange, onRemove }) {
  const grain = Object.entries(FACT).find(([t]) => t.toLowerCase() === p.table.toLowerCase())?.[1] || '—';
  const reads = sqlTables(p.sql);
  const others = reads.filter(t => t.toLowerCase() !== p.table.toLowerCase());
  const title = piTitle(p, several);
  const short = p.table ? p.table.split('.').pop() : '';
  const status = runState(p, o);
  const needsLabel = editing && several && !p.disambig.trim();
  const changed = k => (o && o[k] !== p[k] ? ' changed' : '');
  return (
    <div className={'pi' + (open ? ' open' : '')}>
      <button className="pirow" onClick={onToggle} aria-expanded={open}>
        <span className={'caret' + (open ? ' open' : '')}>▸</span>
        <span className="grain">{grain}</span>
        <span className="title">{title}</span>
        {short && short !== title ? <span className="tbl">{short}</span> : null}
        <span className="right">
          {isDefault && several ? <span className="badge plain">Default</span> : null}
          {needsLabel ? <span className="badge warn">Add when to use</span> : null}
          <span className={'badge ' + status.tone}>{status.label}</span>
        </span>
      </button>
      {open && !editing && (
        <div className="pibody">
          {p.disambig && p.disambig.trim() !== title ? <p className="readtext">{p.disambig}</p> : null}
          <pre className="sqlread">{p.sql}</pre>
          <CheckBar key={p.rev} p={p} o={o} check={check} />
          <span className="served">
            {p.served ? `Agent uses rev ${p.served}` : 'Not served yet'} · Source: {p.source === 'sme' ? 'SME' : 'Auto-generated'}
          </span>
        </div>
      )}
      {open && editing && (
        <div className="pibody">
          <SqlEditor
            id={'sql-' + p.id}
            fileName={(short || 'new') + '.sql'}
            value={p.sql}
            onChange={v => onChange({ sql: v, table: followTable(p, v) })}
          />
          <CheckBar key={p.rev} p={p} o={o} check={check} />
          <div className="grid2">
            <div className="field">
              <label htmlFor={'tbl-' + p.id}>Fact table</label>
              <input
                id={'tbl-' + p.id}
                className={'input mono' + changed('table')}
                value={p.table}
                list="fact-tables"
                placeholder="Filled in from the SQL: FROM AC.schema.table"
                spellCheck="false"
                onChange={e => onChange({ table: e.target.value.trim() })}
              />
              <datalist id="fact-tables">
                {Object.keys(FACT).map(t => (
                  <option key={t} value={t} />
                ))}
              </datalist>
              <span className={'hint' + (p.table && reads.length && others.length === reads.length ? ' need' : '')}>
                {!p.table
                  ? 'The primary table the SQL reads; filled in as you write it.'
                  : reads.length && others.length === reads.length
                    ? `Not in the SQL, which reads ${reads.join(', ')}.`
                    : `Grain: ${grain}.` + (others.length ? ` The SQL also reads ${others.join(', ')}.` : '')}
              </span>
            </div>
            <div className="field">
              <label htmlFor={'dis-' + p.id}>When to use</label>
              <textarea
                id={'dis-' + p.id}
                className={'ta' + changed('disambig')}
                rows="2"
                value={p.disambig}
                placeholder={several ? 'How this one differs, e.g. "Closed months; the board number"' : 'Optional with one implementation'}
                onChange={e => onChange({ disambig: e.target.value })}
              />
              <span className={'hint' + (needsLabel ? ' need' : '')}>
                {several ? 'Required with more than one implementation; its first line names it.' : 'Optional.'}
              </span>
            </div>
          </div>
          <div className="edbar">
            <span className="served">
              {isDefault && several ? 'Default: the oldest implementation. · ' : null}
              {p.served ? (
                <>
                  Agent uses <b>rev {p.served}</b>
                  {piChanged(p, o) ? ' · unsaved edits' : null}
                </>
              ) : (
                'Not served yet'
              )}
            </span>
            <button className="btn ghost" style={{ marginLeft: 'auto' }} onClick={onRemove}>
              Remove implementation
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// The Implementations section of the metric page. `m`/`orig` = draft and last saved metric; `setM` patches the draft.
// PIs are listed oldest first; the oldest is the default (DEC-019). Removed PIs are retired on save and hidden.
// `newPiId()` resolves to the id for a new PI; `check(id, rev)` runs a saved PI's SQL (null on sample data).
export default function PiSection({ m, orig, editing, setM, openPi, setOpenPi, newPiId, check }) {
  const [addErr, setAddErr] = useState('');
  const setPi = (id, patch) => setM({ pis: m.pis.map(p => (p.id === id ? { ...p, ...patch } : p)) });
  const addPi = async () => {
    setAddErr('');
    let id;
    try {
      id = await newPiId();
    } catch (e) {
      return setAddErr(`Couldn't add an implementation: ${e.message}`);
    }
    const p = {
      id,
      table: '',
      sql: STARTER,
      disambig: '',
      rev: 1,
      validatedRev: null,
      check: null,
      checkMsg: '',
      served: null,
      source: 'sme',
    };
    setM({ pis: [...m.pis, p] });
    setOpenPi(id);
  };
  const several = m.pis.length > 1;
  return (
    <section className="section">
      <div className="sechead">
        <h3>Implementations · {m.pis.length}</h3>
        <div className="rule" />
      </div>
      <div className="pis">
        {m.pis.map((p, i) => (
          <PiRow
            key={p.id}
            p={p}
            o={orig.pis.find(o => o.id === p.id)}
            isDefault={i === 0}
            several={several}
            open={openPi === p.id}
            editing={editing}
            check={check}
            onToggle={() => setOpenPi(openPi === p.id ? null : p.id)}
            onChange={patch => setPi(p.id, patch)}
            onRemove={() => setM({ pis: m.pis.filter(x => x.id !== p.id) })}
          />
        ))}
        {!m.pis.length && (
          <div className="empty" style={{ padding: '16px 14px' }}>
            No implementations yet. The metric saves without one; promoting it needs one whose SQL runs.
          </div>
        )}
        {editing && (
          <button className="addpi" onClick={addPi}>
            + Add implementation
          </button>
        )}
        {addErr && <div className="valmsg bad addpi-err">{addErr}</div>}
      </div>
    </section>
  );
}
