import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Rss, RefreshCw, Globe, Code2, AlertTriangle, Trash2, Edit3, ExternalLink } from 'lucide-react';
import { getSources, getCategories, crawlSource, crawlAll, deleteSource } from '../api';
import SourceSheet from '../components/SourceSheet';

function formatRelativeTime(dateStr) {
  if (!dateStr) return 'Never';
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffHours = Math.round((now - date) / (1000 * 60 * 60));
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.round(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return dateStr;
  }
}

export default function SourcesPage() {
  const [sources, setSources] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [crawlingAll, setCrawlingAll] = useState(false);
  const [crawlingSourceId, setCrawlingSourceId] = useState(null);

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingSource, setEditingSource] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [srcs, cats] = await Promise.all([getSources(), getCategories()]);
      setSources(srcs);
      setCategories(cats);
    } catch (err) {
      console.error('Failed to load sources:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCrawlAll = async () => {
    setCrawlingAll(true);
    try {
      await crawlAll();
      setTimeout(async () => {
        await loadData();
        setCrawlingAll(false);
      }, 1500);
    } catch {
      setCrawlingAll(false);
    }
  };

  const handleCrawlSource = async (id) => {
    setCrawlingSourceId(id);
    try {
      await crawlSource(id, true);
      setTimeout(async () => {
        await loadData();
        setCrawlingSourceId(null);
      }, 1500);
    } catch {
      setCrawlingSourceId(null);
    }
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete source "${name}" and remove its crawled articles?`)) return;
    try {
      await deleteSource(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      console.error('Failed to delete source:', err);
    }
  };

  const handleEdit = (source) => {
    setEditingSource(source);
    setSheetOpen(true);
  };

  const handleAdd = () => {
    setEditingSource(null);
    setSheetOpen(true);
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-serif font-black text-3xl sm:text-4xl text-ink-950 dark:text-cream-50 tracking-tight">
            News Sources
          </h1>
          <p className="text-xs text-ink-500 dark:text-ink-400 mt-1">
            Feeds and publications Current monitors for your household.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            type="button"
            onClick={handleCrawlAll}
            disabled={crawlingAll}
            className="flex items-center gap-2 bg-white dark:bg-ink-900 border border-cream-300 dark:border-ink-700 hover:bg-cream-100 dark:hover:bg-ink-800 text-xs font-semibold px-4 py-2.5 rounded-xl text-ink-800 dark:text-cream-100 shadow-xs transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-volt-500 ${crawlingAll ? 'animate-spin' : ''}`} />
            <span>{crawlingAll ? 'Updating all…' : 'Crawl All'}</span>
          </button>

          <button
            type="button"
            onClick={handleAdd}
            className="flex items-center gap-2 bg-brand-700 hover:bg-brand-800 dark:bg-brand-600 dark:hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-xs transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Add Source</span>
          </button>
        </div>
      </div>

      {/* Sources List */}
      {loading ? (
        <div className="py-20 text-center space-y-3">
          <RefreshCw className="w-6 h-6 animate-spin text-brand-600 dark:text-volt-400 mx-auto" />
          <p className="text-xs text-ink-500 dark:text-ink-400 font-medium">Loading sources...</p>
        </div>
      ) : sources.length === 0 ? (
        <div className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-3xl p-8 sm:p-12 text-center max-w-md mx-auto my-12 shadow-xs space-y-4">
          <div className="w-16 h-16 rounded-3xl bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-volt-400 mx-auto flex items-center justify-center">
            <Rss className="w-8 h-8" />
          </div>
          <div className="space-y-1.5">
            <h2 className="font-serif font-bold text-2xl text-ink-900 dark:text-cream-100">
              No sources configured
            </h2>
            <p className="text-xs sm:text-sm text-ink-600 dark:text-ink-400 leading-relaxed">
              Add URLs of websites, RSS feeds, or news publications. Current automatically detects feeds, respects robots.txt, and schedules periodic crawls.
            </p>
          </div>
          <div>
            <button onClick={handleAdd} className="btn-primary inline-flex gap-2">
              <Plus className="w-4 h-4" /> Add your first source
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sources.map((src) => {
            const cat = categories.find((c) => c.id === src.category_id);
            const isCrawling = crawlingSourceId === src.id || src.crawl_status === 'running';

            return (
              <div
                key={src.id}
                className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-2xl p-4 shadow-xs flex flex-col justify-between space-y-3"
              >
                <div>
                  {/* Top Bar: Icon, Name, Category */}
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      {src.favicon_url ? (
                        <img src={src.favicon_url} alt="" className="w-4 h-4 rounded-xs shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-xs bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center font-bold text-[8px] shrink-0">
                          {src.name[0]}
                        </div>
                      )}
                      <h3 className="font-bold text-sm text-ink-950 dark:text-cream-100 truncate">
                        {src.name}
                      </h3>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ink-800 text-ink-600 dark:text-ink-300">
                        {cat ? cat.label : 'Keyword Auto'}
                      </span>
                    </div>
                  </div>

                  {/* URL */}
                  <div className="flex items-center gap-1 text-xs text-ink-500 dark:text-ink-400">
                    <span className="truncate max-w-[280px]">{src.url}</span>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-brand-700 dark:hover:text-volt-400 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>

                  {/* Status & Error info */}
                  <div className="flex items-center gap-3 text-xs text-ink-500 dark:text-ink-400 mt-3 pt-3 border-t border-cream-100 dark:border-ink-800">
                    <div className="flex items-center gap-1">
                      {src.fetch_mode === 'rss' && <Rss className="w-3.5 h-3.5 text-brand-600 dark:text-volt-400" />}
                      {src.fetch_mode === 'html' && <Globe className="w-3.5 h-3.5 text-brand-600 dark:text-volt-400" />}
                      {src.fetch_mode === 'browser' && <Code2 className="w-3.5 h-3.5 text-brand-600 dark:text-volt-400" />}
                      <span className="capitalize">{src.fetch_mode}</span>
                    </div>

                    <span>•</span>
                    <span>{src.article_count} articles</span>
                    <span>•</span>
                    <span>Last: {formatRelativeTime(src.last_crawl_at)}</span>
                  </div>

                  {src.last_error && (
                    <div className="flex items-start gap-1.5 mt-2 p-2 rounded-lg bg-red-50 dark:bg-red-950/40 text-[11px] text-red-700 dark:text-red-300">
                      <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                      <span className="truncate">{src.last_error}</span>
                    </div>
                  )}
                </div>

                {/* Bottom Actions */}
                <div className="flex items-center justify-between pt-2 border-t border-cream-100 dark:border-ink-800">
                  <button
                    onClick={() => handleCrawlSource(src.id)}
                    disabled={isCrawling}
                    className="flex items-center gap-1 text-xs font-semibold text-brand-700 dark:text-volt-400 hover:underline"
                  >
                    <RefreshCw className={`w-3 h-3 ${isCrawling ? 'animate-spin' : ''}`} />
                    <span>{isCrawling ? 'Crawling…' : 'Crawl now'}</span>
                  </button>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleEdit(src)}
                      className="p-1.5 text-ink-500 hover:text-ink-900 dark:hover:text-cream-100 rounded-lg transition-colors"
                      title="Edit source"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleDelete(src.id, src.name)}
                      className="p-1.5 text-ink-400 hover:text-red-600 rounded-lg transition-colors"
                      title="Delete source"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add / Edit Source Sheet Modal */}
      <SourceSheet
        isOpen={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onSaved={loadData}
        source={editingSource}
        categories={categories}
      />
    </div>
  );
}
