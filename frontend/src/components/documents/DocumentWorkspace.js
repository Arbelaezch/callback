'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '@/lib/apiClient';
import { cleanResume } from '@/lib/resumeContent';
import { primaryButtonClass, textareaClass } from '@/components/ui/styles';
import DocumentPreview from './DocumentPreview';
import ResumeEditor from './ResumeEditor';

const AUTOSAVE_MS = 1200;

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function slug(text) {
  return (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/**
 * Edit one ready document next to its live preview. Edits autosave shortly
 * after the user stops typing and the preview refreshes from the server, so
 * the preview is always the same HTML the PDF is made from.
 *
 * Mount with `key={doc.id}` so a new version starts from fresh state.
 */
export default function DocumentWorkspace({ doc, company }) {
  const isResume = doc.kind === 'resume';
  const [draft, setDraft] = useState(isResume ? doc.content : doc.markdown);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState('saved');
  const [previewHtml, setPreviewHtml] = useState('');
  const [pageCount, setPageCount] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const latest = useRef(draft);

  const previewPath = `/api/documents/documents/${doc.id}/preview/`;

  const refreshPreview = useCallback(() => {
    apiClient.getText(previewPath).then(setPreviewHtml, () => setError('Could not load the preview.'));
  }, [previewPath]);

  useEffect(() => {
    refreshPreview();
  }, [refreshPreview]);

  const save = useCallback(async () => {
    const snapshot = latest.current;
    setSaveState('saving');
    try {
      await apiClient.patch(
        `/api/documents/documents/${doc.id}/`,
        isResume ? { content: cleanResume(snapshot) } : { markdown: snapshot },
      );
      // Edits made while the request was in flight stay dirty.
      if (latest.current === snapshot) setDirty(false);
      setSaveState('saved');
      setError(null);
      refreshPreview();
      return true;
    } catch (err) {
      setSaveState('error');
      setError(err?.detail || 'Could not save your changes.');
      return false;
    }
  }, [doc.id, isResume, refreshPreview]);

  useEffect(() => {
    if (!dirty) return undefined;
    const timer = setTimeout(save, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [dirty, draft, save]);

  function handleChange(next) {
    latest.current = next;
    setDraft(next);
    setDirty(true);
    setSaveState('unsaved');
  }

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      if (dirty && !(await save())) return;
      const { blob, pageCount: pages } = await apiClient.getBlob(
        `/api/documents/documents/${doc.id}/export/`,
      );
      setPageCount(pages);
      const name = isResume ? 'resume' : 'cover-letter';
      downloadBlob(blob, `${name}-${slug(company) || 'job'}.pdf`);
    } catch (err) {
      setError(err?.detail || 'Export failed.');
    } finally {
      setExporting(false);
    }
  }

  const claims = doc.unsupported_claims || [];
  const statusText = {
    saved: 'Saved',
    saving: 'Saving…',
    unsaved: 'Unsaved changes',
    error: 'Not saved',
  }[saveState];

  return (
    <div className="space-y-4">
      {claims.length > 0 && (
        <div className="rounded-md border border-border bg-card p-3 text-sm">
          <p className="font-medium">Check these before you send it</p>
          <p className="mb-2 text-xs text-muted-foreground">
            Our fact-checker could not find these in your resume or documents.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {claims.map((claim, i) => (
              <li key={i}>
                <span>{claim.claim}</span>
                <span className="text-muted-foreground"> — {claim.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={handleExport} disabled={exporting} className={primaryButtonClass}>
          {exporting ? 'Preparing PDF…' : 'Download PDF'}
        </button>
        <span className="text-xs text-muted-foreground">{statusText}</span>
        {isResume && pageCount > 1 && (
          <span className="text-xs text-destructive">
            This resume runs to {pageCount} pages. Trim it to fit on one.
          </span>
        )}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* A letter page is 51rem wide plus the preview padding; side by side only when the screen fits editor + page. */}
      <div className="grid gap-6 min-[1400px]:grid-cols-[minmax(0,1fr)_52.5rem]">
        <div>
          {isResume ? (
            <ResumeEditor content={draft} onChange={handleChange} />
          ) : (
            <textarea
              rows={24}
              value={draft}
              onChange={(e) => handleChange(e.target.value)}
              className={textareaClass}
              aria-label="Cover letter"
            />
          )}
        </div>
        <DocumentPreview html={previewHtml} />
      </div>
    </div>
  );
}
