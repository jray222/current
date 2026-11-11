import React, { useState, useEffect } from 'react';
import { Sliders, Clock, Sparkles, Check, Loader2 } from 'lucide-react';
import { getCrawlSettings, updateCrawlSettings } from '../../api';

export default function CrawlSection() {
  const [enabled, setEnabled] = useState(true);
  const [crawlTime, setCrawlTime] = useState('06:00');
  const [everyHours, setEveryHours] = useState(24);
  const [everyHoursChoices, setEveryHoursChoices] = useState([1, 2, 4, 6, 8, 12, 24]);
  const [times, setTimes] = useState(['06:00']);
  const [aiCategorize, setAiCategorize] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCrawlSettings()
      .then((data) => {
        setEnabled(data.crawl_enabled);
        setCrawlTime(data.crawl_time || '06:00');
        setEveryHours(data.crawl_every_hours || 24);
        if (data.crawl_every_hours_choices) setEveryHoursChoices(data.crawl_every_hours_choices);
        if (data.times) setTimes(data.times);
        setAiCategorize(data.ai_categorize);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load crawl settings.'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const data = await updateCrawlSettings({
        crawl_enabled: enabled,
        crawl_time: crawlTime,
        crawl_every_hours: everyHours,
        ai_categorize: aiCategorize,
      });
      if (data.times) setTimes(data.times);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to update crawl settings.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-xs text-ink-500">
        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-brand-600" />
        Loading schedule...
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-2xl p-6 shadow-xs space-y-5">
      <div>
        <h2 className="font-serif font-bold text-lg text-ink-900 dark:text-cream-100 flex items-center gap-2">
          <Sliders className="w-5 h-5 text-brand-700 dark:text-volt-400" />
          <span>Crawl Schedule & Automation</span>
        </h2>
        <p className="text-xs text-ink-500 dark:text-ink-400 mt-1">
          Configure when Current automatically checks your news feeds and syncs updates.
        </p>
      </div>

      {error && (
        <div className="p-3 text-xs bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 rounded-xl border border-red-200 dark:border-red-800/50">
          {error}
        </div>
      )}

      {/* Enable Toggle */}
      <div className="flex items-center justify-between p-3.5 rounded-xl bg-cream-100 dark:bg-ink-800/60">
        <div>
          <span className="block font-semibold text-xs text-ink-900 dark:text-cream-100">
            Automatic background crawling
          </span>
          <span className="block text-[11px] text-ink-500 dark:text-ink-400">
            Current checks for new stories on your configured schedule.
          </span>
        </div>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500"
        />
      </div>

      {/* Crawl Time */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-semibold text-ink-700 dark:text-ink-300 mb-1">
            Start time of day
          </label>
          <input
            type="time"
            value={crawlTime}
            onChange={(e) => setCrawlTime(e.target.value)}
            disabled={!enabled}
            className="w-full bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-sm text-ink-900 dark:text-cream-100 focus:outline-hidden"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink-700 dark:text-ink-300 mb-1">
            Repeat interval
          </label>
          <select
            value={everyHours}
            onChange={(e) => setEveryHours(parseInt(e.target.value, 10))}
            disabled={!enabled}
            className="w-full bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-sm text-ink-900 dark:text-cream-100 focus:outline-hidden"
          >
            {everyHoursChoices.map((h) => (
              <option key={h} value={h}>
                {h === 24 ? 'Once daily (24 hours)' : `Every ${h} hours`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Computed run times pills */}
      {enabled && times.length > 0 && (
        <div className="p-3.5 rounded-xl bg-cream-50 dark:bg-ink-800/40 border border-cream-200 dark:border-ink-700/60">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-ink-700 dark:text-ink-300 mb-2">
            <Clock className="w-3.5 h-3.5 text-brand-600 dark:text-volt-400" />
            <span>Scheduled Daily Crawl Times ({times.length} runs per day):</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {times.map((t, idx) => (
              <span
                key={idx}
                className="bg-cream-200 dark:bg-ink-700 px-2.5 py-1 rounded-lg text-xs font-mono font-medium text-ink-800 dark:text-cream-100"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* AI categorization toggle */}
      <div className="flex items-center justify-between p-3.5 rounded-xl bg-cream-100 dark:bg-ink-800/60">
        <div>
          <span className="block font-semibold text-xs text-ink-900 dark:text-cream-100 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-volt-500" />
            <span>AI-assisted categorization</span>
          </span>
          <span className="block text-[11px] text-ink-500 dark:text-ink-400">
            Use Claude to automatically categorize stories that lack keyword tags.
          </span>
        </div>
        <input
          type="checkbox"
          checked={aiCategorize}
          onChange={(e) => setAiCategorize(e.target.checked)}
          className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500"
        />
      </div>

      {/* Submit Button */}
      <div className="flex items-center justify-end gap-3 pt-3">
        {saved && (
          <span className="flex items-center gap-1 text-xs text-emerald-600 font-semibold animate-fade-in">
            <Check className="w-4 h-4" /> Schedule saved!
          </span>
        )}
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-1.5 bg-brand-700 hover:bg-brand-800 dark:bg-brand-600 dark:hover:bg-brand-500 text-white px-5 py-2 rounded-xl text-xs font-semibold shadow-xs transition-colors"
        >
          {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          <span>Save Changes</span>
        </button>
      </div>
    </form>
  );
}
