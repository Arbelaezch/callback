'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/lib/apiClient';

export default function DashboardPage() {
  const { user } = useAuth();

  const [agent, setAgent] = useState(null);
  const [searches, setSearches] = useState([]);
  const [applications, setApplications] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState(null);

  // per-search state: { [id]: { triggering, runLogs, loadingLogs, logsOpen } }
  const [searchState, setSearchState] = useState({});

  const patchSearchState = useCallback((id, patch) => {
    setSearchState((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }, []);

  // --- data fetch ---
  const fetchData = useCallback(() => {
    setLoadingData(true);
    Promise.all([
      apiClient.get('/api/jobs/agent/'),
      apiClient.get('/api/jobs/searches/'),
      apiClient.get('/api/jobs/applications/'),
    ])
      .then(([agentData, searchData, appData]) => {
        setAgent(agentData);
        setSearches(searchData);
        setApplications(appData);
      })
      .catch((err) => {
        console.error('[Dashboard] fetch error', err);
        setError(err.detail || 'Failed to load data.');
      })
      .finally(() => setLoadingData(false));
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // --- agent toggle ---
  async function toggleAgent() {
    if (!agent) return;
    try {
      const updated = await apiClient.patch('/api/jobs/agent/', { active: !agent.active });
      setAgent(updated);
    } catch (err) {
      console.error('[Dashboard] agent toggle error', err);
    }
  }

  // --- search active toggle ---
  async function toggleSearch(id) {
    console.debug('[Dashboard] toggling search id=%d', id);
    try {
      const updated = await apiClient.patch(`/api/jobs/searches/${id}/toggle/`);
      setSearches((prev) => prev.map((s) => (s.id === id ? { ...s, active: updated.active } : s)));
    } catch (err) {
      console.error('[Dashboard] toggle error', err);
    }
  }

  // --- search schedule toggle ---
  async function toggleSchedule(id) {
    console.debug('[Dashboard] toggling schedule for search id=%d', id);
    try {
      const updated = await apiClient.patch(`/api/jobs/searches/${id}/schedule/`);
      setSearches((prev) => prev.map((s) => (s.id === id ? { ...s, schedule_enabled: updated.schedule_enabled } : s)));
    } catch (err) {
      console.error('[Dashboard] schedule toggle error', err);
    }
  }

  // --- trigger run ---
  async function triggerRun(id) {
    console.debug('[Dashboard] triggering run for search id=%d', id);
    patchSearchState(id, { triggering: true });
    try {
      await apiClient.post(`/api/jobs/searches/${id}/trigger/`);
      setTimeout(() => { fetchData(); fetchRunLogs(id); }, 1200);
    } catch (err) {
      console.error('[Dashboard] trigger error', err);
      alert(err.detail || 'Failed to trigger run.');
    } finally {
      patchSearchState(id, { triggering: false });
    }
  }

  // --- run logs ---
  async function fetchRunLogs(id) {
    console.debug('[Dashboard] fetching run logs for search id=%d', id);
    patchSearchState(id, { loadingLogs: true });
    try {
      const logs = await apiClient.get(`/api/jobs/searches/${id}/runs/`);
      patchSearchState(id, { runLogs: logs, loadingLogs: false });
    } catch (err) {
      console.error('[Dashboard] run log error', err);
      patchSearchState(id, { loadingLogs: false });
    }
  }

  function toggleLogs(id) {
    const current = searchState[id]?.logsOpen;
    patchSearchState(id, { logsOpen: !current });
    if (!current && !searchState[id]?.runLogs) fetchRunLogs(id);
  }

  return (
    <div className="p-6 space-y-10 max-w-6xl mx-auto">

      {/* Header */}
      <section className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          {user && (
            <p className="text-sm text-muted-foreground mt-1">
              Logged in as <span className="font-mono text-foreground">{user.username}</span>
              {' · '}
              <span className="font-mono">{user.email}</span>
            </p>
          )}
        </div>
        <button
          onClick={fetchData}
          className="text-xs text-muted-foreground hover:text-foreground border border-input rounded-md px-3 py-1.5 transition-colors"
        >
          ↺ Refresh
        </button>
      </section>

      {error && (
        <div className="rounded-md border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Agent */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Agent</h2>
        {loadingData || !agent ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <div className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-3 text-sm">
            <div>
              <p className="font-medium">{agent.name}</p>
              <p className="text-xs text-muted-foreground">
                Master switch — when inactive, no searches run regardless of their own state.
              </p>
            </div>
            <button
              onClick={toggleAgent}
              className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                agent.active
                  ? 'border-green-600 text-green-600 hover:bg-green-600/10'
                  : 'border-input text-muted-foreground hover:bg-muted'
              }`}
            >
              {agent.active ? 'Active' : 'Inactive'}
            </button>
          </div>
        )}
      </section>

      {/* Searches */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Searches ({searches.length})
        </h2>

        {loadingData ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : searches.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No searches yet. <a href="/onboarding" className="underline">Set one up →</a>
          </p>
        ) : (
          <div className="space-y-2">
            {searches.map((s) => {
              const ss = searchState[s.id] || {};
              const agentInactive = agent && !agent.active;
              return (
                <div key={s.id} className="rounded-md border border-border bg-card text-sm">
                  {/* Main row */}
                  <div className="flex items-center justify-between px-4 py-3">
                    <div className="space-y-0.5 min-w-0 flex-1 mr-4">
                      <p className="font-medium truncate">{s.label || 'Search'}</p>
                      <p className="text-muted-foreground text-xs font-mono">
                        {s.role_titles.join(', ') || '—'}
                        {s.cities.length > 0 && ` · ${s.cities.join(', ')}`}
                        {` · target ${s.daily_target}/day · cooldown ${s.job_cooldown}d`}
                      </p>
                      {s.last_run ? (
                        <p className="text-xs text-muted-foreground">
                          Last run:{' '}
                          <span className="font-mono">{new Date(s.last_run.run_at).toLocaleString()}</span>
                          {' · '}<RunStatusBadge status={s.last_run.status} />
                          {' · '}{s.last_run.jobs_fetched} fetched · {s.last_run.jobs_scored} scored · {s.last_run.jobs_applied} applied
                          {s.last_run.jobs_failed > 0 && (
                            <span className="text-destructive"> · {s.last_run.jobs_failed} failed</span>
                          )}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground italic">Never run</p>
                      )}
                    </div>

                    {/* Controls */}
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => toggleLogs(s.id)}
                        className="rounded-md px-2.5 py-1 text-xs font-mono border border-input text-muted-foreground hover:bg-muted transition-colors"
                      >
                        {ss.logsOpen ? '▲ logs' : '▼ logs'}
                      </button>
                      <button
                        onClick={() => triggerRun(s.id)}
                        disabled={ss.triggering || !s.active || agentInactive}
                        className="rounded-md px-3 py-1 text-xs font-medium border border-blue-600 text-blue-600 hover:bg-blue-600/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title={agentInactive ? 'Agent is inactive' : !s.active ? 'Search is paused' : 'Trigger a manual run'}
                      >
                        {ss.triggering ? '…' : '▶ Run Now'}
                      </button>
                      <button
                        onClick={() => toggleSchedule(s.id)}
                        className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                          s.schedule_enabled
                            ? 'border-purple-600 text-purple-600 hover:bg-purple-600/10'
                            : 'border-input text-muted-foreground hover:bg-muted'
                        }`}
                        title={s.schedule_enabled ? 'Daily schedule on' : 'Daily schedule off'}
                      >
                        {s.schedule_enabled ? '⏰ Scheduled' : '⏰ Unscheduled'}
                      </button>
                      <button
                        onClick={() => toggleSearch(s.id)}
                        className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                          s.active
                            ? 'border-green-600 text-green-600 hover:bg-green-600/10'
                            : 'border-input text-muted-foreground hover:bg-muted'
                        }`}
                      >
                        {s.active ? 'Active' : 'Paused'}
                      </button>
                    </div>
                  </div>

                  {/* Run log drawer */}
                  {ss.logsOpen && (
                    <div className="border-t border-border px-4 py-3 bg-muted/20">
                      {ss.loadingLogs ? (
                        <p className="text-xs text-muted-foreground">Loading run history...</p>
                      ) : !ss.runLogs || ss.runLogs.length === 0 ? (
                        <p className="text-xs text-muted-foreground italic">No runs yet.</p>
                      ) : (
                        <table className="w-full text-xs font-mono">
                          <thead>
                            <tr className="text-muted-foreground text-left">
                              {['When', 'Status', 'Fetched', 'Scored', 'Applied', 'Failed', 'Error'].map((h) => (
                                <th key={h} className="pr-4 pb-1.5 font-normal">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {ss.runLogs.map((run) => (
                              <tr key={run.id} className="border-t border-border/50">
                                <td className="pr-4 py-1.5 text-muted-foreground whitespace-nowrap">
                                  {new Date(run.run_at).toLocaleString()}
                                </td>
                                <td className="pr-4 py-1.5"><RunStatusBadge status={run.status} /></td>
                                <td className="pr-4 py-1.5">{run.jobs_fetched}</td>
                                <td className="pr-4 py-1.5">{run.jobs_scored}</td>
                                <td className="pr-4 py-1.5">{run.jobs_applied}</td>
                                <td className="pr-4 py-1.5">
                                  {run.jobs_failed > 0
                                    ? <span className="text-destructive">{run.jobs_failed}</span>
                                    : run.jobs_failed}
                                </td>
                                <td className="py-1.5 text-destructive max-w-xs truncate" title={run.error || ''}>
                                  {run.error || '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
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
          <p className="text-sm text-muted-foreground">No applications yet — trigger a run to start.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-muted-foreground text-xs uppercase tracking-wide">
                  {['Date', 'Company', 'Role', 'Status', 'Score', 'Method', 'Search', 'Failure'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left">{h}</th>
                  ))}
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
                      <a href={app.job_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                        {app.company}
                      </a>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{app.role_title}</td>
                    <td className="px-3 py-2"><StatusBadge status={app.status} /></td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {app.llm_score != null
                        ? <span title={app.llm_score_reason || ''}>{app.llm_score}/10</span>
                        : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                      {app.submission_method || '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{app.search_label}</td>
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

      {/* Dev: raw JSON */}
      <section className="space-y-2">
        {[
          { label: 'Dev: raw user', data: user },
          { label: 'Dev: raw agent', data: agent },
          { label: 'Dev: raw searches', data: searches },
          { label: 'Dev: raw applications', data: applications },
        ].map(({ label, data }) => (
          <details key={label} className="text-xs">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">{label}</summary>
            <pre className="mt-2 rounded-md bg-muted p-3 overflow-x-auto text-muted-foreground">
              {JSON.stringify(data, null, 2)}
            </pre>
          </details>
        ))}
      </section>

    </div>
  );
}

function RunStatusBadge({ status }) {
  const styles = {
    completed: 'text-green-600',
    running: 'text-blue-500',
    partial: 'text-yellow-600',
    failed: 'text-destructive',
  };
  return <span className={`font-mono ${styles[status] || 'text-muted-foreground'}`}>{status}</span>;
}

function StatusBadge({ status }) {
  const styles = {
    submitted: 'text-green-600 border-green-600',
    pending: 'text-yellow-600 border-yellow-600',
    failed: 'text-destructive border-destructive',
    skipped: 'text-muted-foreground border-input',
    deleted: 'text-muted-foreground border-input',
  };
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs font-mono ${styles[status] || 'border-input text-muted-foreground'}`}>
      {status}
    </span>
  );
}