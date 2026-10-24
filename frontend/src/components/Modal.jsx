import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

/** Dialog that is a bottom sheet on phones and a centered card from sm up. */
export default function Modal({ open, title, subtitle, onClose, children, maxWidth = 'sm:max-w-md' }) {
  const dialogRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    // With one dialog over another, Escape closes only the top one.
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (dialogs[dialogs.length - 1] === dialogRef.current) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex justify-center items-end sm:items-center z-50 sm:p-4"
      onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`sheet-in bg-surface rounded-t-4xl sm:rounded-4xl shadow-lift w-full ${maxWidth} max-h-[92vh] overflow-y-auto p-5 sm:p-6 space-y-4 pb-[max(1.25rem,env(safe-area-inset-bottom))]`}
      >
        <div className="mx-auto h-1.5 w-10 rounded-full bg-line sm:hidden" aria-hidden="true" />
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl">{title}</h3>
            {subtitle && <p className="text-sm text-muted mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label="Close" className="btn-icon text-muted hover:bg-sunk hover:text-ink -mr-2 -mt-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const inputClass = 'input';

export function Field({ label, hint, children, htmlFor }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="text-xs text-muted mt-1.5">{hint}</p>}
    </div>
  );
}

export function FormActions({ onCancel, submitLabel, disabled }) {
  return (
    <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-3">
      <button type="button" onClick={onCancel} className="btn-soft">Cancel</button>
      <button type="submit" disabled={disabled} className="btn-primary">{submitLabel}</button>
    </div>
  );
}
