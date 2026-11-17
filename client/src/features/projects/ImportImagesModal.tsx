import { useState, useRef } from 'react'
import { useAppDispatch } from '@app/hooks'
import { openModal, closeModal } from '../ui/uiSlice'
import { Upload, X, Loader2, FileImage, Image as ImageIcon, CheckCircle, AlertCircle, Plus, Minus, FileText, FolderOpen } from 'lucide-react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

interface ImportImagesModalProps {
  projectId: number
  onClose: () => void
  onSuccess: () => void
}

export default function ImportImagesModal({ projectId, onClose, onSuccess }: ImportImagesModalProps) {
  const dispatch = useAppDispatch()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [split, setSplit] = useState<'train' | 'val' | 'test'>('train')
  const [isImporting, setIsImporting] = useState(false)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<'idle' | 'importing' | 'completed' | 'failed'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<{ imported: number; skipped: number } | null>(null)
  
  const handleFilesChange = (newFiles: FileList | File[]) => {
    const fileArray = Array.from(newFiles)
    const validFiles = fileArray.filter(f => {
      // Check MIME type first
      const mimeValid = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'].includes(f.type)
      // Fallback: check file extension if MIME type is empty or invalid
      const extValid = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'].some(ext => 
        f.name.toLowerCase().endsWith(ext)
      )
      return mimeValid || extValid
    })
    const invalidCount = fileArray.length - validFiles.length
    if (invalidCount > 0) {
      toast.error(`${invalidCount} file(s) skipped: unsupported format`)
    }
    setFiles(prev => [...prev, ...validFiles])
  }
  
  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }
  
  const clearFiles = () => {
    setFiles([])
  }
  
  const handleImport = async () => {
    if (files.length === 0) {
      toast.error('No files selected')
      return
    }
    
    setIsImporting(true)
    setStatus('importing')
    setProgress(0)
    setError(null)
    setResults(null)
    
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))
    formData.append('split', split)
    
    try {
      const response = await fetch(`/api/v1/projects/${projectId}/import-images`, {
        method: 'POST',
        body: formData,
      })
      
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Import failed' }))
        throw new Error(err.detail || 'Import failed')
      }
      
      const data = await response.json()
      setResults({ imported: data.imported, skipped: data.skipped })
      setStatus('completed')
      setIsImporting(false)
      toast.success(`Imported ${data.imported} images`)
      onSuccess()
    } catch (err) {
      setIsImporting(false)
      setStatus('failed')
      setError(err instanceof Error ? err.message : 'Import failed')
      toast.error('Failed to import images')
    }
  }
  
  const handleOpenImportLabels = () => {
    onClose()
    dispatch(openModal('importLabels'))
  }
  
  const handleFolderPick = async () => {
    try {
      // @ts-ignore - File System Access API
      if ('showDirectoryPicker' in window) {
        const handle = await (window as any).showDirectoryPicker({ mode: 'read' })
        const files: File[] = []
        
        const traverse = async (dirHandle: any, path = '') => {
          for await (const [name, entry] of dirHandle.entries()) {
            if (entry.kind === 'file') {
              const file = await entry.getFile()
              if (['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'].includes(file.type)) {
                Object.defineProperty(file, 'webkitRelativePath', { value: path ? `${path}/${name}` : name })
                files.push(file)
              }
            } else if (entry.kind === 'directory') {
              await traverse(entry, path ? `${path}/${name}` : name)
            }
          }
        }
        
        await traverse(handle)
        
        if (files.length > 0) {
          handleFilesChange(files)
          toast.success(`Selected ${files.length} images from folder`)
        } else {
          toast.error('No supported image files found in folder')
        }
      } else {
        // Fallback: trigger file input for multi-file selection
        fileInputRef.current?.click()
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        console.error('Folder pick failed:', err)
        toast.error('Folder selection failed. Please use file selection instead.')
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <ImageIcon className="w-6 h-6 text-primary-600" />
            Import Images
          </h2>
          <button onClick={onClose} disabled={isImporting} className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-50">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {status === 'idle' && (
            <>
              {/* Upload options */}
              <div className="space-y-4">
                {/* Option 1: Select multiple files (All browsers) */}
                <div className="border border-gray-200 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FileImage className="w-5 h-5 text-primary-600" />
                      <span className="font-medium text-gray-900">Select Multiple Images (All browsers)</span>
                    </div>
                    <span className="text-xs text-gray-500">Ctrl/Cmd + click for multiple</span>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={(e) => e.target.files && handleFilesChange(e.target.files)}
                    className="hidden"
                    id="file-input"
                  />
                  <label htmlFor="file-input" className="cursor-pointer w-full">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isImporting}
                      className="w-full btn-primary gap-2"
                    >
                      <Upload className="w-4 h-4" />
                      Browse Files
                    </button>
                  </label>
                  <p className="text-xs text-gray-500 mt-2 text-center">Select multiple image files (JPG, PNG, WebP, BMP, TIFF)</p>
                </div>
                
                {/* Option 2: Select folder (Chrome/Edge only) */}
                <div className="border border-gray-200 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FolderOpen className="w-5 h-5 text-primary-600" />
                      <span className="font-medium text-gray-900">Select Folder (Chrome/Edge)</span>
                    </div>
                    <span className="text-xs text-gray-500">Uses modern browser API</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleFolderPick}
                    disabled={isImporting}
                    className="w-full btn-secondary gap-2"
                  >
                    <FolderOpen className="w-4 h-4" />
                    Select Folder
                  </button>
                  <p className="text-xs text-gray-500 mt-2 text-center">Works in Chrome/Edge. In Firefox/Safari, opens file picker instead.</p>
                </div>
                
                {/* Option 3: Drag & drop zone */}
                <div
                  className={clsx(
                    'border-2 border-dashed rounded-xl p-8 text-center transition-colors',
                    files.length > 0 ? 'border-primary-300 bg-primary-50' : 'border-gray-200 hover:border-primary-300'
                  )}
                  onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('bg-primary-50') }}
                  onDragLeave={(e) => { e.currentTarget.classList.remove('bg-primary-50') }}
                  onDrop={(e) => {
                    e.preventDefault()
                    e.currentTarget.classList.remove('bg-primary-50')
                    handleFilesChange(e.dataTransfer.files)
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={(e) => e.target.files && handleFilesChange(e.target.files)}
                    className="hidden"
                    id="file-input-drop"
                  />
                  <label htmlFor="file-input-drop" className="cursor-pointer">
                    <div className="flex flex-col items-center gap-3">
                      <FileImage className="w-12 h-12 text-gray-400" />
                      <div>
                        <p className="text-lg font-medium text-gray-900">Drag & Drop Images or Folder Here</p>
                        <p className="text-gray-500">Supports multiple files (all browsers) and folders (Chrome/Edge)</p>
                      </div>
                      <p className="text-xs text-gray-400">JPG, PNG, WebP, BMP, TIFF</p>
                    </div>
                  </label>
                </div>
              </div>
              
              {/* File list */}
              {files.length > 0 && (
                <div className="space-y-2 max-h-64 overflow-y-auto border-t border-gray-200 pt-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium text-gray-900">{files.length} file(s) selected</h3>
                    <button onClick={clearFiles} className="text-sm text-gray-500 hover:text-gray-700">Clear all</button>
                  </div>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {files.map((file, idx) => (
                      <div key={idx} className="flex items-center gap-3 p-2 bg-gray-50 rounded-lg">
                        <FileImage className="w-5 h-5 text-gray-400" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
                          <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
                        </div>
                        <button onClick={() => removeFile(idx)} className="p-1 text-gray-400 hover:text-red-500">
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Split selection */}
              <div>
                <label className="label">Dataset Split</label>
                <div className="flex gap-2">
                  {(['train', 'val', 'test'] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => setSplit(s)}
                      className={clsx(
                        'flex-1 py-2 px-3 rounded-lg border-2 text-center font-medium transition-colors',
                        split === s
                          ? 'border-primary-600 bg-primary-50 text-primary-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      )}
                    >
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              
              {/* Import button */}
              <button
                onClick={handleImport}
                disabled={files.length === 0 || isImporting}
                className="w-full btn-primary gap-2"
              >
                <Upload className="w-4 h-4" />
                Import {files.length} Image{files.length !== 1 ? 's' : ''}
              </button>
            </>
          )}
          
          {status === 'importing' && (
            <div className="space-y-4 text-center">
              <Loader2 className="w-12 h-12 animate-spin text-primary-600 mx-auto" />
              <p className="text-gray-700">Importing images...</p>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-primary-600 h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
          
          {status === 'completed' && results && (
            <div className="space-y-4 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
                <CheckCircle className="w-8 h-8 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Import Completed!</h3>
              <div className="flex justify-center gap-6 text-sm">
                <div className="flex items-center gap-2 text-green-700">
                  <CheckCircle className="w-4 h-4" />
                  <span>{results.imported} imported</span>
                </div>
                {results.skipped > 0 && (
                  <div className="flex items-center gap-2 text-yellow-700">
                    <AlertCircle className="w-4 h-4" />
                    <span>{results.skipped} skipped</span>
                  </div>
                )}
              </div>
              
              {/* Ask to import labels */}
              <div className="border-t border-gray-200 pt-4">
                <p className="text-gray-600 mb-4">Would you like to import label annotations (LabelMe JSON files) for these images?</p>
                <div className="flex gap-3 justify-center">
                  <button
                    onClick={handleOpenImportLabels}
                    className="btn-primary gap-2"
                  >
                    <FileText className="w-4 h-4" />
                    Import Labels
                  </button>
                  <button
                    onClick={onClose}
                    className="btn-secondary"
                  >
                    Skip
                  </button>
                </div>
              </div>
            </div>
          )}
          
          {status === 'failed' && (
            <div className="space-y-4 text-center">
              <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto">
                <AlertCircle className="w-8 h-8 text-red-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Import Failed</h3>
              <p className="text-red-600">{error || 'Unknown error'}</p>
              <button onClick={() => { setStatus('idle'); setError(null); }} className="w-full btn-primary">Try Again</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

