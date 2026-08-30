import { useEffect, useRef, useState } from 'react'
import { uploadDocument, listDocuments, deleteDocument } from '../api'
import { cn } from '../lib/utils'

export default function DocumentPanel() {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef(null)

  async function refresh() {
    try {
      setDocuments(await listDocuments())
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (!file) return
    await uploadFile(file)
  }

  async function uploadFile(file) {
    setUploading(true)
    setError(null)
    try {
      await uploadDocument(file)
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
      setDragActive(false)
    }
  }

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) uploadFile(file)
  }

  async function handleDelete(docId) {
    try {
      await deleteDocument(docId)
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <aside className="space-y-4 h-fit sticky top-24">
      {/* Documents Card */}
      <div className="card-modern interactive">
        <div className="card-header">
          <div className="card-title">Documents</div>
          <div className="card-subtitle">
            {documents.length} {documents.length === 1 ? 'document' : 'documents'} •{' '}
            {documents.reduce((sum, doc) => sum + (doc.chunks || 0), 0)} chunks
          </div>
        </div>
        
        <div className="card-content space-y-4">
          {/* Upload Area */}
          <div
            className={cn(
              'relative rounded-xl border-2 border-dashed transition-all duration-200 cursor-pointer p-6',
              dragActive
                ? 'border-blue-400/70 bg-blue-500/10'
                : 'border-slate-600/40 hover:border-slate-600/60 bg-slate-950/30'
            )}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              onChange={handleFileChange}
              disabled={uploading}
              className="hidden"
            />
            
            <div className="text-center">
              <div className="text-2xl mb-2">📄</div>
              <div className="text-sm font-semibold text-slate-200 mb-1">
                {dragActive ? 'Drop PDF here' : 'Upload PDF'}
              </div>
              <div className="text-xs text-slate-400">
                Drag and drop or click to browse
              </div>
            </div>

            {uploading && (
              <div className="absolute inset-0 bg-blue-500/5 rounded-xl flex items-center justify-center backdrop-blur-sm">
                <div className="text-sm text-blue-300 font-medium">Indexing...</div>
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}

          {/* Documents List */}
          <div className="space-y-2 max-h-96 overflow-y-auto custom-scrollbar">
            {documents.length > 0 ? (
              documents.map((doc) => (
                <div
                  key={doc.doc_id}
                  className="group rounded-lg border border-slate-700/40 bg-slate-950/50 hover:bg-slate-900/70 hover:border-slate-600/60 p-3 transition-all duration-200"
                >
                  <div className="flex items-start gap-3">
                    <div className="text-lg mt-0.5">📑</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-slate-100 truncate">
                        {doc.filename}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-200 border border-blue-500/30">
                          {doc.chunks} chunks
                        </span>
                        <span className="inline-flex items-center gap-1 text-xs text-green-300">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                          Indexed
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDelete(doc.doc_id)}
                      className={cn(
                        'btn-icon opacity-0 group-hover:opacity-100 transition-opacity',
                        'text-slate-400 hover:text-red-400 hover:bg-red-500/10'
                      )}
                      title="Delete document"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-6 text-slate-400">
                <div className="text-3xl mb-2">📭</div>
                <div className="text-sm">No documents yet</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </aside>
  )
}
