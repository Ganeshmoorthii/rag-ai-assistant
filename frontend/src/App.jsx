import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import ChunksPanel from './components/ChunksPanel'
import DocumentPanel from './components/DocumentPanel'
import EvalPanel from './components/EvalPanel'
import InspectorPanel from './components/InspectorPanel'
import { IconDatabase, IconSettings } from './components/icons'
import { cn } from './lib/utils'

const TABS = [
  ['chat', 'Chat'],
  ['inspect', 'Retrieval Inspector'],
  ['eval', 'Measurement'],
  ['chunks', 'Document Chunks'],
]

export default function App() {
  const [tab, setTab] = useState('chunks')
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [docRefreshKey, setDocRefreshKey] = useState(0)

  function handleViewChunks(docId) {
    setSelectedDocId(docId)
    setTab('chunks')
  }


  return (
    <div className="min-h-screen bg-[#08111F] text-slate-100">
      {/* Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-brand-icon">
            <IconDatabase width={18} height={18} />
          </div>
          <div className="header-brand-text">
            <div className="header-brand-title">RAG Assistant</div>
            <div className="header-brand-subtitle">Retrieval Debugger</div>
          </div>
        </div>

        <div className="header-status">
          <span className="status-indicator"></span>
          <span className="status-text">System Ready</span>
          <button type="button" className="btn-icon" title="Settings">
            <IconSettings width={16} height={16} />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex flex-col">
        {/* Navigation Tabs */}
        <div className="border-b border-slate-800/50 bg-[#08111F]/50 px-8 py-4">
          <nav className="nav-tabs">
            {TABS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setTab(key)
                  if (key !== 'chunks') {
                    setSelectedDocId(null)
                  }
                }}
                className={cn('nav-tab', tab === key && 'active')}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>

        {/* Workspace Content */}
        <main className="flex-1 px-8 py-6">
          {tab === 'chat' && (
            <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
              <DocumentPanel
                onViewChunks={handleViewChunks}
                selectedDocId={selectedDocId}
                onDocumentsChange={() => setDocRefreshKey((k) => k + 1)}
              />
              <ChatPanel />
            </div>
          )}

          {tab === 'inspect' && (
            <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
              <DocumentPanel
                onViewChunks={handleViewChunks}
                selectedDocId={selectedDocId}
                onDocumentsChange={() => setDocRefreshKey((k) => k + 1)}
              />
              <InspectorPanel />
            </div>
          )}

          {tab === 'eval' && (
            <div>
              <EvalPanel />
            </div>
          )}

          {tab === 'chunks' && (
            <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
              <DocumentPanel
                onViewChunks={handleViewChunks}
                selectedDocId={selectedDocId}
                onDocumentsChange={() => setDocRefreshKey((k) => k + 1)}
              />
              <ChunksPanel initialDocId={selectedDocId} refreshKey={docRefreshKey} />
            </div>
          )}
        </main>

      </div>
    </div>
  )
}

