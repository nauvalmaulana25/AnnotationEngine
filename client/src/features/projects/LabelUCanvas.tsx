import { useEffect, useRef, useCallback, useState } from 'react'
import { useImageAnnotator, type ImageAnnotatorOptions } from '@labelu/image-annotator-react/src/hooks/useImageAnnotator'
import { Annotator } from '@labelu/image'
import type { ToolName, AnnotationData } from '@labelu/image'
import type { LabelMeShape } from '@shared/types'
import { useAppDispatch } from '@app/hooks'
import { setShapes } from '../annotation/annotationSlice'

const TOOL_MAP: Record<string, ToolName> = {
  select: 'rect' as ToolName,
  bbox: 'rect' as ToolName,
  polygon: 'polygon' as ToolName,
  keypoint: 'point' as ToolName,
  pan: 'rect' as ToolName,
}

function labelMeShapeToLabelU(shape: LabelMeShape, index: number, toolName: ToolName) {
  const base = {
    id: String(index),
    label: shape.label,
    order: index,
    valid: true,
    visible: true,
  }

  switch (toolName) {
    case 'rect': {
      const [[x1, y1], [x2, y2]] = shape.points
      return {
        ...base,
        x: Math.min(x1, x2),
        y: Math.min(y1, y2),
        width: Math.abs(x2 - x1),
        height: Math.abs(y2 - y1),
      }
    }
    case 'point': {
      const [x, y] = shape.points[0]
      return { ...base, x, y }
    }
    case 'polygon': {
      return {
        ...base,
        points: shape.points.flat(),
      }
    }
    default:
      return base
  }
}

function labelUToLabelMeShape(data: any, toolName: ToolName): LabelMeShape {
  switch (toolName) {
    case 'rect': {
      const x = data.x ?? 0
      const y = data.y ?? 0
      const width = data.width ?? 0
      const height = data.height ?? 0
      return {
        label: data.label ?? '',
        points: [[x, y], [x + width, y + height]],
        group_id: null,
        description: '',
        shape_type: 'rectangle',
        flags: {},
        mask: null,
      }
    }
    case 'point': {
      return {
        label: data.label ?? '',
        points: [[data.x ?? 0, data.y ?? 0]],
        group_id: null,
        description: '',
        shape_type: 'point',
        flags: {},
        mask: null,
      }
    }
    case 'polygon': {
      const points: number[] = data.points ?? []
      const pointPairs: number[][] = []
      for (let i = 0; i < points.length; i += 2) {
        pointPairs.push([points[i], points[i + 1]])
      }
      return {
        label: data.label ?? '',
        points: pointPairs,
        group_id: null,
        description: '',
        shape_type: 'polygon',
        flags: {},
        mask: null,
      }
    }
    default:
      return {
        label: '',
        points: [],
        group_id: null,
        description: '',
        shape_type: 'polygon',
        flags: {},
        mask: null,
      }
  }
}

interface LabelUCanvasProps {
  imageId: number
  shapes: LabelMeShape[]
  selectedShapeIds: number[]
  tool: 'select' | 'bbox' | 'polygon' | 'keypoint' | 'pan'
  onShapeAdd: (shape: LabelMeShape) => void
  onShapeUpdate: (index: number, shape: Partial<LabelMeShape>) => void
  onShapeDelete: (index: number) => void
  onShapeSelect: (index: number) => void
  onShapeToggleSelect: (index: number) => void
  onClearSelection: () => void
}

