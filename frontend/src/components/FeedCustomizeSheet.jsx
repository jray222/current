import React, { useState, useEffect } from 'react';
import {
  X,
  ArrowUp,
  ArrowDown,
  Eye,
  EyeOff,
  Sliders,
  Check,
  Flame,
  Globe,
  Flag,
  Landmark,
  Briefcase,
  Cpu,
  FlaskConical,
  HeartPulse,
  Trophy,
  MapPin,
  Palette,
  Newspaper,
} from 'lucide-react';
import { updateFeedSettings } from '../api';

const ICON_MAP = {
  flame: Flame,
  globe: Globe,
  flag: Flag,
  landmark: Landmark,
  briefcase: Briefcase,
  cpu: Cpu,
  'flask-conical': FlaskConical,
  'heart-pulse': HeartPulse,
  trophy: Trophy,
  'map-pin': MapPin,
  palette: Palette,
  newspaper: Newspaper,
};

export default function FeedCustomizeSheet({
  isOpen,
  onClose,
  allCategories = [],
  currentSettings = { category_order: [], excluded_categories: [], preview_lines: 2 },
  onSettingsSaved,
}) {
  const [categoriesList, setCategoriesList] = useState([]);
  const [excludedKeys, setExcludedKeys] = useState(new Set());
  const [previewLines, setPreviewLines] = useState(2);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    const excluded = new Set(currentSettings.excluded_categories || []);
    setExcludedKeys(excluded);
    setPreviewLines(
      typeof currentSettings.preview_lines === 'number' ? currentSettings.preview_lines : 2
    );

    // Order categories by currentSettings.category_order if present
    const order = currentSettings.category_order || [];
    const orderMap = new Map(order.map((key, idx) => [key, idx]));

    const sorted = [...allCategories].sort((a, b) => {
      const idxA = orderMap.has(a.key) ? orderMap.get(a.key) : 999;
      const idxB = orderMap.has(b.key) ? orderMap.get(b.key) : 999;
      if (idxA !== idxB) return idxA - idxB;
      return (a.sort_order || 0) - (b.sort_order || 0);
    });

    setCategoriesList(sorted);
  }, [isOpen, allCategories, currentSettings]);

  if (!isOpen) return null;

  const moveCategory = (index, direction) => {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= categoriesList.length) return;
    const updated = [...categoriesList];
    const [moved] = updated.splice(index, 1);
    updated.splice(targetIndex, 0, moved);
    setCategoriesList(updated);
  };

  const toggleExclude = (key) => {
    setExcludedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    const categoryOrder = categoriesList.map((c) => c.key);
    const excludedList = Array.from(excludedKeys);

    try {
      const updated = await updateFeedSettings({
        category_order: categoryOrder,
        excluded_categories: excludedList,
        preview_lines: previewLines,
      });
      if (onSettingsSaved) {
        onSettingsSaved(updated);
      }
      onClose();
    } catch (err) {
      console.error('Failed to save feed preferences:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/60 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg max-h-[90vh] flex flex-col bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-3xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-cream-200 dark:border-ink-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-serif font-bold text-lg text-ink-950 dark:text-cream-50 leading-tight">
                Customize Feed
              </h2>
              <p className="text-xs text-ink-500 dark:text-ink-400">
                Order topics, hide categories, and control preview density
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full text-ink-400 hover:text-ink-700 dark:hover:text-cream-100 hover:bg-cream-100 dark:hover:bg-ink-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Card Preview Text Density */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-ink-700 dark:text-ink-300 mb-2">
              Article Preview Text
            </label>
            <div className="grid grid-cols-4 gap-2">
              {[
                { lines: 0, label: 'None', desc: 'Title only' },
                { lines: 1, label: '1 Line', desc: 'Compact' },
                { lines: 2, label: '2 Lines', desc: 'Standard' },
                { lines: 3, label: '3 Lines', desc: 'Expanded' },
              ].map((opt) => (
                <button
                  key={opt.lines}
                  type="button"
                  onClick={() => setPreviewLines(opt.lines)}
                  className={`p-2.5 rounded-xl border text-center transition-all ${
                    previewLines === opt.lines
                      ? 'border-brand-600 bg-brand-50/50 dark:bg-brand-950/30 text-brand-800 dark:text-volt-400 font-bold shadow-xs'
                      : 'border-cream-200 dark:border-ink-800 hover:border-cream-300 dark:hover:border-ink-700 text-ink-700 dark:text-ink-300'
                  }`}
                >
                  <div className="text-xs font-semibold">{opt.label}</div>
                  <div className="text-[10px] text-ink-500 dark:text-ink-400 mt-0.5">{opt.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Category Ordering & Exclusions */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-ink-700 dark:text-ink-300">
                Category Order & Visibility
              </label>
              <span className="text-[11px] text-ink-400 dark:text-ink-500 italic">
                Use arrows to prioritize
              </span>
            </div>

            <div className="space-y-1.5 border border-cream-200 dark:border-ink-800 rounded-2xl p-2 bg-cream-50/50 dark:bg-ink-950/40 divide-y divide-cream-100 dark:divide-ink-800/60">
              {categoriesList.map((cat, idx) => {
                const Icon = ICON_MAP[cat.icon] || Newspaper;
                const isExcluded = excludedKeys.has(cat.key);

                return (
                  <div
                    key={cat.id || cat.key}
                    className={`flex items-center justify-between py-2 px-2.5 rounded-xl transition-all ${
                      isExcluded
                        ? 'opacity-50 bg-cream-100/40 dark:bg-ink-900/40'
                        : 'bg-white dark:bg-ink-900'
                    }`}
                  >
                    {/* Reorder Buttons & Category Info */}
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="flex flex-col gap-0.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => moveCategory(idx, -1)}
                          disabled={idx === 0}
                          className="p-1 rounded text-ink-400 hover:text-ink-800 dark:hover:text-cream-100 hover:bg-cream-200 dark:hover:bg-ink-800 disabled:opacity-20 transition-colors"
                          title="Move up"
                        >
                          <ArrowUp className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => moveCategory(idx, 1)}
                          disabled={idx === categoriesList.length - 1}
                          className="p-1 rounded text-ink-400 hover:text-ink-800 dark:hover:text-cream-100 hover:bg-cream-200 dark:hover:bg-ink-800 disabled:opacity-20 transition-colors"
                          title="Move down"
                        >
                          <ArrowDown className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="w-7 h-7 rounded-lg bg-cream-100 dark:bg-ink-800 flex items-center justify-center text-ink-700 dark:text-ink-300 shrink-0">
                        <Icon className="w-3.5 h-3.5" />
                      </div>

                      <div className="min-w-0">
                        <div className="font-semibold text-xs sm:text-sm text-ink-900 dark:text-cream-100 truncate">
                          {cat.label}
                        </div>
                        {isExcluded && (
                          <div className="text-[10px] text-rose-500 font-medium">
                            Hidden from feed
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Exclude / Include Visibility Toggle */}
                    <button
                      type="button"
                      onClick={() => toggleExclude(cat.key)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold transition-all ${
                        isExcluded
                          ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300'
                          : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300'
                      }`}
                      title={isExcluded ? 'Include on main screen' : 'Exclude from main screen'}
                    >
                      {isExcluded ? (
                        <>
                          <EyeOff className="w-3.5 h-3.5" />
                          <span>Hidden</span>
                        </>
                      ) : (
                        <>
                          <Eye className="w-3.5 h-3.5" />
                          <span>Visible</span>
                        </>
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-cream-200 dark:border-ink-800 bg-cream-50/50 dark:bg-ink-950/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-ink-700 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-ink-800 rounded-xl transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2 bg-brand-700 hover:bg-brand-800 text-white dark:bg-volt-500 dark:hover:bg-volt-400 dark:text-ink-950 text-xs font-bold rounded-xl shadow-xs transition-all active:scale-95 disabled:opacity-50"
          >
            <Check className="w-4 h-4" />
            <span>{saving ? 'Saving...' : 'Apply Changes'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
