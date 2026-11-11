import React, { useState, useEffect } from 'react';
import { X, Globe, Rss, Code2, Loader2, Check, Sparkles } from 'lucide-react';
import { probeSource, createSource, updateSource } from '../api';

export default function SourceSheet({
  isOpen,
  onClose,
  onSaved,
  source = null,
  categories = [],
}) {
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [fetchMode, setFetchMode] = useState('rss');
  const [feedUrl, setFeedUrl] = useState('');
  const [listingUrl, setListingUrl] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [textWhen, setTextWhen] = useState('open');
  const [textMethod, setTextMethod] = useState('auto');

  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (source) {
      setUrl(source.url || '');
      setName(source.name || '');
      setFetchMode(source.fetch_mode || 'rss');
      setFeedUrl(source.feed_url || '');
      setListingUrl(source.listing_url || '');
      setCategoryId(source.category_id ? String(source.category_id) : '');
      setTextWhen(source.text_when || 'open');
      setTextMethod(source.text_method || 'auto');
      setProbeResult(null);
    } else {
      setUrl('');
      setName('');
      setFetchMode('rss');
      setFeedUrl('');
      setListingUrl('');
      setCategoryId('');
      setTextWhen('open');
      setTextMethod('auto');
      setProbeResult(null);
    }
    setError(null);
  }, [source, isOpen]);

  if (!isOpen) return null;

  const handleProbe = async () => {
    if (!url.trim()) return;
    setProbing(true);
    setError(null);
    try {
      const res = await probeSource(url.trim());
      setProbeResult(res);
      if (res.name && !name) setName(res.name);
      if (res.mode) setFetchMode(res.mode);
      if (res.feed_url) setFeedUrl(res.feed_url);
      if (res.listing_url) setListingUrl(res.listing_url);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to probe source URL.');
    } finally {
      setProbing(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!url.trim() || !name.trim()) return;
    setSaving(true);
    setError(null);

    const payload = {
      url: url.trim(),
      name: name.trim(),
      fetch_mode: fetchMode,
      feed_url: feedUrl.trim() || null,
      listing_url: listingUrl.trim() || null,
      category_id: categoryId ? parseInt(categoryId, 10) : null,
      text_when: textWhen,
      text_method: textMethod,
    };

    try {
      if (source?.id) {
        await updateSource(source.id, payload);
      } else {
        await createSource(payload);
      }
      if (onSaved) onSaved();
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save source.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
      <div className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-cream-200 dark:border-ink-800">
          <h2 className="font-serif font-bold text-lg text-ink-900 dark:text-cream-100">
            {source ? 'Edit News Source' : 'Add News Source'}
          </h2>
          <button
            onClick={onClose}
            className="text-ink-400 hover:text-ink-600 dark:hover:text-cream-200 p-1 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSave} className="p-5 space-y-4">
          {error && (
            <div className="p-3 text-xs bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 rounded-xl border border-red-200 dark:border-red-800/50">
              {error}
            </div>
          )}

          {/* URL with Probe */}
          <div>
            <label className="block text-xs font-semibold text-ink-700 dark:text-ink-300 mb-1">
              Website or RSS Feed URL
            </label>
            <div className="flex gap-2">
              <input
                type="url"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://news.ycombinator.com/rss"
                className="flex-1 bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-sm text-ink-900 dark:text-cream-100 focus:outline-hidden focus:ring-2 focus:ring-brand-500"
              />
              <button
                type="button"
                onClick={handleProbe}
                disabled={probing || !url}
                className="flex items-center gap-1.5 bg-cream-200 dark:bg-ink-800 hover:bg-cream-300 dark:hover:bg-ink-700 px-3.5 py-2 rounded-xl text-xs font-semibold text-ink-800 dark:text-ink-200 transition-colors"
              >
                {probing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 text-volt-500" />}
                <span>Probe</span>
              </button>
            </div>
          </div>

          {/* Probe Findings Banner */}
          {probeResult && (
            <div className="p-3.5 rounded-xl bg-cream-100 dark:bg-ink-800/80 border border-brand-500/20 text-xs space-y-1.5">
              <div className="flex items-center gap-1.5 text-brand-700 dark:text-volt-400 font-semibold">
                <Check className="w-4 h-4" />
                <span>Detected: {probeResult.mode?.toUpperCase()} Mode ({probeResult.found_count} articles found)</span>
              </div>
              {probeResult.sample_titles?.length > 0 && (
                <ul className="text-ink-600 dark:text-ink-400 space-y-0.5 pl-4 list-disc">
                  {probeResult.sample_titles.slice(0, 3).map((t, idx) => (
                    <li key={idx} className="truncate">{t}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-xs font-semibold text-ink-700 dark:text-ink-300 mb-1">
              Source Name
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Hacker News"
              className="w-full bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-sm text-ink-900 dark:text-cream-100 focus:outline-hidden focus:ring-2 focus:ring-brand-500"
            />
          </div>

          {/* Category Picker */}
          <div>
            <label className="block text-xs font-semibold text-ink-700 dark:text-ink-300 mb-1">
              Assigned Category
            </label>
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="w-full bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-sm text-ink-900 dark:text-cream-100 focus:outline-hidden focus:ring-2 focus:ring-brand-500"
            >
              <option value="">Auto-categorize via Keywords</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
          </div>

          {/* Fetch Mode Selection */}
          <div className="grid grid-cols-3 gap-2 pt-1">
            <button
              type="button"
              onClick={() => setFetchMode('rss')}
              className={`flex flex-col items-center justify-center p-3 rounded-xl border text-xs font-medium transition-all ${
                fetchMode === 'rss'
                  ? 'border-brand-600 bg-brand-50/60 dark:bg-brand-950/40 text-brand-700 dark:text-volt-400 font-semibold'
                  : 'border-cream-300 dark:border-ink-700 text-ink-600 dark:text-ink-400 hover:bg-cream-100 dark:hover:bg-ink-800'
              }`}
            >
              <Rss className="w-4 h-4 mb-1" />
              <span>RSS / Atom</span>
            </button>
            <button
              type="button"
              onClick={() => setFetchMode('html')}
              className={`flex flex-col items-center justify-center p-3 rounded-xl border text-xs font-medium transition-all ${
                fetchMode === 'html'
                  ? 'border-brand-600 bg-brand-50/60 dark:bg-brand-950/40 text-brand-700 dark:text-volt-400 font-semibold'
                  : 'border-cream-300 dark:border-ink-700 text-ink-600 dark:text-ink-400 hover:bg-cream-100 dark:hover:bg-ink-800'
              }`}
            >
              <Globe className="w-4 h-4 mb-1" />
              <span>HTML Crawl</span>
            </button>
            <button
              type="button"
              onClick={() => setFetchMode('browser')}
              className={`flex flex-col items-center justify-center p-3 rounded-xl border text-xs font-medium transition-all ${
                fetchMode === 'browser'
                  ? 'border-brand-600 bg-brand-50/60 dark:bg-brand-950/40 text-brand-700 dark:text-volt-400 font-semibold'
                  : 'border-cream-300 dark:border-ink-700 text-ink-600 dark:text-ink-400 hover:bg-cream-100 dark:hover:bg-ink-800'
              }`}
            >
              <Code2 className="w-4 h-4 mb-1" />
              <span>Browser (JS)</span>
            </button>
          </div>

          {/* Full-text fetch strategy */}
          <div className="pt-2">
            <label className="block text-xs font-semibold text-ink-700 dark:text-ink-300 mb-1">
              When to extract full article text:
            </label>
            <select
              value={textWhen}
              onChange={(e) => setTextWhen(e.target.value)}
              className="w-full bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-xs text-ink-900 dark:text-cream-100 focus:outline-hidden"
            >
              <option value="open">On demand (when opening article in reader)</option>
              <option value="keep">When article is swiped Keep</option>
              <option value="crawl">Immediately during crawl</option>
            </select>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-cream-200 dark:border-ink-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-ink-600 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ink-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 bg-brand-700 hover:bg-brand-800 dark:bg-brand-600 dark:hover:bg-brand-500 text-white px-5 py-2 rounded-xl text-xs font-semibold shadow-xs transition-colors"
            >
              {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{source ? 'Save Changes' : 'Add Source'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
