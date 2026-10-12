'use client';

import Field from '@/components/ui/Field';
import { inputClass, secondaryButtonClass, textareaClass } from '@/components/ui/styles';
import { moveItem, patchItem } from '@/lib/resumeContent';

function TextField({ label, value, onChange }) {
  return (
    <Field label={label}>
      <input value={value || ''} onChange={(e) => onChange(e.target.value)} className={inputClass} />
    </Field>
  );
}

// One item per line. Blank lines are kept while typing and dropped on save.
function LinesField({ label, hint, value, onChange, rows = 4 }) {
  return (
    <Field label={label} hint={hint}>
      <textarea
        rows={rows}
        value={(value || []).join('\n')}
        onChange={(e) => onChange(e.target.value.split('\n'))}
        className={textareaClass}
      />
    </Field>
  );
}

function EntryList({ title, items = [], onChange, blank, renderItem }) {
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      {items.map((item, index) => (
        <div key={index} className="space-y-3 rounded-md border border-border bg-card p-3">
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => onChange(moveItem(items, index, -1))}
              disabled={index === 0}
              aria-label="Move up"
              className={secondaryButtonClass}
            >
              ↑
            </button>
            <button
              type="button"
              onClick={() => onChange(moveItem(items, index, 1))}
              disabled={index === items.length - 1}
              aria-label="Move down"
              className={secondaryButtonClass}
            >
              ↓
            </button>
            <button
              type="button"
              onClick={() => onChange(items.filter((_, i) => i !== index))}
              className={secondaryButtonClass}
            >
              Remove
            </button>
          </div>
          {renderItem(item, (patch) => onChange(patchItem(items, index, patch)))}
        </div>
      ))}
      <button type="button" onClick={() => onChange([...items, blank])} className={secondaryButtonClass}>
        + Add
      </button>
    </section>
  );
}

/** Field-by-field editor for the resume content JSON. */
export default function ResumeEditor({ content, onChange }) {
  const header = content.header || {};
  const set = (patch) => onChange({ ...content, ...patch });

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Header</h3>
        <TextField label="Name" value={header.name} onChange={(v) => set({ header: { ...header, name: v } })} />
        <TextField
          label="Headline"
          value={header.headline}
          onChange={(v) => set({ header: { ...header, headline: v } })}
        />
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField label="Email" value={header.email} onChange={(v) => set({ header: { ...header, email: v } })} />
          <TextField label="Phone" value={header.phone} onChange={(v) => set({ header: { ...header, phone: v } })} />
          <TextField
            label="Location"
            value={header.location}
            onChange={(v) => set({ header: { ...header, location: v } })}
          />
        </div>
        <LinesField
          label="Links"
          hint="One per line."
          rows={2}
          value={header.links}
          onChange={(v) => set({ header: { ...header, links: v } })}
        />
      </section>

      <Field label="Summary">
        <textarea
          rows={3}
          value={content.summary || ''}
          onChange={(e) => set({ summary: e.target.value })}
          className={textareaClass}
        />
      </Field>

      <EntryList
        title="Experience"
        items={content.experience}
        onChange={(experience) => set({ experience })}
        blank={{ company: '', title: '', location: '', start: '', end: '', bullets: [''] }}
        renderItem={(job, update) => (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Company" value={job.company} onChange={(v) => update({ company: v })} />
              <TextField label="Title" value={job.title} onChange={(v) => update({ title: v })} />
              <TextField label="Start" value={job.start} onChange={(v) => update({ start: v })} />
              <TextField label="End" value={job.end} onChange={(v) => update({ end: v })} />
            </div>
            <LinesField label="Bullets" hint="One per line." value={job.bullets} onChange={(v) => update({ bullets: v })} />
          </>
        )}
      />

      <EntryList
        title="Projects"
        items={content.projects}
        onChange={(projects) => set({ projects })}
        blank={{ name: '', link: '', bullets: [''] }}
        renderItem={(project, update) => (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Name" value={project.name} onChange={(v) => update({ name: v })} />
              <TextField label="Link" value={project.link} onChange={(v) => update({ link: v })} />
            </div>
            <LinesField
              label="Bullets"
              hint="One per line."
              value={project.bullets}
              onChange={(v) => update({ bullets: v })}
            />
          </>
        )}
      />

      <EntryList
        title="Education"
        items={content.education}
        onChange={(education) => set({ education })}
        blank={{ school: '', degree: '', start: '', end: '', details: [] }}
        renderItem={(school, update) => (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="School" value={school.school} onChange={(v) => update({ school: v })} />
              <TextField label="Degree" value={school.degree} onChange={(v) => update({ degree: v })} />
              <TextField label="Start" value={school.start} onChange={(v) => update({ start: v })} />
              <TextField label="End" value={school.end} onChange={(v) => update({ end: v })} />
            </div>
            <LinesField
              label="Details"
              hint="One per line."
              rows={2}
              value={school.details}
              onChange={(v) => update({ details: v })}
            />
          </>
        )}
      />

      <EntryList
        title="Skills"
        items={content.skills}
        onChange={(skills) => set({ skills })}
        blank={{ category: '', items: [] }}
        renderItem={(group, update) => (
          <>
            <TextField label="Category" value={group.category} onChange={(v) => update({ category: v })} />
            <Field label="Skills" hint="Separate with commas.">
              {/* Uncontrolled and committed on blur so typing commas is not rewritten under the cursor. */}
              <input
                key={(group.items || []).join('|')}
                defaultValue={(group.items || []).join(', ')}
                onBlur={(e) => update({ items: e.target.value.split(',') })}
                className={inputClass}
              />
            </Field>
          </>
        )}
      />
    </div>
  );
}
