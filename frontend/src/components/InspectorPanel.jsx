import { useEffect, useState } from 'react'
import { askQuestion, getGoldenSet, getRetrievalSettings, triage } from '../api'

/**
 * THE INSPECTION VIEW
 *
 * The single most useful debugging tool for a RAG app: question, what was
 * retrieved, and the final answer, all visible at once. Without this you are
 * guessing about which half of the pipeline is broken.
 *
 * It shows three things a normal chat UI hides:
 *  1. every retrieved chunk, with its rank and score
 *  2. WHICH retriever found each chunk (dense / BM25 / both)
 *  3. the verdict: retrieval failure or generation failure
 */
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
  const [retrievalOnly, setRetrievalOnly] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})

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

  /** Run the retrieval-vs-generation classifier for the selected golden question. */
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
    <div className="panel inspector">
      <h2>Retrieval Inspector</h2>
      <p className="hint">
        See the question, what was fetched, and the answer side by side — then
        tell which half of the pipeline is broken.
      </p>

      {/* ---- strategy switches ---- */}
      <div className="controls">
        <div className="strategy-row">
          {[
            ['hybrid', 'Hybrid (BM25+RRF)'],
            ['rerank', 'Rerank'],
            ['rewrite', 'Rewrite'],
            ['hyde', 'HyDE'],
            ['mmr', 'MMR'],
          ].map(([key, label]) => (
            <label key={key} className={strategies[key] ? 'chip on' : 'chip'}>
              <input
                type="checkbox"
                checked={strategies[key]}
                onChange={() => toggle(key)}
              />
              {label}
            </label>
          ))}
        </div>

        <div className="strategy-row">
          <label className="inline">
            top_k
            <input
              type="number"
              min="1"
              max="20"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              style={{ width: 60, marginLeft: 6 }}
            />
          </label>
          <label className="chip">
            <input
              type="checkbox"
              checked={retrievalOnly}
              onChange={() => setRetrievalOnly((v) => !v)}
            />
            Retrieval only (skip LLM)
          </label>
        </div>

        {settings && (
          <p className="hint mono">
            defaults — hybrid:{String(settings.hybrid_enabled)} rerank:
            {String(settings.rerank_enabled)} rewrite:
            {String(settings.rewrite_enabled)} · candidate_k:
            {settings.candidate_k} · rrf_k:{settings.rrf_k} · bm25 index:
            {settings.bm25_index_size} chunks
          </p>
        )}
      </div>

      {/* ---- golden question picker ---- */}
      {golden.length > 0 && (
        <div className="controls">
          <label className="inline">
            Golden question:
            <select
              value={selectedGolden}
              onChange={(e) => pickGolden(e.target.value)}
              style={{ marginLeft: 6, maxWidth: 380 }}
            >
              <option value="">— pick a test question —</option>
              {golden.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.id} [{g.category}] {g.question.slice(0, 52)}
                </option>
              ))}
            </select>
          </label>
          {goldenQ && (
            <>
              <p className="hint">
                <b>Expected:</b>{' '}
                {goldenQ.expected
                  .map((e) => `${e.filename} p.${e.page}`)
                  .join(', ')}
              </p>
              {goldenQ.note && <p className="hint note">{goldenQ.note}</p>}
              <button type="button" onClick={handleTriage} disabled={loading}>
                Diagnose this failure
              </button>
            </>
          )}
        </div>
      )}

      {/* ---- ask ---- */}
      <form onSubmit={handleAsk}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything, or pick a golden question above..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? '...' : 'Run'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {/* ---- the verdict ---- */}
      {triageResult && (
        <div className={`verdict ${triageResult.verdict}`}>
          <h3>
            {triageResult.verdict === 'retrieval_failure'
              ? 'RETRIEVAL FAILURE'
              : triageResult.verdict === 'partial_retrieval'
                ? 'PARTIAL RETRIEVAL'
                : 'RETRIEVAL OK — check generation'}
          </h3>
          <p>{triageResult.reasoning}</p>
          <p className="mono">
            first_hit_rank: {String(triageResult.first_hit_rank)} · hit@k:{' '}
            {String(triageResult.hit_at_k)} · recall@k: {triageResult.recall_at_k}{' '}
            · RR: {triageResult.reciprocal_rank}
          </p>
        </div>
      )}

      {/* ---- side-by-side ---- */}
      {result && (
        <div className="inspect-grid">
          {/* retrieved */}
          <div className="inspect-col">
            <h3>Retrieved ({result.sources.length})</h3>
            {result.sources.map((s, i) => {
              const isExpected = expectedKeys.has(`${s.filename}|${s.page}`)
              const open = expanded[i]
              return (
                <div
                  key={i}
                  className={`chunk ${isExpected ? 'chunk-expected' : ''}`}
                >
                  <div className="chunk-head">
                    <b>#{s.rank ?? i + 1}</b>{' '}
                    <span className="fname">{s.filename}</span> p.{s.page}
                    {isExpected && <span className="badge ok">EXPECTED</span>}
                  </div>
                  <div className="chunk-meta mono">
                    score {s.score?.toFixed(4)}
                    {s.rrf_score != null && ` · rrf ${s.rrf_score.toFixed(5)}`}
                    {s.rerank_score != null &&
                      ` · rerank ${s.rerank_score.toFixed(3)}`}
                    {s.pre_rerank_score != null &&
                      ` · was ${s.pre_rerank_score.toFixed(4)}`}
                  </div>
                  {/* WHICH retriever found it — the point of hybrid search */}
                  {s.retrievers && (
                    <div className="retrievers">
                      {Object.entries(s.retrievers).map(([name, info]) => (
                        <span key={name} className={`badge src-${name}`}>
                          {name} #{info.rank}
                        </span>
                      ))}
                      {Object.keys(s.retrievers).length === 1 && (
                        <span className="badge solo">
                          {Object.keys(s.retrievers)[0]}-only
                        </span>
                      )}
                    </div>
                  )}
                  <button
                    type="button"
                    className="linkish"
                    onClick={() =>
                      setExpanded((e) => ({ ...e, [i]: !e[i] }))
                    }
                  >
                    {open ? 'hide text' : 'show text'}
                  </button>
                  {open && <pre className="chunk-text">{s.text}</pre>}
                </div>
              )
            })}
          </div>

          {/* answer + pipeline */}
          <div className="inspect-col">
            <h3>Answer</h3>
            <div className="answer-box">{result.answer}</div>

            {trace && (
              <>
                <h3>Pipeline</h3>
                {trace.search_query !== trace.original_question && (
                  <div className="stage">
                    <b>query transformed</b>
                    <div className="mono small">
                      <span className="dim">from:</span>{' '}
                      {trace.original_question}
                    </div>
                    <div className="mono small">
                      <span className="dim">to:</span> {trace.search_query}
                    </div>
                  </div>
                )}

                {trace.stages.map((st, i) => (
                  <div className="stage" key={i}>
                    <b>{st.stage}</b>
                    {st.skipped && (
                      <div className="mono small warn">
                        skipped — {st.reason}
                      </div>
                    )}
                    {st.query_terms && (
                      <div className="mono small">
                        terms: [{st.query_terms.join(', ')}]
                      </div>
                    )}
                    {st.returned != null && (
                      <div className="mono small">
                        returned {st.returned}
                      </div>
                    )}
                    {st.stage === 'rrf_fusion' && (
                      <div className="mono small">
                        <div>fused {st.fused_count} unique chunks</div>
                        <div>
                          agreed by both: {st.agreed_in_top_k?.length ?? 0}
                        </div>
                        <div className="highlight">
                          BM25-only wins: {st.bm25_only_in_top_k?.length ?? 0}
                        </div>
                      </div>
                    )}
                    {st.stage === 'rerank' && !st.skipped && (
                      <div className="mono small">
                        <div>scored {st.candidates_scored} candidates</div>
                        <div>
                          changed top-k: {String(st.changed_top_k)}
                        </div>
                        {st.promoted_into_top_k?.length > 0 && (
                          <div className="highlight">
                            promoted {st.promoted_into_top_k.length} chunk(s)
                            into top-k
                          </div>
                        )}
                      </div>
                    )}
                    {st.top && (
                      <ol className="mini-rank">
                        {st.top.map((t) => (
                          <li key={t.id}>
                            p.{t.page}{' '}
                            <span className="dim">
                              {t.score?.toFixed?.(4)}
                            </span>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                ))}

                <div className="stage">
                  <b>timings (ms)</b>
                  <div className="mono small">
                    {Object.entries(trace.timings_ms).map(([k, v]) => (
                      <span key={k} style={{ marginRight: 10 }}>
                        {k}:{v}
                      </span>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
