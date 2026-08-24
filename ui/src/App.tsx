import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard   from './pages/Dashboard'
import NewResearch from './pages/NewResearch'
import Results     from './pages/Results'
import AuthGuard   from './AuthGuard'

export default function App() {
  return (
    <BrowserRouter>
      <AuthGuard>
        <Routes>
          <Route path="/"               element={<Dashboard />} />
          <Route path="/new"       element={<NewResearch />} />
          <Route path="/results/:jobId" element={<Results />} />
        </Routes>
      </AuthGuard>
    </BrowserRouter>
  )
}