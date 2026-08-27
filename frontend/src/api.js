const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${BASE_URL}/documents`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed')
  return res.json()
}

export async function listDocuments() {
  const res = await fetch(`${BASE_URL}/documents`)
  if (!res.ok) throw new Error('Failed to load documents')
  return res.json()
}

export async function deleteDocument(docId) {
  const res = await fetch(`${BASE_URL}/documents/${docId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete document')
  return res.json()
}

/**
 * Ask a question. `options` carries the per-request strategy overrides so the
 * inspection UI can flip hybrid/rerank/rewrite without restarting the server.
 */
export async function askQuestion(question, options = {}) {
  const res = await fetch(`${BASE_URL}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...options }),
  })
  if (!res.ok) throw new Error((await res.json()).detail || 'Query failed')
  return res.json()
}

/** Classify a failure as retrieval vs generation, given the expected page(s). */
export async function triage(payload) {
  const res = await fetch(`${BASE_URL}/triage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error((await res.json()).detail || 'Triage failed')
  return res.json()
}

export async function getGoldenSet() {
  const res = await fetch(`${BASE_URL}/golden-set`)
  if (!res.ok) throw new Error('Failed to load golden set')
  return res.json()
}

export async function runEvaluation(config, topK) {
  const res = await fetch(`${BASE_URL}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config, top_k: topK }),
  })
  if (!res.ok) throw new Error((await res.json()).detail || 'Evaluation failed')
  return res.json()
}

export async function listConfigs() {
  const res = await fetch(`${BASE_URL}/configs`)
  if (!res.ok) throw new Error('Failed to load configs')
  return res.json()
}

export async function getRetrievalSettings() {
  const res = await fetch(`${BASE_URL}/retrieval-settings`)
  if (!res.ok) throw new Error('Failed to load retrieval settings')
  return res.json()
}
