import React from 'react';

// The Definition section of the metric page. `changed(k)` marks a field edited since the last save.
export default function DefinitionSection({ m, editing, setM, changed }) {
  return (
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
  );
}
