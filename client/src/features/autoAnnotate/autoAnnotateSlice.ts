import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface AutoAnnotateJobState {
  jobId: number | null
  status: 'idle' | 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  current: number
  total: number
  message: string
  params: Record<string, unknown> | null
  results: unknown[] | null
  error: string | null
}

const initialJobState: AutoAnnotateJobState = {
  jobId: null,
  status: 'idle',
  progress: 0,
  current: 0,
  total: 0,
  message: '',
  params: null,
  results: null,
  error: null,
}

interface AutoAnnotateState {
  groundingDino: AutoAnnotateJobState
  mobileSam: AutoAnnotateJobState
  dinov2Keypoint: AutoAnnotateJobState
}

const initialState: AutoAnnotateState = {
  groundingDino: { ...initialJobState },
  mobileSam: { ...initialJobState },
  dinov2Keypoint: { ...initialJobState },
}

const autoAnnotateSlice = createSlice({
  name: 'autoAnnotate',
  initialState,
  reducers: {
    setJobStarted: (state, action: PayloadAction<{ type: keyof AutoAnnotateState; jobId: number; params: Record<string, unknown> }>) => {
      const { type, jobId, params } = action.payload
      state[type] = {
        ...initialJobState,
        jobId,
        status: 'pending',
        params,
        message: 'Job queued...',
      }
    },
    setJobProgress: (state, action: PayloadAction<{ type: keyof AutoAnnotateState; progress: number; current: number; total: number; message: string }>) => {
      const { type, progress, current, total, message } = action.payload
      state[type] = {
        ...state[type],
        status: 'running',
        progress,
        current,
        total,
        message,
      }
    },
    setJobCompleted: (state, action: PayloadAction<{ type: keyof AutoAnnotateState; results: unknown[] }>) => {
      const { type, results } = action.payload
      state[type] = {
        ...state[type],
        status: 'completed',
        progress: 100,
        results,
        message: 'Completed successfully',
      }
    },
    setJobFailed: (state, action: PayloadAction<{ type: keyof AutoAnnotateState; error: string }>) => {
      const { type, error } = action.payload
      state[type] = {
        ...state[type],
        status: 'failed',
        error,
        message: `Failed: ${error}`,
      }
    },
    resetJob: (state, action: PayloadAction<keyof AutoAnnotateState>) => {
      state[action.payload] = { ...initialJobState }
    },
    clearResults: (state, action: PayloadAction<keyof AutoAnnotateState>) => {
      state[action.payload].results = null
    },
  },
})

export const {
  setJobStarted,
  setJobProgress,
  setJobCompleted,
  setJobFailed,
  resetJob,
  clearResults,
} = autoAnnotateSlice.actions
export default autoAnnotateSlice.reducer