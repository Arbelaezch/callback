'use client';

import Link from 'next/link';
import { useApiResource } from '@/hooks/useApiResource';
import { primaryButtonClass } from '@/components/ui/styles';

const KINDS = ['resume', 'cover_letter'];

// Documents come newest first; the newest of each kind is the current version.
function latestOfKind(documents, kind) {
  return documents.find((d) => d.kind === kind);
}

function statusLabel(job) {
  const docs = job.documents || [];
  if (docs.length === 0) return 'Not generated';
  const latest = KINDS.map((kind) => latestOfKind(docs, kind));
  if (latest.some((d) => d?.status === 'pending')) return 'Generating…';
  if (latest.every((d) => d?.status === 'ready')) return 'Ready';
  return 'Failed';
}

export default function JobsPage() {
  const jobs = useApiResource('/api/documents/jobs/');

  return (
    <main className="min-h-screen bg-background px-4 py-12">
      <div className="mx-auto max-w-2xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Your jobs</h1>
          <Link href="/jobs/new" className={primaryButtonClass}>
            New job
          </Link>
        </div>

        {jobs.loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {jobs.error && (
          <p className="text-sm text-destructive">{jobs.error.detail || 'Could not load your jobs.'}</p>
        )}

        {jobs.data?.length === 0 && (
          <div className="rounded-md border border-border bg-card p-6 text-sm">
            <p className="font-medium">Nothing here yet.</p>
            <p className="mt-1 text-muted-foreground">
              Add your resume on your{' '}
              <Link href="/profile" className="underline">
                profile
              </Link>
              , then paste in a job description to get a tailored resume and cover letter.
            </p>
          </div>
        )}

        <ul className="space-y-2">
          {(jobs.data || []).map((job) => (
            <li key={job.id}>
              <Link
                href={`/jobs/${job.id}`}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-4 py-3 hover:bg-muted transition-colors"
              >
                <span>
                  <span className="block text-sm font-medium">{job.title}</span>
                  <span className="block text-xs text-muted-foreground">{job.company}</span>
                </span>
                <span className="text-xs text-muted-foreground">{statusLabel(job)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
