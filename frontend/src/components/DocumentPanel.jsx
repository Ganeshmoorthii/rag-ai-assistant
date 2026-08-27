import { useEffect, useRef, useState } from 'react'
import { uploadDocument, listDocuments, deleteDocument } from '../api'

export default function DocumentPanel() {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
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
    }
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
    <div className="panel">
      <h2>Documents</h2>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        onChange={handleFileChange}
        disabled={uploading}
      />
      {uploading && <p className="hint">Uploading and indexing...</p>}
      {error && <p className="error">{error}</p>}

      <ul className="doc-list">
        {documents.map((doc) => (
          <li key={doc.doc_id}>
            <span>{doc.filename}</span>
            <span className="chunks">{doc.chunks} chunks</span>
            <button onClick={() => handleDelete(doc.doc_id)}>Remove</button>
          </li>
        ))}
        {documents.length === 0 && <li className="hint">No documents uploaded yet</li>}
      </ul>
    </div>
  )
}
