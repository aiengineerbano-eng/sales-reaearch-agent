/**
 * useApi — raw fetch wrappers for the Sales Agent API.
 */

const BASE = import.meta.env.VITE_API_URL ?? ''

export interface JobSummary {
  job_id:        string
  contact_name:  string
  company_name:  string
  website:       string
  status:        'pending' | 'running' | 'complete' | 'failed'
  progress_step: string
  progress_pct:  number
  error:         string | null
  created_at:    string
  updated_at:    string
  completed_at:  string | null
}

export interface JobDetail extends JobSummary {
  result: ResearchResult | null
}

export interface ResearchResult {
  contact_name:  string
  company_name:  string
  website:       string
  job_id:        string
  status:        string
  contact_intel: ContactIntel | null
  company_intel: CompanyIntel | null
  job_signals:   JobSignals   | null
  news_summary:  string       | null
  opportunities: Opportunity[]
  email_drafts:  EmailDraft[]
}

export interface ContactIntel {
  full_name:           string
  current_role:        string
  seniority:           string
  tenure_months:       number | null
  linkedin_url:        string | null
  email:               string | null
  email_confidence:    number | null
  previous_companies:  string[]
  key_facts:           string[]
}

export interface CompanyIntel {
  name:            string
  website:         string
  cloud_provider:  string[]
  tech_stack:      string[]
  employee_count:  string
  industry:        string
  hq_location:     string
  recent_funding:  string
  annual_revenue:  string
}

export interface JobSignals {
  open_roles:           string[]
  hiring_themes:        string[]
  pain_points_inferred: string[]
  growth_signals:       string[]
}

export interface Opportunity {
  service:        string
  rationale:      string
  urgency:        'High' | 'Medium' | 'Low'
  urgency_reason: string
  talking_points: string[]
}

export interface EmailDraft {
  variant:               string
  subject:               string
  body:                  string
  personalisation_notes: string
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 30000) // 30s for normal requests

  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new Error(`${res.status}: ${text}`)
    }
    if (res.status === 204) return undefined as T
    return res.json()
  } finally {
    clearTimeout(timeout)
  }
}

export const api = {
  enqueue: (contactName: string, companyName: string, website: string) =>
    request<JobSummary>('/research', {
      method: 'POST',
      body: JSON.stringify({
        contact_name: contactName,
        company_name: companyName,
        website,
      }),
    }),

  getJob: (jobId: string) =>
    request<JobDetail>(`/research/${jobId}`),

  listJobs: (limit = 50) =>
    request<JobSummary[]>(`/research?limit=${limit}`),

  deleteJob: (jobId: string) =>
    request<void>(`/research/${jobId}`, { method: 'DELETE' }),
}