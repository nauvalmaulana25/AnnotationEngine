import { useState, useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '@app/hooks'
import { startGroundingDino, startMobileSam, startDinoV2Keypoint } from '../autoAnnotate/autoAnnotateAPI'
import { openModal } from '../ui/uiSlice'
import { Zap, Box, MapPin, Loader2, X, CheckCircle, AlertCircle, ChevronRight, ChevronLeft, Settings, Image as ImageIcon } from 'lucide-react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

interface AutoAnnotatePanelProps {
  projectId: number
  selectedImageIds: number[]
  onClose: () => void
}

const TABS = [
  { id: 'groundingDino', label: 'Grounding DINO', icon: <Box className="w-5 h-5" />, desc: 'Object detection with text prompts' },
  { id: 'mobileSam', label: 'MobileSAM', icon: <ImageIcon className="w-5 h-5" />, desc: 'Instance segmentation from boxes' },
  { id: 'dinov2Keypoint', label: 'DINOv2 Keypoint', icon: <MapPin className="w-5 h-5" />, desc: 'Zero-shot keypoint transfer' },
] as const

type TabId = typeof TABS[number]['id']

export default function AutoAnnotatePanel({ projectId, selectedImageIds, onClose }: AutoAnnotatePanelProps) {
  const dispatch = useAppDispatch()
  const { groundingDino, mobileSam, dinov2Keypoint } = useAppSelector((state) => state.autoAnnotate)
  const [activeTab, setActiveTab] = useState<TabId>('groundingDino')
  const [gdPrompt, setGdPrompt] = useState('')
  const [gdThreshold, setGdThreshold] = useState(0.3)
  const [dvThreshold, setDvThreshold] = useState(0.4)
  const [dvConsensus, setDvConsensus] = useState(2)
  const [dvNms, setDvNms] = useState(0.025)
  const [referenceImages, setReferenceImages] = useState<number[]>([])
  
  const currentJob = useAppSelector((state) => state.autoAnnotate[activeTab])
  
  const handleRunGroundingDino = async () => {
    if (!gdPrompt.trim()) {
      toast.error('Enter a text prompt')
      return
    }
    if (selectedImageIds.length === 0) {
      toast.error('Select at least one image')
      return
    }
    try {
      const jobId = await startGroundingDino(projectId, selectedImageIds, gdPrompt, gdThreshold)
      dispatch({ type: 'autoAnnotate/setJobStarted', payload: { type: 'groundingDino', jobId, params: { prompt: gdPrompt, threshold: gdThreshold } } })
      toast.success('Grounding DINO job started')
    } catch (err) {
      toast.error('Failed to start job')
    }
  }
  
  const handleRunMobileSam = async () => {
    if (selectedImageIds.length === 0) {
      toast.error('Select at least one image')
      return
    }
    try {
      const jobId = await startMobileSam(projectId, selectedImageIds, [])
      dispatch({ type: 'autoAnnotate/setJobStarted', payload: { type: 'mobileSam', jobId, params: {} } })
      toast.success('MobileSAM job started')
    } catch (err) {
      toast.error('Failed to start job')
    }
  }
  
  const handleRunDinoV2 = async () => {
    if (selectedImageIds.length === 0) {
      toast.error('Select target images')
      return
    }
    if (referenceImages.length === 0) {
      toast.error('Select reference images with keypoints')
      return
    }
    try {
      const jobId = await startDinoV2Keypoint(projectId, selectedImageIds, referenceImages, dvThreshold, dvConsensus, dvNms)
      dispatch({ type: 'autoAnnotate/setJobStarted', payload: { type: 'dinov2Keypoint', jobId, params: { threshold: dvThreshold, consensus: dvConsensus, nms: dvNms } } })
      toast.success('DINOv2 keypoint job started')
    } catch (err) {
      toast.error('Failed to start job')
    }
  }
  
  const renderTabContent = () => {
    switch (activeTab) {
      case 'groundingDino':
        return (
          <div className="space-y-4">
            <div>
              <label className="label">Text Prompt</label>
              <input
                type="text"
                value={gdPrompt}
                onChange={(e) => setGdPrompt(e.target.value)}
                placeholder="e.g., person, car, dog, cup"
                className="input"
              />
              <p className="text-xs text-gray-500 mt-1">Describe objects to detect. End with period for better results.</p>
            </div>
            
            <div>
              <label className="label">Confidence Threshold: {gdThreshold.toFixed(1)}</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={gdThreshold}
                onChange={(e) => setGdThreshold(parseFloat(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
              />
            </div>
            
            <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              <p className="font-medium">Selected: {selectedImageIds.length} image(s)</p>
              <p>Grounding DINO will detect objects matching your prompt.</p>
            </div>
            
            <button
              onClick={handleRunGroundingDino}
              disabled={currentJob.status === 'running' || !gdPrompt.trim() || selectedImageIds.length === 0}
              className="w-full btn-primary gap-2"
            >
              {currentJob.status === 'running' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running... {currentJob.progress}%
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Run Grounding DINO
                </>
              )}
            </button>
            
            {currentJob.status === 'completed' && currentJob.results && (
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-green-800 font-medium flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Completed! Found detections in {currentJob.results.length} images.
                </p>
                <button className="mt-2 text-sm text-green-700 hover:underline">View Results</button>
              </div>
            )}
            
            {currentJob.status === 'failed' && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-800 font-medium flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Failed: {currentJob.error}
                </p>
              </div>
            )}
          </div>
        )
      
      case 'mobileSam':
        return (
          <div className="space-y-4">
            <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              <p className="font-medium">Selected: {selectedImageIds.length} image(s)</p>
              <p>MobileSAM segments objects using bounding boxes from Grounding DINO or manual boxes.</p>
            </div>
            
            <button
              onClick={handleRunMobileSam}
              disabled={currentJob.status === 'running' || selectedImageIds.length === 0}
              className="w-full btn-primary gap-2"
            >
              {currentJob.status === 'running' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running... {currentJob.progress}%
                </>
              ) : (
                <>
                  <ImageIcon className="w-4 h-4" />
                  Run MobileSAM
                </>
              )}
            </button>
            
            {currentJob.status === 'completed' && currentJob.results && (
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-green-800 font-medium flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Completed! Generated {currentJob.results.length} segmentation masks.
                </p>
              </div>
            )}
            
            {currentJob.status === 'failed' && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-800 font-medium flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Failed: {currentJob.error}
                </p>
              </div>
            )}
          </div>
        )
      
      case 'dinov2Keypoint':
        return (
          <div className="space-y-4">
            <div>
              <label className="label">Reference Images (with keypoints)</label>
              <div className="border border-gray-200 rounded-lg p-3 min-h-[80px] max-h-40 overflow-y-auto">
                {referenceImages.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-4">No reference images selected</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {referenceImages.map((id, idx) => (
                      <span key={id} className="px-2 py-1 bg-primary-100 text-primary-700 rounded text-sm flex items-center gap-1">
                        Ref {idx + 1}
                        <button onClick={() => setReferenceImages(referenceImages.filter(r => r !== id))} className="hover:text-primary-900">×</button>
                      </span>
                    ))}
                  </div>
                )}
                <button
                  onClick={() => {
                    // Open image selector for references
                    // For now, just add from selected
                    const newRefs = selectedImageIds.filter(id => !referenceImages.includes(id))
                    setReferenceImages([...referenceImages, ...newRefs])
                  }}
                  className="mt-2 text-sm text-primary-600 hover:underline"
                >
                  + Add from selected ({selectedImageIds.filter(id => !referenceImages.includes(id)).length})
                </button>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Similarity Threshold: {dvThreshold.toFixed(2)}</label>
                <input type="range" min="0" max="1" step="0.05" value={dvThreshold} onChange={(e) => setDvThreshold(parseFloat(e.target.value))} className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600" />
              </div>
              <div>
                <label className="label">Consensus Votes: {dvConsensus}</label>
                <input type="range" min="1" max="5" step="1" value={dvConsensus} onChange={(e) => setDvConsensus(parseInt(e.target.value))} className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600" />
              </div>
            </div>
            
            <div>
              <label className="label">NMS Distance %: {dvNms.toFixed(3)}</label>
              <input type="range" min="0" max="0.1" step="0.005" value={dvNms} onChange={(e) => setDvNms(parseFloat(e.target.value))} className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600" />
            </div>
            
            <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              <p className="font-medium">Target: {selectedImageIds.length} image(s) | References: {referenceImages.length} image(s)</p>
              <p>DINOv2 transfers keypoints from references to targets using visual correspondence.</p>
            </div>
            
            <button
              onClick={handleRunDinoV2}
              disabled={currentJob.status === 'running' || selectedImageIds.length === 0 || referenceImages.length === 0}
              className="w-full btn-primary gap-2"
            >
              {currentJob.status === 'running' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running... {currentJob.progress}%
                </>
              ) : (
                <>
                  <MapPin className="w-4 h-4" />
                  Run DINOv2 Keypoint
                </>
              )}
            </button>
            
            {currentJob.status === 'completed' && currentJob.results && (
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-green-800 font-medium flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Completed! Transferred keypoints to {currentJob.results.length} images.
                </p>
              </div>
            )}
            
            {currentJob.status === 'failed' && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-800 font-medium flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Failed: {currentJob.error}
                </p>
              </div>
            )}
          </div>
        )
    }
  }
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <Zap className="w-6 h-6 text-primary-600" />
            Auto Annotate
          </h2>
          <button onClick={onClose} className="p-2 rounded-lg text-gray-500 hover:bg-gray-100">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* Tabs */}
        <div className="flex border-b border-gray-200 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              )}
              title={tab.desc}
            >
              {tab.icon}
              {tab.label}
{(activeTab === 'groundingDino' && groundingDino.status === 'running') ||
                (activeTab === 'mobileSam' && mobileSam.status === 'running') ||
                (activeTab === 'dinov2Keypoint' && dinov2Keypoint.status === 'running') && (
                <Loader2 className="w-4 h-4 animate-spin" />
              )}
            </button>
          ))}
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {renderTabContent()}
        </div>
      </div>
    </div>
  )
}