import { useEffect, useMemo, useState } from 'react'
import { listChunks, listDocuments } from '../api'
import { cn } from '../lib/utils'
import {
  IconSearch,
  IconFile,
  IconCopy,
  IconCheck,
  IconChevron,
  IconLoader,
  IconInbox,
  IconLayers,
  IconFilter,
  IconX,
} from './icons'

export default function ChunksPanel({ initialDocId = null, refreshKey = 0 }) {
  const [chunks, setChunks] = useState([])
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedDocId, setSelectedDocId] = useState(initialDocId || 'all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedPage, setSelectedPage] = useState('all')
  const [copiedId, setCopiedId] = useState(null)
  const [expandedChunks, setExpandedChunks] = useState({})
  const [expandAll, setExpandAll] = useState(false)

  // Sync if initialDocId changes from parent
  useEffect(() => {
    if (initialDocId) {
      setSelectedDocId(initialDocId)
    }
  }, [initialDocId])

  // Load documents and chunks
  useEffect(() => {
    async function loadData() {
      setLoading(true)
      setError('')
      try {
        const [docsData, chunksData] = await Promise.all([
          listDocuments(),
          listChunks(),
        ])
        setDocuments(docsData || [])
        setChunks(chunksData || [])
      } catch (e) {
        setError(e.message || 'Failed to load chunks')
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [refreshKey])


  // Available pages for current document selection
  const availablePages = useMemo(() => {
    const relevantChunks =
      selectedDocId === 'all'
        ? chunks
        : chunks.filter((c) => c.doc_id === selectedDocId)
    const pages = Array.from(
      new Set(relevantChunks.map((c) => c.page).filter((p) => p !== null && p !== undefined))
    ).sort((a, b) => a - b)
    return pages
  }, [chunks, selectedDocId])

  // Filtered chunks based on document, page, and search query
  const filteredChunks = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return chunks.filter((chunk) => {
      if (selectedDocId !== 'all' && chunk.doc_id !== selectedDocId) {
        return false
      }
      if (selectedPage !== 'all' && String(chunk.page) !== String(selectedPage)) {
        return false
      }
      if (q) {
        const inText = (chunk.text || '').toLowerCase().includes(q)
        const inDoc = (chunk.filename || '').toLowerCase().includes(q)
        const inId = (chunk.id || '').toLowerCase().includes(q)
        if (!inText && !inDoc && !inId) return false
      }
      return true
    })
  }, [chunks, selectedDocId, selectedPage, searchQuery])

  // Metric stats
  const stats = useMemo(() => {
    const totalCount = chunks.length
    const docCount = documents.length
    const totalWords = chunks.reduce((sum, c) => sum + (c.word_count || 0), 0)
    const avgWords = totalCount ? Math.round(totalWords / totalCount) : 0
    return {
      totalCount,
      docCount,
      avgWords,
      filteredCount: filteredChunks.length,
    }
  }, [chunks, documents, filteredChunks])

  async function copyToClipboard(id, text) {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 1800)
    } catch {
      // fallback if clipboard API fails
    }
  }

  function toggleChunkExpand(id) {
    setExpandedChunks((prev) => ({
      ...prev,
      [id]: !prev[id],
    }))
  }

  function toggleExpandAll() {
    const nextState = !expandAll
    setExpandAll(nextState)
    const newExpanded = {}
    if (nextState) {
      filteredChunks.forEach((c) => {
        newExpanded[c.id] = true
      })
    }
    setExpandedChunks(newExpanded)
  }

  // Highlight search matches
  function renderHighlightedText(text, query) {
    if (!query.trim()) return text

    const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
    return parts.map((part, i) =>
      part.toLowerCase() === query.toLowerCase() ? (
        <mark key={i} className="bg-yellow-400/30 text-yellow-200 px-0.5 rounded font-semibold">
          {part}
        </mark>
      ) : (
        part
      )
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white mb-1 flex items-center gap-2.5">
            <IconLayers width={24} height={24} className="text-blue-400" />
            Document Chunks Explorer
          </h2>
          <p className="text-sm text-slate-400">
            Browse, search, and inspect all {stats.totalCount} extracted chunks across your indexed PDF documents.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleExpandAll}
            className="btn btn-secondary btn-small text-xs flex items-center gap-1.5"
            title={expandAll ? 'Collapse all chunk previews' : 'Expand all chunk text'}
          >
            <IconChevron
              width={14}
              height={14}
              className={cn('transition-transform duration-200', expandAll && 'rotate-180')}
            />
            {expandAll ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-700/40 bg-slate-900/60 p-4">
          <div className="text-xs font-medium text-slate-400">Total Chunks</div>
          <div className="text-2xl font-bold text-blue-400 mt-1">{stats.totalCount}</div>
          <div className="text-xs text-slate-500 mt-0.5">Across all PDFs</div>
        </div>

        <div className="rounded-xl border border-slate-700/40 bg-slate-900/60 p-4">
          <div className="text-xs font-medium text-slate-400">Documents</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">{stats.docCount}</div>
          <div className="text-xs text-slate-500 mt-0.5">Indexed files</div>
        </div>

        <div className="rounded-xl border border-slate-700/40 bg-slate-900/60 p-4">
          <div className="text-xs font-medium text-slate-400">Avg Chunk Length</div>
          <div className="text-2xl font-bold text-purple-400 mt-1">~{stats.avgWords}</div>
          <div className="text-xs text-slate-500 mt-0.5">Words per chunk</div>
        </div>

        <div className="rounded-xl border border-slate-700/40 bg-slate-900/60 p-4">
          <div className="text-xs font-medium text-slate-400">Filtered Matches</div>
          <div className="text-2xl font-bold text-amber-400 mt-1">{stats.filteredCount}</div>
          <div className="text-xs text-slate-500 mt-0.5">
            {selectedDocId === 'all' && !searchQuery ? 'Showing all' : 'Matches criteria'}
          </div>
        </div>
      </div>

      {/* Main Filter & Search Toolbar */}
      <div className="card-modern">
        <div className="card-content space-y-4">
          {/* Document Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 custom-scrollbar">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider shrink-0 mr-1 flex items-center gap-1">
              <IconFilter width={12} height={12} />
              Filter by PDF:
            </span>
            <button
              type="button"
              onClick={() => {
                setSelectedDocId('all')
                setSelectedPage('all')
              }}
              className={cn(
                'toggle-pill text-xs py-1.5 px-3 whitespace-nowrap',
                selectedDocId === 'all' && 'active'
              )}
            >
              All Documents ({stats.totalCount})
            </button>
            {documents.map((doc) => (
              <button
                key={doc.doc_id}
                type="button"
                onClick={() => {
                  setSelectedDocId(doc.doc_id)
                  setSelectedPage('all')
                }}
                className={cn(
                  'toggle-pill text-xs py-1.5 px-3 whitespace-nowrap flex items-center gap-1.5',
                  selectedDocId === doc.doc_id && 'active'
                )}
              >
                <IconFile width={12} height={12} className="text-slate-400 shrink-0" />
                <span className="truncate max-w-[180px]">{doc.filename}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-blue-500/20 text-blue-300 font-mono">
                  {doc.chunks}
                </span>
              </button>
            ))}
          </div>

          {/* Search and Secondary Filter Row */}
          <div className="flex flex-col sm:flex-row gap-3 items-center">
            {/* Search Input */}
            <div className="relative flex-1 w-full">
              <IconSearch
                width={16}
                height={16}
                className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search across chunk content, document title, or chunk ID..."
                className="form-input pl-10 pr-9 py-2 text-sm bg-slate-950/70 border-slate-700/60"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                >
                  <IconX width={14} height={14} />
                </button>
              )}
            </div>

            {/* Page Filter Selector */}
            {availablePages.length > 0 && (
              <div className="settings-input shrink-0">
                <span className="text-xs">Page:</span>
                <select
                  value={selectedPage}
                  onChange={(e) => setSelectedPage(e.target.value)}
                  className="w-auto px-2 text-xs bg-slate-900 border-slate-700"
                >
                  <option value="all">All Pages ({availablePages.length})</option>
                  {availablePages.map((pg) => (
                    <option key={pg} value={pg}>
                      Page {pg}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="py-20 text-center">
          <IconLoader width={32} height={32} className="animate-spin text-blue-400 mx-auto mb-3" />
          <div className="text-sm font-medium text-slate-300">Loading document chunks...</div>
          <div className="text-xs text-slate-500 mt-1">Retrieving chunks from ChromaDB vector store</div>
        </div>
      ) : filteredChunks.length === 0 ? (
        <div className="card-modern p-12 text-center">
          <IconInbox width={40} height={40} className="mx-auto mb-3 text-slate-600" />
          <div className="text-base font-medium text-slate-300">No chunks found</div>
          <div className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            {searchQuery
              ? `No chunks match "${searchQuery}". Try clearing or changing your search terms.`
              : 'No chunks available. Upload a PDF document in the Documents sidebar to begin.'}
          </div>
          {searchQuery && (
            <button
              type="button"
              onClick={() => {
                setSearchQuery('')
                setSelectedDocId('all')
                setSelectedPage('all')
              }}
              className="btn btn-secondary btn-small mx-auto mt-4 text-xs"
            >
              Reset Filters
            </button>
          )}
        </div>
      ) : (
        /* Chunk Cards List */
        <div className="space-y-4">
          {filteredChunks.map((chunk) => {
            const isCopied = copiedId === chunk.id
            const isExpanded = expandAll || expandedChunks[chunk.id]
            const textContent = chunk.text || ''
            const previewLength = 320
            const needsTruncation = textContent.length > previewLength
            const displayText =
              isExpanded || !needsTruncation
                ? textContent
                : textContent.slice(0, previewLength) + '...'

            return (
              <div
                key={chunk.id}
                className="card-modern interactive overflow-hidden border-slate-700/40 hover:border-slate-600/70 transition-all duration-200"
              >
                {/* Chunk Header */}
                <div className="card-header py-3 px-5 flex flex-wrap items-center justify-between gap-3 bg-slate-900/40">
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Document Name Badge */}
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-500/15 border border-blue-500/30 text-blue-200 text-xs font-medium">
                      <IconFile width={13} height={13} className="text-blue-300 shrink-0" />
                      <span className="truncate max-w-[240px]">{chunk.filename}</span>
                    </span>

                    {/* Page Badge */}
                    {chunk.page !== null && chunk.page !== undefined && (
                      <span className="inline-flex items-center px-2 py-1 rounded-md bg-purple-500/15 border border-purple-500/30 text-purple-200 text-xs font-medium">
                        Page {chunk.page}
                      </span>
                    )}

                    {/* Chunk Index */}
                    <span className="inline-flex items-center px-2 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono">
                      Chunk #{chunk.chunk_index}
                    </span>

                    {/* Word & Character Count */}
                    <span className="text-xs text-slate-500 ml-1">
                      {chunk.word_count} words • {chunk.char_count} chars
                    </span>
                  </div>

                  {/* Right Header Actions */}
                  <div className="flex items-center gap-2 ml-auto">
                    {/* Chunk ID tag */}
                    <span
                      className="text-[11px] font-mono text-slate-500 bg-slate-950/60 px-2 py-0.5 rounded border border-slate-800"
                      title={`Full Chunk ID: ${chunk.id}`}
                    >
                      {chunk.id.length > 20 ? `${chunk.id.slice(0, 10)}..._${chunk.chunk_index}` : chunk.id}
                    </span>

                    {/* Copy Button */}
                    <button
                      type="button"
                      onClick={() => copyToClipboard(chunk.id, chunk.text)}
                      className={cn(
                        'btn-icon py-1 px-2 text-xs flex items-center gap-1 rounded-md border transition-all duration-150',
                        isCopied
                          ? 'border-green-500/40 bg-green-500/10 text-green-300'
                          : 'border-slate-700/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                      )}
                      title="Copy chunk text to clipboard"
                    >
                      {isCopied ? (
                        <>
                          <IconCheck width={12} height={12} className="text-green-400" />
                          <span className="text-green-300 text-[11px]">Copied!</span>
                        </>
                      ) : (
                        <>
                          <IconCopy width={12} height={12} />
                          <span className="text-[11px]">Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Chunk Content */}
                <div className="p-5">
                  <div className="rounded-xl bg-slate-950/70 border border-slate-800/80 p-4 font-mono text-sm leading-relaxed text-slate-200 whitespace-pre-wrap select-text break-words">
                    {renderHighlightedText(displayText, searchQuery)}
                  </div>

                  {/* Expand / Collapse Button if chunk is long */}
                  {needsTruncation && !expandAll && (
                    <div className="mt-2.5 flex justify-end">
                      <button
                        type="button"
                        onClick={() => toggleChunkExpand(chunk.id)}
                        className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium transition-colors"
                      >
                        {isExpanded ? (
                          <>
                            Show less <IconChevron width={12} height={12} className="rotate-180" />
                          </>
                        ) : (
                          <>
                            Show full chunk ({chunk.char_count} characters){' '}
                            <IconChevron width={12} height={12} />
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
