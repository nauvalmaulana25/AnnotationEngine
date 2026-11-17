import { useState } from 'react'
import { useAppDispatch } from '@app/hooks'
import { startExport } from '../autoAnnotate/autoAnnotateAPI'
import { openModal, closeModal } from '../ui/uiSlice'
import { Download, X, Loader2, CheckCircle, AlertCircle, FileText, Code } from 'lucide-react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

interface ExportModalProps {
  projectId: number
  onClose: () => void
}

export default function ExportModal({ projectId, onClose }: ExportModalProps) {
  const dispatch = useAppDispatch()
  const [format, setFormat] = useState<'yolo' | 'coco' | 'both'>('both')
  const [splitRatios, setSplitRatios] = useState({ train: 0.7, val: 0.2, test: 0.1 })
  const [includeBboxes, setIncludeBboxes] = useState(true)
  const [includePolygons, setIncludePolygons] = useState(true)
  const [includeKeypoints, setIncludeKeypoints] = useState(true)
  const [isExporting, setIsExporting] = useState(false)
  const [jobId, setJobId] = useState<number | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  
  const handleExport = async () => {
    setIsExporting(true)
    setStatus('running')
    setProgress(0)
    setError(null)
    setDownloadUrl(null)
    
    try {
      const result = await startExport(projectId, {
        format,
        split_ratios: splitRatios,
        include_bboxes: includeBboxes,
        include_polygons: includePolygons,
        include_keypoints: includeKeypoints,
      })
      
      setJobId(result.job_id)
      pollJobStatus(result.job_id)
    } catch (err) {
      setIsExporting(false)
      setStatus('failed')
      setError(err instanceof Error ? err.message : 'Export failed')
      toast.error('Failed to start export')
    }
  }
  
  const pollJobStatus = async (jobId: number) => {
    const checkStatus = async () => {
      try {
        const response = await fetch(`/api/v1/auto-annotate/jobs/${jobId}`)
        if (!response.ok) throw new Error('Failed to get status')
        const data = await response.json()
        
        setProgress(data.progress)
        
        if (data.status === 'completed') {
          setStatus('completed')
          setIsExporting(false)
          // Get download URL
          const results = await fetch(`/api/v1/auto-annotate/jobs/${jobId}/results`)
          if (results.ok) {
            const resultData = await results.json()
            if (resultData.output_path) {
              setDownloadUrl(`/api/v1/auto-annotate/jobs/${jobId}/download`)
            }
          }
          toast.success('Export completed!')
        } else if (data.status === 'failed') {
          setStatus('failed')
          setIsExporting(false)
          setError(data.error || 'Export failed')
          toast.error('Export failed')
        } else {
          // Still running, poll again
          setTimeout(checkStatus, 1000)
        }
      } catch (err) {
        setStatus('failed')
        setIsExporting(false)
        setError('Failed to check status')
      }
    }
    
    checkStatus()
  }
  
  const handleDownload = () => {
    if (downloadUrl) {
      window.open(downloadUrl, '_blank')
    }
  }
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <Download className="w-6 h-6 text-primary-600" />
            Export Dataset
          </h2>
          <button onClick={onClose} className="p-2 rounded-lg text-gray-500 hover:bg-gray-100">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-4 space-y-6">
          {status === 'idle' && (
            <>
              <div>
                <label className="label">Export Format</label>
                <div className="grid grid-cols-3 gap-2">
                  {(['yolo', 'coco', 'both'] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFormat(f)}
                      className={clsx(
                        'p-3 rounded-lg border-2 text-center transition-colors',
                        format === f
                          ? 'border-primary-600 bg-primary-50 text-primary-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      )}
                    >
                      <div className="font-medium capitalize">{f.toUpperCase()}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        {f === 'yolo' ? '.txt files' : f === 'coco' ? '.json file' : 'Both formats'}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              
              <div>
                <label className="label">Train/Val/Test Split</label>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="text-xs text-gray-500">Train: {Math.round(splitRatios.train * 100)}%</label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(splitRatios.train * 100)}
                      onChange={(e) => setSplitRatios({ ...splitRatios, train: parseInt(e.target.value) / 100 })}
                      className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500">Val: {Math.round(splitRatios.val * 100)}%</label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(splitRatios.val * 100)}
                      onChange={(e) => setSplitRatios({ ...splitRatios, val: parseInt(e.target.value) / 100 })}
                      className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500">Test: {Math.round(splitRatios.test * 100)}%</label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(splitRatios.test * 100)}
                      onChange={(e) => setSplitRatios({ ...splitRatios, test: parseInt(e.target.value) / 100 })}
                      className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-1">Ratios will be normalized to sum to 100%</p>
              </div>
              
              <div className="space-y-2">
                <label className="label">Include in Export</label>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={includeBboxes} onChange={(e) => setIncludeBboxes(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
                    <span className="text-sm text-gray-700">Bounding Boxes</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={includePolygons} onChange={(e) => setIncludePolygons(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
                    <span className="text-sm text-gray-700">Polygons / Segmentation</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={includeKeypoints} onChange={(e) => setIncludeKeypoints(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
                    <span className="text-sm text-gray-700">Keypoints</span>
                  </label>
                </div>
              </div>
              
              <button
                onClick={handleExport}
                disabled={isExporting}
                className="w-full btn-primary gap-2"
              >
                <Download className="w-4 h-4" />
                Start Export
              </button>
            </>
          )}
          
          {status === 'running' && (
            <div className="space-y-4 text-center">
              <Loader2 className="w-12 h-12 animate-spin text-primary-600 mx-auto" />
              <p className="text-gray-700">Exporting dataset...</p>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-sm text-gray-500">{progress}%</p>
            </div>
          )}
          
          {status === 'completed' && (
            <div className="space-y-4 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
                <CheckCircle className="w-8 h-8 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Export Completed!</h3>
              <p className="text-gray-600">Your dataset is ready to download.</p>
              <button onClick={handleDownload} className="w-full btn-primary gap-2">
                <Download className="w-4 h-4" />
                Download ZIP
              </button>
              <button onClick={() => { setStatus('idle'); setJobId(null); setProgress(0); setDownloadUrl(null); }} className="w-full btn-secondary">
                Export Again
              </button>
            </div>
          )}
          
          {status === 'failed' && (
            <div className="space-y-4 text-center">
              <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto">
                <AlertCircle className="w-8 h-8 text-red-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Export Failed</h3>
              <p className="text-red-600">{error || 'Unknown error'}</p>
              <button onClick={() => { setStatus('idle'); setError(null); }} className="w-full btn-primary">
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}