'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/apiClient';
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

  // Documents
  const [resumeFile, setResumeFile] = useState(null);
  const [portfolioBody, setPortfolioBody] = useState('');
  const [coverLetterBody, setCoverLetterBody] = useState('');

  // Search preferences
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
    if (!coverLetterBody.trim()) return setError('Please add a cover letter sample.');
    if (roleTitles.length === 0) return setError('Please add at least one role title.');

    setLoading(true);

    try {
      const formData = new FormData();

      // Resume
      formData.append('resume', resumeFile);

      // Portfolio (optional — user can fill in more later)
      formData.append('portfolio_label', 'My Portfolio');
      formData.append('portfolio_body', portfolioBody);

      // Cover letter sample
      formData.append('cover_letter_label', 'Default');
      formData.append('cover_letter_body', coverLetterBody);

      // Search preferences
      roleTitles.forEach((t) => formData.append('role_titles', t));
      cities.forEach((c) => formData.append('cities', c));
      locationTypes.forEach((l) => formData.append('location_types', l));
      seniorityLevels.forEach((s) => formData.append('seniority_levels', s));
      if (yearsExperience) formData.append('years_experience', yearsExperience);
      if (salaryMin) formData.append('salary_min', salaryMin);
      excludedCompanies.forEach((c) => formData.append('excluded_companies', c));

      await apiClient.multipart('/api/onboarding/', formData);
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
                Your agent will search for jobs matching these criteria daily.
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

            <Field label="Exclude companies" hint="Your agent will never apply to these.">
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
                Free plan includes 1 resume, 1 portfolio, and 1 cover letter sample.{' '}
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
              label="Portfolio"
              hint="Paste your accomplishments, skills, and career highlights. The more detail you give your agent, the better it can tailor your applications. You can always add more later."
            >
              <textarea
                rows={8}
                value={portfolioBody}
                onChange={(e) => setPortfolioBody(e.target.value)}
                placeholder={`e.g.\n- Led a team of 5 engineers to deliver X, reducing latency by 40%\n- Built and shipped Y from scratch in 3 months\n- Proficient in Python, Django, React, PostgreSQL\n- 5 years of full-stack experience in SaaS products`}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </Field>

            <Field
              label="Cover letter sample *"
              hint="Paste a cover letter written in your voice. Your agent uses this as a reference to match your tone — it won't be sent as-is."
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