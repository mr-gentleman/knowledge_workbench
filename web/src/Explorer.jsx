import { useState } from 'react';

// The left metric tree: department folders → metrics. `visible` is already filtered by the search.
export default function Explorer({ search, visible, depts, q, sel, pick }) {
  const [openDept, setOpenDept] = useState({ Finance: true });
  return (
    <aside className="explorer" aria-label="Metric explorer">
      <div className="exhead">
        <h2>Metrics</h2>
        {search}
      </div>
      <div className="tree">
        {depts.map(dp => {
          const items = visible.filter(x => x.dept === dp);
          const open = openDept[dp] || !!q;
          return (
            <div key={dp}>
              <button className="folder" onClick={() => setOpenDept(o => ({ ...o, [dp]: !o[dp] }))} aria-expanded={open}>
                <span className={'caret' + (open ? ' open' : '')}>▸</span>
                {dp}
                <span className="count">{items.length}</span>
              </button>
              {open &&
                items.map(x => (
                  <button key={x.key} className={'item' + (x.key === sel ? ' on' : '')} onClick={() => pick(x.key)}>
                    <span className={'dot ' + x.kind} />
                    <span className="nm">{x.name}</span>
                    {x.live && <span className="live">live</span>}
                  </button>
                ))}
            </div>
          );
        })}
        {!visible.length && (
          <div className="empty" style={{ padding: '20px 8px' }}>
            No metrics match “{q}”.
          </div>
        )}
      </div>
    </aside>
  );
}
