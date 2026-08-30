import { useEffect, useState } from 'react'
import { askQuestion, getGoldenSet, getRetrievalSettings, triage } from '../api'

export default function InspectorPanel() {
  const [question, setQuestion] = useState('')
  const [strategies, setStrategies] = useState({
    hybrid: false,
    rerank: false,
    rewrite: false,
    mmr: false,
    hyde: false,
  })
  const [topK, setTopK] = useState(3)
  const [candidateK, setCandidateK] = useState(20)
  const [rrfK, setRrfK] = useState(60)
  const [retrievalOnly, setRetrievalOnly] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})
  const [expandedDebug, setExpandedDebug] = useState(false)

  const [golden, setGolden] = useState([])
  const [selectedGolden, setSelectedGolden] = useState('')
  const [settings, setSettings] = useState(null)
  const [triageResult, setTriageResult] = useState(null)

  useEffect(() => {
    getGoldenSet()
      .then((d) => setGolden(d.questions || []))
      .catch(() => setGolden([]))
    getRetrievalSettings()
      .then(setSettings)
      .catch(() => setSettings(null))
  }, [])

  function toggle(key) {
    setStrategies((s) => ({ ...s, [key]: !s[key] }))
  }

  function pickGolden(id) {
    setSelectedGolden(id)
    const q = golden.find((g) => g.id === id)
    if (q) {
      setQuestion(q.question)
      setResult(null)
      setTriageResult(null)
    }
  }

  async function handleAsk(e) {
    e?.preventDefault()
    const q = question.trim()
    if (!q || loading) return

    setLoading(true)
    setError('')
    setTriageResult(null)
    try {
      const res = await askQuestion(q, {
        ...strategies,
        top_k: topK,
        retrieval_only: retrievalOnly,
      })
      setResult(res)
    } catch (err) {
      setError(err.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  async function handleTriage() {
    const g = golden.find((x) => x.id === selectedGolden)
    if (!g || loading) return

    setLoading(true)
    setError('')
    try {
      const res = await triage({
        question: g.question,
        expected: g.expected,
        top_k: topK,
        ...strategies,
        generate: !retrievalOnly,
      })
      setTriageResult(res)
      setResult({ answer: res.answer, sources: res.sources, trace: res.trace })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const trace = result?.trace
  const goldenQ = golden.find((g) => g.id === selectedGolden)
  const expectedKeys = new Set(
    (goldenQ?.expected || []).map((e) => `${e.filename}|${e.page}`)
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Retrieval Inspector</h2>
        <p className="text-sm text-slate-400">
          Inspect how your query is rewritten, retrieved, ranked, and used to generate an answer.
        </p>
      </div>

      {/* Test Your Retrieval Card */}
      <form onSubmit={handleAsk} className="card-modern interactive">
        <div className="card-header">
          <div className="card-title">Test Your Retrieval</div>
        </div>
        <div className="card-content space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-200 mb-2">Query</label>
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask anything about your indexed documents..."
              disabled={loading}
              className="form-input w-full"
            />
          </div>

          {golden.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-slate-200 mb-2">
                Golden Question (Optional)
              </label>
              <select
                value={selectedGolden}
                onChange={(e) => pickGolden(e.target.value)}
                className="form-select w-full"
              >
                <option value="">— select a predefined test question —</option>
                {golden.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.id} [{g.category}] {g.question.slice(0, 52)}
                  </option>
                ))}
              </select>
              {goldenQ && (
                <div className="mt-3 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-sm">
                  <div className="text-blue-200 font-medium mb-1">Expected documents:</div>
                  <div className="text-blue-200/70">
                    {goldenQ.expected.map((e) => `${e.filename} (p. ${e.page})`).join(', ')}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="btn-primary flex-1"
            >
              {loading ? '🔄 Running...' : '▶ Run Retrieval'}
            </button>
            {goldenQ && (
              <button
                type="button"
                onClick={handleTriage}
                disabled={loading}
                className="btn-secondary"
              >
                🔍 Diagnose
              </button>
            )}
          </div>
        </div>
      </form>

      {/* Retrieval Pipeline Card */}
      <div className="card-modern interactive">
        <div className="card-header">
          <div className="card-title">Retrieval Pipeline</div>
          <div className="card-subtitle">
            Configure how relevant context is found and ranked.
          </div>
        </div>
        <div className="card-content space-y-4">
          <div className="flex flex-wrap gap-2">
            {[
              ['hybrid', 'Hybrid Search'],
              ['rerank', 'Rerank'],
              ['rewrite', 'Query Rewrite'],
              ['hyde', 'HyDE'],
              ['mmr', 'MMR'],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => toggle(key)}
                className={`toggle-pill ${strategies[key] ? 'active' : ''}`}
              >
                <span className="text-base">{strategies[key] ? '✓' : '○'}</span>
                <span>{label}</span>
              </button>
            ))}
          </div>

          {/* Retrieval Settings */}
          <div className="border-t border-slate-700/30 pt-4">
            <div className="text-sm font-medium text-slate-300 mb-3">Settings</div>
            <div className="flex flex-wrap gap-4">
              <div className="settings-input">
                <span>Top K</span>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                />
              </div>
              <div className="settings-input">
                <span>Candidate K</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={candidateK}
                  onChange={(e) => setCandidateK(Number(e.target.value))}
                />
              </div>
              <div className="settings-input">
                <span>RRF K</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={rrfK}
                  onChange={(e) => setRrfK(Number(e.target.value))}
                />
              </div>
            </div>

            <div className="mt-3">
              <label className="flex items-center gap-3 cursor-pointer p-2 rounded hover:bg-slate-800/30 transition">
                <input
                  type="checkbox"
                  checked={retrievalOnly}
                  onChange={() => setRetrievalOnly((v) => !v)}
                  className="w-4 h-4 rounded accent-blue-500 cursor-pointer"
                />
                <span className="text-sm text-slate-200">Retrieval only (skip LLM generation)</span>
              </label>
            </div>
          </div>

          {/* System Configuration */}
          {settings && (
            <div className="border-t border-slate-700/30 pt-4">
              <div className="text-xs font-mono text-slate-400 space-y-1 p-3 bg-slate-950/40 rounded-lg">
                <div>
                  <span className="text-slate-500">Defaults:</span>{' '}
                  hybrid: {String(settings.hybrid_enabled)} · rerank: {String(settings.rerank_enabled)} · rewrite: {String(settings.rewrite_enabled)}
                </div>
                <div>
                  <span className="text-slate-500">Config:</span> candidate_k: {settings.candidate_k} · rrf_k:{settings.rrf_k}
                </div>
                <div>
                  <span className="text-slate-500">Index:</span> BM25 {settings.bm25_index_size} chunks
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Triage Result */}
      {triageResult && (
        <div className="card-modern interactive" style={{
          borderColor: triageResult.verdict === 'retrieval_failure' ? 'rgba(239, 68, 68, 0.3)' : triageResult.verdict === 'partial_retrieval' ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)',
          background: triageResult.verdict === 'retrieval_failure' ? 'rgba(239, 68, 68, 0.05)' : triageResult.verdict === 'partial_retrieval' ? 'rgba(245, 158, 11, 0.05)' : 'rgba(16, 185, 129, 0.05)',
        }}>
          <div className="card-header">
            <div className="card-title text-base">
              {triageResult.verdict === 'retrieval_failure'
                ? '❌ Retrieval Failure'
                : triageResult.verdict === 'partial_retrieval'
                  ? '⚠️ Partial Retrieval'
                  : '✓ Retrieval OK'}
            </div>
          </div>
          <div className="card-content space-y-3">
            <p className="text-sm text-slate-200">{triageResult.reasoning}</p>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2 bg-slate-950/40 rounded font-mono">
                <div className="text-slate-400">First hit rank</div>
                <div className="text-blue-300 font-semibold">{triageResult.first_hit_rank}</div>
              </div>
              <div className="p-2 bg-slate-950/40 rounded font-mono">
                <div className="text-slate-400">Hit@K</div>
                <div className="text-blue-300 font-semibold">{String(triageResult.hit_at_k)}</div>
              </div>
              <div className="p-2 bg-slate-950/40 rounded font-mono">
                <div className="text-slate-400">Recall@K</div>
                <div className="text-blue-300 font-semibold">{triageResult.recall_at_k}</div>
              </div>
              <div className="p-2 bg-slate-950/40 rounded font-mono">
                <div className="text-slate-400">Reciprocal Rank</div>
                <div className="text-blue-300 font-semibold">{triageResult.reciprocal_rank}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="card-modern" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.05)' }}>
          <div className="card-content">
            <p className="text-sm text-red-200">❌ {error}</p>
          </div>
        </div>
      )}

      {/* Results Section */}
      {result && (
        <>
          {/* Results Grid */}
          <div className="results-grid">
            {/* Retrieved Documents Column */}
            <div>
              <div className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                <span>📄 Retrieved Documents</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-200">
                  {result.sources?.length || 0}
                </span>
              </div>

              <div className="results-column-left">
                {result.sources?.map((s, i) => {
                  const isExpected = expectedKeys.has(`${s.filename}|${s.page}`)
                  const isOpen = expanded[i]

                  return (
                    <div
                      key={i}
                      className={`result-card ${isExpected ? 'border-green-500/30' : ''}`}
                    >
                      <div className="result-rank">#{s.rank ?? i + 1}</div>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="result-source">{s.filename}</div>
                          <div className="text-xs text-slate-400 mt-1">Page {s.page}</div>
                        </div>
                        {isExpected && (
                          <span className="badge badge-green text-xs">✓ Expected</span>
                        )}
                      </div>

                      <div className="result-score">
                        <span className="text-slate-400">Score:</span>
                        <span className="score-value font-mono">{s.score?.toFixed(4)}</span>
                        {s.rerank_score != null && (
                          <>
                            <span className="text-slate-400">Reranked:</span>
                            <span className="score-value font-mono">{s.rerank_score.toFixed(3)}</span>
                          </>
                        )}
                      </div>

                      {s.retrievers && Object.keys(s.retrievers).length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-3">
                          {Object.entries(s.retrievers).map(([name, info]) => (
                            <span key={name} className="badge badge-slate text-xs">
                              {name} #{info.rank}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="result-preview">{s.text?.substring(0, 150)}...</div>

                      <button
                        type="button"
                        onClick={() => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
                        className="text-xs text-blue-300 hover:text-blue-200 mt-2 transition"
                      >
                        {isOpen ? '▼ Hide full text' : '▶ Show full text'}
                      </button>

                      {isOpen && (
                        <pre className="mt-3 p-3 bg-slate-950/50 rounded text-xs text-slate-300 overflow-x-auto max-h-40 custom-scrollbar whitespace-pre-wrap break-words">
                          {s.text}
                        </pre>
                      )}
                    </div>
                  )
                })}

                {!result.sources || result.sources.length === 0 && (
                  <div className="text-center py-8 text-slate-400">
                    <div className="text-2xl mb-2">📭</div>
                    <p className="text-sm">No documents retrieved</p>
                  </div>
                )}
              </div>
            </div>

            {/* Generated Answer Column */}
            <div>
              <div className="text-sm font-semibold text-slate-300 mb-4">✨ Generated Answer</div>

              <div className="card-modern interactive">
                <div className="card-content space-y-4">
                  {result.answer ? (
                    <>
                      <div className="text-sm leading-relaxed text-slate-100">
                        {result.answer}
                      </div>

                      <div className="border-t border-slate-700/30 pt-4">
                        <div className="text-xs text-slate-400 space-y-2">
                          <div className="flex justify-between">
                            <span>Model</span>
                            <span className="font-mono text-slate-300">GPT</span>
                          </div>
                          <div className="flex justify-between">
                            <span>Sources Used</span>
                            <span className="font-mono text-slate-300">{result.sources?.length || 0}</span>
                          </div>
                          {trace?.timings_ms?.total && (
                            <div className="flex justify-between">
                              <span>Latency</span>
                              <span className="font-mono text-slate-300">{trace.timings_ms.total}ms</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(result.answer)
                        }}
                        className="btn-secondary w-full text-xs"
                      >
                        📋 Copy Answer
                      </button>
                    </>
                  ) : (
                    <div className="text-center py-8 text-slate-400">
                      <p className="text-sm">No answer generated</p>
                      <p className="text-xs text-slate-500 mt-1">(Check "Retrieval only" setting)</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Debugging Insights */}
          {trace && (
            <div className="card-modern interactive">
              <button
                type="button"
                onClick={() => setExpandedDebug(!expandedDebug)}
                className="w-full text-left card-header flex items-center justify-between cursor-pointer hover:bg-slate-700/20 transition"
              >
                <div className="card-title">🔍 Retrieval Diagnostics</div>
                <span className="text-xl">{expandedDebug ? '▼' : '▶'}</span>
              </button>

              {expandedDebug && (
                <div className="card-content space-y-4 border-t border-slate-700/30">
                  {/* Query Rewrite */}
                  {trace.search_query !== trace.original_question && (
                    <div className="space-y-2">
                      <div className="text-xs font-semibold text-slate-300">Query Rewrite</div>
                      <div className="p-3 bg-slate-950/40 rounded font-mono text-xs space-y-1">
                        <div>
                          <span className="text-slate-500">Original:</span>
                          <div className="text-slate-300 mt-1">{trace.original_question}</div>
                        </div>
                        <div className="mt-2">
                          <span className="text-slate-500">Rewritten:</span>
                          <div className="text-slate-300 mt-1">{trace.search_query}</div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Pipeline Stages */}
                  {trace.stages && trace.stages.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-semibold text-slate-300">Pipeline Stages</div>
                      {trace.stages.map((st, idx) => (
                        <div key={idx} className="p-3 bg-slate-950/40 rounded font-mono text-xs space-y-1">
                          <div className="text-blue-300 font-semibold capitalize">{st.stage}</div>
                          {st.skipped && (
                            <div className="text-amber-300">Skipped — {st.reason}</div>
                          )}
                          {st.returned != null && (
                            <div className="text-slate-300">Returned: {st.returned}</div>
                          )}
                          {st.stage === 'rrf_fusion' && (
                            <div className="text-slate-300 space-y-1">
                              <div>Fused: {st.fused_count} unique chunks</div>
                              <div>Agreed by both: {st.agreed_in_top_k?.length ?? 0}</div>
                            </div>
                          )}
                          {st.stage === 'rerank' && !st.skipped && (
                            <div className="text-slate-300 space-y-1">
                              <div>Scored: {st.candidates_scored} candidates</div>
                              <div>Changed top-k: {String(st.changed_top_k)}</div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Timings */}
                  {trace.timings_ms && (
                    <div className="space-y-2">
                      <div className="text-xs font-semibold text-slate-300">Latency Breakdown</div>
                      <div className="p-3 bg-slate-950/40 rounded font-mono text-xs">
                        <div className="flex flex-wrap gap-4">
                          {Object.entries(trace.timings_ms).map(([k, v]) => (
                            <div key={k}>
                              <span className="text-slate-500">{k}:</span>
                              <span className="text-blue-300 ml-1">{v}ms</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Loading State */}
      {loading && !result && (
        <div className="card-modern interactive">
          <div className="card-content flex items-center gap-3">
            <div className="animate-spin">⚙️</div>
            <div>
              <div className="text-sm font-medium text-slate-200">Running retrieval pipeline...</div>
              <div className="text-xs text-slate-400 mt-1">This may take a moment</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
