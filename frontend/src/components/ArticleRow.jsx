import React from 'react';
import { Bookmark, Trash2, Layers, Clock, ExternalLink } from 'lucide-react';
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

export default function ArticleRow({
  article,
  onSwipe,
  onOpenReader,
  onOpenOriginal,
  previewLines = 2,
  isOpened = false,
}) {
  const opened = isOpened || Boolean(article.is_opened);

  const { rowRef, offsetX, isDragging, isCollapsing, swipeAction, handlers } = useSwipeRow({
    onSwipeRight: () => onSwipe(article.id, 'keep'),
    onSwipeLeft: () => onSwipe(article.id, 'skip'),
    onTap: () => onOpenReader(article.id),
  });

  const bgStyle = swipeAction === 'keep'
    ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white'
    : swipeAction === 'skip'
    ? 'bg-gradient-to-l from-rose-600 to-red-600 text-white'
    : 'bg-cream-200 dark:bg-ink-800 text-ink-500';

  const hasImage = Boolean(article.thumb_path || article.image_remote_url);

  return (
    <div
      ref={rowRef}
      className={`relative overflow-hidden transition-all duration-300 ${
        isCollapsing ? 'max-h-0 opacity-0 mb-0 py-0' : 'max-h-[220px] opacity-100 mb-2.5'
      }`}
    >
      {/* Background Reveal under swipe */}
      <div className={`absolute inset-0 flex items-center justify-between px-6 rounded-2xl transition-all duration-200 ${bgStyle}`}>
        <div className={`flex items-center gap-2 font-bold text-xs uppercase tracking-wider transition-transform ${offsetX > 40 ? 'scale-110 opacity-100' : 'scale-90 opacity-60'}`}>
          <Bookmark className="w-4 h-4 fill-current" />
          <span>Keep Story</span>
        </div>
        <div className={`flex items-center gap-2 font-bold text-xs uppercase tracking-wider transition-transform ${offsetX < -40 ? 'scale-110 opacity-100' : 'scale-90 opacity-60'}`}>
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
        className={`group relative bg-white dark:bg-ink-900 border border-cream-200/90 dark:border-ink-800/90 rounded-2xl p-3.5 sm:p-4 shadow-[0_1px_3px_rgba(0,0,0,0.03)] hover:shadow-md hover:border-brand-500/30 dark:hover:border-volt-500/30 transition-all cursor-pointer select-none ${
          opened ? 'opacity-65 dark:opacity-55' : 'opacity-100'
        }`}
      >
        <div className="flex items-center gap-3.5 sm:gap-4">
          <div className="flex-1 min-w-0">
            {/* Source, Timestamp, Read Badge & Original Link */}
            <div className="flex items-center justify-between text-xs text-ink-500 dark:text-ink-400 mb-1.5">
              <div className="flex items-center gap-1.5 min-w-0 pr-2">
                {article.source_favicon ? (
                  <img src={article.source_favicon} alt="" className="w-3.5 h-3.5 rounded-xs shrink-0" />
                ) : (
                  <div className="w-3.5 h-3.5 rounded-xs bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center font-bold text-[8px] shrink-0">
                    {article.source_name?.[0] || 'N'}
                  </div>
                )}
                <span className="font-semibold text-ink-800 dark:text-ink-200 truncate max-w-[120px]">
                  {article.source_name}
                </span>
                <span>•</span>
                <div className="flex items-center gap-1 shrink-0">
                  <Clock className="w-3 h-3 text-ink-400" />
                  <span>{formatRelativeTime(article.published_at || article.discovered_at)}</span>
                </div>
                {opened && (
                  <span className="ml-1 text-[10px] uppercase font-bold tracking-wider text-ink-400 dark:text-ink-500 bg-cream-200/70 dark:bg-ink-800 px-1.5 py-0.2 rounded">
                    Read
                  </span>
                )}
              </div>

              {article.url && (
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenOriginal?.(article);
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium text-ink-500 dark:text-ink-400 hover:text-brand-700 dark:hover:text-volt-400 hover:bg-cream-100 dark:hover:bg-ink-800 transition-colors shrink-0"
                  title="Open original article on publisher website"
                  aria-label="Open original article"
                >
                  <span className="hidden sm:inline">Original</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>

            {/* Headline */}
            <h3
              className={`font-serif text-[15px] sm:text-[17px] leading-snug line-clamp-2 transition-colors ${
                opened
                  ? 'font-medium text-ink-600 dark:text-ink-400'
                  : 'font-bold text-ink-950 dark:text-cream-50 group-hover:text-brand-700 dark:group-hover:text-volt-400'
              }`}
            >
              {article.title}
            </h3>

            {/* Snippet (Dynamic line clamp according to user preference) */}
            {article.summary && previewLines > 0 && (
              <p
                className="text-xs text-ink-600 dark:text-ink-400 leading-relaxed mt-1"
                style={{
                  display: '-webkit-box',
                  WebkitLineClamp: previewLines,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {article.summary}
              </p>
            )}

            {/* Also in indicator */}
            {article.also_in && article.also_in.length > 0 && (
              <div className="flex items-center gap-1 text-[10px] text-ink-500 dark:text-ink-400 mt-1.5">
                <Layers className="w-3 h-3 text-brand-600 dark:text-volt-400 shrink-0" />
                <span className="truncate">Also in {article.also_in.map((s) => s.source_name).join(', ')}</span>
              </div>
            )}
          </div>

          {/* Right Thumbnail */}
          {hasImage && (
            <div
              className={`w-20 h-20 min-w-[5rem] max-w-[5rem] sm:w-24 sm:h-24 sm:min-w-[6rem] sm:max-w-[6rem] shrink-0 overflow-hidden rounded-xl bg-cream-200 dark:bg-ink-800 shadow-xs border border-cream-200/50 dark:border-ink-700/50 ${
                opened ? 'grayscale-[35%] opacity-85' : ''
              }`}
            >
              {article.thumb_path ? (
                <AuthImage
                  path={`/images/${article.thumb_path}`}
                  alt=""
                  className="w-full h-full"
                  imgClassName="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                />
              ) : (
                <img
                  src={article.image_remote_url}
                  alt=""
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  loading="lazy"
                  onError={(e) => { e.currentTarget.parentElement.style.display = 'none'; }}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
