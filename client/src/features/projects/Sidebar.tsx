import { useState } from 'react'
import { Image as ImageType } from '@shared/types'
import ImageGrid from './ImageGrid'
import { clsx } from 'clsx'

interface SidebarProps {
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

export default function Sidebar({
  images,
  selectedIds,
  currentImageId,
  status,
  pagination,
  onImageClick,
  onLoadMore,
  onSelectionChange,
  onClearSelection,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  
  if (collapsed) {
    return (
      <aside className="w-16 bg-white border-r border-gray-200 flex flex-col transition-all duration-300">
        <button
          onClick={() => setCollapsed(false)}
          className="p-3 mx-auto mt-2 hover:bg-gray-100 rounded-lg"
          aria-label="Expand sidebar"
        >
          <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </aside>
    )
  }
  
  return (
    <aside className={clsx(
      'bg-white border-r border-gray-200 flex flex-col transition-all duration-300 overflow-hidden',
      'w-80'
    )}>
      <div className="flex-1 flex flex-col min-h-0">
        <ImageGrid
          images={images}
          selectedIds={selectedIds}
          currentImageId={currentImageId}
          status={status}
          pagination={pagination}
          onImageClick={onImageClick}
          onLoadMore={onLoadMore}
          onSelectionChange={onSelectionChange}
          onClearSelection={onClearSelection}
        />
      </div>
      
      <button
        onClick={() => setCollapsed(true)}
        className="p-2 mx-auto mb-2 hover:bg-gray-100 rounded-lg border border-gray-200"
        aria-label="Collapse sidebar"
      >
        <svg className="w-5 h-5 text-gray-500 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>
    </aside>
  )
}