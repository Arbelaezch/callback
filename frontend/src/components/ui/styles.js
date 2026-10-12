// Shared Tailwind class strings so form controls look the same on every page.

export const inputClass =
  'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring';

export const textareaClass = `${inputClass} resize-y`;

export const primaryButtonClass =
  'rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50';

export const secondaryButtonClass =
  'rounded-md border border-input px-3 py-1.5 text-sm text-foreground hover:bg-muted transition-colors disabled:opacity-50';
