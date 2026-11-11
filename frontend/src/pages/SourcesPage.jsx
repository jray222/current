import React from 'react';
import { Plus, Rss } from 'lucide-react';
import { PageHeader } from '../components/ui';

export default function SourcesPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <PageHeader title="News Sources" subtitle="Feeds and websites Current crawls for your household" />
        <button
          type="button"
          className="btn-primary self-start sm:self-auto gap-2"
        >
          <Plus className="w-4 h-4" /> Add site
        </button>
      </div>

      <div className="card card-pad text-center py-12 space-y-4">
        <div className="w-16 h-16 rounded-3xl bg-brand-100 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 mx-auto flex items-center justify-center">
          <Rss className="w-8 h-8" />
        </div>
        <div className="max-w-md mx-auto space-y-2">
          <h2 className="text-2xl font-display font-semibold text-ink">No sources configured</h2>
          <p className="text-sm text-muted">
            Add URLs of websites, RSS feeds, or news publications. Current automatically detects feeds, respects robots.txt, and schedules periodic crawls.
          </p>
        </div>
      </div>
    </div>
  );
}
