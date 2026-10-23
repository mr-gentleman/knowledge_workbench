// Which metrics a search and kind filter keep. The explorer tree shows only these.
export const matches = (x, q, filter) =>
  (filter === 'all' || x.kind === filter) &&
  (!q || (x.name + ' ' + x.description + ' ' + x.disambig).toLowerCase().includes(q.toLowerCase()));

export default function SearchBox({ q, setQ, filter, setFilter }) {
  return (
    <>
      <input
        className="search"
        id="search"
        placeholder="Search names, definitions, when-to-use"
        value={q}
        onChange={e => setQ(e.target.value)}
      />
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
      </div>
    </>
  );
}
