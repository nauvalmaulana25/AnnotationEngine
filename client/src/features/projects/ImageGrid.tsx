import { useRef, useEffect, useState } from 'react'
import { Image as ImageType } from '@shared/types'
import { Image as ImageIcon, Loader2, CheckCircle, FileText } from 'lucide-react'
import { clsx } from 'clsx'

interface ImageGridProps {
  images: ImageType[]
  selectedIds: number[]
  currentImageId: number | null
  status: 'idle' | 'loading' | 'succeeded' | 'failed'
  pagination: { page: number; total_pages: number } | null
  onImageClick: (imageId: number, e: React.MouseEvent) => void
  onLoadMore: () => void
  onSelectionChange: (ids: number[]) => void
  onClearSelection: () => void
}

export default function ImageGrid({
  images,
  selectedIds,
  currentImageId,
  status,
  pagination,
  onImageClick,
  onLoadMore,
  onSelectionChange,
  onClearSelection,
}: ImageGridProps) {
  const gridRef = useRef<HTMLDivElement>(null)
  const selectAllRef = useRef<HTMLInputElement>(null)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  
  // Update indeterminate state
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedIds.length > 0 && selectedIds.length < images.length
    }
  }, [selectedIds, images.length])
  
  // Infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && pagination && pagination.page < pagination.total_pages && status !== 'loading') {
          onLoadMore()
        }
      },
      { threshold: 0.1 }
    )
    
    const sentinel = gridRef.current?.querySelector('[data-sentinel]')
    if (sentinel) observer.observe(sentinel)
    return () => observer.disconnect()
  }, [pagination, status, onLoadMore])
  
  const handleSelectAll = () => {
    if (selectedIds.length === images.length) {
      onClearSelection()
    } else {
      onSelectionChange(images.map(i => i.id))
    }
  }
  
  if (images.length === 0 && status !== 'loading') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-500 p-8">
        <ImageIcon className="w-16 h-16 mb-4 opacity-50" />
        <p className="text-lg font-medium">No images in this project</p>
        <p className="text-sm mt-1">Click "Import Images" to add images</p>
      </div>
    )
  }
  
  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white rounded-xl border border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              ref={selectAllRef}
              type="checkbox"
              checked={selectedIds.length === images.length && images.length > 0}
              onChange={handleSelectAll}
              className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-sm font-medium text-gray-700">
              {selectedIds.length > 0 ? `${selectedIds.length} selected` : `${images.length} images`}
            </span>
          </label>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('grid')}
            className={clsx('p-2 rounded-lg transition-colors', viewMode === 'grid' ? 'bg-primary-100 text-primary-700' : 'text-gray-500 hover:bg-gray-100')}
            title="Grid view"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={clsx('p-2 rounded-lg transition-colors', viewMode === 'list' ? 'bg-primary-100 text-primary-700' : 'text-gray-500 hover:bg-gray-100')}
            title="List view"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
          </button>
        </div>
      </div>
      
      {/* Image Grid/List */}
      <div
        ref={gridRef}
        className="flex-1 overflow-y-auto p-3"
        style={{ scrollbarWidth: 'thin' }}
      >
        {viewMode === 'grid' ? (
          <div className="grid grid-cols-2 gap-3">
            {images.map((image) => (
              <ImageThumbnail
                key={image.id}
                image={image}
                isSelected={selectedIds.includes(image.id)}
                isCurrent={currentImageId === image.id}
                onClick={(e) => onImageClick(image.id, e)}
              />
            ))}
            <div data-sentinel className="h-4" />
            {status === 'loading' && (
              <div className="col-span-full flex justify-center py-4">
                <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
              </div>
            )}
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {images.map((image) => (
              <ImageListItem
                key={image.id}
                image={image}
                isSelected={selectedIds.includes(image.id)}
                isCurrent={currentImageId === image.id}
                onClick={(e) => onImageClick(image.id, e)}
              />
            ))}
            <div data-sentinel className="h-4" />
            {status === 'loading' && (
              <div className="flex justify-center py-4">
                <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ImageThumbnail({ image, isSelected, isCurrent, onClick }: { image: ImageType; isSelected: boolean; isCurrent: boolean; onClick: (e: React.MouseEvent) => void }) {
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)
  
  const imgSrc = `/api/v1/images/${image.id}/thumbnail`
  
  return (
    <button
      onClick={onClick}
      className={clsx(
        'relative group overflow-hidden rounded-lg border-2 transition-all',
        isCurrent ? 'border-primary-500 ring-2 ring-primary-300 bg-primary-50' : isSelected ? 'border-primary-300 bg-primary-50' : 'border-gray-200 hover:border-gray-300',
        'cursor-pointer aspect-square'
      )}
    >
      <div className="w-full h-full relative bg-gray-100">
        {imgError ? (
          <div className="w-full h-full flex flex-col items-center justify-center text-gray-400 gap-1">
            <ImageIcon className="w-8 h-8" />
            <span className="text-xs truncate max-w-full px-1">{image.filename}</span>
          </div>
        ) : (
          <>
            {!imgLoaded && (
              <div className="absolute inset-0 flex items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            )}
            <img
              src={imgSrc}
              alt={image.filename}
              className={clsx(
                'w-full h-full object-cover transition-opacity duration-200',
                imgLoaded ? 'opacity-100' : 'opacity-0'
              )}
              onLoad={() => setImgLoaded(true)}
              onError={() => setImgError(true)}
              loading="lazy"
            />
          </>
        )}
        
        {/* Selection indicator */}
        {isSelected && (
          <div className="absolute inset-0 bg-primary-600/20 flex items-center justify-center">
            <CheckCircle className="w-8 h-8 text-primary-600" />
          </div>
        )}
        
        {/* Current indicator */}
        {isCurrent && (
          <div className="absolute top-1.5 right-1.5">
            <span className="w-5 h-5 rounded-full bg-primary-600 flex items-center justify-center shadow-md">
              <CheckCircle className="w-3 h-3 text-white" />
            </span>
          </div>
        )}
        
        {/* Annotation indicator */}
        {image.has_annotation && (
          <div className="absolute bottom-1.5 left-1.5">
            <FileText className="w-4 h-4 text-primary-600 bg-white rounded-full p-0.5 shadow" />
          </div>
        )}
      </div>
      
      {/* Info overlay - always visible at bottom */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 via-black/40 to-transparent p-2 pt-6">
        <p className="text-white text-xs truncate font-medium">{image.filename}</p>
        {image.width && image.height && (
          <p className="text-white/70 text-[10px]">{image.width} × {image.height}</p>
        )}
      </div>
    </button>
  )
}

function ImageListItem({ image, isSelected, isCurrent, onClick }: { image: ImageType; isSelected: boolean; isCurrent: boolean; onClick: (e: React.MouseEvent) => void }) {
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)
  
  const imgSrc = `/api/v1/images/${image.id}/thumbnail`
  
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full flex items-center gap-3 p-2 rounded-lg transition-colors',
        isCurrent ? 'bg-primary-50 border-l-4 border-primary-500' : isSelected ? 'bg-primary-50' : 'hover:bg-gray-50'
      )}
    >
      <div className="w-16 h-12 flex-shrink-0 rounded overflow-hidden bg-gray-100 relative">
        {imgError ? (
          <ImageIcon className="w-full h-full text-gray-400 p-2" />
        ) : (
          <img
            src={imgSrc}
            alt={image.filename}
            className={clsx(
              'w-full h-full object-cover',
              imgLoaded ? 'opacity-100' : 'opacity-0'
            )}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
            loading="lazy"
          />
        )}
        {isCurrent && (
          <div className="absolute top-1 right-1">
            <span className="w-5 h-5 rounded-full bg-primary-600 flex items-center justify-center">
              <CheckCircle className="w-3 h-3 text-white" />
            </span>
          </div>
        )}
        {image.has_annotation && (
          <div className="absolute bottom-1 right-1">
            <FileText className="w-4 h-4 text-primary-600 bg-white rounded-full p-0.5 shadow" />
          </div>
        )}
      </div>
      
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{image.filename}</p>
        <p className="text-xs text-gray-500 flex items-center gap-2">
          {image.width && image.height && `${image.width} × ${image.height}`}
          {image.file_size && `• ${(image.file_size / 1024).toFixed(1)} KB`}
          <span className="px-1.5 py-0.5 text-xs rounded bg-gray-100 text-gray-600 capitalize">{image.split}</span>
        </p>
      </div>
      
      {isSelected && (
        <CheckCircle className="w-5 h-5 text-primary-600 flex-shrink-0" />
      )}
    </button>
  )
}
