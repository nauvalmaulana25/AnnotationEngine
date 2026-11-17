import { Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useAppDispatch } from './hooks'
import Layout from '../components/Layout'
import LandingPage from '../features/projects/LandingPage'
import ProjectView from '../features/projects/ProjectView'
import { Toaster } from 'react-hot-toast'

function App() {
  const dispatch = useAppDispatch()
  
  useEffect(() => {
    console.log('App mounted')
    // Initialize any needed state here
  }, [dispatch])
  
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/projects/:projectId" element={<ProjectView />} />
      </Route>
      
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App