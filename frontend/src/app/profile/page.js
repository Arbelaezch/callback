'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/apiClient';
import { useApiResource } from '@/hooks/useApiResource';
import Field from '@/components/ui/Field';
import {
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
  textareaClass,
} from '@/components/ui/styles';

const POLL_MS = 3000;
const PARSE_POLL_TIMEOUT_MS = 3 * 60 * 1000;

function errorText(err, fallback) {
  return err?.detail || fallback;
}

function SectionHeading({ title, description }) {
  return (
    <div className="border-b border-border pb-2">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function ResumeSection({ parsedIds, reloadParsed }) {
  const resumes = useApiResource('/api/users/resumes/');
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  // In-progress state comes from the server, so a page refresh still shows it.
  const isWaiting = (resumes.data || []).some((r) => r.parse_status === 'pending');
  const reloadResumes = resumes.reload;

  // Reload the parsed list once more after the last pending resume clears.
  const wasWaiting = useRef(false);
  useEffect(() => {
    if (wasWaiting.current && !isWaiting) reloadParsed();
    wasWaiting.current = isWaiting;
  }, [isWaiting, reloadParsed]);

  useEffect(() => {
    if (!isWaiting || timedOut) return undefined;
    const poll = setInterval(() => {
      reloadResumes();
      reloadParsed();
    }, POLL_MS);
    const stop = setTimeout(() => setTimedOut(true), PARSE_POLL_TIMEOUT_MS);
    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [isWaiting, timedOut, reloadResumes, reloadParsed]);

  async function analyze(resumeId) {
    setError(null);
    setTimedOut(false);
    try {
      await apiClient.post(`/api/documents/resumes/${resumeId}/parse/`, {});
    } catch (err) {
      setError(errorText(err, 'Could not start analysis.'));
    } finally {
      reloadResumes();
    }
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('resume', file);
      const created = await apiClient.multipart('/api/users/resumes/', formData);
      await analyze(created.id);
    } catch (err) {
      setError(errorText(err, 'Upload failed.'));
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="space-y-4">
      <SectionHeading
        title="Resume"
        description="Upload your current resume as a PDF. We read its content and copy its layout, so tailored versions look like yours."
      />

      <ul className="space-y-2">
        {(resumes.data || []).map((resume) => {
          const parsed = resume.parse_status === 'ready' || parsedIds.has(resume.id);
          const pending = resume.parse_status === 'pending';
          const failed = resume.parse_status === 'failed';
          const retry = (
            <button
              type="button"
              onClick={() => analyze(resume.id)}
              className={secondaryButtonClass}
            >
              Retry
            </button>
          );
          return (
            <li
              key={resume.id}
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2 text-sm"
            >
              <span className="truncate">{resume.label || resume.filename}</span>
              {pending && !timedOut ? (
                <span className="text-xs text-muted-foreground">Analyzing…</span>
              ) : pending ? (
                <span className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Taking longer than expected.</span>
                  {retry}
                </span>
              ) : failed ? (
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    className="truncate text-xs text-destructive"
                    title={resume.parse_error}
                  >
                    Failed: {resume.parse_error}
                  </span>
                  {retry}
                </span>
              ) : parsed ? (
                <span className="text-xs text-muted-foreground">Ready</span>
              ) : resume.status === 'ready' ? (
                <button
                  type="button"
                  onClick={() => analyze(resume.id)}
                  className={secondaryButtonClass}
                >
                  Analyze
                </button>
              ) : (
                <span className="text-xs text-destructive">Upload {resume.status}</span>
              )}
            </li>
          );
        })}
        {resumes.data?.length === 0 && (
          <li className="text-sm text-muted-foreground">No resume yet.</li>
        )}
      </ul>

      <label className={`${secondaryButtonClass} inline-block cursor-pointer`}>
        {uploading ? 'Uploading…' : 'Upload resume (PDF)'}
        <input
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleUpload}
          disabled={uploading}
          className="hidden"
        />
      </label>

      {(error || resumes.error) && (
        <p className="text-sm text-destructive">
          {error || errorText(resumes.error, 'Could not load resumes.')}
        </p>
      )}
    </section>
  );
}

function SourcesSection() {
  const sources = useApiResource('/api/documents/sources/');
  const [label, setLabel] = useState('');
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (label.trim()) formData.append('label', label.trim());
      await apiClient.multipart('/api/documents/sources/', formData);
      setLabel('');
    } catch (err) {
      setError(errorText(err, 'Upload failed.'));
    } finally {
      setUploading(false);
      sources.reload();
    }
  }

  async function remove(id) {
    setError(null);
    try {
      await apiClient.delete(`/api/documents/sources/${id}/`);
      sources.reload();
    } catch (err) {
      setError(errorText(err, 'Could not delete.'));
    }
  }

  return (
    <section className="space-y-4">
      <SectionHeading
        title="Supporting documents"
        description="Optional. A text or markdown file listing your projects and accomplishments. The more detail, the better the tailoring. Only what you add here is ever searched."
      />

      <ul className="space-y-2">
        {(sources.data || []).map((source) => (
          <li
            key={source.id}
            className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2 text-sm"
          >
            <span className="truncate">{source.label}</span>
            <span className="flex items-center gap-3">
              <span
                className={`text-xs ${
                  source.status === 'failed' ? 'text-destructive' : 'text-muted-foreground'
                }`}
              >
                {source.status === 'failed' ? source.error || 'Failed' : source.status}
              </span>
              <button
                type="button"
                onClick={() => remove(source.id)}
                className={secondaryButtonClass}
              >
                Remove
              </button>
            </span>
          </li>
        ))}
        {sources.data?.length === 0 && (
          <li className="text-sm text-muted-foreground">Nothing added yet.</li>
        )}
      </ul>

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Name (optional)"
          className={`${inputClass} max-w-48`}
        />
        <label className={`${secondaryButtonClass} cursor-pointer`}>
          {uploading ? 'Uploading…' : 'Upload .md or .txt'}
          <input
            type="file"
            accept=".md,.txt,text/markdown,text/plain"
            onChange={handleUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {(error || sources.error) && (
        <p className="text-sm text-destructive">
          {error || errorText(sources.error, 'Could not load documents.')}
        </p>
      )}
    </section>
  );
}

function CoverLetterSection() {
  const sample = useApiResource('/api/documents/cover-letter-sample/');

  if (sample.loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (sample.error) {
    return (
      <p className="text-sm text-destructive">
        {errorText(sample.error, 'Could not load your cover letter.')}
      </p>
    );
  }
  return <CoverLetterForm initialBody={sample.data.body} />;
}

function CoverLetterForm({ initialBody }) {
  const [body, setBody] = useState(initialBody);
  const [saved, setSaved] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function save() {
    setError(null);
    setSaving(true);
    try {
      await apiClient.put('/api/documents/cover-letter-sample/', { body });
      setSaved(true);
    } catch (err) {
      setError(errorText(err, 'Could not save.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="space-y-4">
      <SectionHeading
        title="Cover letter sample"
        description="A cover letter you have written. It teaches the writer your voice; its facts are never reused."
      />
      <Field label="Your cover letter">
        <textarea
          rows={10}
          value={body}
          onChange={(e) => {
            setBody(e.target.value);
            setSaved(false);
          }}
          className={textareaClass}
        />
      </Field>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || saved || !body.trim()}
          className={primaryButtonClass}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved && body && <span className="text-xs text-muted-foreground">Saved</span>}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </section>
  );
}

export default function ProfilePage() {
  const parsed = useApiResource('/api/documents/resumes/parsed/');
  const parsedIds = new Set((parsed.data || []).map((p) => p.resume));

  return (
    <main className="min-h-screen bg-background px-4 py-12">
      <div className="mx-auto max-w-2xl space-y-10">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Your profile</h1>
          <p className="text-sm text-muted-foreground">
            Set this up once. Every tailored resume and cover letter starts from it.
          </p>
        </div>

        <ResumeSection parsedIds={parsedIds} reloadParsed={parsed.reload} />
        <SourcesSection />
        <CoverLetterSection />

        {parsedIds.size > 0 && (
          <Link href="/jobs/new" className={`${primaryButtonClass} inline-block`}>
            Tailor for a job →
          </Link>
        )}
      </div>
    </main>
  );
}
