import React from 'react';

/** The Dose mark: a drop of knowledge with a small amber spark. */
export function Logo({ className = 'w-10 h-10' }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect width="64" height="64" rx="18" fill="#147f74" />
      <path d="M32 12c7 9 14 17 14 25a14 14 0 0 1-28 0c0-8 7-16 14-25z" fill="#fff" />
      <circle cx="37" cy="38" r="5" fill="#fbab24" />
    </svg>
  );
}

export function Wordmark({ className = '' }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <Logo className="w-9 h-9" />
      <span className="font-display font-semibold text-2xl tracking-tight text-ink">Dose</span>
    </span>
  );
}
