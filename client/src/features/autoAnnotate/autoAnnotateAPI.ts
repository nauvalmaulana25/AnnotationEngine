import type { GroundingDinoRequest, MobileSamRequest, DinoV2KeypointRequest } from '@shared/types'

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

export async function startGroundingDino(
  projectId: number,
  imageIds: number[],
  textPrompt: string,
  confThreshold: number
): Promise<number> {
  const payload: GroundingDinoRequest = { project_id: projectId, image_ids: imageIds, text_prompt: textPrompt, conf_threshold: confThreshold }
  const result = await request<{ job_id: number }>('/auto-annotate/grounding-dino', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return result.job_id
}

export async function startMobileSam(
  projectId: number,
  imageIds: number[],
  boxes: number[][]
): Promise<number> {
  const payload: MobileSamRequest = { project_id: projectId, image_ids: imageIds, boxes }
  const result = await request<{ job_id: number }>('/auto-annotate/mobile-sam', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return result.job_id
}

export async function startDinoV2Keypoint(
  projectId: number,
  targetImageIds: number[],
  referenceImageIds: number[],
  similarityThreshold: number,
  consensusVotes: number,
  nmsDistPct: number
): Promise<number> {
  const payload: DinoV2KeypointRequest = {
    project_id: projectId,
    target_image_ids: targetImageIds,
    reference_image_ids: referenceImageIds,
    similarity_threshold: similarityThreshold,
    consensus_votes: consensusVotes,
    nms_dist_pct: nmsDistPct,
  }
  const result = await request<{ job_id: number }>('/auto-annotate/dinov2-keypoint', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return result.job_id
}

export async function getJobStatus(jobId: number) {
  return request(`/auto-annotate/jobs/${jobId}`)
}

export async function getJobResults(jobId: number) {
  return request(`/auto-annotate/jobs/${jobId}/results`)
}

export async function startExport(projectId: number, payload: {
  format: 'yolo' | 'coco' | 'both'
  split_ratios?: Record<string, number>
  include_bboxes: boolean
  include_polygons: boolean
  include_keypoints: boolean
}) {
  return request<{ job_id: number }>(`/auto-annotate/export`, {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, ...payload }),
  })
}