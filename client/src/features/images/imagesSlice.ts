import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import type { Image, PaginatedResponse } from '../../shared/types'

interface ImagesState {
  byProjectId: Record<number, {
    items: Image[]
    pagination: PaginatedResponse<Image> | null
    selectedIds: number[]
    status: 'idle' | 'loading' | 'succeeded' | 'failed'
    error: string | null
  }>
}

const initialState: ImagesState = {
  byProjectId: {},
}

const getProjectState = (state: ImagesState, projectId: number) => {
  if (!state.byProjectId[projectId]) {
    state.byProjectId[projectId] = {
      items: [],
      pagination: null,
      selectedIds: [],
      status: 'idle',
      error: null,
    }
  }
  return state.byProjectId[projectId]
}

export const fetchImages = createAsyncThunk(
  'images/fetch',
  async ({ projectId, page = 1, pageSize = 50, split }: { projectId: number; page?: number; pageSize?: number; split?: string }, { rejectWithValue }) => {
    try {
      const params = new URLSearchParams()
      params.append('page', page.toString())
      params.append('page_size', pageSize.toString())
      if (split) params.append('split', split)
      
      const response = await fetch(`/api/v1/projects/${projectId}/images?${params}`)
      if (!response.ok) throw new Error('Failed to fetch images')
      const data = await response.json()
      return { projectId, ...data }
    } catch (err) {
      return rejectWithValue(err instanceof Error ? err.message : 'Failed to fetch images')
    }
  }
)

const imagesSlice = createSlice({
  name: 'images',
  initialState,
  reducers: {
    toggleImageSelection: (state, action: PayloadAction<{ projectId: number; imageId: number }>) => {
      const projectState = getProjectState(state, action.payload.projectId)
      const index = projectState.selectedIds.indexOf(action.payload.imageId)
      if (index >= 0) {
        projectState.selectedIds.splice(index, 1)
      } else {
        projectState.selectedIds.push(action.payload.imageId)
      }
    },
    selectAllImages: (state, action: PayloadAction<{ projectId: number; imageIds: number[] }>) => {
      const projectState = getProjectState(state, action.payload.projectId)
      projectState.selectedIds = action.payload.imageIds
    },
    clearSelection: (state, action: PayloadAction<number>) => {
      const projectState = getProjectState(state, action.payload)
      projectState.selectedIds = []
    },
    setImages: (state, action: PayloadAction<{ projectId: number; data: PaginatedResponse<Image> }>) => {
      const projectState = getProjectState(state, action.payload.projectId)
      projectState.items = action.payload.data.items
      projectState.pagination = action.payload.data
      projectState.status = 'succeeded'
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchImages.pending, (state, action) => {
        const projectState = getProjectState(state, action.meta.arg.projectId)
        projectState.status = 'loading'
        projectState.error = null
      })
      .addCase(fetchImages.fulfilled, (state, action) => {
        const projectState = getProjectState(state, action.payload.projectId)
        projectState.items = action.payload.items
        projectState.pagination = {
          items: action.payload.items,
          total: action.payload.total,
          page: action.payload.page,
          page_size: action.payload.page_size,
          total_pages: action.payload.total_pages,
        }
        projectState.status = 'succeeded'
      })
      .addCase(fetchImages.rejected, (state, action) => {
        const projectState = getProjectState(state, action.meta.arg.projectId)
        projectState.status = 'failed'
        projectState.error = action.payload as string
      })
  },
})

export const { toggleImageSelection, selectAllImages, clearSelection, setImages } = imagesSlice.actions
export default imagesSlice.reducer