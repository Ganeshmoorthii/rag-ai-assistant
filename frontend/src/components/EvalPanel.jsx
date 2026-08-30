import { useEffect, useState } from 'react'
import { listConfigs, runEvaluation } from '../api'
import { IconPlay, IconLoader, IconAlert } from './icons'

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
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Measurement</h2>
        <p className="text-sm text-slate-400">
          Run the golden set under each configuration, then compare two runs to get a before/after number.
        </p>
      </div>

      {/* Run Configurations Card */}
      <div className="card-modern interactive">
        <div className="card-header flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="card-title">Evaluation Configurations</div>
            <div className="card-subtitle">Run the golden set under each named pipeline config.</div>
          </div>
          <div className="settings-input">
            <span>Top K</span>
            <input
              type="number"
              min="1"
              max="10"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="card-content space-y-2">
          {configs.map((c) => (
            <div
              key={c.name}
              className="flex items-center justify-between gap-4 rounded-xl border border-slate-700/40 bg-slate-950/40 px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-slate-100">{c.name}</span>
                  {runs[c.name] && (
                    <span className="badge badge-green text-xs font-mono">
                      hit@3 {(runs[c.name].overall['hit_rate@3'] * 100).toFixed(1)}% · MRR{' '}
                      {runs[c.name].overall.mrr.toFixed(3)}
                    </span>
                  )}
                </div>
                <div className="mt-1 text-xs text-slate-400">{c.description}</div>
              </div>
              <button
                type="button"
                onClick={() => run(c.name)}
                disabled={!!running}
                className="btn-secondary btn-small shrink-0"
              >
                {running === c.name ? (
                  <IconLoader width={13} height={13} className="animate-spin" />
                ) : (
                  <IconPlay width={12} height={12} />
                )}
                {running === c.name ? 'Running' : 'Run'}
              </button>
            </div>
          ))}

          {configs.length === 0 && (
            <div className="text-center py-6 text-sm text-slate-400">No configurations available</div>
          )}
        </div>
      </div>

      {error && (
        <div className="card-modern" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.05)' }}>
          <div className="card-content flex items-center gap-2">
            <IconAlert width={16} height={16} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-200">{error}</p>
          </div>
        </div>
      )}

      {/* Before / After Card */}
      <div className="card-modern interactive">
        <div className="card-header">
          <div className="card-title">Before / After Comparison</div>
          <div className="card-subtitle">Pick two completed runs to see the delta.</div>
        </div>

        <div className="card-content space-y-6">
          <div className="flex flex-wrap gap-4">
            <div className="settings-input">
              <span>Before</span>
              <select value={before} onChange={(e) => setBefore(e.target.value)} className="w-32">
                {Object.keys(runs).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="settings-input">
              <span>After</span>
              <select value={after} onChange={(e) => setAfter(e.target.value)} className="w-32">
                {Object.keys(runs).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {b && a ? (
            <>
              <div className="overflow-x-auto custom-scrollbar">
                <table className="metrics">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>{before}</th>
                      <th>{after}</th>
                      <th>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {['hit_rate@1', 'hit_rate@3', 'hit_rate@5'].map((m) => delta(m))}
                    {['recall@1', 'recall@3', 'recall@5'].map((m) => delta(m))}
                    {delta('mrr', false)}
                  </tbody>
                </table>
              </div>

              <div>
                <div className="text-sm font-semibold text-slate-200 mb-3">Hit-rate@3 by category</div>
                <div className="overflow-x-auto custom-scrollbar">
                  <table className="metrics">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>{before}</th>
                        <th>{after}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from(
                        new Set([...Object.keys(b.by_category), ...Object.keys(a.by_category)])
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
                </div>
              </div>

              <div className="movement">
                <div>
                  <h4 className="up">Fixed ({fixed.length})</h4>
                  <ul>
                    {fixed.map((q) => (
                      <li key={q.id}>
                        <b>{q.id}</b> [{q.category}] {q.question.slice(0, 50)}
                      </li>
                    ))}
                    {!fixed.length && <li className="text-subtle">none</li>}
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
                    {!broke.length && <li className="text-subtle">none</li>}
                  </ul>
                </div>
                <div>
                  <h4>Still broken ({still.length})</h4>
                  <ul>
                    {still.map((q) => (
                      <li key={q.id}>
                        <b>{q.id}</b> [{q.category}] {q.question.slice(0, 50)}
                      </li>
                    ))}
                    {!still.length && <li className="text-subtle">none</li>}
                  </ul>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-8 text-slate-400">
              <p className="text-sm">Run at least two configurations to compare.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
