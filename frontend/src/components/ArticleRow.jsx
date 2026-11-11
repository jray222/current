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

export default function ArticleRow({ article, onSwipe, onOpenReader }) {
  const { rowRef, offsetX, isDragging, isCollapsing, swipeAction, handlers } = useSwipeRow({
    onSwipeRight: () => onSwipe(article.id, 'keep'),
    onSwipeLeft: () => onSwipe(article.id, 'skip'),
    onTap: () => onOpenReader(article.id),
  });

  const bgStyle = swipeAction === 'keep'
    ? 'bg-emerald-600 text-white'
    : swipeAction === 'skip'
    ? 'bg-slate-700 text-white'
    : 'bg-cream-200 dark:bg-ink-800 text-ink-500';

  const hasImage = Boolean(article.thumb_path || article.image_remote_url);

  return (
    <div
      ref={rowRef}
      className={`relative overflow-hidden transition-all duration-300 ${
        isCollapsing ? 'max-h-0 opacity-0 mb-0 py-0' : 'max-h-[300px] opacity-100 mb-2'
      }`}
    >
      {/* Background Reveal under swipe */}
      <div className={`absolute inset-0 flex items-center justify-between px-5 rounded-xl transition-colors ${bgStyle}`}>
        <div className={`flex items-center gap-1.5 font-bold text-xs uppercase tracking-wider transition-transform ${offsetX > 40 ? 'scale-110' : 'scale-90'}`}>
          <Bookmark className="w-4 h-4 fill-current" />
          <span>Keep</span>
        </div>
        <div className={`flex items-center gap-1.5 font-bold text-xs uppercase tracking-wider transition-transform ${offsetX < -40 ? 'scale-110' : 'scale-90'}`}>
          <span>Dismiss</span>
          <Trash2 className="w-4 h-4" />
        </div>
      </div>

      {/* Foreground Article Item */}
      <div
        {...handlers}
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isDragging ? 'none' : 'transform 250ms cubic-bezier(0.2, 0.8, 0.2, 1)',
        }}
        className="relative bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-xl p-3.5 shadow-xs hover:border-brand-500/40 dark:hover:border-volt-500/40 transition-colors cursor-pointer select-none"
      >
        <div className="flex items-start gap-3.5">
          <div className="flex-1 min-w-0">
            {/* Source & Timestamp */}
            <div className="flex items-center gap-1.5 text-[11px] text-ink-500 dark:text-ink-400 mb-1">
              {article.source_favicon ? (
                <img src={article.source_favicon} alt="" className="w-3.5 h-3.5 rounded-xs" />
              ) : (
                <div className="w-3.5 h-3.5 rounded-xs bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center font-bold text-[8px]">
                  {article.source_name?.[0] || 'N'}
                </div>
              )}
              <span className="font-semibold text-ink-700 dark:text-ink-300 truncate max-w-[120px]">
                {article.source_name}
              </span>
              <span>•</span>
              <div className="flex items-center gap-0.5">
                <Clock className="w-2.5 h-2.5" />
                <span>{formatRelativeTime(article.published_at || article.discovered_at)}</span>
              </div>
            </div>

            {/* Headline */}
            <h3 className="font-semibold text-sm sm:text-base text-ink-900 dark:text-cream-100 line-clamp-2 leading-snug mb-1">
              {article.title}
            </h3>

            {/* Snippet */}
            {article.summary && (
              <p className="text-xs text-ink-600 dark:text-ink-400 line-clamp-1 leading-normal mb-1.5">
                {article.summary}
              </p>
            )}

            {/* Also in indicator */}
            {article.also_in && article.also_in.length > 0 && (
              <div className="flex items-center gap-1 text-[10px] text-ink-500 dark:text-ink-400 mt-1">
                <Layers className="w-3 h-3 text-brand-600 dark:text-volt-400" />
                <span>Also in {article.also_in.map((s) => s.source_name).join(', ')}</span>
              </div>
            )}
          </div>

          {/* Right Thumbnail */}
          {hasImage && (
            <div className="w-18 h-18 sm:w-20 sm:h-20 shrink-0 overflow-hidden rounded-lg bg-cream-100 dark:bg-ink-800">
              {article.thumb_path ? (
                <AuthImage
                  path={`/images/${article.thumb_path}`}
                  alt=""
                  className="w-full h-full"
                  imgClassName="w-full h-full object-cover"
                />
              ) : (
                <img
                  src={article.image_remote_url}
                  alt=""
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
