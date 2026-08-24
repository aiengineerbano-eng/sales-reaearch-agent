/**
 * useResearch — polls GET /research/{job_id} every 3s until complete or failed.
 * Used by the Results page to drive the spinner → results transition.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, JobDetail } from './useApi'

const POLL_INTERVAL_MS = 3000
const TERMINAL = new Set(['complete', 'failed'])

export function useResearch(jobId: string | null) {
  const [job, setJob]       = useState<JobDetail | null>(null)
  const [error, setError]   = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const poll = useCallback(async () => {
    if (!jobId) return
    try {
      const data = await api.getJob(jobId)
      setJob(data)
      setError(null)

      if (!TERMINAL.has(data.status)) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    setLoading(true)
    setJob(null)
    setError(null)
    poll()

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [jobId, poll])

  return { job, error, loading }
}