export default function LabelUCanvas({
  imageId,
  shapes,
  selectedShapeIds,
  tool,
  onShapeAdd,
  onShapeUpdate,
  onShapeDelete,
  onShapeSelect,
  onShapeToggleSelect,
  onClearSelection,
}: LabelUCanvasProps) {
  const dispatch = useAppDispatch()
  const containerRef = useRef<HTMLDivElement>(null)
  const engineRef = useRef<Annotator | null>(null)
  const imageLoadedRef = useRef(false)
  const prevShapesRef = useRef<LabelMeShape[]>([])
  const isUpdatingRef = useRef(false)
  const annotationsLoadedRef = useRef(false)
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })

  const imageUrl = `/api/v1/images/${imageId}/file`

  const rectData = shapes
    .filter((s) => s.shape_type === 'rectangle')
    .map((s, i) => labelMeShapeToLabelU(s, i, 'rect' as ToolName))
  
  const pointData = shapes
    .filter((s) => s.shape_type === 'point')
    .map((s, i) => labelMeShapeToLabelU(s, i, 'point' as ToolName))
  
  const polygonData = shapes
    .filter((s) => s.shape_type === 'polygon')
    .map((s, i) => labelMeShapeToLabelU(s, i, 'polygon' as ToolName))

  const options: ImageAnnotatorOptions = {
    width: containerSize.width || 800,
    height: containerSize.height || 600,
    image: { url: imageUrl, rotate: 0 },
    strokeWidth: 2,
    fillOpacity: 0.1,
    strokeOpacity: 1,
    showOrder: false,
    rect: { labels: [] },
    point: { labels: [] },
    polygon: { labels: [] },
  }

  const engine = useImageAnnotator(containerRef, options)
  
  // Sync engine ref
  useEffect(() => {
    engineRef.current = engine
  }, [engine])

  // Handle container resize
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      
      const { width, height } = entry.contentRect
      console.log('[LabelUCanvas] Container resize:', width, height)
      setContainerSize({ width, height })
    })
    
    resizeObserver.observe(container)
    return () => resizeObserver.disconnect()
  }, [])

  // Initialize engine and set up event listeners
  useEffect(() => {
    if (!engine) return
    
    console.log('[LabelUCanvas] Engine initialized')
    imageLoadedRef.current = true

    // Load the image - wait for backgroundRenderer to be ready
    const loadImageAsync = async () => {
      // Wait for backgroundRenderer to be initialized
      let retries = 0
      while (!engine.backgroundRenderer && retries < 50) {
        await new Promise(resolve => setTimeout(resolve, 50))
        retries++
      }
      
      if (!engine.backgroundRenderer) {
        console.error('[LabelUCanvas] backgroundRenderer not initialized after retries')
        return
      }
      
      try {
        await engine.loadImage(imageUrl, { rotate: 0 })
        console.log('[LabelUCanvas] Image loaded, calling fit()')
        engine.fit()
        engine.center()
        
        // Load initial annotation data AFTER image is loaded (loadImage calls clearData internally)
        console.log('[LabelUCanvas] Loading annotation data')
        if (rectData.length > 0) {
          engine.loadData('rect', rectData as any)
        }
        if (pointData.length > 0) {
          engine.loadData('point', pointData as any)
        }
        if (polygonData.length > 0) {
          engine.loadData('polygon', polygonData as any)
        }
        annotationsLoadedRef.current = true
        console.log('[LabelUCanvas] Initial annotations loaded')
      } catch (err) {
        console.error('[LabelUCanvas] Failed to load image:', err)
      }
    }
    
    loadImageAsync()

    const handleAnnotationChange = () => {
      if (isUpdatingRef.current) return
      isUpdatingRef.current = true
      try {
        // Use getDataByTool to get all annotations
        const allAnnotations = engine.getDataByTool()
        if (!allAnnotations) return

        const newShapes: LabelMeShape[] = []

        Object.entries(allAnnotations).forEach(([toolName, annotations]) => {
          if (!Array.isArray(annotations)) return
          annotations.forEach((ann: any, idx: number) => {
            if (ann?.valid === false) return
            const labelMeShape = labelUToLabelMeShape(ann, toolName as ToolName)
            newShapes.push(labelMeShape)
          })
        })

        dispatch(setShapes(newShapes))
        prevShapesRef.current = newShapes
      } finally {
        isUpdatingRef.current = false
      }
    }

    engine.on('change', handleAnnotationChange)

    return () => {
      engine.off('change', handleAnnotationChange)
    }
  }, [engine, dispatch])

  // Switch tool when tool prop changes
  useEffect(() => {
    if (!engine) return
    const mappedTool = TOOL_MAP[tool] || ('rect' as ToolName)
    engine.switch(mappedTool)
  }, [engine, tool])

  // Sync external shapes changes
  useEffect(() => {
    if (shapes.length !== prevShapesRef.current.length) {
      console.log('[LabelUCanvas] Shapes changed externally, count:', shapes.length)
      prevShapesRef.current = shapes
    }
  }, [shapes])

  return (
    <div 
      ref={containerRef}
      className="flex-1 relative overflow-hidden bg-gray-900"
      style={{ width: '100%', height: '100%', minHeight: '400px' }}
    >
      {!imageLoadedRef.current && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 z-10">
          <div className="text-center">
            <div className="w-12 h-12 border-4 border-primary-400 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-300 text-sm">Loading image...</p>
          </div>
        </div>
      )}
    </div>
  )
}