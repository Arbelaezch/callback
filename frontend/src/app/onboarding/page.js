'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useChoices } from '@/hooks/onboarding/useChoices';
import TagInput from '@/components/ui/TagInput';

function ToggleGroup({ options = [], value, onChange }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(({ value: opt, label }) => {
        const active = value.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() =>
              onChange(active ? value.filter((v) => v !== opt) : [...value, opt])
            }
            className={`rounded-full px-3 py-1 text-sm font-medium border transition-colors ${
              active
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-background text-muted-foreground border-input hover:border-primary/50'
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const { choices, loading: choicesLoading } = useChoices();

  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const [resumeFile, setResumeFile] = useState(null);
  const [coverLetterBody, setCoverLetterBody] = useState('');
  const [roleTitles, setRoleTitles] = useState([]);
  const [cities, setCities] = useState([]);
  const [locationTypes, setLocationTypes] = useState([]);
  const [seniorityLevels, setSeniorityLevels] = useState([]);
  const [yearsExperience, setYearsExperience] = useState('');
  const [salaryMin, setSalaryMin] = useState('');
  const [excludedCompanies, setExcludedCompanies] = useState([]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (!resumeFile) return setError('Please upload your resume.');
    if (!coverLetterBody.trim()) return setError('Please add a cover letter template.');
    if (roleTitles.length === 0) return setError('Please add at least one role title.');

    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('resume', resumeFile);
      formData.append('cover_letter_label', 'Default');
      formData.append('cover_letter_body', coverLetterBody);
      roleTitles.forEach((t) => formData.append('role_titles', t));
      cities.forEach((c) => formData.append('cities', c));
      locationTypes.forEach((l) => formData.append('location_types', l));
      seniorityLevels.forEach((s) => formData.append('seniority_levels', s));
      if (yearsExperience) formData.append('years_experience', yearsExperience);
      if (salaryMin) formData.append('salary_min', salaryMin);
      excludedCompanies.forEach((c) => formData.append('excluded_companies', c));

      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/onboarding/`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
        // No Content-Type — browser sets multipart boundary automatically
      });

      router.push('/dashboard');
    } catch (err) {
      setError(err.detail || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-background px-4 py-12">
      <div className="mx-auto max-w-2xl space-y-10">

        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Let's get you set up</h1>
          <p className="text-sm text-muted-foreground">
            This takes about 2 minutes. You can update everything from your dashboard later.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-10">

          {/* Section 1 — Job Search */}
          <section className="space-y-6">
            <div className="border-b border-border pb-2">
              <h2 className="text-base font-semibold">Job search preferences</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Callback will search for jobs matching these criteria daily.
              </p>
            </div>

            <Field label="Role titles *" hint="Press Enter or comma to add. e.g. 'Software Engineer', 'Backend Developer'">
              <TagInput
                id="role_titles"
                value={roleTitles}
                onChange={setRoleTitles}
                placeholder="Add a role title..."
              />
            </Field>

            <Field label="Cities" hint="Leave empty to search everywhere.">
              <TagInput
                id="cities"
                value={cities}
                onChange={setCities}
                placeholder="Add a city..."
              />
            </Field>

            <Field label="Location type">
              <ToggleGroup
                options={choices?.location_types ?? []}
                value={locationTypes}
                onChange={setLocationTypes}
              />
            </Field>

            <Field label="Seniority">
              <ToggleGroup
                options={choices?.seniority_levels ?? []}
                value={seniorityLevels}
                onChange={setSeniorityLevels}
              />
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field label="Years of experience">
                <input
                  type="number"
                  min="0"
                  max="50"
                  value={yearsExperience}
                  onChange={(e) => setYearsExperience(e.target.value)}
                  placeholder="e.g. 5"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </Field>

              <Field label="Minimum salary (CAD)">
                <input
                  type="number"
                  min="0"
                  value={salaryMin}
                  onChange={(e) => setSalaryMin(e.target.value)}
                  placeholder="e.g. 80000"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </Field>
            </div>

            <Field label="Exclude companies" hint="Callback will never apply to these.">
              <TagInput
                id="excluded_companies"
                value={excludedCompanies}
                onChange={setExcludedCompanies}
                placeholder="Add a company to exclude..."
              />
            </Field>
          </section>

          {/* Section 2 — Documents */}
          <section className="space-y-6">
            <div className="border-b border-border pb-2">
              <h2 className="text-base font-semibold">Documents</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Free plan includes 1 resume and 1 cover letter template.{' '}
                <span className="text-primary font-medium cursor-pointer hover:underline">
                  Upgrade for more →
                </span>
              </p>
            </div>

            <Field label="Resume *" hint="PDF only, max 5MB.">
              <div className="flex items-center gap-3">
                <label
                  htmlFor="resume"
                  className="cursor-pointer rounded-md border border-input px-4 py-2 text-sm hover:bg-muted transition-colors"
                >
                  {resumeFile ? resumeFile.name : 'Choose file'}
                </label>
                <input
                  id="resume"
                  type="file"
                  accept=".pdf"
                  className="sr-only"
                  onChange={(e) => setResumeFile(e.target.files[0] || null)}
                />
                {resumeFile && (
                  <span className="text-xs text-muted-foreground">
                    {(resumeFile.size / 1024 / 1024).toFixed(2)} MB
                  </span>
                )}
              </div>
            </Field>

            <Field
              label="Cover letter template *"
              hint="Callback will personalise the company name, role title, and opening sentence for each application. Keep everything else as-is."
            >
              <textarea
                rows={10}
                value={coverLetterBody}
                onChange={(e) => setCoverLetterBody(e.target.value)}
                placeholder={`Dear Hiring Manager,\n\nI am excited to apply for the [Role] position at [Company]...`}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </Field>
          </section>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={loading || choicesLoading}
            className="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? 'Setting up your account...' : 'Start applying →'}
          </button>
        </form>
      </div>
    </main>
  );
}