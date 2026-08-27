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
    <div className="panel chat-panel">
      <h2>Ask your documents</h2>
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <p>{m.text}</p>
            {m.sources && m.sources.length > 0 && (
              <details>
                <summary>{m.sources.length} source(s)</summary>
                <ul>
                  {m.sources.map((s, j) => (
                    <li key={j}>
                      {s.filename} (p.{s.page}) — score {s.score.toFixed(2)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
        {loading && <div className="message assistant">Thinking...</div>}
      </div>

      <form onSubmit={handleSubmit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about your documents..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}
