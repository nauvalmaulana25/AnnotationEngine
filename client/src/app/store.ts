import { configureStore } from '@reduxjs/toolkit'
import projectsReducer from '../features/projects/projectsSlice'
import imagesReducer from '../features/images/imagesSlice'
import annotationReducer from '../features/annotation/annotationSlice'
import autoAnnotateReducer from '../features/autoAnnotate/autoAnnotateSlice'
import exportReducer from '../features/export/exportSlice'
import uiReducer from '../features/ui/uiSlice'

export const store = configureStore({
  reducer: {
    projects: projectsReducer,
    images: imagesReducer,
    annotation: annotationReducer,
    autoAnnotate: autoAnnotateReducer,
    export: exportReducer,
    ui: uiReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['annotation/setShapes'],
        ignoredPaths: ['annotation.shapes'],
      },
    }),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch