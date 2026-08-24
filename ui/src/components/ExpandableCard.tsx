import { useState } from 'react'

interface Props {
  title: string
  subtitle?: string
  color: 'teal' | 'coral' | 'purple' | 'blue' | 'amber'
  defaultOpen?: boolean
  children: React.ReactNode
}

export default function ExpandableCard({
  title, subtitle, color, defaultOpen = false, children
}: Props) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="card">
      <div className="card-header" onClick={() => setOpen(o => !o)}>
        <div className="card-header-left">
          <div className={`card-accent accent-${color}`} />
          <div>
            <div className={`card-title title-${color}`}>{title}</div>
            {subtitle && <div className="card-subtitle">{subtitle}</div>}
          </div>
        </div>
        <span className={`card-chevron ${open ? 'open' : ''}`}>▼</span>
      </div>
      {open && <div className="card-body">{children}</div>}
    </div>
  )
}