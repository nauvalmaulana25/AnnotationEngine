import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@app/hooks'
import { fetchProject, fetchProjectImages, setCurrentProject, deleteImage, importImages, importLabels } from './projectsSlice'
import { fetchImages, toggleImageSelection, selectAllImages, clearSelection } from '../images/imagesSlice'
import { setCurrentImage, clearCurrentImage, addShape, updateShape, deleteShape, deleteSelectedShapes, selectShape, toggleShapeSelection, clearSelection as clearAnnotationSelection, undo, redo, setTool, setShapes } from '../annotation/annotationSlice'
import { openModal, closeModal, setActiveImageDrawer } from '../ui/uiSlice'
import { fetchAnnotation, saveAnnotation } from '../annotation/annotationAPI'
import type { LabelMeShape } from '@shared/types'
import { FolderOpen, Image, Upload, Download, Settings, Plus, Trash2, ChevronLeft, ChevronRight, Grid, List, Search, Filter, MoreVertical, Check, X, Loader2, Eye, EyeOff, RotateCcw, RotateCw, Undo2, Redo2, Move, MousePointer2, Square, PenTool, MapPin, Copy, Delete } from 'lucide-react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import ImageGrid from './ImageGrid'
import LabelUCanvas from './LabelUCanvas'
import Toolbar from './Toolbar'
import Sidebar from './Sidebar'
import AutoAnnotatePanel from '../autoAnnotate/AutoAnnotatePanel'
import ExportModal from '../export/ExportModal'
import ImportImagesModal from './ImportImagesModal'
import ImportLabelsModal from './ImportLabelsModal'

