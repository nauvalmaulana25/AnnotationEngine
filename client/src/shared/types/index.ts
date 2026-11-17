export interface User {
  id: number
  email: string
  is_active: boolean
  created_at: string
  hf_api_key_set?: boolean
}

export interface Token {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Project {
  id: number
  user_id: number
  name: string
  description: string | null
  base_path: string
  created_at: string
  updated_at: string
  image_count: number
}

export interface Image {
  id: number
  project_id: number
  filename: string
  relative_path: string
  width: number | null
  height: number | null
  file_size: number | null
  split: string
  imported_at: string
  has_annotation: boolean
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// LabelMe annotation types
export interface LabelMePoint {
  x: number
  y: number
}

export interface LabelMeShape {
  label: string
  points: number[][]
  group_id: number | null
  description: string
  shape_type: 'rectangle' | 'polygon' | 'point' | 'circle' | 'line'
  flags: Record<string, unknown>
  mask: unknown | null
}

export interface LabelMeAnnotation {
  version: string
  flags: Record<string, unknown>
  shapes: LabelMeShape[]
  imagePath: string
  imageData: string | null
  imageHeight: number
  imageWidth: number
}

export interface Annotation {
  id: number
  image_id: number
  data: LabelMeAnnotation
  version: number
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface Job {
  id: number
  project_id: number
  user_id: number
  job_type: 'grounding_dino' | 'mobile_sam' | 'dinov2_keypoint' | 'export'
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  payload: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface GroundingDinoRequest {
  project_id: number
  image_ids: number[]
  text_prompt: string
  conf_threshold: number
}

export interface MobileSamRequest {
  project_id: number
  image_ids: number[]
  boxes: number[][]
}

export interface DinoV2KeypointRequest {
  project_id: number
  target_image_ids: number[]
  reference_image_ids: number[]
  similarity_threshold: number
  consensus_votes: number
  nms_dist_pct: number
}

export interface ExportRequest {
  format: 'yolo' | 'coco' | 'both'
  split_ratios?: Record<string, number>
  include_bboxes: boolean
  include_polygons: boolean
  include_keypoints: boolean
}

export interface WebSocketMessage {
  job_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  current?: number
  total?: number
  message: string
}