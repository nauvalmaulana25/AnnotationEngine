import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface UIState {
  sidebarOpen: boolean
  modals: {
    createProject: boolean
    importImages: boolean
    importLabels: boolean
    export: boolean
    autoAnnotate: { open: boolean; tab: 'groundingDino' | 'mobileSam' | 'dinov2Keypoint' }
    projectSelector: boolean
    importDatabase: boolean
  }
  toasts: Array<{ id: string; message: string; type: 'success' | 'error' | 'info' | 'loading' }>
  activeImageDrawer: boolean
}

const initialState: UIState = {
  sidebarOpen: true,
  modals: {
    createProject: false,
    importImages: false,
    importLabels: false,
    export: false,
    autoAnnotate: { open: false, tab: 'groundingDino' },
    projectSelector: false,
    importDatabase: false,
  },
  toasts: [],
  activeImageDrawer: false,
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen
    },
    setSidebarOpen: (state, action: PayloadAction<boolean>) => {
      state.sidebarOpen = action.payload
    },
    openModal: (state, action: PayloadAction<keyof UIState['modals']>) => {
      const modalKey = action.payload
      if (modalKey === 'autoAnnotate') {
        state.modals.autoAnnotate.open = true
      } else {
        state.modals[modalKey] = true
      }
    },
    closeModal: (state, action: PayloadAction<keyof UIState['modals']>) => {
      const modalKey = action.payload
      if (modalKey === 'autoAnnotate') {
        state.modals.autoAnnotate.open = false
      } else {
        state.modals[modalKey] = false
      }
    },
    closeAllModals: (state) => {
      (Object.keys(state.modals) as Array<keyof typeof state.modals>).forEach((key) => {
        if (key === 'autoAnnotate') {
          state.modals.autoAnnotate.open = false
        } else {
          state.modals[key] = false
        }
      })
    },
    setAutoAnnotateTab: (state, action: PayloadAction<'groundingDino' | 'mobileSam' | 'dinov2Keypoint'>) => {
      state.modals.autoAnnotate.tab = action.payload
    },
    addToast: (state, action: PayloadAction<{ message: string; type: 'success' | 'error' | 'info' | 'loading' }>) => {
      const id = Math.random().toString(36).substr(2, 9)
      state.toasts.push({ id, ...action.payload })
    },
    removeToast: (state, action: PayloadAction<string>) => {
      state.toasts = state.toasts.filter((t) => t.id !== action.payload)
    },
    setActiveImageDrawer: (state, action: PayloadAction<boolean>) => {
      state.activeImageDrawer = action.payload
    },
  },
})

export const {
  toggleSidebar,
  setSidebarOpen,
  openModal,
  closeModal,
  closeAllModals,
  setAutoAnnotateTab,
  addToast,
  removeToast,
  setActiveImageDrawer,
} = uiSlice.actions
export default uiSlice.reducer