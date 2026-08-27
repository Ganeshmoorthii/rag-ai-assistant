import { useEffect, useState } from 'react'
import { listConfigs, runEvaluation } from '../api'

/**
 * THE MEASUREMENT PANEL
 *
 * Runs the golden set under a named configuration and shows hit-rate@k,
 * recall@k and MRR. Keeps every run in memory so you can pick a BEFORE and
 * an AFTER and get a real delta -- which is the assignment deliverable.
 */
export default function EvalPanel() {
  const [configs, setConfigs] = useState([])
  const [runs, setRuns] = useState({})
  const [running, setRunning] = useState('')
  const [error, setError] = useState('')
  const [before, setBefore] = useState('baseline')
  const [after, setAfter] = useState('hybrid')
  const [topK, setTopK] = useState(3)

  useEffect(() => {
    listConfigs()
      .then(setConfigs)
      .catch((e) => setError(e.message))
  }, [])

  async function run(name) {
    setRunning(name)
    setError('')
    try {
      const res = await runEvaluation(name, topK)
      setRuns((r) => ({ ...r, [name]: res }))
    } catch (e) {
      setError(`${name}: ${e.message}`)
    } finally {
      setRunning('')
    }
  }

  const b = runs[before]
  const a = runs[after]

  function delta(metric, isPct = true) {
    if (!b || !a) return null
    const bv = b.overall[metric]
    const av = a.overall[metric]
    const d = av - bv
    const cls = d > 0 ? 'up' : d < 0 ? 'down' : 'flat'
    const fmt = (v) => (isPct ? `${(v * 100).toFixed(1)}%` : v.toFixed(4))
    return (
      <tr key={metric}>
        <td className="mono">{metric}</td>
        <td className="mono">{fmt(bv)}</td>
        <td className="mono">{fmt(av)}</td>
        <td className={`mono ${cls}`}>
          {d > 0 ? '+' : ''}
          {isPct ? `${(d * 100).toFixed(1)}%` : d.toFixed(4)}
        </td>
      </tr>
    )
  }

  // Per-question movement: what the change fixed, broke, and left broken.
  let fixed = [], broke = [], still = []
  if (b && a) {
    const bq = Object.fromEntries(b.questions.map((q) => [q.id, q]))
    const aq = Object.fromEntries(a.questions.map((q) => [q.id, q]))
    for (const id of Object.keys(bq)) {
      if (!aq[id]) continue
      const was = bq[id]['hit@3']
      const now = aq[id]['hit@3']
      if (!was && now) fixed.push(aq[id])
      else if (was && !now) broke.push(aq[id])
      else if (!was && !now) still.push(aq[id])
    }
  }

  return (
    <div className="panel">
      <h2>Measurement</h2>
      <p className="hint">
        Run the golden set under each configuration, then compare two runs to
        get a before/after number.
      </p>

      <label className="inline">
        top_k
        <input
          type="number"
          min="1"
          max="10"
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          style={{ width: 60, marginLeft: 6 }}
        />
      </label>

      <div className="config-list">
        {configs.map((c) => (
          <div key={c.name} className="config-row">
            <div>
              <b>{c.name}</b>
              {runs[c.name] && (
                <span className="badge ok">
                  hit@3 {(runs[c.name].overall['hit_rate@3'] * 100).toFixed(1)}%
                  {' · MRR '}
                  {runs[c.name].overall.mrr.toFixed(3)}
                </span>
              )}
              <div className="hint">{c.description}</div>
            </div>
            <button
              type="button"
              onClick={() => run(c.name)}
              disabled={!!running}
            >
              {running === c.name ? 'running...' : 'run'}
            </button>
          </div>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      <h3>Before / After</h3>
      <div className="strategy-row">
        <label className="inline">
          before
          <select value={before} onChange={(e) => setBefore(e.target.value)}>
            {Object.keys(runs).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="inline">
          after
          <select value={after} onChange={(e) => setAfter(e.target.value)}>
            {Object.keys(runs).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      {b && a ? (
        <>
          <table className="metrics">
            <thead>
              <tr>
                <th>metric</th>
                <th>{before}</th>
                <th>{after}</th>
                <th>delta</th>
              </tr>
            </thead>
            <tbody>
              {['hit_rate@1', 'hit_rate@3', 'hit_rate@5'].map((m) => delta(m))}
              {['recall@1', 'recall@3', 'recall@5'].map((m) => delta(m))}
              {delta('mrr', false)}
            </tbody>
          </table>

          <h3>hit-rate@3 by category</h3>
          <table className="metrics">
            <thead>
              <tr>
                <th>category</th>
                <th>{before}</th>
                <th>{after}</th>
              </tr>
            </thead>
            <tbody>
              {Array.from(
                new Set([
                  ...Object.keys(b.by_category),
                  ...Object.keys(a.by_category),
                ])
              )
                .sort()
                .map((cat) => {
                  const bc = b.by_category[cat] || {}
                  const ac = a.by_category[cat] || {}
                  const bv = bc['hit_rate@3'] ?? 0
                  const av = ac['hit_rate@3'] ?? 0
                  const cls = av > bv ? 'up' : av < bv ? 'down' : ''
                  return (
                    <tr key={cat}>
                      <td>{cat}</td>
                      <td className="mono">
                        {bc.hits}/{bc.n} ({(bv * 100).toFixed(0)}%)
                      </td>
                      <td className={`mono ${cls}`}>
                        {ac.hits}/{ac.n} ({(av * 100).toFixed(0)}%)
                      </td>
                    </tr>
                  )
                })}
            </tbody>
          </table>

          <div className="movement">
            <div>
              <h4 className="up">Fixed ({fixed.length})</h4>
              <ul>
                {fixed.map((q) => (
                  <li key={q.id}>
                    <b>{q.id}</b> [{q.category}] {q.question.slice(0, 50)}
                  </li>
                ))}
                {!fixed.length && <li className="dim">none</li>}
              </ul>
            </div>
            <div>
              <h4 className="down">Broke ({broke.length})</h4>
              <ul>
                {broke.map((q) => (
                  <li key={q.id}>
                    <b>{q.id}</b> [{q.category}] {q.question.slice(0, 50)}
                  </li>
                ))}
                {!broke.length && <li className="dim">none</li>}
              </ul>
            </div>
            <div>
              {/* The question the mentor explicitly asks. */}
              <h4>Still broken ({still.length})</h4>
              <ul>
                {still.map((q) => (
                  <li key={q.id}>
                    <b>{q.id}</b> [{q.category}] {q.question.slice(0, 50)}
                  </li>
                ))}
                {!still.length && <li className="dim">none</li>}
              </ul>
            </div>
          </div>
        </>
      ) : (
        <p className="hint">Run at least two configurations to compare.</p>
      )}
    </div>
  )
}
