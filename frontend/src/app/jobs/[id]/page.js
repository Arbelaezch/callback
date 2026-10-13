'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/apiClient';
import { useApiResource } from '@/hooks/useApiResource';
import DocumentWorkspace from '@/components/documents/DocumentWorkspace';
import { secondaryButtonClass } from '@/components/ui/styles';

const POLL_MS = 3000;
const GENERATION_POLL_TIMEOUT_MS = 5 * 60 * 1000;
const TABS = [
  { kind: 'resume', label: 'Resume' },
  { kind: 'cover_letter', label: 'Cover letter' },
];

// Documents come newest first; the newest of each kind is the current version.
function latestOfKind(documents, kind) {
  return documents.find((d) => d.kind === kind);
}

export default function JobPage() {
  const { id } = useParams();
  const job = useApiResource(`/api/documents/jobs/${id}/`);
  const parsed = useApiResource('/api/documents/resumes/parsed/');
  const [tab, setTab] = useState('resume');
  const [error, setError] = useState(null);
  const [regenerating, setRegenerating] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  const documents = job.data?.documents || [];
  // Only the current version of each kind counts; superseded pending rows are ignored.
  const isPending = TABS.some(({ kind }) => latestOfKind(documents, kind)?.status === 'pending');
  const current = latestOfKind(documents, tab);
  const reloadJob = job.reload;

  useEffect(() => {
    if (!isPending || timedOut) return undefined;
    const poll = setInterval(reloadJob, POLL_MS);
    const stop = setTimeout(() => setTimedOut(true), GENERATION_POLL_TIMEOUT_MS);
    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [isPending, timedOut, reloadJob]);

  async function regenerate() {
    const sourceResume = latestOfKind(documents, 'resume')?.resume;
    const parsedIds = (parsed.data || []).map((p) => p.resume);
    const resumeId = parsedIds.includes(sourceResume) ? sourceResume : parsedIds[0];
    if (!resumeId) return setError('Analyze a resume on your profile first.');
    if (
      documents.some((d) => d.edited) &&
      !window.confirm('Generating again creates a new version. Your edits stay on the old one. Continue?')
    ) {
      return undefined;
    }
    setError(null);
    setTimedOut(false);
    setRegenerating(true);
    try {
      await apiClient.post(`/api/documents/jobs/${id}/generate/`, { resume_id: resumeId });
      reloadJob();
    } catch (err) {
      setError(err?.detail || 'Could not start generation.');
    } finally {
      setRegenerating(false);
    }
    return undefined;
  }

  if (job.loading) {
    return <main className="px-4 py-12 text-sm text-muted-foreground">Loading…</main>;
  }
  if (job.error && !job.data) {
    return (
      <main className="space-y-3 px-4 py-12 text-sm">
        <Link href="/jobs" className="text-muted-foreground hover:text-foreground">
          ← All jobs
        </Link>
        <p className="text-destructive">{job.error.detail || 'Could not load this job.'}</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background px-4 py-10">
      <div className="mx-auto max-w-400 space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link href="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
              ← All jobs
            </Link>
            <h1 className="text-2xl font-semibold tracking-tight">{job.data.title}</h1>
            <p className="text-sm text-muted-foreground">{job.data.company}</p>
          </div>
          <button
            type="button"
            onClick={regenerate}
            disabled={regenerating || (isPending && !timedOut)}
            className={secondaryButtonClass}
          >
            Generate again
          </button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        {job.error && job.data && (
          <p className="text-sm text-destructive">{job.error.detail || 'Could not refresh this job.'}</p>
        )}

        <div className="flex gap-2 border-b border-border">
          {TABS.map(({ kind, label }) => (
            <button
              key={kind}
              type="button"
              onClick={() => setTab(kind)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                tab === kind
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {!current && (
          <p className="text-sm text-muted-foreground">
            Nothing generated yet. Use “Generate again” to start.
          </p>
        )}
        {current?.status === 'pending' && timedOut && (
          <p className="text-sm text-muted-foreground">
            This is taking longer than expected. You can generate again.
          </p>
        )}
        {current?.status === 'pending' && !timedOut && (
          <p className="text-sm text-muted-foreground">
            Writing your {tab === 'resume' ? 'resume' : 'cover letter'}. This usually takes under a minute.
          </p>
        )}
        {current?.status === 'failed' && (
          <p className="text-sm text-destructive">
            Generation failed{current.error ? `: ${current.error}` : '.'} Try generating again.
          </p>
        )}
        {current?.status === 'ready' && (
          <DocumentWorkspace key={current.id} doc={current} company={job.data.company} />
        )}
      </div>
    </main>
  );
}
