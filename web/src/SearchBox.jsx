import { useEffect, useRef } from 'react';
import './SearchBox.css';

// Where a search word can hit, best first: [weight, label, text].
const FIELDS = [
  [5, 'name', x => x.name],
  [3, 'category', x => `${x.id} ${x.category} ${x.dept}`],
  [2, 'definition', x => `${x.description} ${x.disambig}`],
  [1, 'SQL', x => (x.pis || []).map(p => `${p.table} ${p.sql}`).join(' ')],
];
const words = q => q.toLowerCase().split(/\s+/).filter(Boolean);
const bestField = (x, w) => FIELDS.find(([, , text]) => (text(x) || '').toLowerCase().includes(w));

// Every word must hit some field; each scores its best field, +1 when the name starts with it. 0 = no match.
export const rank = (x, q) => {
  let score = 0;
  for (const w of words(q)) {
    const f = bestField(x, w);
    if (!f) return 0;
    score += f[0] + (x.name.toLowerCase().startsWith(w) ? 1 : 0);
  }
  return score;
};

// The metrics a search and kind filter keep: best match first, list order on ties or with no query.
export const search = (data, q, filter) => {
  const kept = data.filter(x => filter === 'all' || x.kind === filter);
  if (!words(q).length) return kept;
  return kept
    .map(x => [rank(x, q), x])
    .filter(([s]) => s)
    .sort((a, b) => b[0] - a[0])
    .map(([, x]) => x);
};

// Where a kept metric matched when its name didn't ('definition', 'SQL', …); null when the name hits.
export const hitWhere = (x, q) => {
  const ws = words(q);
  if (!ws.length || ws.some(w => x.name.toLowerCase().includes(w))) return null;
  return bestField(x, ws[0])?.[1] ?? null;
};

// `text` split into [part, isHit] runs for highlighting the query's words.
export const hitParts = (text, q) => {
  const ws = words(q);
  if (!ws.length) return [[text, false]];
  const re = new RegExp(`(${ws.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  return text
    .split(re)
    .filter(Boolean)
    .map(s => [s, ws.includes(s.toLowerCase())]);
};

export default function SearchBox({ q, setQ, filter, setFilter, count }) {
  const input = useRef(null);
  // `/` (outside a text field) or ⌘K / Ctrl-K jumps to search from anywhere on the page.
  useEffect(() => {
    const onKey = e => {
      const typing = e.target.closest?.('input, textarea, select, [contenteditable]');
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        input.current.focus();
        input.current.select();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      <div className="searchbox">
        <input
          ref={input}
          className="search"
          id="search"
          placeholder="Search names, definitions, SQL"
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => e.key === 'Escape' && (q ? setQ('') : e.target.blur())}
        />
        {q ? (
          <button className="clear" aria-label="Clear search" onClick={() => (setQ(''), input.current.focus())}>
            ×
          </button>
        ) : (
          <kbd className="kbd">/</kbd>
        )}
      </div>
      <div className="chips">
        {[
          ['all', 'All'],
          ['canon', 'Canon'],
          ['cand', 'Candidates'],
        ].map(([k, l]) => (
          <button key={k} className={'chip' + (filter === k ? ' on' : '')} onClick={() => setFilter(k)}>
            {l}
          </button>
        ))}
        {q && (
          <span className="hits" aria-live="polite">
            {count} {count === 1 ? 'match' : 'matches'}
          </span>
        )}
      </div>
    </>
  );
}
