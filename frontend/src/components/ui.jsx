import React from 'react';
import { AlertCircle, Check, Loader2 } from 'lucide-react';

export const errorOf = (err, fallback) => err?.response?.data?.detail || fallback;

export function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div className="banner-error" role="alert">
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      <p>{typeof message === 'string' ? message : 'Something went wrong.'}</p>
    </div>
  );
}

export function SuccessBanner({ message }) {
  if (!message) return null;
  return (
    <div className="banner-ok" role="status">
      <Check className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex justify-center py-10 text-muted" role="status" aria-label={label}>
      <Loader2 className="w-6 h-6 animate-spin" />
    </div>
  );
}

/** A friendly blank state: a big icon on a coloured blob, a headline, a line of help and an action. */
export function EmptyState({ icon: Icon, title, children, tone = 'brand' }) {
  const tones = {
    brand: 'bg-brand-100 text-brand-600 dark:bg-brand-900/50 dark:text-brand-300',
    leaf: 'bg-moss-100 text-moss-700 dark:bg-moss-900/50 dark:text-moss-300',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-600/20 dark:text-amber-300',
  };
  return (
    <div className="flex flex-col items-center text-center py-12 px-6 max-w-sm mx-auto">
      <div className={`w-24 h-24 rounded-4xl flex items-center justify-center rotate-3 ${tones[tone]}`}>
        <Icon className="w-11 h-11" aria-hidden="true" />
      </div>
      <h2 className="text-2xl mt-6">{title}</h2>
      <div className="text-muted mt-2 space-y-4">{children}</div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, back }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-5">
      <div className="min-w-0">
        {back}
        <h1 className="text-3xl sm:text-4xl leading-tight">{title}</h1>
        {subtitle && <p className="text-muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
