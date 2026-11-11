import React from 'react';
import { Bookmark, Trash2, Layers, Clock } from 'lucide-react';
import { useSwipeRow } from '../lib/useSwipeRow';
import AuthImage from './AuthImage';

function formatRelativeTime(dateStr) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffHours = Math.round((now - date) / (1000 * 60 * 60));
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.round(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return '';
  }
}

export default function LeadStoryCard({ article, onSwipe, onOpenReader }) {
  const { rowRef, offsetX, isDragging, isCollapsing, swipeAction, handlers } = useSwipeRow({
    onSwipeRight: () => onSwipe(article.id, 'keep'),
    onSwipeLeft: () => onSwipe(article.id, 'skip'),
    onTap: () => onOpenReader(article.id),
  });

  if (!article) return null;

  const bgStyle = swipeAction === 'keep'
    ? 'bg-emerald-600 text-white'
    : swipeAction === 'skip'
    ? 'bg-slate-700 text-white'
    : 'bg-cream-200 dark:bg-ink-800 text-ink-500';

  return (
    <div
      ref={rowRef}
      className={`relative overflow-hidden rounded-2xl mb-6 transition-all duration-300 ${
        isCollapsing ? 'max-h-0 opacity-0 mb-0 py-0' : 'max-h-[800px] opacity-100'
      }`}
    >
      {/* Background Action Reveal */}
      <div className={`absolute inset-0 flex items-center justify-between px-6 transition-colors ${bgStyle}`}>
        <div className={`flex items-center gap-2 font-bold text-sm transition-transform ${offsetX > 50 ? 'scale-110' : 'scale-95'}`}>
          <Bookmark className="w-5 h-5 fill-current" />
          <span>Keep</span>
        </div>
        <div className={`flex items-center gap-2 font-bold text-sm transition-transform ${offsetX < -50 ? 'scale-110' : 'scale-95'}`}>
          <span>Dismiss</span>
          <Trash2 className="w-5 h-5" />
        </div>
      </div>

      {/* Foreground Content Card */}
      <div
        {...handlers}
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isDragging ? 'none' : 'transform 250ms cubic-bezier(0.2, 0.8, 0.2, 1)',
        }}
        className="relative bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-2xl shadow-sm hover:shadow-md transition-shadow cursor-pointer select-none"
      >
        {/* Lead Image */}
        {(article.thumb_path || article.image_remote_url) && (
          <div className="relative aspect-[16/9] w-full overflow-hidden rounded-t-2xl bg-cream-200 dark:bg-ink-800">
            {article.thumb_path ? (
              <AuthImage
                path={`/images/${article.thumb_path}`}
                alt={article.title}
                className="w-full h-full"
                imgClassName="w-full h-full object-cover"
                eager
              />
            ) : (
              <img
                src={article.image_remote_url}
                alt={article.title}
                className="w-full h-full object-cover"
                loading="eager"
              />
            )}
            <div className="absolute top-3 left-3 bg-brand-700/90 backdrop-blur-sm text-white px-2.5 py-1 rounded-md text-[11px] font-bold tracking-wider uppercase">
              Top Story
            </div>
          </div>
        )}

        <div className="p-5">
          {/* Metadata Bar */}
          <div className="flex items-center gap-2 text-xs text-ink-500 dark:text-ink-400 mb-2.5">
            {article.source_favicon ? (
              <img src={article.source_favicon} alt="" className="w-4 h-4 rounded-sm" />
            ) : (
              <div className="w-4 h-4 rounded-sm bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center font-bold text-[9px]">
                {article.source_name?.[0] || 'N'}
              </div>
            )}
            <span className="font-semibold text-ink-800 dark:text-ink-200">{article.source_name}</span>
            <span>•</span>
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{formatRelativeTime(article.published_at || article.discovered_at)}</span>
            </div>
          </div>

          {/* Headline */}
          <h2 className="font-serif font-bold text-xl sm:text-2xl text-ink-900 dark:text-cream-100 leading-snug mb-2">
            {article.title}
          </h2>

          {/* Summary snippet */}
          {article.summary && (
            <p className="text-sm text-ink-600 dark:text-ink-300 line-clamp-3 leading-relaxed mb-3">
              {article.summary}
            </p>
          )}

          {/* Story Clustering Indicators */}
          {article.also_in && article.also_in.length > 0 && (
            <div className="pt-3 border-t border-cream-100 dark:border-ink-800 flex items-center gap-1.5 text-xs text-ink-500 dark:text-ink-400">
              <Layers className="w-3.5 h-3.5 text-brand-600 dark:text-volt-400" />
              <span>Also in:</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {article.also_in.map((s) => (
                  <span
                    key={s.article_id}
                    className="bg-cream-100 dark:bg-ink-800 px-2 py-0.5 rounded text-[11px] font-medium text-ink-700 dark:text-ink-300"
                  >
                    {s.source_name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
