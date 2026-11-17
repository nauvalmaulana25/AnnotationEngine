import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import type { LabelMeAnnotation, LabelMeShape } from '../../shared/types'

interface AnnotationState {
  currentImageId: number | null
  shapes: LabelMeShape[]
  selectedShapeIds: number[]
  tool: 'select' | 'bbox' | 'polygon' | 'keypoint' | 'pan'
  history: {
    past: LabelMeShape[][]
    future: LabelMeShape[][]
  }
  isLoading: boolean
  isSaving: boolean
  error: string | null
}

const initialState: AnnotationState = {
  currentImageId: null,
  shapes: [],
  selectedShapeIds: [],
  tool: 'select',
  history: { past: [], future: [] },
  isLoading: false,
  isSaving: false,
  error: null,
}

const MAX_HISTORY = 50

const annotationSlice = createSlice({
  name: 'annotation',
  initialState,
  reducers: {
    setCurrentImage: (state, action: PayloadAction<{ imageId: number; annotation: LabelMeAnnotation | null }>) => {
      state.currentImageId = action.payload.imageId
      state.shapes = action.payload.annotation?.shapes || []
      state.selectedShapeIds = []
      state.history = { past: [], future: [] }
    },
    clearCurrentImage: (state) => {
      state.currentImageId = null
      state.shapes = []
      state.selectedShapeIds = []
      state.history = { past: [], future: [] }
    },
    setTool: (state, action: PayloadAction<AnnotationState['tool']>) => {
      state.tool = action.payload
      state.selectedShapeIds = []
    },
    addShape: (state, action: PayloadAction<LabelMeShape>) => {
      // Push current state to history
      state.history.past.push([...state.shapes])
      if (state.history.past.length > MAX_HISTORY) {
        state.history.past.shift()
      }
      state.history.future = []
      
      state.shapes.push(action.payload)
    },
    updateShape: (state, action: PayloadAction<{ index: number; shape: Partial<LabelMeShape> }>) => {
      const { index, shape } = action.payload
      if (index >= 0 && index < state.shapes.length) {
        // Push current state to history
        state.history.past.push([...state.shapes])
        if (state.history.past.length > MAX_HISTORY) {
          state.history.past.shift()
        }
        state.history.future = []
        
        state.shapes[index] = { ...state.shapes[index], ...shape }
      }
    },
    deleteShape: (state, action: PayloadAction<number>) => {
      const index = action.payload
      if (index >= 0 && index < state.shapes.length) {
        // Push current state to history
        state.history.past.push([...state.shapes])
        if (state.history.past.length > MAX_HISTORY) {
          state.history.past.shift()
        }
        state.history.future = []
        
        state.shapes.splice(index, 1)
        state.selectedShapeIds = state.selectedShapeIds.filter(id => id !== index)
        // Adjust selected indices
        state.selectedShapeIds = state.selectedShapeIds.map(id => id > index ? id - 1 : id)
      }
    },
    deleteSelectedShapes: (state) => {
      if (state.selectedShapeIds.length === 0) return
      
      state.history.past.push([...state.shapes])
      if (state.history.past.length > MAX_HISTORY) {
        state.history.past.shift()
      }
      state.history.future = []
      
      // Sort indices descending to delete correctly
      const sortedIndices = [...state.selectedShapeIds].sort((a, b) => b - a)
      sortedIndices.forEach(index => {
        if (index >= 0 && index < state.shapes.length) {
          state.shapes.splice(index, 1)
        }
      })
      state.selectedShapeIds = []
    },
    selectShape: (state, action: PayloadAction<number>) => {
      const index = action.payload
      if (index >= 0 && index < state.shapes.length) {
        state.selectedShapeIds = [index]
      }
    },
    toggleShapeSelection: (state, action: PayloadAction<number>) => {
      const index = action.payload
      const currentIndex = state.selectedShapeIds.indexOf(index)
      if (currentIndex >= 0) {
        state.selectedShapeIds.splice(currentIndex, 1)
      } else {
        state.selectedShapeIds.push(index)
      }
    },
    clearSelection: (state) => {
      state.selectedShapeIds = []
    },
    setShapes: (state, action: PayloadAction<LabelMeShape[]>) => {
      state.shapes = action.payload
      state.selectedShapeIds = []
      state.history = { past: [], future: [] }
    },
    undo: (state) => {
      if (state.history.past.length === 0) return
      
      state.history.future.unshift([...state.shapes])
      state.shapes = state.history.past.pop()!
      state.selectedShapeIds = []
    },
    redo: (state) => {
      if (state.history.future.length === 0) return
      
      state.history.past.push([...state.shapes])
      state.shapes = state.history.future.shift()!
      state.selectedShapeIds = []
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },
    setSaving: (state, action: PayloadAction<boolean>) => {
      state.isSaving = action.payload
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload
    },
  },
})

export const {
  setCurrentImage,
  clearCurrentImage,
  setTool,
  addShape,
  updateShape,
  deleteShape,
  deleteSelectedShapes,
  selectShape,
  toggleShapeSelection,
  clearSelection,
  setShapes,
  undo,
  redo,
  setLoading,
  setSaving,
  setError,
} = annotationSlice.actions
export default annotationSlice.reducer