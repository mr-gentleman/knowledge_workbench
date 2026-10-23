import { useState } from 'react';
import SqlEditor from './SqlEditor.jsx';
import { FACT, pi } from './sample.js';

// Wording of services.validation_state (DEC-019): a result counts only for the revision it checked.
function piStatus(p) {
  if (p.status === 'stale' || p.rev !== p.validatedRev) return <span className="badge warn">Not run</span>;
  if (p.status === 'bad') return <span className="badge bad">✗ SQL failed · rev {p.validatedRev}</span>;
  return <span className="badge ok">✓ Runs · rev {p.validatedRev}</span>;
}

function PiRow({ p, open, onToggle, onChange, onDefault, onRemove, showDefault, orig, editing }) {
  const grain = FACT[p.table] || '—';
  const [check, setCheck] = useState(null);
  const short = p.table ? p.table.split('.').slice(-1)[0] : 'No fact table yet';
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
        <span className="grain">{grain}</span>
        <span className="tbl">{short}</span>
        <span className="right">
          {p.isDefault && showDefault ? <span className="badge plain">Default</span> : null}
          {piStatus(p)}
        </span>
      </button>
      {open && !editing && (
        <div className="pibody">
          {p.disambig ? <p className="readtext">{p.disambig}</p> : null}
          <pre className="sqlread">{p.sql}</pre>
          <span className="served">
            {p.served ? `Agent uses rev ${p.served}` : 'Not served yet'} · Source: {p.source === 'sme' ? 'SME' : 'Auto-generated'}
          </span>
        </div>
      )}
      {open && editing && (
        <div className="pibody">
          <SqlEditor
            id={'sql-' + p.id}
            fileName={(p.table ? short : 'new') + '.sql'}
            value={p.sql}
            onChange={v =>
              onChange({ sql: v, rev: orig && v !== orig.sql ? orig.rev + 1 : p.rev, status: orig && v !== orig.sql ? 'stale' : p.status })
            }
          />
          <div className="edbar">
            <button className="btn" onClick={validate} disabled={check && check.state === 'run'}>
              {check && check.state === 'run' ? 'Running…' : 'Validate SQL'}
            </button>
            {check && check.state === 'ok' ? (
              <span className="valmsg ok">
                Ran in {(check.ms / 1000).toFixed(1)}s · 1 row · runs on rev {p.rev}
              </span>
            ) : (check && check.state === 'bad') || p.status === 'bad' ? (
              <span className="valmsg bad">{p.msg || 'Query failed'}. Fix the SQL and validate again.</span>
            ) : (
              <span className="valmsg">Checks that it runs. It doesn't prove the number is right.</span>
            )}
          </div>
          <div className="grid2">
            <div className="field">
              <label htmlFor={'tbl-' + p.id}>Fact table</label>
              <select
                id={'tbl-' + p.id}
                className={'select' + changed('table')}
                value={p.table}
                onChange={e => onChange({ table: e.target.value })}
              >
                <option value="" disabled>
                  Choose a fact table…
                </option>
                {Object.keys(FACT).map(t => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <span className="hint">{p.table ? `Grain comes from the fact table: ${grain}.` : 'Grain comes from the fact table.'}</span>
            </div>
            <div className="field">
              <label htmlFor={'dis-' + p.id}>When to use</label>
              <textarea
                id={'dis-' + p.id}
                className={'ta' + changed('disambig')}
                rows="2"
                value={p.disambig}
                placeholder={showDefault ? 'Required when a metric has more than one implementation' : 'Optional with one implementation'}
                onChange={e => onChange({ disambig: e.target.value })}
              />
            </div>
          </div>
          <div className="edbar">
            {showDefault ? (
              <label className="radio">
                <input type="radio" name="default-pi" checked={p.isDefault} onChange={onDefault} /> Default implementation
              </label>
            ) : null}
            <span className="served">
              {p.served ? (
                <>
                  Agent uses <b>rev {p.served}</b>
                  {p.rev !== p.served ? ` · you're editing rev ${p.rev}` : null}
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
export default function PiSection({ m, orig, editing, setM, openPi, setOpenPi }) {
  const setPi = (id, patch) => setM({ pis: m.pis.map(p => (p.id === id ? { ...p, ...patch } : p)) });
  const addPi = () => {
    const id = Date.now();
    setM({
      pis: [
        ...m.pis,
        pi(id, '', '-- New implementation\nSELECT\n    \nFROM AC.\nWHERE ', {
          isDefault: m.pis.length === 0,
          validatedRev: 0,
          rev: 1,
          served: null,
          status: 'stale',
          source: 'sme',
        }),
      ],
    });
    setOpenPi(id);
  };
  return (
    <section className="section">
      <div className="sechead">
        <h3>Implementations · {m.pis.length}</h3>
        <div className="rule" />
      </div>
      <div className="pis">
        {m.pis.map(p => (
          <PiRow
            key={p.id}
            p={p}
            orig={orig.pis.find(o => o.id === p.id)}
            open={openPi === p.id}
            showDefault={m.pis.length > 1}
            editing={editing}
            onToggle={() => setOpenPi(openPi === p.id ? null : p.id)}
            onChange={patch => setPi(p.id, patch)}
            onRemove={() => setM({ pis: m.pis.filter(x => x.id !== p.id) })}
            onDefault={() => setM({ pis: m.pis.map(x => ({ ...x, isDefault: x.id === p.id })) })}
          />
        ))}
        {!m.pis.length && (
          <div className="empty" style={{ padding: '16px 14px' }}>
            No implementations yet.{editing ? ' Add the SQL that computes this metric.' : ''}
          </div>
        )}
        {editing && (
          <button className="addpi" onClick={addPi}>
            + Add implementation
          </button>
        )}
      </div>
    </section>
  );
}
