import { useState } from 'react'
import { askQuestion } from '../api'

export default function ChatPanel() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || loading) return

    setMessages((prev) => [...prev, { role: 'user', text: q }])
    setQuestion('')
    setLoading(true)

    try {
      const result = await askQuestion(q)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: result.answer, sources: result.sources },
      ])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'error', text: err.message }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Chat Assistant</h2>
        <p className="text-sm text-slate-400">
          Ask questions about your indexed documents and get instant answers.
        </p>
      </div>

      {/* Chat Container */}
      <div className="card-modern interactive flex flex-col" style={{ minHeight: '70vh' }}>
        <div className="card-content flex-1 overflow-y-auto custom-scrollbar space-y-4 mb-4">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center text-center">
              <div className="space-y-3">
                <div className="text-4xl">💬</div>
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
                      className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                        m.role === 'user'
                          ? 'bg-blue-500/20 text-blue-100 rounded-br-none'
                          : m.role === 'error'
                            ? 'bg-red-500/20 text-red-100 rounded-bl-none'
                            : 'bg-slate-700/40 text-slate-100 rounded-bl-none'
                      }`}
                    >
                      <p className="text-sm leading-relaxed">{m.text}</p>
                    </div>
                  </div>

                  {m.sources && m.sources.length > 0 && (
                    <div className="ml-0 mr-auto max-w-xs lg:max-w-md">
                      <details className="text-xs">
                        <summary className="cursor-pointer text-slate-400 hover:text-slate-300 font-medium">
                          📚 {m.sources.length} source{m.sources.length !== 1 ? 's' : ''}
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
                      <span className="animate-spin">⚙️</span>
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
