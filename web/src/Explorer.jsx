import { useState } from 'react';
import { hitParts, hitWhere } from './SearchBox.jsx';
import './Explorer.css';

const OPEN_KEY = 'kw.openDepts';
const readOpen = () => {
  try {
    return JSON.parse(localStorage.getItem(OPEN_KEY)) || { Finance: true };
  } catch {
    return { Finance: true }; // storage blocked: default folders, not remembered
  }
};
const DOT = { canon: 'Canon', cand: 'Candidate', draft: 'Unsaved or unconfirmed changes' };

// The left metric tree: department folders → metrics. `visible` is already searched and ranked (SearchBox);
// `unsaved` lists the keys with edits not yet confirmed saved.
export default function Explorer({ search, visible, depts, q, sel, pick, unsaved }) {
  const [openDept, setOpenDept] = useState(readOpen);
  const toggle = dp => {
    const next = { ...openDept, [dp]: !openDept[dp] };
    setOpenDept(next);
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify(next));
    } catch {
      /* storage blocked: remembered for this page only */
    }
  };
  // Searching: folders in order of their best hit. Otherwise the usual order. Empty folders are hidden.
  const folders = q ? [...new Set(visible.map(x => x.dept))] : depts.filter(dp => visible.some(x => x.dept === dp));

  // ↑/↓ walk the search box and every shown folder and metric; Enter in the search box opens the top hit.
  const onKey = e => {
    if (e.key === 'Enter' && e.target.id === 'search') return q && visible[0] && pick(visible[0].key);
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const stops = [...e.currentTarget.querySelectorAll('#search, .tree button')];
    const next = stops[stops.indexOf(e.target) + (e.key === 'ArrowDown' ? 1 : -1)];
    if (next) {
      e.preventDefault();
      next.focus();
    }
  };

  return (
    <aside className="explorer" aria-label="Metric explorer" onKeyDown={onKey}>
      <div className="exhead">
        <h2>Metrics</h2>
        {search}
      </div>
      <div className="tree">
        {folders.map(dp => {
          const items = visible.filter(x => x.dept === dp);
          const open = openDept[dp] || !!q;
          return (
            <div key={dp}>
              <button className="folder" onClick={() => toggle(dp)} aria-expanded={open}>
                <span className={'caret' + (open ? ' open' : '')}>▸</span>
                {dp}
                <span className="count">{items.length}</span>
              </button>
              {open &&
                items.map(x => {
                  const status = unsaved.includes(x.key) ? 'draft' : x.kind;
                  const where = hitWhere(x, q);
                  return (
                    <button key={x.key} className={'item' + (x.key === sel ? ' on' : '')} onClick={() => pick(x.key)}>
                      <span className={'dot ' + status} title={DOT[status]} aria-label={DOT[status]} />
                      <span className="nm">{hitParts(x.name, q).map(([s, hit], i) => (hit ? <mark key={i}>{s}</mark> : s))}</span>
                      {where && <span className="noname">in {where}</span>}
                      {x.live && <span className="live">live</span>}
                    </button>
                  );
                })}
            </div>
          );
        })}
        {!visible.length && (
          <div className="empty" style={{ padding: '20px 8px' }}>
            {q ? `No metrics match “${q}”.` : 'No metrics here.'}
          </div>
        )}
      </div>
      <div className="legend" aria-hidden="true">
        {Object.entries(DOT).map(([k, l]) => (
          <span key={k}>
            <i className={'dot ' + k} />
            {k === 'draft' ? 'Unsaved' : l}
          </span>
        ))}
      </div>
    </aside>
  );
}
