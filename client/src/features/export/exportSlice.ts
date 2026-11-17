import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface ExportState {
  jobId: number | null
  status: 'idle' | 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  current: number
  total: number
  message: string
  format: 'yolo' | 'coco' | 'both' | null
  downloadUrl: string | null
  error: string | null
}

const initialState: ExportState = {
  jobId: null,
  status: 'idle',
  progress: 0,
  current: 0,
  total: 0,
  message: '',
  format: null,
  downloadUrl: null,
  error: null,
}

const exportSlice = createSlice({
  name: 'export',
  initialState,
  reducers: {
    setExportStarted: (state, action: PayloadAction<{ jobId: number; format: 'yolo' | 'coco' | 'both' }>) => {
      state.jobId = action.payload.jobId
      state.format = action.payload.format
      state.status = 'pending'
      state.progress = 0
      state.message = 'Export queued...'
      state.downloadUrl = null
      state.error = null
    },
    setExportProgress: (state, action: PayloadAction<{ progress: number; current: number; total: number; message: string }>) => {
      state.status = 'running'
      state.progress = action.payload.progress
      state.current = action.payload.current
      state.total = action.payload.total
      state.message = action.payload.message
    },
    setExportCompleted: (state, action: PayloadAction<{ downloadUrl: string }>) => {
      state.status = 'completed'
      state.progress = 100
      state.downloadUrl = action.payload.downloadUrl
      state.message = 'Export completed'
    },
    setExportFailed: (state, action: PayloadAction<{ error: string }>) => {
      state.status = 'failed'
      state.error = action.payload.error
      state.message = `Export failed: ${action.payload.error}`
    },
    resetExport: (state) => {
      Object.assign(state, initialState)
    },
  },
})

export const {
  setExportStarted,
  setExportProgress,
  setExportCompleted,
  setExportFailed,
  resetExport,
} = exportSlice.actions
export default exportSlice.reducer