export default function ProjectView() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const dispatch = useAppDispatch()
  const pid = parseInt(projectId || '0', 10)
  
  const { currentProject, items: projects } = useAppSelector((state) => state.projects)
  const { items: images, pagination, selectedIds, status: imagesStatus } = useAppSelector((state) => state.images.byProjectId[pid] || { items: [], pagination: null, selectedIds: [], status: 'idle' })
  const { currentImageId, shapes, selectedShapeIds, tool, isLoading: annotationLoading, isSaving } = useAppSelector((state) => state.annotation)
  const { modals } = useAppSelector((state) => state.ui)
  
  const project = currentProject?.id === pid ? currentProject : projects.find(p => p.id === pid)
  
  useEffect(() => {
    if (pid) {
      dispatch(fetchProject(pid))
      dispatch(fetchImages({ projectId: pid, page: 1 }))
    }
  }, [pid, dispatch])
  
  useEffect(() => {
    if (currentImageId) {
      loadAnnotation(currentImageId)
    } else {
      dispatch(clearCurrentImage())
    }
  }, [currentImageId, dispatch])
  
  const loadAnnotation = async (imageId: number) => {
    dispatch(setCurrentImage({ imageId, annotation: null }))
    try {
      const response = await fetch(`/api/v1/annotations/images/${imageId}`)
      if (response.ok) {
        const data = await response.json()
        dispatch(setCurrentImage({ imageId, annotation: data.data }))
      }
    } catch (err) {
      console.error('Failed to load annotation:', err)
    }
  }
  
  const handleShapeUpdate = (index: number, shape: Partial<LabelMeShape>) => {
    dispatch(updateShape({ index, shape }))
  }
  
  const handleShapeAdd = (shape: LabelMeShape) => {
    dispatch(addShape(shape))
  }
  
  const handleShapeDelete = (index: number) => {
    dispatch(deleteShape(index))
  }
  
  const handleShapeSelect = (index: number) => {
    dispatch(selectShape(index))
  }
  
  const handleShapeToggleSelect = (index: number) => {
    dispatch(toggleShapeSelection(index))
  }
  
  const handleClearSelection = () => {
    dispatch(clearAnnotationSelection())
  }
  
  const handleUndo = () => {
    dispatch(undo())
  }
  
  const handleRedo = () => {
    dispatch(redo())
  }
  
  const handleToolChange = (tool: 'select' | 'bbox' | 'polygon' | 'keypoint' | 'pan') => {
    dispatch(setTool(tool))
  }
  
  const handleSaveAnnotation = async () => {
    if (!currentImageId) return
    try {
      await saveAnnotation(currentImageId, { version: "5.4.1", flags: {}, shapes, imagePath: "", imageData: null, imageHeight: 0, imageWidth: 0 })
      toast.success('Annotation saved')
    } catch (err) {
      toast.error('Failed to save annotation')
    }
  }
  
  const handleImageClick = (imageId: number, e: React.MouseEvent) => {
    if (e.ctrlKey || e.metaKey) {
      dispatch(toggleImageSelection({ projectId: pid, imageId }))
    } else if (e.shiftKey && selectedIds.length > 0) {
      // Range selection
      const currentIndex = images.findIndex(img => img.id === imageId)
      const lastIndex = images.findIndex(img => img.id === selectedIds[selectedIds.length - 1])
      const start = Math.min(currentIndex, lastIndex)
      const end = Math.max(currentIndex, lastIndex)
      const rangeIds = images.slice(start, end + 1).map(img => img.id)
      dispatch(selectAllImages({ projectId: pid, imageIds: rangeIds }))
    } else {
      dispatch(setCurrentImage({ imageId, annotation: null }))
      loadAnnotation(imageId)
    }
  }
  
  const handleDeleteSelected = async () => {
    if (selectedIds.length === 0) return
    if (!confirm(`Delete ${selectedIds.length} image(s)?`)) return
    
    for (const imageId of selectedIds) {
      await dispatch(deleteImage({ projectId: pid, imageId })).unwrap()
    }
    dispatch(clearSelection(pid))
    toast.success('Images deleted')
  }
  
  const handleKeyboardShortcuts = (e: KeyboardEvent) => {
    // Prevent shortcuts when typing in inputs
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
      e.preventDefault()
      if (e.shiftKey) {
        dispatch(redo())
      } else {
        dispatch(undo())
      }
    }
    
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (selectedShapeIds.length > 0) {
        e.preventDefault()
        dispatch(deleteSelectedShapes())
      }
    }
    
    if (e.key === 'Escape') {
      dispatch(clearAnnotationSelection())
    }
    
    // Tool shortcuts
    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
      switch (e.key.toLowerCase()) {
        case 'v': dispatch(setTool('select')); break
        case 'b': dispatch(setTool('bbox')); break
        case 'p': dispatch(setTool('polygon')); break
        case 'k': dispatch(setTool('keypoint')); break
        case 'h': dispatch(setTool('pan')); break
      }
    }
  }
  
  useEffect(() => {
    window.addEventListener('keydown', handleKeyboardShortcuts)
    return () => window.removeEventListener('keydown', handleKeyboardShortcuts)
  }, [dispatch, selectedShapeIds])
  
  if (!project) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    )
  }
  
  return (
    <div className="h-full flex flex-col">
      {/* Top Toolbar */}
      <Toolbar
        project={project}
        currentImageId={currentImageId}
        selectedCount={selectedIds.length}
        tool={tool}
        onToolChange={handleToolChange}
        onImportImages={() => dispatch(openModal('importImages'))}
        onImportLabels={() => dispatch(openModal('importLabels'))}
        onExport={() => dispatch(openModal('export'))}
        onAutoAnnotate={() => dispatch(openModal('autoAnnotate'))}
        onSave={handleSaveAnnotation}
        isSaving={isSaving}
        onUndo={handleUndo}
        onRedo={handleRedo}
        canUndo={useAppSelector(s => s.annotation.history.past.length > 0)}
        canRedo={useAppSelector(s => s.annotation.history.future.length > 0)}
      />
      
      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar - Image Grid */}
        <Sidebar
          images={images}
          selectedIds={selectedIds}
          currentImageId={currentImageId}
          status={imagesStatus}
          pagination={pagination}
          onImageClick={handleImageClick}
          onLoadMore={() => {
            if (pagination && pagination.page < pagination.total_pages) {
              dispatch(fetchImages({ projectId: pid, page: pagination.page + 1 }))
            }
          }}
          onSelectionChange={(ids) => dispatch(selectAllImages({ projectId: pid, imageIds: ids }))}
          onClearSelection={() => dispatch(clearSelection(pid))}
        />
        
        {/* Canvas Area */}
        <div className="flex-1 flex flex-col min-w-0 relative">
          {currentImageId ? (
            <LabelUCanvas
              imageId={currentImageId}
              shapes={shapes}
              selectedShapeIds={selectedShapeIds}
              tool={tool}
              onShapeAdd={handleShapeAdd}
              onShapeUpdate={handleShapeUpdate}
              onShapeDelete={handleShapeDelete}
              onShapeSelect={handleShapeSelect}
              onShapeToggleSelect={handleShapeToggleSelect}
              onClearSelection={handleClearSelection}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center bg-gray-50">
              <div className="text-center">
                <Image className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900">No image selected</h3>
                <p className="text-gray-500 mt-1">Click an image from the sidebar to start annotating</p>
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Modals */}
      {modals.importImages && (
        <ImportImagesModal
          projectId={pid}
          onClose={() => dispatch(closeModal('importImages'))}
          onSuccess={() => {
            dispatch(fetchProject(pid))
            dispatch(fetchImages({ projectId: pid, page: 1 }))
          }}
        />
      )}
      
      {modals.importLabels && (
        <ImportLabelsModal
          projectId={pid}
          onClose={() => dispatch(closeModal('importLabels'))}
          onSuccess={() => {
            dispatch(fetchProject(pid))
          }}
        />
      )}
      
      {modals.export && (
        <ExportModal
          projectId={pid}
          onClose={() => dispatch(closeModal('export'))}
        />
      )}
      
      {modals.autoAnnotate.open && (
        <AutoAnnotatePanel
          projectId={pid}
          selectedImageIds={selectedIds.length > 0 ? selectedIds : images.map(i => i.id)}
          onClose={() => dispatch(closeModal('autoAnnotate'))}
        />
      )}
    </div>
  )
}