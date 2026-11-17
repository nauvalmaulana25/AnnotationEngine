import { useEffect, useRef, useCallback, useState } from 'react'
import { LabelMeShape } from '@shared/types'
import { PaperScope } from 'paper'

// Use any for Paper.js internals to avoid type issues
type PaperAny = any;
type PaperPath = any;
type PaperPoint = any;
type PaperRectangle = any;
type PaperRaster = any;
type PaperKeyEvent = any;
type PaperToolEvent = any;

const COLORS = [
  '#ef4444', '#f97316', '#f59e0b', '#22c55e', '#06b6d4',
  '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f43f5e',
]

interface AnnotationCanvasProps {
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

export default function AnnotationCanvas({
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
}: AnnotationCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const paperRef = useRef<any>(null)
  const rasterRef = useRef<any>(null)
  const shapePathsRef = useRef<Map<number, any>>(new Map())
  const isDrawingRef = useRef(false)
  const currentPathRef = useRef<any>(null)
  const startPointRef = useRef<any>(null)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 })
  const [paperReady, setPaperReady] = useState(false)
  
  // Tool refs to persist across tool changes
  const selectToolRef = useRef<any>(null)
  const drawToolRef = useRef<any>(null)
  const panToolRef = useRef<any>(null)
  
  // Stable refs for callbacks used inside Paper.js event handlers
  const toolRef = useRef(tool)
  const shapesRef = useRef(shapes)
  const selectedShapeIdsRef = useRef(selectedShapeIds)
  const onShapeAddRef = useRef(onShapeAdd)
  const onShapeUpdateRef = useRef(onShapeUpdate)
  const onShapeDeleteRef = useRef(onShapeDelete)
  const onShapeSelectRef = useRef(onShapeSelect)
  const onShapeToggleSelectRef = useRef(onShapeToggleSelect)
  const onClearSelectionRef = useRef(onClearSelection)
  
  // Keep refs in sync
  useEffect(() => { toolRef.current = tool }, [tool])
  useEffect(() => { shapesRef.current = shapes }, [shapes])
  useEffect(() => { selectedShapeIdsRef.current = selectedShapeIds }, [selectedShapeIds])
  useEffect(() => { onShapeAddRef.current = onShapeAdd }, [onShapeAdd])
  useEffect(() => { onShapeUpdateRef.current = onShapeUpdate }, [onShapeUpdate])
  useEffect(() => { onShapeDeleteRef.current = onShapeDelete }, [onShapeDelete])
  useEffect(() => { onShapeSelectRef.current = onShapeSelect }, [onShapeSelect])
  useEffect(() => { onShapeToggleSelectRef.current = onShapeToggleSelect }, [onShapeToggleSelect])
  useEffect(() => { onClearSelectionRef.current = onClearSelection }, [onClearSelection])

  // Initialize Paper.js ONCE when canvas mounts
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || paperRef.current) return
    
    console.log('[AnnotationCanvas] Initializing Paper.js')
    
    // Size the canvas to its container before setup
    const container = containerRef.current
    if (container) {
      const rect = container.getBoundingClientRect()
      canvas.width = rect.width * window.devicePixelRatio
      canvas.height = rect.height * window.devicePixelRatio
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
    }
    
    // @ts-ignore
    const paper = new PaperScope()
    try {
      paper.setup(canvas)
      console.log('[AnnotationCanvas] Paper.setup() succeeded, view size:', paper.view.size.width, 'x', paper.view.size.height)
    } catch (err) {
      console.error('[AnnotationCanvas] Paper.setup() failed:', err)
      return
    }
    paperRef.current = paper
    setPaperReady(true)
    
    // Create tools once
    const selectTool = new paper.Tool()
    const drawTool = new paper.Tool()
    const panTool = new paper.Tool()
    
    selectToolRef.current = selectTool
    drawToolRef.current = drawTool
    panToolRef.current = panTool
    
    // ---- Pan Tool ----
    panTool.onMouseDrag = (event: any) => {
      paper.view.center = paper.view.center.subtract(event.delta)
    }
    
    // ---- Select Tool ----
    selectTool.onMouseDown = (event: any) => {
      const hit = paper.project.hitTest(event.point, {
        segments: true,
        stroke: true,
        fill: true,
        tolerance: 8
      })
      
      if (hit) {
        const path = hit.item as PaperPath
        const index = Array.from(shapePathsRef.current.entries()).find(([_, p]) => p === path)?.[0]
        if (index !== undefined) {
          if (event.modifiers.shift) {
            onShapeToggleSelectRef.current(index)
          } else {
            onShapeSelectRef.current(index)
          }
        } else {
          onClearSelectionRef.current()
        }
      } else {
        onClearSelectionRef.current()
      }
    }
    
    selectTool.onMouseDrag = (event: any) => {
      if (selectedShapeIdsRef.current.length === 0) return
      
      selectedShapeIdsRef.current.forEach((index: number) => {
        const path = shapePathsRef.current.get(index)
        if (path) {
          path.position = path.position.add(event.delta)
        }
      })
    }
    
    selectTool.onMouseUp = (event: any) => {
      if (selectedShapeIdsRef.current.length === 0) return
      
      selectedShapeIdsRef.current.forEach((index: number) => {
        const path = shapePathsRef.current.get(index)
        if (path) {
          updateShapeFromPath(index, path)
        }
      })
    }
    
    // ---- Draw Tool ----
    drawTool.onMouseDown = (event: any) => {
      const currentTool = toolRef.current
      if (currentTool === 'select' || currentTool === 'pan') return
      if (event.event.button !== 0) return
      
      isDrawingRef.current = true
      startPointRef.current = event.point
      const shapeCount = shapesRef.current.length
      
      if (currentTool === 'bbox') {
        const rect = new paper.Path.Rectangle({
          from: event.point,
          to: event.point,
          strokeColor: getColor(shapeCount),
          strokeWidth: 2,
          data: { label: `class_${shapeCount}` }
        })
        rect.fillColor = getColorWithAlpha(paper, shapeCount, 0.1)
        currentPathRef.current = rect
      } else if (currentTool === 'polygon') {
        const path = new paper.Path({
          segments: [event.point],
          strokeColor: getColor(shapeCount),
          strokeWidth: 2,
          closed: false,
          data: { label: `class_${shapeCount}` }
        })
        currentPathRef.current = path
      } else if (currentTool === 'keypoint') {
        const circle = new paper.Path.Circle({
          center: event.point,
          radius: 6,
          strokeColor: getColor(shapeCount),
          strokeWidth: 2,
          fillColor: getColor(shapeCount),
          data: { label: `keypoint_${shapeCount}` }
        })
        currentPathRef.current = circle
      }
    }
    
    drawTool.onMouseDrag = (event: any) => {
      if (!isDrawingRef.current || !currentPathRef.current) return
      const currentTool = toolRef.current
      
      if (currentTool === 'bbox' && currentPathRef.current && startPointRef.current) {
        currentPathRef.current.bounds = new paper.Rectangle(startPointRef.current, event.point)
      } else if (currentTool === 'polygon' && currentPathRef.current) {
        currentPathRef.current.add(event.point)
      }
    }
    
    drawTool.onMouseUp = (event: any) => {
      if (!isDrawingRef.current || !currentPathRef.current) return
      
      const path = currentPathRef.current
      const currentTool = toolRef.current
      const shapeCount = shapesRef.current.length
      let shape: LabelMeShape | null = null
      
      if (currentTool === 'bbox') {
        const bounds = path.bounds
        if (bounds.width > 5 && bounds.height > 5) {
          shape = {
            label: (path.data?.label as string) || `class_${shapeCount}`,
            points: [
              [bounds.left, bounds.top],
              [bounds.right, bounds.bottom]
            ],
            group_id: null,
            description: '',
            shape_type: 'rectangle',
            flags: {},
            mask: null
          }
        }
      } else if (currentTool === 'polygon') {
        if (path.segments.length >= 3) {
          shape = {
            label: (path.data?.label as string) || `class_${shapeCount}`,
            points: path.segments.map((s: any) => [s.point.x, s.point.y]),
            group_id: null,
            description: '',
            shape_type: 'polygon',
            flags: {},
            mask: null
          }
        }
      } else if (currentTool === 'keypoint') {
        shape = {
          label: (path.data?.label as string) || `keypoint_${shapeCount}`,
          points: [[path.position.x, path.position.y]],
          group_id: null,
          description: '',
          shape_type: 'point',
          flags: {},
          mask: null
        }
      }
      
      if (shape) {
        onShapeAddRef.current(shape)
        shapePathsRef.current.set(shapeCount, path)
      } else {
        path.remove()
      }
      
      isDrawingRef.current = false
      currentPathRef.current = null
      startPointRef.current = null
    }
    
    // Keyboard shortcuts
    // @ts-ignore - Paper.js view has key events but types don't expose them
    paper.view.onKeyDown = (event: PaperKeyEvent) => {
      if (event.key === 'delete' || event.key === 'backspace') {
        if (selectedShapeIdsRef.current.length > 0) {
          event.preventDefault()
          selectedShapeIdsRef.current.forEach((index: number) => onShapeDeleteRef.current(index))
          onClearSelectionRef.current()
        }
      }
      if (event.key === 'escape') {
        onClearSelectionRef.current()
      }
      if (event.key === 'space') {
        paper.view.element.style.cursor = 'grab'
      }
    }
    
    // @ts-ignore
    paper.view.onKeyUp = (event: PaperKeyEvent) => {
      if (event.key === 'space') {
        paper.view.element.style.cursor = 'default'
      }
    }
    
    // Zoom with mouse wheel
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      if (!paperRef.current) return
      const view = paperRef.current.view
      const delta = e.deltaY
      const scaleFactor = delta > 0 ? 0.9 : 1.1
      const point = view.viewToProject(new paperRef.current.Point(e.offsetX, e.offsetY))
      
      const newZoom = view.zoom * scaleFactor
      if (newZoom >= 0.05 && newZoom <= 20) {
        view.zoom = newZoom
        // Zoom towards cursor
        const newCenter = point.subtract(
          point.subtract(view.center).multiply(1 / scaleFactor)
        )
        view.center = newCenter
      }
    }
    canvas.addEventListener('wheel', handleWheel, { passive: false })
    
    // Cleanup
    return () => {
      canvas.removeEventListener('wheel', handleWheel)
      selectTool.remove()
      drawTool.remove()
      panTool.remove()
      if (paperRef.current) {
        paperRef.current.project.clear()
        paperRef.current.view.remove()
      }
      paperRef.current = null
      setPaperReady(false)
    }
  }, []) // Empty deps — init once

  // Activate appropriate tool when tool changes
  useEffect(() => {
    if (!paperRef.current) return
    console.log('[AnnotationCanvas] Activating tool:', tool)
    if (tool === 'pan') {
      panToolRef.current?.activate()
    } else if (tool === 'select') {
      selectToolRef.current?.activate()
    } else {
      drawToolRef.current?.activate()
    }
  }, [tool])

  // Load image when imageId changes (and Paper.js is ready)
  useEffect(() => {
    console.log('[AnnotationCanvas] Image load effect — imageId:', imageId, 'paperReady:', paperReady)
    if (!paperReady || !paperRef.current) return
    
    setImageLoaded(false)
    setImageError(false)
    
    // Clear previous raster and shapes
    if (rasterRef.current) {
      rasterRef.current.remove()
      rasterRef.current = null
    }
    shapePathsRef.current.forEach((path) => path.remove())
    shapePathsRef.current.clear()
    
    const img = new window.Image()
    img.onload = () => {
      console.log('[AnnotationCanvas] Image loaded successfully:', img.width, 'x', img.height)
      if (!paperRef.current) return
      
      setImageSize({ width: img.width, height: img.height })
      
      try {
        const raster = new paperRef.current.Raster(img)
        // Position raster so TOP-LEFT is at project (0,0) to match LabelMe coordinates
        // Paper.js positions raster CENTER at position, so offset by half dimensions
        raster.position = new paperRef.current.Point(img.width / 2, img.height / 2)
        rasterRef.current = raster
        
        // DEBUG: Log coordinate systems
        console.log('[DEBUG] Raster position:', raster.position.x, raster.position.y)
        console.log('[DEBUG] Image size:', img.width, 'x', img.height)
        console.log('[DEBUG] Raster bounds:', raster.bounds.left, raster.bounds.top, raster.bounds.right, raster.bounds.bottom)
        
        // Send raster to back so annotations draw on top
        raster.sendToBack()
        
        // Fit to view with padding
        const padding = 40
        const viewW = paperRef.current.view.size.width
        const viewH = paperRef.current.view.size.height
        
        if (viewW > 0 && viewH > 0 && img.width > 0 && img.height > 0) {
          const scale = Math.min(
            (viewW - padding * 2) / img.width,
            (viewH - padding * 2) / img.height
          )
          console.log('[DEBUG] Fitting — view:', viewW, 'x', viewH, 'scale:', scale)
          paperRef.current.view.zoom = scale
          // Center view on image center (in project coordinates)
          paperRef.current.view.center = new paperRef.current.Point(img.width / 2, img.height / 2)
          console.log('[DEBUG] After zoom - View center:', paperRef.current.view.center.x, paperRef.current.view.center.y)
        }
        
        setImageLoaded(true)
      } catch (err) {
        console.error('[AnnotationCanvas] Failed to create raster:', err)
        setImageError(true)
        setImageLoaded(true)
      }
    }
    img.onerror = () => {
      console.error('[AnnotationCanvas] Failed to load image:', `/api/v1/images/${imageId}/file`)
      setImageError(true)
      setImageLoaded(true)
    }
    img.src = `/api/v1/images/${imageId}/file`
  }, [imageId, paperReady])
  
  // Sync shapes from Redux to Paper.js
  useEffect(() => {
    if (!paperRef.current || !imageLoaded) return
    
    // Remove paths that are no longer in shapes
    const currentIndices = new Set(shapes.map((_, i) => i))
    shapePathsRef.current.forEach((path, index) => {
      if (!currentIndices.has(index)) {
        path.remove()
        shapePathsRef.current.delete(index)
      }
    })
    
    // Update or create paths
    shapes.forEach((shape, index) => {
      let path = shapePathsRef.current.get(index)
      
      if (!path) {
        path = createPathFromShape(shape, index)
        shapePathsRef.current.set(index, path)
      } else {
        updatePathFromShape(path, shape)
      }
      
      // Update selection visual
      updateSelectionVisual(path, selectedShapeIds.includes(index))
    })
  }, [shapes, selectedShapeIds, imageLoaded])
  
  // Handle container resize
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      
      const { width, height } = entry.contentRect
      const canvas = canvasRef.current
      if (!canvas || !paperRef.current) return
      
      canvas.width = width * window.devicePixelRatio
      canvas.height = height * window.devicePixelRatio
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      
      paperRef.current.view.viewSize = new paperRef.current.Size(width, height)
    })
    
    resizeObserver.observe(container)
    return () => resizeObserver.disconnect()
  }, [paperReady])
  
  const createPathFromShape = (shape: LabelMeShape, index: number): PaperPath => {
    const paper = paperRef.current!
    const color = getColor(index)
    let path: PaperPath
    
    if (shape.shape_type === 'rectangle' && shape.points.length >= 2) {
      const [[x1, y1], [x2, y2]] = shape.points
      path = new paper.Path.Rectangle({
        from: new paper.Point(x1, y1),
        to: new paper.Point(x2, y2),
        strokeColor: color,
        strokeWidth: 2,
        data: { label: shape.label, index }
      })
      path.fillColor = new paper.Color(color)
      path.fillColor.alpha = 0.1
    } else if (shape.shape_type === 'polygon' && shape.points.length >= 3) {
      path = new paper.Path({
        segments: shape.points.map(([x, y]) => new paper.Point(x, y)),
        strokeColor: color,
        strokeWidth: 2,
        closed: true,
        data: { label: shape.label, index }
      })
      path.fillColor = new paper.Color(color)
      path.fillColor.alpha = 0.1
    } else if (shape.shape_type === 'point' && shape.points.length >= 1) {
      const [x, y] = shape.points[0]
      path = new paper.Path.Circle({
        center: new paper.Point(x, y),
        radius: 6,
        strokeColor: color,
        strokeWidth: 2,
        fillColor: color,
        data: { label: shape.label, index }
      })
    } else {
      path = new paper.Path()
    }
    
    return path
  }
  
  const updatePathFromShape = (path: PaperPath, shape: LabelMeShape) => {
    const paper = paperRef.current!
    if (shape.shape_type === 'rectangle' && shape.points.length >= 2) {
      const [[x1, y1], [x2, y2]] = shape.points
      path.bounds = new paper.Rectangle(x1, y1, x2 - x1, y2 - y1)
    } else if (shape.shape_type === 'polygon' && shape.points.length >= 3) {
      path.segments = shape.points.map(([x, y]: number[]) => new paper.Segment(new paper.Point(x, y)))
      path.closed = true
    } else if (shape.shape_type === 'point' && shape.points.length >= 1) {
      const [x, y] = shape.points[0]
      path.position = new paper.Point(x, y)
    }
  }
  
  const updateShapeFromPath = (index: number, path: PaperPath) => {
    const paper = paperRef.current!
    let shape: Partial<LabelMeShape> = {}
    
    const bounds = path.bounds
    if (path.segments && path.segments.length === 4 && path.closed) {
      // Rectangle
      shape.points = [
        [bounds.left, bounds.top],
        [bounds.right, bounds.bottom]
      ]
    } else if (path.segments && path.segments.length === 1) {
      // Point
      shape.points = [[path.position.x, path.position.y]]
    } else if (path.segments) {
      // Polygon
      shape.points = path.segments.map((s: any) => [s.point.x, s.point.y])
    }
    
    onShapeUpdateRef.current(index, shape)
  }
  
  const updateSelectionVisual = (path: PaperPath, selected: boolean) => {
    const paper = paperRef.current!
    if (selected) {
      path.strokeWidth = 3
      path.strokeColor = '#ffffff'
      path.shadowColor = new paper.Color(0, 0, 0, 0.3)
      path.shadowBlur = 4
      path.shadowOffset = new paper.Point(0, 2)
    } else {
      path.strokeWidth = 2
      path.strokeColor = getColor(path.data?.index ?? 0)
      path.shadowColor = null
      path.shadowBlur = 0
      path.shadowOffset = new paper.Point(0, 0)
    }
  }
  
  const getColor = (index: number) => COLORS[index % COLORS.length]
  
  const getColorWithAlpha = (paper: any, index: number, alpha: number) => {
    const c = new paper.Color(getColor(index))
    c.alpha = alpha
    return c
  }
  
  // ALWAYS render the canvas + overlay spinner on top
  return (
    <div
      ref={containerRef}
      className="flex-1 relative overflow-hidden bg-gray-900"
      style={{ cursor: tool === 'pan' ? 'grab' : tool === 'select' ? 'default' : 'crosshair' }}
    >
      {/* Canvas is ALWAYS in the DOM so Paper.js can initialize */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
        style={{ touchAction: 'none' }}
      />
      
      {/* Loading overlay */}
      {!imageLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 z-10">
          <div className="text-center">
            <div className="w-12 h-12 border-4 border-primary-400 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-300 text-sm">Loading image...</p>
          </div>
        </div>
      )}
      
      {/* Error overlay */}
      {imageError && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 z-10">
          <div className="text-center">
            <p className="text-red-400 text-sm">Failed to load image</p>
          </div>
        </div>
      )}
      
      {/* Coordinates display */}
      {imageLoaded && (
        <div className="absolute bottom-2 right-2 bg-black/60 backdrop-blur-sm rounded-lg px-3 py-1 text-xs text-gray-300 font-mono pointer-events-none z-20">
          {imageSize.width} × {imageSize.height}
        </div>
      )}
    </div>
  )
}
