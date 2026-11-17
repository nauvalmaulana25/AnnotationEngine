import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@app/hooks'
import { fetchProjects, createProject, setCurrentProject, deleteProject } from './projectsSlice'
import { openModal, closeModal, closeAllModals } from '../ui/uiSlice'
import { FolderOpen, Plus, ArrowRight, ChevronRight, Loader2, AlertCircle, CheckCircle, Database, Download, Upload, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { useEffect } from 'react'

export default function LandingPage() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { items: projects, status } = useAppSelector((state) => state.projects)
  const { modals } = useAppSelector((state) => state.ui)
  const [newProjectName, setNewProjectName] = useState('')
  const [customPath, setCustomPath] = useState('')
  const [useCustomPath, setUseCustomPath] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [showPathSelector, setShowPathSelector] = useState(false)
  
  // Database export/import state
  const [isExporting, setIsExporting] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  
  useEffect(() => {
    console.log('LandingPage mounted, status:', status)
    dispatch(fetchProjects())
  }, [dispatch])
  
  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newProjectName.trim()) return
    
    setIsCreating(true)
    try {
      const basePath = useCustomPath && customPath.trim() ? customPath.trim() : undefined
      const result = await dispatch(createProject({
        name: newProjectName.trim(),
        base_path: basePath
      })).unwrap()
      
      dispatch(setCurrentProject(result.id))
      dispatch(closeModal('createProject'))
      setNewProjectName('')
      setCustomPath('')
      setUseCustomPath(false)
      toast.success('Project created successfully')
      
      // Navigate to project page and open import images modal
      dispatch(closeAllModals())
      navigate(`/projects/${result.id}`)
      dispatch(openModal('importImages'))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create project')
    } finally {
      setIsCreating(false)
    }
  }
  
  const handleLoadProject = (projectId: number) => {
    dispatch(setCurrentProject(projectId))
    navigate(`/projects/${projectId}`)
  }
  
  const handleDeleteProject = async (projectId: number, projectName: string) => {
    if (!confirm(`Are you sure you want to delete "${projectName}"? This will permanently delete the project, all its images, and annotations. This action cannot be undone.`)) {
      return
    }
    
    try {
      await dispatch(deleteProject(projectId)).unwrap()
      toast.success(`Project "${projectName}" deleted successfully`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete project')
    }
  }
  
  const handleSelectPath = async () => {
    try {
      // @ts-ignore - File System Access API
      const handle = await window.showDirectoryPicker({
        mode: 'readwrite',
        startIn: 'documents'
      })
      const path = handle.name
      setShowPathSelector(true)
    } catch (err) {
      console.log('Directory picker cancelled or not supported')
      setShowPathSelector(true)
    }
  }
  
  const handleExportDatabase = async () => {
    setIsExporting(true)
    try {
      const response = await fetch('/api/v1/database/export')
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Export failed' }))
        throw new Error(err.detail)
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'annotation_engine.db'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success('Database exported successfully')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export database')
    } finally {
      setIsExporting(false)
    }
  }
  
  const handleImportFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setImportFile(e.target.files[0])
    }
  }
  
  const handleImportDatabase = async () => {
    if (!importFile) {
      toast.error('Please select a database file')
      return
    }
    
    if (!importFile.name.endsWith('.db') && !importFile.name.endsWith('.sqlite') && !importFile.name.endsWith('.sqlite3')) {
      toast.error('File must be a SQLite database (.db, .sqlite, .sqlite3)')
      return
    }
    
    if (!confirm('This will REPLACE the current database. All existing projects and annotations will be lost. Continue?')) {
      return
    }
    
    setIsImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', importFile)
      
      const response = await fetch('/api/v1/database/import', {
        method: 'POST',
        body: formData,
      })
      
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Import failed' }))
        throw new Error(err.detail)
      }
      
      toast.success('Database imported successfully. Please refresh the page.')
      dispatch(closeModal('importDatabase'))
      setImportFile(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to import database')
    } finally {
      setIsImporting(false)
    }
  }
  
  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    )
  }
  
  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-3 mb-6">
          <div className="w-16 h-16 rounded-2xl bg-primary-600 flex items-center justify-center">
            <FolderOpen className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-4xl font-bold text-gray-900">AnnotationEngine</h1>
        </div>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          Hybrid image annotation with Grounding DINO, MobileSAM & DINOv2.
          Create projects, annotate images, and export datasets in YOLO/COCO formats.
        </p>
      </div>
      
      {/* Action Buttons */}
      <div className="grid md:grid-cols-2 gap-6 mb-12">
        {/* Create New Project */}
        <button
          onClick={() => dispatch(openModal('createProject'))}
          className={clsx(
            'p-8 border-2 rounded-2xl transition-all hover:shadow-lg',
            'border-primary-200 bg-primary-50 hover:bg-primary-100',
            'flex flex-col items-center gap-4 cursor-pointer'
          )}
        >
          <div className="w-14 h-14 rounded-xl bg-primary-600 flex items-center justify-center">
            <Plus className="w-7 h-7 text-white" />
          </div>
          <div className="text-center">
            <h3 className="text-xl font-semibold text-gray-900">Create New Project</h3>
            <p className="text-gray-600 mt-1">Start a new annotation project</p>
          </div>
          <ArrowRight className="w-5 h-5 text-primary-600" />
        </button>
        
        {/* Load Existing Project */}
        <button
          onClick={() => dispatch(openModal('projectSelector'))}
          disabled={projects.length === 0}
          className={clsx(
            'p-8 border-2 rounded-2xl transition-all hover:shadow-lg',
            'flex flex-col items-center gap-4 cursor-pointer',
            projects.length > 0
              ? 'border-gray-200 bg-white hover:bg-gray-50'
              : 'border-gray-100 bg-gray-50 text-gray-400 cursor-not-allowed'
          )}
        >
          <div className={clsx(
            'w-14 h-14 rounded-xl flex items-center justify-center',
            projects.length > 0 ? 'bg-gray-100' : 'bg-gray-50'
          )}>
            <FolderOpen className={clsx('w-7 h-7', projects.length > 0 ? 'text-gray-700' : 'text-gray-400')} />
          </div>
          <div className="text-center">
            <h3 className={clsx('text-xl font-semibold', projects.length > 0 ? 'text-gray-900' : 'text-gray-400')}>
              Load Existing Project
            </h3>
            <p className={clsx('text-gray-600 mt-1', projects.length > 0 ? '' : 'text-gray-400')}>
              {projects.length > 0 ? `Continue with ${projects.length} project${projects.length !== 1 ? 's' : ''}` : 'No projects found'}
            </p>
          </div>
          <ChevronRight className={clsx('w-5 h-5', projects.length > 0 ? 'text-gray-400' : 'text-gray-300')} />
        </button>
      </div>
      
      {/* Database Management */}
      <div className="grid md:grid-cols-2 gap-4 mb-12">
        <button
          onClick={handleExportDatabase}
          disabled={isExporting}
          className="p-6 border-2 border-gray-200 rounded-2xl hover:border-primary-300 hover:bg-primary-50 transition-colors flex flex-col items-center gap-3 cursor-pointer"
        >
          <div className="w-14 h-14 rounded-xl bg-green-100 flex items-center justify-center">
            <Database className="w-7 h-7 text-green-700" />
          </div>
          <div className="text-center">
            <h3 className="text-xl font-semibold text-gray-900">Export Database</h3>
            <p className="text-gray-600 mt-1">Download SQLite database file to share with team</p>
          </div>
          <Download className="w-5 h-5 text-green-700" />
        </button>
        
        <button
          onClick={() => dispatch(openModal('importDatabase'))}
          disabled={isImporting}
          className="p-6 border-2 border-gray-200 rounded-2xl hover:border-primary-300 hover:bg-primary-50 transition-colors flex flex-col items-center gap-3 cursor-pointer"
        >
          <div className="w-14 h-14 rounded-xl bg-blue-100 flex items-center justify-center">
            <Upload className="w-7 h-7 text-blue-700" />
          </div>
          <div className="text-center">
            <h3 className="text-xl font-semibold text-gray-900">Import Database</h3>
            <p className="text-gray-600 mt-1">Load a shared database file to continue annotation work</p>
          </div>
          <Upload className="w-5 h-5 text-blue-700" />
        </button>
      </div>
      
      {/* Recent Projects */}
      {projects.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Projects</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.slice(0, 6).map((project) => (
              <div key={project.id} className="border border-gray-200 rounded-xl hover:border-primary-300 hover:bg-primary-50 transition-colors">
                <button
                  onClick={() => handleLoadProject(project.id)}
                  className="w-full p-4 text-left"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-gray-900 truncate">{project.name}</h3>
                      <p className="text-sm text-gray-500 mt-1">{project.image_count} images</p>
                      <p className="text-xs text-gray-400 mt-1">
                        Updated {new Date(project.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
                  </div>
                </button>
                <button
                  onClick={() => handleDeleteProject(project.id, project.name)}
                  className="w-full p-2 border-t border-gray-100 text-red-600 hover:bg-red-50 rounded-b-xl transition-colors flex items-center justify-center gap-1 text-sm"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>Delete</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Create Project Modal */}
      {modals.createProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">Create New Project</h2>
            
            <form onSubmit={handleCreateProject}>
              <div className="space-y-4">
                <div>
                  <label className="label">Project Name</label>
                  <input
                    type="text"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    placeholder="my_project"
                    className="input"
                    required
                    autoFocus
                  />
                </div>
                
                <div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={useCustomPath}
                      onChange={(e) => setUseCustomPath(e.target.checked)}
                      className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm text-gray-700">Use custom project location</span>
                  </label>
                </div>
                
                {useCustomPath && (
                  <div>
                    <label className="label">Custom Path (optional)</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={customPath}
                        onChange={(e) => setCustomPath(e.target.value)}
                        placeholder="~/Documents/AnnotationEngine/Projects"
                        className="input flex-1"
                      />
                      <button
                        type="button"
                        onClick={handleSelectPath}
                        className="btn-secondary"
                      >
                        Browse
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Default: ~/Documents/AnnotationEngine/Projects
                    </p>
                  </div>
                )}
              </div>
              
              <div className="flex justify-end gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => { dispatch(closeModal('createProject')); setNewProjectName(''); setCustomPath(''); setUseCustomPath(false); }}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !newProjectName.trim()}
                  className="btn-primary"
                >
                  {isCreating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    'Create Project'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      
      {/* Project Selector Modal */}
      {modals.projectSelector && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold text-gray-900">Select Project</h2>
              <button
                onClick={() => dispatch(closeModal('projectSelector'))}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            
            {projects.length === 0 ? (
              <div className="text-center py-12">
                <AlertCircle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500 mb-4">No projects found</p>
                <button
                  onClick={() => { dispatch(closeModal('projectSelector')); dispatch(openModal('createProject')) }}
                  className="btn-primary"
                >
                  Create Your First Project
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {projects.map((project) => (
                  <div key={project.id} className="w-full">
                    <button
                      onClick={() => { handleLoadProject(project.id); dispatch(closeModal('projectSelector')) }}
                      className="w-full p-4 border border-gray-200 rounded-xl hover:border-primary-300 hover:bg-primary-50 transition-colors text-left flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <CheckCircle className="w-5 h-5 text-primary-600" />
                        <span className="font-medium text-gray-900">{project.name}</span>
                      </div>
                      <p className="text-sm text-gray-500">{project.image_count} images • Updated {new Date(project.updated_at).toLocaleDateString()}</p>
                      <ChevronRight className="w-5 h-5 text-gray-400" />
                    </button>
                    <button
                      onClick={() => handleDeleteProject(project.id, project.name)}
                      className="w-full p-2 mt-1 text-red-600 hover:bg-red-50 rounded-lg transition-colors flex items-center justify-center gap-1 text-sm"
                    >
                      <Trash2 className="w-4 h-4" />
                      <span>Delete</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* Import Database Modal */}
      {modals.importDatabase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-6 flex items-center gap-2">
              <Upload className="w-6 h-6 text-blue-600" />
              Import Database
            </h2>
            <p className="text-gray-600 mb-6">
              Select a SQLite database file (.db, .sqlite, .sqlite3) exported from another AnnotationEngine instance.
              <strong className="text-red-600"> This will replace all current projects and annotations.</strong>
            </p>
            
            <div className="space-y-4">
              <div>
                <label className="label">Database File</label>
                <div className="border-2 border-dashed rounded-xl p-6 text-center">
                  <input
                    type="file"
                    accept=".db,.sqlite,.sqlite3"
                    onChange={handleImportFileChange}
                    className="hidden"
                    id="db-import-file"
                    disabled={isImporting}
                  />
                  <label htmlFor="db-import-file" className="cursor-pointer flex flex-col items-center gap-2">
                    <Database className="w-12 h-12 text-gray-400" />
                    <div>
                      <p className="text-lg font-medium text-gray-900">Drag & drop or click to browse</p>
                      <p className="text-gray-500">.db, .sqlite, .sqlite3 files</p>
                    </div>
                    {importFile && (
                      <p className="text-sm text-green-600 flex items-center gap-1">
                        <CheckCircle className="w-4 h-4" />
                        {importFile.name}
                      </p>
                    )}
                  </label>
                </div>
              </div>
              
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => { dispatch(closeModal('importDatabase')); setImportFile(null); }}
                  disabled={isImporting}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  onClick={handleImportDatabase}
                  disabled={isImporting || !importFile}
                  className="btn-primary gap-2"
                >
                  {isImporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
                  {isImporting ? 'Importing...' : 'Import Database'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}