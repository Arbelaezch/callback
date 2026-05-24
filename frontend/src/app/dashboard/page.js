'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/lib/apiClient';

/**
 * Dashboard — dev-focused view.
 * Shows raw application data + job search controls.
 * Designed for testing, not polish — build real components on top once
 * the backend is wired and you know what data you have.
 */
export default function DashboardPage() {
  const router = useRouter();
  const { user, loading: loadingUser } = useAuth();

  const [searches, setSearches] = useState([]);
  const [applications, setApplications] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState(null);

  // --- data fetch ---
  useEffect(() => {
    console.debug('[Dashboard] fetching searches + applications');
    Promise.all([
      apiClient.get('/api/jobs/searches/'),
      apiClient.get('/api/jobs/applications/'),
    ])
      .then(([searchData, appData]) => {
        console.debug('[Dashboard] searches=%d applications=%d', searchData.length, appData.length);
        setSearches(searchData);
        setApplications(appData);
      })
      .catch((err) => {
        console.error('[Dashboard] fetch error', err);
        setError(err.detail || 'Failed to load data.');
      })
      .finally(() => setLoadingData(false));
  }, []);

  async function toggleSearch(id, currentActive) {
    console.debug('[Dashboard] toggling search id=%d currentActive=%s', id, currentActive);
    try {
      const updated = await apiClient.patch(`/api/jobs/searches/${id}/toggle/`);
      console.debug('[Dashboard] toggle result=%o', updated);
      setSearches((prev) =>
        prev.map((s) => (s.id === id ? { ...s, active: updated.active } : s))
      );
    } catch (err) {
      console.error('[Dashboard] toggle error', err);
    }
  }

  if (loadingUser) {
    return <div className="p-8 text-muted-foreground text-sm">Checking auth...</div>;
  }

  return (
    <div className="p-6 space-y-10 max-w-6xl mx-auto">

      {/* Dev header */}
      <section>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        {user && (
          <p className="text-sm text-muted-foreground mt-1">
            Logged in as <span className="font-mono text-foreground">{user.username}</span>
            {' · '}
            <span className="font-mono">{user.email}</span>
          </p>
        )}
      </section>

      {error && (
        <div className="rounded-md border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Job searches */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Job Searches ({searches.length})
        </h2>

        {loadingData ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : searches.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No job searches yet.{' '}
            <a href="/onboarding" className="underline">Set one up →</a>
          </p>
        ) : (
          <div className="space-y-2">
            {searches.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-3 text-sm"
              >
                <div className="space-y-0.5">
                  <p className="font-medium">{s.label}</p>
                  <p className="text-muted-foreground text-xs font-mono">
                    {s.role_titles.join(', ') || '—'}
                    {s.cities.length > 0 && ` · ${s.cities.join(', ')}`}
                    {` · limit ${s.daily_limit}/day`}
                  </p>
                </div>
                <button
                  onClick={() => toggleSearch(s.id, s.active)}
                  className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                    s.active
                      ? 'border-green-600 text-green-600 hover:bg-green-600/10'
                      : 'border-input text-muted-foreground hover:bg-muted'
                  }`}
                >
                  {s.active ? 'Active' : 'Paused'}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Applications table */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Applications ({applications.length})
        </h2>

        {loadingData ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : applications.length === 0 ? (
          <p className="text-sm text-muted-foreground">No applications yet — the daily loop hasn't run.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-muted-foreground text-xs uppercase tracking-wide">
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-left">Company</th>
                  <th className="px-3 py-2 text-left">Role</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Score</th>
                  <th className="px-3 py-2 text-left">Method</th>
                  <th className="px-3 py-2 text-left">Search</th>
                  <th className="px-3 py-2 text-left">Failure</th>
                </tr>
              </thead>
              <tbody>
                {applications.map((app, i) => (
                  <tr
                    key={app.id}
                    className={`border-b border-border last:border-0 ${i % 2 === 0 ? '' : 'bg-muted/20'}`}
                  >
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(app.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2 font-medium whitespace-nowrap">
                      <a
                        href={app.job_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        {app.company}
                      </a>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{app.role_title}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={app.status} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {app.llm_score != null ? (
                        <span title={app.llm_score_reason || ''}>{app.llm_score}/10</span>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                      {app.submission_method || '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {app.job_search_label}
                    </td>
                    <td className="px-3 py-2 text-xs text-destructive max-w-xs truncate">
                      {app.failure_reason || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Dev: raw JSON dump */}
      <section className="space-y-2">
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">
            Dev: raw user object
          </summary>
          <pre className="mt-2 rounded-md bg-muted p-3 overflow-x-auto text-muted-foreground">
            {JSON.stringify(user, null, 2)}
          </pre>
        </details>
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">
            Dev: raw searches
          </summary>
          <pre className="mt-2 rounded-md bg-muted p-3 overflow-x-auto text-muted-foreground">
            {JSON.stringify(searches, null, 2)}
          </pre>
        </details>
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">
            Dev: raw applications
          </summary>
          <pre className="mt-2 rounded-md bg-muted p-3 overflow-x-auto text-muted-foreground">
            {JSON.stringify(applications, null, 2)}
          </pre>
        </details>
      </section>

    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    submitted: 'text-green-600 border-green-600',
    pending:   'text-yellow-600 border-yellow-600',
    failed:    'text-destructive border-destructive',
    skipped:   'text-muted-foreground border-input',
    deleted:   'text-muted-foreground border-input',
  };
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs font-mono ${styles[status] || 'border-input text-muted-foreground'}`}>
      {status}
    </span>
  );
}