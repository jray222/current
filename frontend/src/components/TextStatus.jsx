import React from 'react';
import { Loader2, ExternalLink, AlertTriangle, BookOpen, Clock } from 'lucide-react';

export default function TextStatus({
  textStatus = 'none',
  wordCount = 0,
  url = '',
  loading = false,
  onFetchText,
}) {
  const readingTime = Math.max(1, Math.round(wordCount / 220));

  if (textStatus === 'ok') {
    return (
      <div className="flex items-center gap-3 py-3 px-4 rounded-xl bg-cream-100 dark:bg-ink-800/60 text-xs text-ink-600 dark:text-ink-400 mb-6">
        <div className="flex items-center gap-1.5 font-medium">
          <BookOpen className="w-4 h-4 text-brand-600 dark:text-volt-400" />
          <span>Full Article</span>
        </div>
        <span>•</span>
        <div className="flex items-center gap-1">
          <Clock className="w-3.5 h-3.5" />
          <span>{readingTime} min read ({wordCount} words)</span>
        </div>
      </div>
    );
  }

  if (textStatus === 'queued' || textStatus === 'running' || loading) {
    return (
      <div className="flex items-center gap-2.5 p-4 rounded-xl bg-cream-100 dark:bg-ink-800/80 text-sm text-ink-700 dark:text-ink-300 mb-6">
        <Loader2 className="w-4 h-4 animate-spin text-brand-600 dark:text-volt-400" />
        <span>Extracting clean full text from publisher...</span>
      </div>
    );
  }

  if (textStatus === 'partial') {
    return (
      <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40 text-xs text-amber-800 dark:text-amber-200 mb-6 space-y-2">
        <div className="flex items-center gap-2 font-semibold">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>Partial preview — full text may be gated or subscriber-only.</span>
        </div>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-brand-700 dark:text-volt-400 font-semibold hover:underline pt-1"
          >
            <span>Read full story on original site</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    );
  }

  // textStatus === 'none' or 'failed'
  return (
    <div className="p-5 rounded-2xl bg-cream-100 dark:bg-ink-800/80 border border-cream-200 dark:border-ink-700/60 text-center my-6">
      <h3 className="font-serif font-bold text-base text-ink-900 dark:text-cream-100 mb-1">
        Read In Current
      </h3>
      <p className="text-xs text-ink-600 dark:text-ink-400 mb-4 max-w-sm mx-auto">
        Extract clean, distraction-free reading text without ads or clutter.
      </p>
      <div className="flex items-center justify-center gap-3">
        <button
          onClick={onFetchText}
          disabled={loading}
          className="flex items-center gap-1.5 bg-brand-700 hover:bg-brand-800 dark:bg-brand-600 dark:hover:bg-brand-500 text-white px-4 py-2 rounded-xl text-xs font-semibold shadow-xs transition-colors"
        >
          {loading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Loading text...</span>
            </>
          ) : (
            <>
              <BookOpen className="w-3.5 h-3.5" />
              <span>Load Full Text</span>
            </>
          )}
        </button>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-ink-700 dark:text-ink-300 hover:text-brand-700 dark:hover:text-volt-400 font-medium px-3 py-2 rounded-xl hover:bg-cream-200 dark:hover:bg-ink-700 transition-colors"
          >
            <span>Open Original</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>
    </div>
  );
}
