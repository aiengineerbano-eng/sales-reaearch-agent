import { FormEvent, useState } from 'react';
import { useApi } from '../hooks/useApi';

export function NewResearch() {
  const { post } = useApi();
  const [company, setCompany] = useState('Northstar Labs');
  const [objective, setObjective] = useState('Identify expansion opportunities in the healthcare software market.');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      await post('/api/research', {
        company,
        objective,
      });

      setMessage('Research request submitted successfully.');
      setCompany('');
      setObjective('');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Failed to submit research request.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page research-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Create</p>
          <h1>New research brief</h1>
        </div>
      </header>

      <form className="card research-form" onSubmit={handleSubmit}>
        <label>
          Company
          <input value={company} onChange={(event) => setCompany(event.target.value)} placeholder="Acme Inc" />
        </label>

        <label>
          Objective
          <textarea
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            rows={6}
            placeholder="Summarize what the Multi-Agent research should investigate."
          />
        </label>

        {message ? <p className="status-message">{message}</p> : null}

        <button type="submit" disabled={loading}>
          {loading ? 'Submitting...' : 'Submit research'}
        </button>
      </form>
    </div>
  );
}
