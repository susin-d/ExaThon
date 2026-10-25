import type { Cluster, ClusterDetail, PipelineStatus, TicketEvidence } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Actor-Id': 'ombudsman.demo',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'The service returned an unreadable error.' }))
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  clusters: (search = '', product = '') => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (product) params.set('product', product)
    return request<Cluster[]>(`/api/v1/clusters?${params}`)
  },
  cluster: (id: string) => request<ClusterDetail>(`/api/v1/clusters/${id}`),
  reviewQueue: (minimum = 0.65) => request<TicketEvidence[]>(`/api/v1/review-queue?minimum_confidence=${minimum}`),
  pipeline: () => request<PipelineStatus>('/api/v1/pipeline/status'),
  review: (
    ticketId: string,
    payload: { decision: 'confirm' | 'dismiss' | 'reclassify'; reason?: string; corrected_type?: string },
  ) => request(`/api/v1/tickets/${ticketId}/reviews`, { method: 'POST', body: JSON.stringify(payload) }),
  importCsv: async (file: File) => {
    const data = new FormData()
    data.append('file', file)
    const response = await fetch(`${API_URL}/api/v1/imports/csv`, {
      method: 'POST',
      headers: { 'X-Actor-Id': 'ombudsman.demo' },
      body: data,
    })
    if (!response.ok) throw new Error((await response.json()).detail ?? 'Import failed.')
    return response.json()
  },
}
