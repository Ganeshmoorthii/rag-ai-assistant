import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import DocumentPanel from './components/DocumentPanel'
import EvalPanel from './components/EvalPanel'
import InspectorPanel from './components/InspectorPanel'

const TABS = [
  ['chat', 'Chat'],
  ['inspect', 'Inspector'],
  ['eval', 'Measurement'],
]

export default function App() {
  const [tab, setTab] = useState('inspect')

  return (
    <div className="app">
      <header>
        <h1>RAG Assistant — Retrieval Debugger</h1>
        <nav className="tabs">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              className={tab === key ? 'tab active' : 'tab'}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      {tab === 'chat' && (
        <main className="two-col">
          <DocumentPanel />
          <ChatPanel />
        </main>
      )}

      {tab === 'inspect' && (
        <main className="two-col">
          <DocumentPanel />
          <InspectorPanel />
        </main>
      )}

      {tab === 'eval' && (
        <main className="one-col">
          <EvalPanel />
        </main>
      )}
    </div>
  )
}
