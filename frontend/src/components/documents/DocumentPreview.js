/**
 * Live preview of a generated document. The HTML comes from the same
 * renderer as the PDF export, so what you see is what you download.
 * Rendered in a sandboxed iframe (no scripts, no navigation).
 */
export default function DocumentPreview({ html }) {
  return (
    <div className="overflow-auto rounded-md border border-border bg-muted p-3">
      {html ? (
        <iframe
          title="Document preview"
          sandbox=""
          srcDoc={html}
          className="mx-auto block h-264 w-204 bg-white"
        />
      ) : (
        <p className="p-6 text-sm text-muted-foreground">Loading preview…</p>
      )}
    </div>
  );
}
