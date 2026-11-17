import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import api from '../../shared/utils/api'
import type { Project, Image, PaginatedResponse } from '../../shared/types'

interface ProjectsState {
  items: Project[]
  currentProjectId: number | null
  currentProject: Project | null
  status: 'idle' | 'loading' | 'succeeded' | 'failed'
  error: string | null
}

const initialState: ProjectsState = {
  items: [],
  currentProjectId: null,
  currentProject: null,
  status: 'idle',
  error: null,
}

export const fetchProjects = createAsyncThunk(
  'projects/fetchAll',
  async (_, { rejectWithValue }) => {
    try {
      const response = await api.get<Project[]>('/projects')
      return response.data
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to fetch projects')
    }
  }
)

export const createProject = createAsyncThunk(
  'projects/create',
  async (data: { name: string; description?: string; base_path?: string }, { rejectWithValue }) => {
    try {
      const response = await api.post<Project>('/projects', data)
      return response.data
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to create project')
    }
  }
)

export const fetchProject = createAsyncThunk(
  'projects/fetchOne',
  async (projectId: number, { rejectWithValue }) => {
    try {
      const response = await api.get<Project>(`/projects/${projectId}`)
      return response.data
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to fetch project')
    }
  }
)

export const updateProject = createAsyncThunk(
  'projects/update',
  async ({ projectId, data }: { projectId: number; data: Partial<Project> }, { rejectWithValue }) => {
    try {
      const response = await api.put<Project>(`/projects/${projectId}`, data)
      return response.data
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to update project')
    }
  }
)

export const deleteProject = createAsyncThunk(
  'projects/delete',
  async (projectId: number, { rejectWithValue }) => {
    try {
      await api.delete(`/projects/${projectId}`)
      return projectId
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to delete project')
    }
  }
)

export const importImages = createAsyncThunk(
  'projects/importImages',
  async ({ projectId, files, split }: { projectId: number; files: File[]; split: string }, { rejectWithValue }) => {
    try {
      const formData = new FormData()
      files.forEach((file) => formData.append('files', file))
      formData.append('split', split)
      
      const response = await api.post<{ imported: number; skipped: number; images: Image[] }>(
        `/projects/${projectId}/import-images`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      return { projectId, ...response.data }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to import images')
    }
  }
)

export const importLabels = createAsyncThunk(
  'projects/importLabels',
  async ({ projectId, files }: { projectId: number; files: File[] }, { rejectWithValue }) => {
    try {
      const formData = new FormData()
      files.forEach((file) => formData.append('files', file))
      
      const response = await api.post<{ imported: number; skipped: number; errors: string[] }>(
        `/projects/${projectId}/import-labels`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      return response.data
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to import labels')
    }
  }
)

export const fetchProjectImages = createAsyncThunk(
  'projects/fetchImages',
  async ({ projectId, page = 1, pageSize = 50, split }: { projectId: number; page?: number; pageSize?: number; split?: string }, { rejectWithValue }) => {
    try {
      const params = new URLSearchParams()
      params.append('page', page.toString())
      params.append('page_size', pageSize.toString())
      if (split) params.append('split', split)
      
      const response = await api.get<PaginatedResponse<Image>>(`/projects/${projectId}/images?${params}`)
      return { projectId, ...response.data }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to fetch images')
    }
  }
)

export const deleteImage = createAsyncThunk(
  'projects/deleteImage',
  async ({ projectId, imageId }: { projectId: number; imageId: number }, { rejectWithValue }) => {
    try {
      await api.delete(`/projects/${projectId}/images/${imageId}`)
      return { projectId, imageId }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      return rejectWithValue(error.response?.data?.detail || 'Failed to delete image')
    }
  }
)

const projectsSlice = createSlice({
  name: 'projects',
  initialState,
  reducers: {
    setCurrentProject: (state, action: PayloadAction<number | null>) => {
      state.currentProjectId = action.payload
      state.currentProject = action.payload ? state.items.find(p => p.id === action.payload) || null : null
    },
    clearError: (state) => {
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // Fetch all projects
      .addCase(fetchProjects.pending, (state) => {
        state.status = 'loading'
        state.error = null
      })
      .addCase(fetchProjects.fulfilled, (state, action) => {
        state.status = 'succeeded'
        state.items = action.payload
      })
      .addCase(fetchProjects.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.payload as string
      })
      // Create project
      .addCase(createProject.fulfilled, (state, action) => {
        state.items.unshift(action.payload)
      })
      // Fetch project
      .addCase(fetchProject.fulfilled, (state, action) => {
        const index = state.items.findIndex(p => p.id === action.payload.id)
        if (index >= 0) {
          state.items[index] = action.payload
        } else {
          state.items.push(action.payload)
        }
        // Always update currentProject when fetching a project
        state.currentProject = action.payload
      })
      // Update project
      .addCase(updateProject.fulfilled, (state, action) => {
        const index = state.items.findIndex(p => p.id === action.payload.id)
        if (index >= 0) {
          state.items[index] = action.payload
        }
        // Always update currentProject when updating a project
        state.currentProject = action.payload
      })
      // Delete project
      .addCase(deleteProject.fulfilled, (state, action) => {
        state.items = state.items.filter(p => p.id !== action.payload)
        if (state.currentProjectId === action.payload) {
          state.currentProjectId = null
          state.currentProject = null
        }
      })
      // Import images
      .addCase(importImages.fulfilled, (state, action) => {
        if (state.currentProjectId === action.payload.projectId && state.currentProject) {
          state.currentProject.image_count += action.payload.imported
        }
        const proj = state.items.find(p => p.id === action.payload.projectId)
        if (proj) {
          proj.image_count += action.payload.imported
        }
      })
      // Delete image
      .addCase(deleteImage.fulfilled, (state, action) => {
        if (state.currentProjectId === action.payload.projectId && state.currentProject) {
          state.currentProject.image_count = Math.max(0, state.currentProject.image_count - 1)
        }
        const proj = state.items.find(p => p.id === action.payload.projectId)
        if (proj) {
          proj.image_count = Math.max(0, proj.image_count - 1)
        }
      })
  },
})

export const { setCurrentProject, clearError } = projectsSlice.actions
export default projectsSlice.reducer