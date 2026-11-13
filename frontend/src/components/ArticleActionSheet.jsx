import React, { useEffect } from 'react';
import { Ban, Bookmark, Trash2, BookOpen, X } from 'lucide-react';

export default function ArticleActionSheet({ article, onClose, onDislike, onKeep, onDismiss, onOpenReader }) {
  useEffect(() => {
    if (!article) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [article, onClose]);

  if (!article) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-ink-950/55 backdrop-blur-xs"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Article options"
        className="sheet-in w-full sm:max-w-md bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-t-3xl sm:rounded-3xl shadow-2xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] space-y-4"
      >
        <div className="mx-auto h-1.5 w-10 rounded-full bg-cream-300 dark:bg-ink-700 sm:hidden" aria-hidden="true" />

        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-wider text-brand-700 dark:text-volt-400 truncate">
              {article.source_name || 'Story'}
            </p>
            <h3 className="font-serif font-bold text-base text-ink-950 dark:text-cream-50 leading-snug line-clamp-2 mt-0.5">
              {article.title}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-full text-ink-400 hover:text-ink-700 dark:hover:text-cream-100 hover:bg-cream-100 dark:hover:bg-ink-800 transition-colors shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-2">
          <button
            type="button"
            onClick={() => onDislike(article)}
            className="w-full flex items-center gap-3.5 p-3 rounded-2xl bg-rose-50/90 dark:bg-rose-950/35 border border-rose-200/80 dark:border-rose-800/50 hover:bg-rose-100/80 dark:hover:bg-rose-950/55 text-left transition-colors active:scale-[0.99]"
          >
            <div className="w-10 h-10 rounded-xl bg-rose-600 text-white flex items-center justify-center shrink-0">
              <Ban className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-rose-900 dark:text-rose-100">
                Do not show articles like this
              </div>
              <div className="text-xs text-rose-700/90 dark:text-rose-300/90">
                Hide this story and show fewer like it
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onKeep(article)}
            className="w-full flex items-center gap-3.5 p-3 rounded-2xl bg-cream-50 dark:bg-ink-800/70 border border-cream-200 dark:border-ink-700/70 hover:bg-cream-100 dark:hover:bg-ink-800 text-left transition-colors active:scale-[0.99]"
          >
            <div className="w-10 h-10 rounded-xl bg-emerald-600/15 text-emerald-700 dark:text-emerald-400 flex items-center justify-center shrink-0">
              <Bookmark className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-ink-900 dark:text-cream-100">
                Keep story
              </div>
              <div className="text-xs text-ink-500 dark:text-ink-400">
                Save to Kept and show more like this
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onDismiss(article)}
            className="w-full flex items-center gap-3.5 p-3 rounded-2xl bg-cream-50 dark:bg-ink-800/70 border border-cream-200 dark:border-ink-700/70 hover:bg-cream-100 dark:hover:bg-ink-800 text-left transition-colors active:scale-[0.99]"
          >
            <div className="w-10 h-10 rounded-xl bg-ink-200/70 dark:bg-ink-700 text-ink-700 dark:text-ink-200 flex items-center justify-center shrink-0">
              <Trash2 className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-ink-900 dark:text-cream-100">
                Dismiss
              </div>
              <div className="text-xs text-ink-500 dark:text-ink-400">
                Hide from feed without affecting ranking
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onOpenReader(article.id)}
            className="w-full flex items-center gap-3.5 p-3 rounded-2xl bg-cream-50 dark:bg-ink-800/70 border border-cream-200 dark:border-ink-700/70 hover:bg-cream-100 dark:hover:bg-ink-800 text-left transition-colors active:scale-[0.99]"
          >
            <div className="w-10 h-10 rounded-xl bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center shrink-0">
              <BookOpen className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-ink-900 dark:text-cream-100">
                Open in reader
              </div>
              <div className="text-xs text-ink-500 dark:text-ink-400">
                Read full story and boost similar articles
              </div>
            </div>
          </button>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="w-full py-2.5 rounded-2xl text-xs font-bold text-ink-600 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-ink-800 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
