import { useState } from "react";
import "./App.css";

const API = "http://localhost:8000";

const SAMPLES = [
  "Which course is the most competitive?",
  "What is the best course?",
  "Which marketing course is the most competitive?",
  "What is the best finance course?",
  "What is the lowest rated course?",
];

function Table({ rows }) {
  if (!rows || rows.length === 0) return <p className="muted">No rows returned.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{cols.map((c) => <td key={c}>{String(r[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Panel({ variant, title, subtitle, data, consistency }) {
  const [open, setOpen] = useState(false);
  if (!data) return null;
  return (
    <div className={`panel ${variant}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        <span className="tag">{subtitle}</span>
      </div>

      <div className="answer">
        {data.error ? <span className="err">Error: {data.error}</span>
          : data.answer ? data.answer
          : <span className="muted">No answer (query returned nothing)</span>}
      </div>

      {consistency && (
        <div className={`consistency ${consistency.distinct === 1 ? "good" : "bad"}`}>
          Ran 5×: <b>{consistency.distinct}</b> distinct answer{consistency.distinct === 1 ? "" : "s"}
          <div className="runs">{consistency.answers.map((a, i) => <span key={i}>{a}</span>)}</div>
        </div>
      )}

      {data.definition && (
        <div className="definition">
          <span className="def-label">Governed definition</span>
          {data.definition}
        </div>
      )}

      <button className="toggle" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} under the hood
      </button>
      {open && (
        <div className="under">
          {data.request && (
            <>
              <div className="label">Semantic request</div>
              <pre>{JSON.stringify(data.request, null, 2)}</pre>
            </>
          )}
          <div className="label">{data.request ? "Compiled SQL" : "Generated SQL"}</div>
          <pre>{data.sql || "—"}</pre>
        </div>
      )}

      <div className="label">Result</div>
      <Table rows={data.table} />
    </div>
  );
}

export default function App() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [cons, setCons] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingC, setLoadingC] = useState(false);

  async function ask(question) {
    const query = question ?? q;
    if (!query.trim()) return;
    setQ(query);
    setLoading(true); setRes(null); setCons(null);
    try {
      const r = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query }),
      });
      setRes(await r.json());
    } catch (e) {
      setRes({ error: String(e) });
    } finally {
      setLoading(false);
    }
  }

  async function runConsistency() {
    if (!q.trim()) return;
    setLoadingC(true); setCons(null);
    try {
      const r = await fetch(`${API}/api/consistency`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, runs: 5 }),
      });
      setCons(await r.json());
    } catch (e) {
      /* ignore */
    } finally {
      setLoadingC(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Course Compass</h1>
        <p>Same question, two agents: a naive text-to-SQL agent vs. one grounded in a semantic layer.</p>
      </header>

      <div className="ask-bar">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Ask about Kellogg courses… e.g. Which finance course is the best?"
        />
        <button onClick={() => ask()} disabled={loading}>
          {loading ? "Asking…" : "Ask"}
        </button>
      </div>

      <div className="samples">
        {SAMPLES.map((s) => (
          <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
        ))}
      </div>

      {res && res.error && (
        <p className="err">Backend error: {res.error}. Is the API running on :8000?</p>
      )}

      {res && !res.error && (
        <>
          <div className="cons-bar">
            <button onClick={runConsistency} disabled={loadingC}>
              {loadingC ? "Running 5×…" : "Run 5× consistency check"}
            </button>
            <span className="hint">Runs the same question 5 times through each agent.</span>
          </div>
          <div className="grid">
            <Panel variant="v1" title="V1 — Naive text-to-SQL"
                   subtitle="no semantic layer" data={res.v1} consistency={cons?.v1} />
            <Panel variant="v2" title="V2 — Semantic layer"
                   subtitle="governed definitions" data={res.v2} consistency={cons?.v2} />
          </div>
        </>
      )}
    </div>
  );
}