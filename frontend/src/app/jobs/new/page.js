'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/apiClient';
import { useApiResource } from '@/hooks/useApiResource';
import Field from '@/components/ui/Field';
import { inputClass, primaryButtonClass, textareaClass } from '@/components/ui/styles';

export default function NewJobPage() {
  const router = useRouter();
  const parsed = useApiResource('/api/documents/resumes/parsed/');
  const resumes = useApiResource('/api/users/resumes/');

  const [title, setTitle] = useState('');
  const [company, setCompany] = useState('');
  const [description, setDescription] = useState('');
  const [resumeId, setResumeId] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const parsedIds = new Set((parsed.data || []).map((p) => p.resume));
  const usable = (resumes.data || []).filter((r) => parsedIds.has(r.id));
  const selected = resumeId || String(usable[0]?.id || '');
  const ready = !parsed.loading && !resumes.loading;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!title.trim() || !company.trim() || !description.trim()) {
      return setError('Please fill in the title, company and job description.');
    }
    setSubmitting(true);
    try {
      const job = await apiClient.post('/api/documents/jobs/', { title, company, description });
      await apiClient.post(`/api/documents/jobs/${job.id}/generate/`, { resume_id: Number(selected) });
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err?.detail || 'Something went wrong. Please try again.');
      setSubmitting(false);
    }
  }

  if (ready && usable.length === 0) {
    return (
      <main className="min-h-screen bg-background px-4 py-12">
        <div className="mx-auto max-w-2xl space-y-3">
          <h1 className="text-2xl font-semibold tracking-tight">New job</h1>
          <p className="text-sm text-muted-foreground">
            Add and analyze your resume first. It only takes a minute.
          </p>
          <Link href="/profile" className={`${primaryButtonClass} inline-block`}>
            Go to your profile
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background px-4 py-12">
      <form onSubmit={handleSubmit} className="mx-auto max-w-2xl space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">New job</h1>
          <p className="text-sm text-muted-foreground">
            Paste the job description. We will tailor your resume and write a cover letter for it.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Job title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Company">
            <input value={company} onChange={(e) => setCompany(e.target.value)} className={inputClass} />
          </Field>
        </div>

        <Field label="Job description" hint="Paste the full posting.">
          <textarea
            rows={14}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={textareaClass}
          />
        </Field>

        {usable.length > 1 && (
          <Field label="Resume to start from">
            <select value={selected} onChange={(e) => setResumeId(e.target.value)} className={inputClass}>
              {usable.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label || r.filename}
                </option>
              ))}
            </select>
          </Field>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <button type="submit" disabled={submitting || !ready} className={primaryButtonClass}>
          {submitting ? 'Starting…' : 'Generate documents'}
        </button>
      </form>
    </main>
  );
}
