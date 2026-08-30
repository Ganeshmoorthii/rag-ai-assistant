import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import { askQuestion, getGoldenSet, getRetrievalSettings, triage } from '../api'
import {
  IconPlay,
  IconSearch,
  IconCheck,
  IconCircle,
  IconCopy,
  IconAlert,
  IconCheckCircle,
  IconChevron,
  IconInbox,
  IconLoader,
  IconSparkle,
  IconFile,
  IconX,
} from './icons'

const PIPELINE_STEPS = ['Rewriting', 'Retrieving', 'Reranking', 'Generating']

function cnBadge(active) {
  return active ? 'badge badge-blue' : 'badge badge-slate opacity-60'
}

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
  const [loadingStep, setLoadingStep] = useState(0)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})
  const [expandedDebug, setExpandedDebug] = useState(true)
  const [copied, setCopied] = useState(false)

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

  function runLoadingSteps() {
    setLoadingStep(0)
    const stepCount = strategies.rewrite ? PIPELINE_STEPS.length : PIPELINE_STEPS.length - 1
    const interval = setInterval(() => {
      setLoadingStep((s) => (s < stepCount - 1 ? s + 1 : s))
    }, 450)
    return () => clearInterval(interval)
  }

  async function handleAsk(e) {
    e?.preventDefault()
    const q = question.trim()
    if (!q || loading) return

    setLoading(true)
    setError('')
    setTriageResult(null)
    const stopSteps = runLoadingSteps()
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
      stopSteps()
      setLoading(false)
    }
  }

  async function handleTriage() {
    const g = golden.find((x) => x.id === selectedGolden)
    if (!g || loading) return

    setLoading(true)
    setError('')
    const stopSteps = runLoadingSteps()
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
      stopSteps()
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
              {loading ? (
                <IconLoader width={16} height={16} className="animate-spin" />
              ) : (
                <IconPlay width={14} height={14} />
              )}
              {loading ? 'Running...' : 'Run Retrieval'}
            </button>
            {goldenQ && (
              <button
                type="button"
                onClick={handleTriage}
                disabled={loading}
                className="btn-secondary"
              >
                <IconSearch width={14} height={14} />
                Diagnose
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
                {strategies[key] ? (
                  <IconCheck width={13} height={13} />
                ) : (
                  <IconCircle width={13} height={13} />
                )}
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

          {/* Pipeline Summary */}
          <div className="border-t border-slate-700/30 pt-4">
            <div className="text-xs font-semibold text-slate-300 mb-3 tracking-wide uppercase">
              Pipeline Summary
            </div>
            <div className="rounded-xl border border-slate-700/40 bg-slate-950/40 p-4 space-y-4">
              <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
                {[
                  ['hybrid', 'Hybrid Search'],
                  ['rewrite', 'Rewrite'],
                  ['rerank', 'Rerank'],
                ].map(([key, label], idx, arr) => (
                  <div key={key} className="flex items-center gap-2">
                    <span
                      className={cnBadge(strategies[key])}
                    >
                      {label}
                    </span>
                    {idx < arr.length - 1 && <span className="text-slate-600">→</span>}
                  </div>
                ))}
                <span className="text-slate-600">→</span>
                <span className="badge badge-blue">Retrieval</span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-800/60">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    Candidate Pool
                  </div>
                  <div className="text-sm font-mono text-slate-100">{candidateK}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    Final Results
                  </div>
                  <div className="text-sm font-mono text-slate-100">{topK}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    RRF K
                  </div>
                  <div className="text-sm font-mono text-slate-100">{rrfK}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                    BM25 Index
                  </div>
                  <div className="text-sm font-mono text-slate-100">
                    {settings ? `${settings.bm25_index_size} chunks` : '—'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Triage Result */}
      {triageResult && (
        <div className="card-modern interactive" style={{
          borderColor: triageResult.verdict === 'retrieval_failure' ? 'rgba(239, 68, 68, 0.3)' : triageResult.verdict === 'partial_retrieval' ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)',
          background: triageResult.verdict === 'retrieval_failure' ? 'rgba(239, 68, 68, 0.05)' : triageResult.verdict === 'partial_retrieval' ? 'rgba(245, 158, 11, 0.05)' : 'rgba(16, 185, 129, 0.05)',
        }}>
          <div className="card-header flex items-center gap-2">
            {triageResult.verdict === 'retrieval_failure' ? (
              <IconX width={16} height={16} className="text-red-400" />
            ) : triageResult.verdict === 'partial_retrieval' ? (
              <IconAlert width={16} height={16} className="text-amber-400" />
            ) : (
              <IconCheckCircle width={16} height={16} className="text-emerald-400" />
            )}
            <div className="card-title text-base">
              {triageResult.verdict === 'retrieval_failure'
                ? 'Retrieval Failure'
                : triageResult.verdict === 'partial_retrieval'
                  ? 'Partial Retrieval'
                  : 'Retrieval OK'}
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
          <div className="card-content flex items-center gap-2">
            <IconAlert width={16} height={16} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-200">{error}</p>
          </div>
        </div>
      )}

      {/* Results Section */}
      {result && (
        <div className={loading ? 'opacity-40 pointer-events-none transition-opacity space-y-6' : 'space-y-6'}>
          {/* Results Grid */}
          <div className="results-grid">
            {/* Retrieved Documents Column */}
            <div>
              <div className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                <IconFile width={14} height={14} className="text-slate-400" />
                <span>Retrieved Documents</span>
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
                          <span className="badge badge-green text-xs">
                            <IconCheck width={11} height={11} />
                            Expected
                          </span>
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
                        className="flex items-center gap-1 text-xs text-blue-300 hover:text-blue-200 mt-2 transition"
                      >
                        <IconChevron
                          width={12}
                          height={12}
                          className={`transition-transform ${isOpen ? '' : '-rotate-90'}`}
                        />
                        {isOpen ? 'Hide full text' : 'Show full text'}
                      </button>

                      {isOpen && (
                        <pre className="mt-3 p-3 bg-slate-950/50 rounded text-xs text-slate-300 overflow-x-auto max-h-40 custom-scrollbar whitespace-pre-wrap break-words">
                          {s.text}
                        </pre>
                      )}
                    </div>
                  )
                })}

                {(!result.sources || result.sources.length === 0) && (
                  <div className="text-center py-8 text-slate-400">
                    <IconInbox width={28} height={28} className="mx-auto mb-2 text-slate-600" />
                    <p className="text-sm">No documents retrieved</p>
                  </div>
                )}
              </div>
            </div>

            {/* Generated Answer Column */}
            <div>
              <div className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                <IconSparkle width={14} height={14} className="text-slate-400" />
                <span>Generated Answer</span>
              </div>

              <div className="card-modern interactive">
                <div className="card-content space-y-4">
                  {result.answer ? (
                    <>
                      <div className="text-sm leading-relaxed text-slate-100 markdown-body">
                        <Markdown>{result.answer}</Markdown>
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
                          setCopied(true)
                          setTimeout(() => setCopied(false), 1500)
                        }}
                        className="btn-secondary w-full text-xs"
                      >
                        {copied ? (
                          <IconCheck width={13} height={13} />
                        ) : (
                          <IconCopy width={13} height={13} />
                        )}
                        {copied ? 'Copied' : 'Copy Answer'}
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
                <div className="card-title flex items-center gap-2">
                  <IconSearch width={15} height={15} className="text-slate-400" />
                  Retrieval Diagnostics
                </div>
                <IconChevron
                  width={16}
                  height={16}
                  className={`text-slate-400 transition-transform ${expandedDebug ? '' : '-rotate-90'}`}
                />
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
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="card-modern interactive">
          <div className="card-content">
            <div className="flex items-center gap-3 mb-4">
              <IconLoader width={16} height={16} className="animate-spin text-blue-400" />
              <div className="text-sm font-medium text-slate-200">Running retrieval pipeline...</div>
            </div>
            <div className="flex items-center">
              {PIPELINE_STEPS.map((step, idx) => {
                const isSkipped = step === 'Rewriting' && !strategies.rewrite
                const isDone = idx < loadingStep
                const isActive = idx === loadingStep
                return (
                  <div key={step} className="flex items-center flex-1 last:flex-none">
                    <div className="flex flex-col items-center gap-1.5 shrink-0">
                      <div
                        className={`w-6 h-6 rounded-full flex items-center justify-center border text-[10px] font-mono transition-colors ${
                          isSkipped
                            ? 'border-slate-700 text-slate-600'
                            : isDone
                              ? 'border-blue-400/60 bg-blue-500/20 text-blue-200'
                              : isActive
                                ? 'border-blue-400 bg-blue-500/10 text-blue-300'
                                : 'border-slate-700 text-slate-500'
                        }`}
                      >
                        {isDone ? <IconCheck width={11} height={11} /> : idx + 1}
                      </div>
                      <span
                        className={`text-[11px] whitespace-nowrap ${
                          isSkipped ? 'text-slate-600 line-through' : isActive ? 'text-blue-200' : 'text-slate-400'
                        }`}
                      >
                        {step}
                      </span>
                    </div>
                    {idx < PIPELINE_STEPS.length - 1 && (
                      <div
                        className={`h-px flex-1 mx-2 mb-4 transition-colors ${
                          isDone ? 'bg-blue-400/40' : 'bg-slate-700'
                        }`}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
