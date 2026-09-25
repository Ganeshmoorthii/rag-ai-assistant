import { useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { askQuestion } from '../api'
import { IconMessage, IconLoader } from './icons'

export default function ChatPanel() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [useAgent, setUseAgent] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || loading) return

    setMessages((prev) => [...prev, { role: 'user', text: q, isAgent: useAgent }])
    setQuestion('')
    setLoading(true)

    try {
      // Toggle ON  -> use_graph:true  runs the 3-agent LangGraph pipeline
      //               (query_analyser_agent -> retrieval_agent -> response_agent).
      // Toggle OFF -> use_graph:false forces the plain single-shot retrieve+generate
      //               baseline, bypassing agents entirely.
      const result = await askQuestion(q, { use_graph: useAgent, use_agent: false })
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: result.answer,
          sources: result.sources,
          graphExecution: useAgent ? result.trace : null,
        },
      ])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'error', text: err.message }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header with Mode Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white mb-1">Chat Assistant</h2>
          <p className="text-sm text-slate-400">
            {useAgent
              ? 'Agentic RAG — 3 agents run per query: query analyser, retrieval agent, response agent.'
              : 'Ask questions about your indexed documents and get instant answers.'}
          </p>
        </div>

        {/* Toggle Switch */}
        <div className="flex items-center gap-3 bg-slate-800/80 px-3.5 py-2 rounded-xl border border-slate-700/60 shadow-sm self-start sm:self-auto">
          {/* <span className={`text-xs font-medium transition-colors ${!useAgent ? 'text-blue-400 font-semibold' : 'text-slate-400'}`}>
            Standard RAG
          </span> */}
          <button
            type="button"
            role="switch"
            aria-checked={useAgent}
            onClick={() => setUseAgent(!useAgent)}
            className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              useAgent ? 'bg-indigo-600' : 'bg-slate-700'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 ease-in-out ${
                useAgent ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
          <span className={`text-xs font-medium transition-colors ${useAgent ? 'text-indigo-300 font-semibold' : 'text-slate-400'}`}>
            Agentic RAG
          </span>
        </div>
      </div>

      {/* Chat Container */}
      <div className="card-modern interactive flex flex-col" style={{ minHeight: '70vh' }}>
        <div className="card-content flex-1 overflow-y-auto custom-scrollbar space-y-4 mb-4">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center text-center">
              <div className="space-y-3">
                <IconMessage width={28} height={28} className="mx-auto text-slate-600" />
                <div className="text-slate-400">
                  <p className="text-sm font-medium">Start a conversation</p>
                  <p className="text-xs text-slate-500 mt-1">Ask anything about your documents</p>
                </div>
              </div>
            </div>
          ) : (
            <>
              {messages.map((m, i) => (
                <div key={i} className="space-y-2">
                  <div className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`px-4 py-3 rounded-lg ${
                        m.role === 'user'
                          ? 'max-w-xs lg:max-w-md bg-blue-500/20 text-blue-100 rounded-br-none'
                          : m.role === 'error'
                            ? 'max-w-xs lg:max-w-md bg-red-500/20 text-red-100 rounded-bl-none'
                            : 'max-w-xl lg:max-w-2xl xl:max-w-3xl bg-slate-700/40 text-slate-100 rounded-bl-none'
                      }`}
                    >
                      {m.role === 'assistant' ? (
                        <div className="text-sm leading-relaxed markdown-body">
                          <Markdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              table: ({ node, ...props }) => (
                                <div className="overflow-x-auto my-3 rounded-lg border border-slate-700/50">
                                  <table className="w-full text-xs border-collapse" {...props} />
                                </div>
                              ),
                            }}
                          >
                            {m.text}
                          </Markdown>
                        </div>
                      ) : (
                        <p className="text-sm leading-relaxed">{m.text}</p>
                      )}
                    </div>
                  </div>

                  {m.graphExecution && (
                    <div className="ml-0 mr-auto max-w-xl lg:max-w-2xl xl:max-w-3xl">
                      <div className="p-3 bg-slate-900/90 rounded-xl border border-indigo-700/40 text-xs space-y-2 shadow-lg">
                        <div className="flex items-center justify-between border-b border-slate-700/50 pb-2">
                          <span className="font-semibold text-indigo-300 flex items-center gap-1.5">
                            <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse"></span>
                            3-Agent Pipeline Diagnostics
                            <span className="ml-1 px-1.5 py-0.2 bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/30 text-[10px] font-mono font-semibold">
                              LangGraph
                            </span>
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium ${
                              m.graphExecution.low_confidence
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            }`}
                          >
                            {m.graphExecution.low_confidence ? 'Low Confidence' : 'Confident'}
                          </span>
                        </div>

                        {/* Agent 1: query_analyser_agent */}
                        <div className="grid grid-cols-3 gap-2 font-mono text-[11px] bg-slate-950/50 p-2 rounded-lg border border-slate-800">
                          <div>
                            <span className="text-slate-400">Intent:</span>{' '}
                            <span className="text-indigo-200 font-bold">{m.graphExecution.agentic?.intent}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Route:</span>{' '}
                            <span className="text-indigo-200 font-bold">{m.graphExecution.agentic?.route}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Complexity:</span>{' '}
                            <span className="text-indigo-200 font-bold">{m.graphExecution.agentic?.complexity}</span>
                          </div>
                        </div>

                        {m.graphExecution.agentic?.sub_queries?.length > 0 && (
                          <div className="pt-0.5 flex flex-wrap items-center gap-1.5">
                            <span className="text-slate-400 text-[11px]">Sub-queries:</span>
                            {m.graphExecution.agentic.sub_queries.map((sq, idx) => (
                              <span
                                key={idx}
                                className="px-2 py-0.5 bg-indigo-950/80 text-indigo-300 rounded-md border border-indigo-600/50 font-mono text-[11px]"
                              >
                                {sq}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Agent 2: retrieval_agent */}
                        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase border ${
                              m.graphExecution.agentic?.evidence_sufficient
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                                : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                            }`}
                          >
                            Evidence {m.graphExecution.agentic?.evidence_sufficient ? 'Sufficient' : 'Insufficient'}
                          </span>

                          {/* Agent 3: response_agent + grade_generation */}
                          {m.graphExecution.agentic?.format && (
                            <span className="px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded text-[10px] font-mono border border-slate-700">
                              Format: {m.graphExecution.agentic.format}
                            </span>
                          )}
                          {m.graphExecution.agentic?.hallucination_grade && (
                            <span className="px-1.5 py-0.5 bg-cyan-500/20 text-cyan-300 rounded text-[10px] font-mono font-bold uppercase border border-cyan-500/30">
                              Grade: {m.graphExecution.agentic.hallucination_grade}
                            </span>
                          )}
                          {m.graphExecution.agentic?.self_corrected && (
                            <span className="px-1.5 py-0.5 bg-amber-500/20 text-amber-300 rounded text-[10px] font-mono font-bold uppercase border border-amber-500/40">
                              Self-Corrected
                            </span>
                          )}
                        </div>

                        {m.graphExecution.agentic?.uncertainty_note && (
                          <div className="text-[11px] text-slate-300 bg-slate-900/80 p-2 rounded-md border border-slate-800 leading-relaxed">
                            <span className="text-amber-400/90 font-medium block text-[10px] uppercase tracking-wider mb-0.5">
                              ⚠️ Uncertainty Note:
                            </span>
                            {m.graphExecution.agentic.uncertainty_note}
                          </div>
                        )}

                        {m.graphExecution.timings_ms?.total && (
                          <div className="text-[10px] text-slate-400 font-mono pt-0.5">
                            Total time: {m.graphExecution.timings_ms.total}ms
                          </div>
                        )}

                        {m.graphExecution.stages && m.graphExecution.stages.length > 0 && (
                          <details className="mt-2 pt-2 border-t border-slate-800 group" open>
                            <summary className="cursor-pointer text-[11px] font-semibold text-indigo-300 hover:text-indigo-200 flex items-center justify-between py-1 select-none">
                              <span>🔎 Agent Execution Trace ({m.graphExecution.stages.length} stages)</span>
                              <span className="text-[10px] text-slate-400 font-normal">Toggle View</span>
                            </summary>

                            <div className="mt-2.5 space-y-2.5">
                              {m.graphExecution.stages.map((stage, sIdx) => (
                                <div key={sIdx} className="rounded-lg bg-slate-950/80 border border-slate-800 p-2.5 space-y-2">
                                  <div className="flex items-center justify-between text-[10px] text-slate-400 border-b border-slate-800/70 pb-1 font-mono">
                                    <span className="font-bold text-indigo-300">
                                      {sIdx + 1}. {stage.stage}
                                    </span>
                                    {stage.timings_ms != null && <span>{stage.timings_ms}ms</span>}
                                  </div>

                                  {/* query_analyser stage */}
                                  {stage.stage === 'query_analyser' && (
                                    <div className="font-mono text-[10.5px] text-slate-300 space-y-1">
                                      <div>intent: <span className="text-indigo-200">{stage.intent}</span> · route: <span className="text-indigo-200">{stage.route}</span> · complexity: <span className="text-indigo-200">{stage.complexity}</span></div>
                                      <div>sub_queries: {stage.sub_queries?.map((sq, i) => (
                                        <span key={i} className="px-1.5 py-0.5 ml-1 bg-indigo-950/80 text-indigo-300 rounded border border-indigo-600/40">{sq}</span>
                                      ))}</div>
                                    </div>
                                  )}

                                  {/* retrieval_agent stage: one block per sub-query, each with its full loop history */}
                                  {stage.stage === 'retrieval_agent' && (
                                    <div className="space-y-2">
                                      <div className="font-mono text-[10.5px] text-slate-400">
                                        {stage.sub_query_count} sub-quer{stage.sub_query_count === 1 ? 'y' : 'ies'} · {stage.document_count} chunks merged · overall sufficient: <span className={stage.sufficient ? 'text-emerald-300' : 'text-amber-300'}>{String(stage.sufficient)}</span>
                                      </div>
                                      {stage.sub_results?.map((sr, srIdx) => (
                                        <div key={srIdx} className="bg-slate-900/90 p-2 rounded-md border border-slate-800 space-y-1.5">
                                          <div className="flex items-center justify-between font-mono text-[10.5px]">
                                            <span className="text-slate-200">"{sr.sub_query}"</span>
                                            <span className={sr.sufficient ? 'text-emerald-300' : 'text-amber-300'}>
                                              {sr.retry_count} {sr.retry_count === 1 ? 'retry' : 'retries'}{sr.stalled ? ' · stalled' : ''}
                                            </span>
                                          </div>
                                          {sr.laps?.map((lap, lapIdx) => (
                                            <div key={lapIdx} className="ml-2 pl-2 border-l border-slate-700/60 font-mono text-[10px] text-slate-400">
                                              <div className="text-slate-300">
                                                Loop {lap.attempt + 1}: search "<span className="text-slate-200">{lap.search_query}</span>" → {lap.document_count} docs →{' '}
                                                <span className={lap.sufficient ? 'text-emerald-300' : 'text-amber-300'}>
                                                  {lap.sufficient ? 'sufficient' : 'insufficient'}
                                                </span>
                                              </div>
                                              <div>
                                                relevance {lap.scores?.relevance?.toFixed(2)} · coverage {lap.scores?.coverage?.toFixed(2)} · authority {lap.scores?.authority?.toFixed(2)}
                                                {lap.scores?.contradiction ? ' · contradiction!' : ''}
                                              </div>
                                              {lap.scores?.reason && <div className="italic text-slate-500">{lap.scores.reason}</div>}
                                            </div>
                                          ))}
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  {/* response_agent stage */}
                                  {stage.stage === 'response_agent' && (
                                    <div className="font-mono text-[10.5px] text-slate-300 space-y-1">
                                      <div>format: <span className="text-indigo-200">{stage.format}</span> · self_corrected: <span className={stage.self_corrected ? 'text-amber-300' : 'text-emerald-300'}>{String(stage.self_corrected)}</span></div>
                                      {stage.self_correction_reason && <div className="text-amber-300/90">reason: {stage.self_correction_reason}</div>}
                                      {stage.uncertainty_note && <div className="text-slate-400 italic">note: {stage.uncertainty_note}</div>}
                                    </div>
                                  )}

                                  {/* grade_generation stage */}
                                  {stage.stage === 'grade_generation' && (
                                    <div className="font-mono text-[10.5px] text-slate-300">
                                      hallucination_grade: <span className="text-cyan-300">{stage.hallucination_grade}</span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </details>
                        )}
                      </div>
                    </div>
                  )}

                  {m.sources && m.sources.length > 0 && (
                    <div className="ml-0 mr-auto max-w-xl lg:max-w-2xl xl:max-w-3xl">
                      <details className="text-xs">
                        <summary className="cursor-pointer text-slate-400 hover:text-slate-300 font-medium">
                          {m.sources.length} source{m.sources.length !== 1 ? 's' : ''}
                        </summary>
                        <ul className="mt-2 space-y-1 pl-3 border-l border-slate-600/50 text-slate-300">
                          {m.sources.map((s, j) => (
                            <li key={j} className="text-xs">
                              <span className="text-blue-300">{s.filename}</span>{' '}
                              <span className="text-slate-500">p. {s.page}</span>{' '}
                              <span className="font-mono text-slate-400">({s.score?.toFixed(2)})</span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="max-w-xs lg:max-w-md px-4 py-3 rounded-lg bg-slate-700/40 text-slate-100 rounded-bl-none">
                    <div className="flex items-center gap-2">
                      <IconLoader width={14} height={14} className="animate-spin text-blue-400" />
                      <span className="text-sm">Thinking...</span>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="flex gap-3 border-t border-slate-700/30 pt-4">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question..."
            disabled={loading}
            className="flex-1 form-input"
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="btn-primary px-6"
          >
            {loading ? '...' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  )
}
