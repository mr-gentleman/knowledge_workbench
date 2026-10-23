import { useEffect, useRef, useState } from 'react';
import CodeMirror from 'codemirror';
import 'codemirror/mode/sql/sql';
import 'codemirror/addon/edit/matchbrackets';
import 'codemirror/addon/edit/closebrackets';
import 'codemirror/addon/hint/show-hint';
import 'codemirror/addon/hint/sql-hint';
import 'codemirror/addon/selection/active-line';
import 'codemirror/addon/comment/comment';
import { COLS } from './sample.js';

const KW =
  /\b(select|from|where|and|or|group|by|order|as|in|is|not|null|case|when|then|else|end|with|on|join|left|inner|between|distinct|all|true|false|having|limit|sum|count|power|coalesce|nullifzero|nullif|date_trunc|dateadd|current_date|upper|abs|iff|datediff)\b/gi;
const formatSql = src =>
  src
    .split(/('(?:[^']|'')*')/)
    .map((part, i) => (i % 2 ? part : part.replace(KW, w => w.toUpperCase())))
    .join('');

// Preview output is still faked, as in the mockup; a real run would go through the read-only safe-execution path.
function fakeRun(sql) {
  const cols = [...sql.matchAll(/\bAS\s+([A-Za-z_][A-Za-z0-9_]*)/gi)].map(m => m[1]).filter(c => !/^(date|month)$/i.test(c));
  const first = /\bdate_cst\b/i.test(sql) ? 'date_cst' : /\bmonth\b/i.test(sql) ? 'month' : 'date';
  const vals = ['1.0412', '1.0387', '1.0455'];
  const names = cols.length ? cols : ['value'];
  return { cols: [first, ...names], rows: ['2026-09-01', '2026-08-01', '2026-07-01'].map((d, i) => [d, ...names.map(() => vals[i])]) };
}

export default function SqlEditor({ value, onChange, id, fileName }) {
  const host = useRef(null),
    cm = useRef(null),
    cb = useRef(onChange);
  cb.current = onChange;
  const [pos, setPos] = useState('Ln 1, Col 1');
  const [res, setRes] = useState(null);
  const run = () => {
    setRes({ state: 'run' });
    setTimeout(() => setRes({ state: 'done', ms: 700 + Math.round(Math.random() * 900), ...fakeRun(cm.current.getValue()) }), 550);
  };
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    const ed = CodeMirror(host.current, {
      value,
      mode: 'text/x-sql',
      lineNumbers: true,
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      matchBrackets: true,
      autoCloseBrackets: true,
      styleActiveLine: true,
      viewportMargin: Infinity,
      hintOptions: { tables: COLS, completeSingle: false },
      extraKeys: {
        'Ctrl-Space': 'autocomplete',
        Tab: c => (c.somethingSelected() ? c.indentSelection('add') : c.replaceSelection('    ')),
        'Shift-Tab': c => c.indentSelection('subtract'),
        'Ctrl-Enter': () => runRef.current(),
        'Cmd-Enter': () => runRef.current(),
        'Cmd-/': 'toggleComment',
        'Ctrl-/': 'toggleComment',
      },
    });
    ed.getInputField().id = id;
    ed.on('change', () => cb.current(ed.getValue()));
    ed.on('cursorActivity', () => {
      const c = ed.getCursor();
      setPos(`Ln ${c.line + 1}, Col ${c.ch + 1}`);
    });
    ed.on('inputRead', (c, ch) => {
      if (ch.text[0] === '.') c.showHint({ completeSingle: false });
    });
    cm.current = ed;
    const el = host.current;
    return () => {
      el.innerHTML = '';
    };
    // Build CodeMirror once per mount; the effect below syncs later `value` changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const ed = cm.current;
    if (ed && ed.getValue() !== value) ed.setValue(value);
  }, [value]);

  const format = () => {
    const ed = cm.current,
      c = ed.getCursor();
    ed.setValue(formatSql(ed.getValue()));
    ed.setCursor(c);
    ed.focus();
  };
  const lines = value.split('\n').length;
  return (
    <div className="ide">
      <div className="idebar">
        <div className="idetab">
          <span className="ext">SQL</span>
          {fileName}
        </div>
        <div className="idetools">
          <button className="tool" onClick={format} title="Uppercase keywords">
            Format
          </button>
          <button
            className="tool"
            onClick={() => {
              cm.current.focus();
              cm.current.showHint({ completeSingle: false });
            }}
            title="Ctrl+Space"
          >
            Suggest
          </button>
          <button className="tool run" onClick={run} title="Ctrl+Enter">
            ▶ Run preview
          </button>
        </div>
      </div>
      <div ref={host} />
      {res && (
        <div className="results">
          <div className="rh">
            {res.state === 'run' ? (
              'Running…'
            ) : (
              <>
                <span>
                  Preview · {res.rows.length} rows · {(res.ms / 1000).toFixed(1)}s
                </span>
                <span style={{ marginLeft: 'auto' }}>sample output</span>
                <button className="tool" onClick={() => setRes(null)}>
                  Close
                </button>
              </>
            )}
          </div>
          {res.state === 'done' && (
            <table>
              <thead>
                <tr>
                  {res.cols.map(c => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {res.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((v, j) => (
                      <td key={j} className={j ? 'num' : ''}>
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div className="idestatus">
        <span>{pos}</span>
        <span>{lines} lines</span>
        <span>Spaces: 4</span>
        <span className="r">Snowflake SQL · Ctrl+Space suggest · Ctrl+Enter run · Ctrl+/ comment</span>
      </div>
    </div>
  );
}
