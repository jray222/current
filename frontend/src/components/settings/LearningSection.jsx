import React, { useState, useEffect } from 'react';
import { Sparkles, VolumeX, RotateCcw, Plus, X, Loader2, ThumbsUp, ThumbsDown } from 'lucide-react';
import { getLearningSettings, muteLearningTerm, unmuteLearningTerm, resetLearningModel } from '../../api';

export default function LearningSection() {
  const [learning, setLearning] = useState(null);
  const [newMute, setNewMute] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const loadData = () => {
    setLoading(true);
    getLearningSettings()
      .then(setLearning)
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load interest settings.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAddMute = async (e) => {
    e.preventDefault();
    if (!newMute.trim()) return;
    setSubmitting(true);
    try {
      const data = await muteLearningTerm(newMute.trim());
      setLearning(data);
      setNewMute('');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to mute term.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnmute = async (term) => {
    try {
      const data = await unmuteLearningTerm(term);
      setLearning(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to unmute term.');
    }
  };

  const handleReset = async () => {
    if (!window.confirm('Reset your learned interest model? Current will forget your past swipe preferences and begin learning again from scratch.')) return;
    try {
      const data = await resetLearningModel();
      setLearning(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to reset model.');
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-xs text-ink-500">
        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-brand-600" />
        Loading learning model...
      </div>
    );
  }

  const positiveInterests = learning?.top_interests?.filter(([_, w]) => w > 0) || [];
  const negativeInterests = learning?.top_interests?.filter(([_, w]) => w < 0) || [];

  return (
    <div className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-2xl p-6 shadow-xs space-y-6">
      <div>
        <h2 className="font-serif font-bold text-lg text-ink-900 dark:text-cream-100 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-volt-500" />
          <span>Interest Learning & Adaptive Ranking</span>
        </h2>
        <p className="text-xs text-ink-500 dark:text-ink-400 mt-1">
          Current runs an on-device machine learning model that learns from stories you keep and read. Long-press any story and choose “Do not show articles like this” to tune down unwanted topics.
        </p>
      </div>

      {error && (
        <div className="p-3 text-xs bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 rounded-xl border border-red-200 dark:border-red-800/50">
          {error}
        </div>
      )}

      {/* Model Stats */}
      <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-cream-50 dark:bg-ink-800/60 border border-cream-200 dark:border-ink-700/60">
        <div>
          <span className="block text-[11px] font-semibold text-ink-500 dark:text-ink-400">Signals Learned</span>
          <span className="text-xl font-bold font-mono text-ink-900 dark:text-cream-100">{learning?.n_votes || 0}</span>
        </div>
        <div>
          <span className="block text-[11px] font-semibold text-ink-500 dark:text-ink-400">Algorithm</span>
          <span className="text-sm font-semibold text-ink-800 dark:text-cream-200">AdaGrad Logistic</span>
        </div>
      </div>

      {/* Learned Preferences */}
      <div className="space-y-4">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5 mb-2">
            <ThumbsUp className="w-3.5 h-3.5" />
            <span>Learned Positive Topics & Sources</span>
          </h3>
          {positiveInterests.length === 0 ? (
            <p className="text-xs text-ink-500 italic">No positive patterns learned yet. Swipe right on stories to train.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {positiveInterests.map(([k, w]) => (
                <span
                  key={k}
                  className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/40 text-emerald-800 dark:text-emerald-200 px-2.5 py-1 rounded-lg text-xs font-mono font-medium"
                >
                  {k} <span className="opacity-70">+{w}</span>
                </span>
              ))}
            </div>
          )}
        </div>

        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-ink-600 dark:text-ink-400 flex items-center gap-1.5 mb-2">
            <ThumbsDown className="w-3.5 h-3.5" />
            <span>Less Frequent Topics & Sources</span>
          </h3>
          {negativeInterests.length === 0 ? (
            <p className="text-xs text-ink-500 italic">No negative patterns learned yet. Long-press a story and choose “Do not show articles like this” to tune down topics you dislike.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {negativeInterests.map(([k, w]) => (
                <span
                  key={k}
                  className="bg-cream-100 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 text-ink-700 dark:text-ink-300 px-2.5 py-1 rounded-lg text-xs font-mono font-medium"
                >
                  {k} <span className="opacity-70">{w}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Muted Terms Section */}
      <div className="pt-4 border-t border-cream-200 dark:border-ink-800 space-y-3">
        <div>
          <h3 className="font-serif font-bold text-sm text-ink-900 dark:text-cream-100 flex items-center gap-1.5">
            <VolumeX className="w-4 h-4 text-brand-600 dark:text-volt-400" />
            <span>Muted Topics & Outlets</span>
          </h3>
          <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">
            Stories containing muted words will never appear in your feeds.
          </p>
        </div>

        <form onSubmit={handleAddMute} className="flex gap-2">
          <input
            type="text"
            value={newMute}
            onChange={(e) => setNewMute(e.target.value)}
            placeholder="Add keyword to mute (e.g. celebrity, crypto)"
            className="flex-1 bg-cream-50 dark:bg-ink-800 border border-cream-300 dark:border-ink-700 rounded-xl px-3.5 py-2 text-xs text-ink-900 dark:text-cream-100 focus:outline-hidden"
          />
          <button
            type="submit"
            disabled={submitting || !newMute}
            className="flex items-center gap-1 bg-cream-200 dark:bg-ink-800 hover:bg-cream-300 dark:hover:bg-ink-700 px-3.5 py-2 rounded-xl text-xs font-semibold text-ink-800 dark:text-ink-200 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Mute</span>
          </button>
        </form>

        {learning?.muted_terms?.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {learning.muted_terms.map((term) => (
              <span
                key={term}
                className="flex items-center gap-1 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/40 text-red-700 dark:text-red-300 px-2.5 py-1 rounded-lg text-xs font-medium"
              >
                <span>{term}</span>
                <button
                  type="button"
                  onClick={() => handleUnmute(term)}
                  className="hover:text-red-900 dark:hover:text-red-100"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Reset Button */}
      <div className="pt-4 border-t border-cream-200 dark:border-ink-800 flex justify-end">
        <button
          type="button"
          onClick={handleReset}
          className="flex items-center gap-1.5 text-xs font-semibold text-red-600 hover:text-red-700 dark:text-red-400 px-3 py-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset Learned Preferences</span>
        </button>
      </div>
    </div>
  );
}
