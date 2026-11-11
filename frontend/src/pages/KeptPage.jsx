import React, { useState, useEffect, useCallback } from 'react';
import { Bookmark, CheckCircle2, Circle, Trash2, Clock, RefreshCw, ExternalLink } from 'lucide-react';
import { getKept, updateKeptState } from '../api';
import { navigate, onLinkClick } from '../lib/router';
import AuthImage from '../components/AuthImage';

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

export default function KeptPage() {
  const [tab, setTab] = useState('all'); // 'all' | 'unread' | 'read'
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadKept = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getKept(tab);
      setItems(data);
    } catch (err) {
      console.error('Failed to load kept articles:', err);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    loadKept();
  }, [loadKept]);

  const handleToggleState = async (e, articleId, currentState) => {
    e.stopPropagation();
    const nextState = currentState === 'read' ? 'unread' : 'read';
    try {
      await updateKeptState(articleId, nextState);
      setItems((prev) =>
        prev.map((item) =>
          item.article.id === articleId ? { ...item, kept_state: nextState } : item
        )
      );
    } catch (err) {
      console.error('Failed to update kept state:', err);
    }
  };

  const handleRemove = async (e, articleId) => {
    e.stopPropagation();
    try {
      await updateKeptState(articleId, 'removed');
      setItems((prev) => prev.filter((item) => item.article.id !== articleId));
    } catch (err) {
      console.error('Failed to remove from kept:', err);
    }
  };

  const handleOpenReader = (articleId) => {
    navigate(`/reader/${articleId}`);
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Header & Filter Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-serif font-black text-3xl sm:text-4xl text-ink-950 dark:text-cream-50 tracking-tight">
            Kept Articles
          </h1>
          <p className="text-xs text-ink-500 dark:text-ink-400 mt-1">
            Stories you swiped right to save for reading.
          </p>
        </div>

        <div className="flex gap-1 self-start sm:self-auto bg-cream-200 dark:bg-ink-800 p-1 rounded-full border border-cream-300 dark:border-ink-700">
          {['all', 'unread', 'read'].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3.5 py-1 text-xs font-semibold rounded-full capitalize transition-all ${
                tab === t
                  ? 'bg-white dark:bg-ink-900 text-ink-900 dark:text-cream-50 shadow-xs'
                  : 'text-ink-600 dark:text-ink-400 hover:text-ink-900'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Content List */}
      {loading ? (
        <div className="py-20 text-center space-y-3">
          <RefreshCw className="w-6 h-6 animate-spin text-brand-600 dark:text-volt-400 mx-auto" />
          <p className="text-xs text-ink-500 dark:text-ink-400 font-medium">Loading saved articles...</p>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-3xl p-8 sm:p-12 text-center max-w-md mx-auto my-12 shadow-xs space-y-4">
          <div className="w-16 h-16 rounded-3xl bg-volt-500/10 text-volt-600 dark:text-volt-400 mx-auto flex items-center justify-center">
            <Bookmark className="w-8 h-8" />
          </div>
          <div className="space-y-1.5">
            <h2 className="font-serif font-bold text-2xl text-ink-900 dark:text-cream-100">
              No saved stories
            </h2>
            <p className="text-xs sm:text-sm text-ink-600 dark:text-ink-400 leading-relaxed">
              {tab === 'read'
                ? 'You have not marked any articles as read yet.'
                : 'Swipe right on any article in your news feed to save it here for later reading.'}
            </p>
          </div>
          <div>
            <a href="/" onClick={onLinkClick('/')} className="btn-primary inline-flex gap-2">
              Browse Today’s Edition
            </a>
          </div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {items.map(({ article, kept_state }) => (
            <div
              key={article.id}
              onClick={() => handleOpenReader(article.id)}
              className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 hover:border-brand-500/40 rounded-2xl p-4 shadow-xs transition-all cursor-pointer flex items-start gap-4 group"
            >
              {/* Checkbox button */}
              <button
                onClick={(e) => handleToggleState(e, article.id, kept_state)}
                className="mt-1 text-ink-400 hover:text-emerald-600 transition-colors shrink-0"
                title={kept_state === 'read' ? 'Mark as unread' : 'Mark as read'}
              >
                {kept_state === 'read' ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                ) : (
                  <Circle className="w-5 h-5" />
                )}
              </button>

              {/* Main content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-ink-500 dark:text-ink-400 mb-1">
                  <span className="font-bold text-ink-800 dark:text-ink-200 truncate max-w-[140px]">
                    {article.source_name}
                  </span>
                  <span>•</span>
                  <span>{formatRelativeTime(article.published_at || article.discovered_at)}</span>
                  {kept_state === 'read' && (
                    <span className="bg-cream-200 dark:bg-ink-800 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded text-ink-600 dark:text-ink-300">
                      Read
                    </span>
                  )}
                </div>

                <h3 className={`font-semibold text-base leading-snug mb-1 text-ink-950 dark:text-cream-100 ${
                  kept_state === 'read' ? 'opacity-70' : ''
                }`}>
                  {article.title}
                </h3>

                {article.summary && (
                  <p className="text-xs text-ink-600 dark:text-ink-400 line-clamp-1 leading-normal mb-2">
                    {article.summary}
                  </p>
                )}

                <div className="flex items-center gap-3 text-xs text-ink-400 pt-1">
                  {article.word_count > 0 && (
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      <span>{Math.max(1, Math.round(article.word_count / 220))} min read</span>
                    </div>
                  )}
                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1 text-ink-500 hover:text-brand-700 dark:hover:text-volt-400 transition-colors"
                    >
                      <span>Original</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>

              {/* Right Thumbnail & Actions */}
              <div className="flex flex-col items-end gap-2 shrink-0">
                {(article.thumb_path || article.image_remote_url) && (
                  <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-xl overflow-hidden bg-cream-100 dark:bg-ink-800">
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
                <button
                  onClick={(e) => handleRemove(e, article.id)}
                  className="p-1.5 text-ink-400 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100"
                  title="Remove from kept"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
