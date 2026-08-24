import { useEffect, useState } from 'react';
import { useApi } from '../hooks/useApi';

type ResearchItem = {
  id: string;
  company: string;
  status: 'queued' | 'running' | 'complete';
  confidence: number;
  createdAt: string;
};

export function Dashboard() {
  const { get } = useApi();
  const [researches, setResearches] = useState<ResearchItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const data = await get<ResearchItem[]>('/api/research');
        setResearches(data);
      } catch {
        setResearches([
          {
            id: 'demo-1',
            company: 'Northstar Labs',
            status: 'complete',
            confidence: 92,
            createdAt: '2026-08-23T10:00:00Z',
          },
          {
            id: 'demo-2',
            company: 'BluePeak Health',
            status: 'running',
            confidence: 75,
            createdAt: '2026-08-23T11:15:00Z',
          },
        ]);
      } finally {
        setLoading(false);
      }
    };

    void loadDashboard();
  }, [get]);

  return (
    <div className="page dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>Sales Research Dashboard</h1>
        </div>
      </header>

      <div className="stats-grid">
        <div className="card stat-card">
          <span>Active accounts</span>
          <strong>128</strong>
        </div>
        <div className="card stat-card">
          <span>New opportunities</span>
          <strong>23</strong>
        </div>
        <div className="card stat-card">
          <span>Research jobs</span>
          <strong>{researches.length}</strong>
        </div>
      </div>

      <div className="content-grid">
        <section className="card table-card">
          <h2>Recent research</h2>
          {loading ? (
            <p>Loading...</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {researches.map((item) => (
                  <tr key={item.id}>
                    <td>{item.company}</td>
                    <td>{item.status}</td>
                    <td>{item.confidence}%</td>
                    <td>{new Date(item.createdAt).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
