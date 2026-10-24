import React from 'react';

/** A titled card inside a settings page. */
export default function Section({ title, hint, children, tone }) {
  return (
    <section className={`card card-pad space-y-4 mb-5 ${tone || ''}`}>
      <div>
        <h2 className="text-xl">{title}</h2>
        {hint && <p className="text-sm text-muted mt-0.5">{hint}</p>}
      </div>
      {children}
    </section>
  );
}
