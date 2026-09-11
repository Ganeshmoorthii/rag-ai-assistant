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
      const result = await askQuestion(q, { use_agent: useAgent })
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: result.answer,
          sources: result.sources,
          agentExecution: result.agent_execution,
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
              ? 'Powered by Week 7 Docs Agent (Multi-lap tool calling & budget tracking).'
              : 'Ask questions about your indexed documents and get instant answers.'}
          </p>
        </div>

        {/* Toggle Switch */}
        <div className="flex items-center gap-3 bg-slate-800/80 px-3.5 py-2 rounded-xl border border-slate-700/60 shadow-sm self-start sm:self-auto">
          <span className={`text-xs font-medium transition-colors ${!useAgent ? 'text-blue-400 font-semibold' : 'text-slate-400'}`}>
            Standard RAG
          </span>
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
          <span className={`text-xs font-medium flex items-center gap-1.5 transition-colors ${useAgent ? 'text-indigo-300 font-semibold' : 'text-slate-400'}`}>
            Docs Agent
            <span className="px-1.5 py-0.2 text-[10px] uppercase tracking-wider font-semibold bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/40">
              Week 7 Loop
            </span>
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

                  {m.agentExecution && (
                    <div className="ml-0 mr-auto max-w-xl lg:max-w-2xl xl:max-w-3xl">
                      <div className="p-3 bg-slate-900/90 rounded-xl border border-indigo-700/40 text-xs space-y-2 shadow-lg">
                        <div className="flex items-center justify-between border-b border-slate-700/50 pb-2">
                          <span className="font-semibold text-indigo-300 flex items-center gap-1.5">
                            <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse"></span>
                            Week 7 Docs Agent Diagnostics
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium ${
                              m.agentExecution.budget_fired
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            }`}
                          >
                            {m.agentExecution.budget_fired
                              ? `Budget Fired: ${m.agentExecution.budget_fired}`
                              : 'All 4 Budgets OK'}
                          </span>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[11px] bg-slate-950/50 p-2 rounded-lg border border-slate-800">
                          <div>
                            <span className="text-slate-400">Laps:</span>{' '}
                            <span className="text-indigo-200 font-bold">{m.agentExecution.lap_count}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Time:</span>{' '}
                            <span className="text-indigo-200 font-bold">{m.agentExecution.wall_clock_seconds}s</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Tokens:</span>{' '}
                            <span className="text-indigo-200 font-bold">
                              {m.agentExecution.total_tokens?.toLocaleString() || 0}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400">Cost:</span>{' '}
                            <span className="text-indigo-200 font-bold">
                              ${m.agentExecution.total_cost?.toFixed(5) || '0.00000'}
                            </span>
                          </div>
                        </div>

                        {m.agentExecution.tools_called && m.agentExecution.tools_called.length > 0 && (
                          <div className="pt-0.5 flex flex-wrap items-center gap-1.5">
                            <span className="text-slate-400 text-[11px]">Tools Dispatched:</span>
                            {m.agentExecution.tools_called.map((tool, idx) => (
                              <span
                                key={idx}
                                className="px-2 py-0.5 bg-indigo-950/80 text-indigo-300 rounded-md border border-indigo-600/50 font-mono text-[11px]"
                              >
                                {tool}()
                              </span>
                            ))}
                          </div>
                        )}

                        {m.agentExecution.lap_traces && m.agentExecution.lap_traces.length > 0 && (
                          <details className="mt-2 pt-2 border-t border-slate-800 group" open>
                            <summary className="cursor-pointer text-[11px] font-semibold text-indigo-300 hover:text-indigo-200 flex items-center justify-between py-1 select-none">
                              <span className="flex items-center gap-1.5">
                                <span>🔎 Tool Calls & Observations ({m.agentExecution.tools_called?.length || 0} calls)</span>
                              </span>
                              <span className="text-[10px] text-slate-400 font-normal">Toggle View</span>
                            </summary>

                            <div className="mt-2.5 space-y-2.5">
                              {m.agentExecution.lap_traces.map((trace, tIdx) => (
                                <div key={tIdx} className="rounded-lg bg-slate-950/80 border border-slate-800 p-2.5 space-y-2">
                                  {/* Lap Header */}
                                  <div className="flex items-center justify-between text-[10px] text-slate-400 border-b border-slate-800/70 pb-1 font-mono">
                                    <span className="font-bold text-indigo-300">
                                      Lap {trace.lap}: {trace.type === 'tool_call' ? 'Tool Invocation' : 'Synthesis & Answer'}
                                    </span>
                                    <span>{trace.lap_time_s}s • {trace.lap_tokens} tokens</span>
                                  </div>

                                  {/* Model Reasoning / Thought */}
                                  {trace.reasoning && (
                                    <div className="text-[11px] text-slate-300 bg-slate-900/80 p-2 rounded-md border border-slate-800 leading-relaxed">
                                      <span className="text-amber-400/90 font-medium block text-[10px] uppercase tracking-wider mb-0.5">
                                        💭 Model Reasoning:
                                      </span>
                                      {trace.reasoning}
                                    </div>
                                  )}

                                  {/* Tools executed in this lap */}
                                  {trace.tools && trace.tools.map((t, toolIdx) => (
                                    <div key={toolIdx} className="space-y-1.5 pt-0.5">
                                      {/* Tool Call with Input Arguments */}
                                      <div className="bg-slate-900/90 p-2 rounded-md border border-indigo-900/40 space-y-1">
                                        <div className="flex items-center justify-between">
                                          <div className="flex items-center gap-1.5">
                                            <span className="px-1.5 py-0.2 bg-emerald-500/20 text-emerald-300 rounded text-[9px] font-mono font-bold uppercase border border-emerald-500/30">
                                              EXECUTE
                                            </span>
                                            <span className="font-mono text-[11px] font-bold text-indigo-300">
                                              {t.tool}()
                                            </span>
                                          </div>
                                        </div>
                                        {t.args && Object.keys(t.args).length > 0 && (
                                          <pre className="font-mono text-[10px] text-slate-300 bg-black/40 p-1.5 rounded overflow-x-auto">
                                            {JSON.stringify(t.args, null, 2)}
                                          </pre>
                                        )}
                                      </div>

                                      {/* Tool Response / Observation */}
                                      <div className="bg-slate-900/90 p-2 rounded-md border border-slate-800 space-y-1">
                                        <div className="flex items-center gap-1.5">
                                          <span className="px-1.5 py-0.2 bg-cyan-500/20 text-cyan-300 rounded text-[9px] font-mono font-bold uppercase border border-cyan-500/30">
                                            OBSERVATION
                                          </span>
                                          <span className="text-[10px] text-slate-400 font-mono">Output received by agent</span>
                                        </div>
                                        <div className="font-mono text-[10.5px] text-slate-200 bg-black/50 p-2 rounded max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed custom-scrollbar border border-slate-800/60">
                                          {t.output || t.output_preview || 'No output returned.'}
                                        </div>
                                      </div>
                                    </div>
                                  ))}
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
