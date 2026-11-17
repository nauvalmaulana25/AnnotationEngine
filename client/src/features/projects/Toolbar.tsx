import { useAppDispatch } from '@app/hooks'
import { setTool, undo, redo, clearSelection } from '../annotation/annotationSlice'
import { openModal } from '../ui/uiSlice'
import { MousePointer2, Square, PenTool, MapPin, Move, RotateCcw, RotateCw, Undo2, Redo2, Upload, Download, Zap, Box, Save, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'

interface ToolbarProps {
  project: { name: string; id: number }
  currentImageId: number | null
  selectedCount: number
  tool: 'select' | 'bbox' | 'polygon' | 'keypoint' | 'pan'
  onToolChange: (tool: 'select' | 'bbox' | 'polygon' | 'keypoint' | 'pan') => void
  onImportImages: () => void
  onImportLabels: () => void
  onExport: () => void
  onAutoAnnotate: () => void
  onSave: () => void
  isSaving: boolean
  onUndo: () => void
  onRedo: () => void
  canUndo: boolean
  canRedo: boolean
}

export default function Toolbar({
  project,
  currentImageId,
  selectedCount,
  tool,
  onToolChange,
  onImportImages,
  onImportLabels,
  onExport,
  onAutoAnnotate,
  onSave,
  isSaving,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
}: ToolbarProps) {
  const tools: { id: ToolbarProps['tool']; icon: React.ReactNode; label: string; shortcut: string }[] = [
    { id: 'select', icon: <MousePointer2 className="w-5 h-5" />, label: 'Select', shortcut: 'V' },
    { id: 'bbox', icon: <Square className="w-5 h-5" />, label: 'Bounding Box', shortcut: 'B' },
    { id: 'polygon', icon: <PenTool className="w-5 h-5" />, label: 'Polygon', shortcut: 'P' },
    { id: 'keypoint', icon: <MapPin className="w-5 h-5" />, label: 'Keypoint', shortcut: 'K' },
    { id: 'pan', icon: <Move className="w-5 h-5" />, label: 'Pan', shortcut: 'H' },
  ]
  
  return (
    <div className="flex flex-wrap items-center gap-4 px-4 py-3 bg-white border-b border-gray-200 shadow-sm">
      {/* Project info */}
      <div className="flex items-center gap-3 mr-4 border-r border-gray-200 pr-4">
        <h2 className="text-lg font-semibold text-gray-900 truncate max-w-[200px]">{project.name}</h2>
        <span className="px-2 py-0.5 text-xs rounded bg-primary-100 text-primary-700">ID: {project.id}</span>
      </div>
      
      {/* Tools */}
      <div className="flex items-center gap-1 mr-4 border-r border-gray-200 pr-4">
        {tools.map(({ id, icon, label, shortcut }) => (
          <button
            key={id}
            onClick={() => onToolChange(id)}
            className={clsx(
              'p-2 rounded-lg transition-colors relative group',
              tool === id
                ? 'bg-primary-100 text-primary-700'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            )}
            title={`${label} (${shortcut})`}
          >
            {icon}
            <span className="absolute bottom-0 right-0 text-[10px] text-gray-400 bg-gray-100 px-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">
              {shortcut}
            </span>
          </button>
        ))}
      </div>
      
      {/* Actions */}
      <div className="flex items-center gap-2 mr-4 border-r border-gray-200 pr-4">
        <button
          onClick={onImportImages}
          className="btn-secondary gap-2"
          title="Import Images"
        >
          <Upload className="w-4 h-4" />
          <span className="hidden sm:inline">Import Images</span>
        </button>
        <button
          onClick={onImportLabels}
          className="btn-secondary gap-2"
          title="Import Labels"
        >
          <Box className="w-4 h-4" />
          <span className="hidden sm:inline">Import Labels</span>
        </button>
      </div>
      
      {/* Auto-annotate & Export */}
      <div className="flex items-center gap-2 mr-4 border-r border-gray-200 pr-4">
        <button
          onClick={onAutoAnnotate}
          className="btn-primary gap-2"
          title="Auto Annotate"
        >
          <Zap className="w-4 h-4" />
          <span className="hidden sm:inline">Auto Annotate</span>
        </button>
        <button
          onClick={onExport}
          className="btn-secondary gap-2"
          title="Export Dataset"
        >
          <Download className="w-4 h-4" />
          <span className="hidden sm:inline">Export</span>
        </button>
      </div>
      
      {/* History & Save */}
      <div className="flex items-center gap-2">
        <button
          onClick={onUndo}
          disabled={!canUndo}
          className={clsx('p-2 rounded-lg transition-colors', canUndo ? 'text-gray-500 hover:bg-gray-100' : 'text-gray-300 cursor-not-allowed')}
          title="Undo (Ctrl+Z)"
        >
          <Undo2 className="w-5 h-5" />
        </button>
        <button
          onClick={onRedo}
          disabled={!canRedo}
          className={clsx('p-2 rounded-lg transition-colors', canRedo ? 'text-gray-500 hover:bg-gray-100' : 'text-gray-300 cursor-not-allowed')}
          title="Redo (Ctrl+Shift+Z)"
        >
          <Redo2 className="w-5 h-5" />
        </button>
        <button
          onClick={onSave}
          disabled={isSaving || !currentImageId}
          className={clsx('btn-primary gap-2', isSaving ? 'opacity-75' : '')}
          title="Save Annotation (Ctrl+S)"
        >
          {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          <span className="hidden sm:inline">{isSaving ? 'Saving...' : 'Save'}</span>
        </button>
      </div>
    </div>
  )
}