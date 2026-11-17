import type { LabelMeAnnotation } from '@shared/types'

const API_BASE = '/api/v1'

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  
  return response.json()
}

export async function fetchAnnotation(imageId: number): Promise<LabelMeAnnotation> {
  return request<LabelMeAnnotation>(`/annotations/images/${imageId}`)
}

export async function saveAnnotation(imageId: number, annotation: LabelMeAnnotation): Promise<void> {
  await request(`/annotations/images/${imageId}`, {
    method: 'PUT',
    body: JSON.stringify({ data: annotation }),
  })
}

export async function deleteAnnotation(imageId: number): Promise<void> {
  await request(`/annotations/images/${imageId}`, {
    method: 'DELETE',
  })
}