import { Outlet, NavLink } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '../app/hooks'
import { toggleSidebar } from '../features/ui/uiSlice'
import { LayoutDashboard, ChevronLeft, ChevronRight, FolderOpen } from 'lucide-react'
import { clsx } from 'clsx'

export default function Layout() {
  const dispatch = useAppDispatch()
  const { sidebarOpen } = useAppSelector((state) => state.ui)
  
  const toggleSidebarHandler = () => {
    dispatch(toggleSidebar())
  }
  
  console.log('Layout rendering, sidebarOpen:', sidebarOpen)
  
  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed left-0 top-0 z-40 h-screen bg-white border-r border-gray-200 transition-all duration-300',
          sidebarOpen ? 'w-64' : 'w-20'
        )}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className={clsx('flex items-center gap-3 px-4 py-5 border-b border-gray-200', sidebarOpen ? '' : 'justify-center')}>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center">
                <FolderOpen className="w-5 h-5 text-white" />
              </div>
              {sidebarOpen && (
                <span className="text-xl font-bold text-gray-900">AnnotationEngine</span>
              )}
            </div>
            <button
              onClick={toggleSidebarHandler}
              className={clsx('ml-auto p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors', sidebarOpen ? '' : 'mx-auto')}
              aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            >
              {sidebarOpen ? <ChevronLeft className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
            </button>
          </div>
          
          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Main navigation">
            <NavLink
              to="/"
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              )}
              title="Projects"
            >
              <LayoutDashboard className="w-5 h-5 flex-shrink-0" />
              {sidebarOpen && <span>Projects</span>}
            </NavLink>
          </nav>
        </div>
      </aside>
      
      {/* Main content */}
      <main
        className={clsx(
          'flex-1 min-h-screen transition-all duration-300',
          sidebarOpen ? 'ml-64' : 'ml-20'
        )}
      >
        <div className="p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}