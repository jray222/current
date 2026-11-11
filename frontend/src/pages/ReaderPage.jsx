import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { onLinkClick } from '../lib/router';

export default function ReaderPage({ id }) {
  return (
    <article className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <a
          href="/"
          onClick={onLinkClick('/')}
          className="btn-soft inline-flex items-center gap-1.5 text-xs font-bold !py-1.5"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Edition
        </a>
      </div>

      <div className="card card-pad space-y-4">
        <header className="space-y-2">
          <p className="text-xs font-bold text-muted uppercase tracking-wider">Reader View</p>
          <h1 className="text-2xl sm:text-3xl font-display font-semibold text-ink">
            Article {id}
          </h1>
        </header>
        <p className="text-muted leading-relaxed">
          Clean article reader view with ad-free structured blocks, customizable typography, and reading metrics.
        </p>
      </div>
    </article>
  );
}
