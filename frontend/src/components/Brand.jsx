import React from 'react';

/** The Current mark: a folded newspaper with an electric current running through it. */
export function Logo({ className = 'w-10 h-10' }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      {/* Background brand-700 */}
      <rect width="64" height="64" rx="16" fill="#1F3A5F" />
      {/* Folded newspaper */}
      <g>
        <rect x="17" y="11" width="31" height="40" rx="3" fill="#E5E1D8" opacity="0.7" transform="rotate(-3 32 32)" />
        <rect x="16" y="12" width="31" height="40" rx="3" fill="#F6F4EF" />
        <line x1="16" y1="32" x2="47" y2="32" stroke="#D8D4C8" strokeWidth="0.8" strokeDasharray="1.5 1" />
        <rect x="19" y="16" width="25" height="3.5" rx="1" fill="#1F3A5F" />
        {/* Column lines */}
        <rect x="19" y="21" width="11" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="19" y="24" width="11" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="19" y="27" width="9" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="32" y="21" width="12" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="32" y="24" width="12" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="32" y="27" width="12" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="19" y="35" width="11" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="19" y="38" width="11" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="19" y="41" width="9" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="32" y="35" width="12" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="32" y="38" width="12" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="32" y="41" width="12" height="1.8" rx="0.6" fill="#8FAED1" />
        <rect x="19" y="45" width="25" height="2" rx="0.8" fill="#5F8BBC" />
      </g>
      {/* Electric Current lightning bolt */}
      <path
        d="M 39 8 L 28 27 L 37 27 L 24 56 L 36 33 L 28 33 Z"
        fill="#F5C518"
        stroke="#14253C"
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Wordmark({ className = '' }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <Logo className="w-9 h-9" />
      <span className="font-display font-semibold text-2xl tracking-tight text-ink">Current</span>
    </span>
  );
}
