import React, { useState, useMemo } from 'react';
import { Newspaper, RefreshCw, Rss } from 'lucide-react';
import { onLinkClick } from '../lib/router';

export default function TodayPage() {
  const [crawling, setCrawling] = useState(false);
  const formattedDate = useMemo(
    () => new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }),
    [],
  );

  const handleCrawlNow = () => {
    setCrawling(true);
    setTimeout(() => setCrawling(false), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-brand-700 dark:text-brand-300">
            {formattedDate}
          </p>
          <h1 className="text-3xl sm:text-4xl mt-0.5 font-display font-semibold tracking-tight text-ink">
            Today’s Edition
          </h1>
        </div>
        <button
          type="button"
          onClick={handleCrawlNow}
          disabled={crawling}
          className="btn-primary self-start sm:self-auto gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${crawling ? 'animate-spin' : ''}`} />
          {crawling ? 'Crawling…' : 'Crawl now'}
        </button>
      </div>

      <div className="card card-pad text-center py-12 space-y-4">
        <div className="w-16 h-16 rounded-3xl bg-brand-100 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 mx-auto flex items-center justify-center">
          <Newspaper className="w-8 h-8" />
        </div>
        <div className="max-w-md mx-auto space-y-2">
          <h2 className="text-2xl font-display font-semibold text-ink">Welcome to Current</h2>
          <p className="text-sm text-muted">
            Add news sites, blogs, and RSS feeds to get started. Your front page will organize coverage into Top Stories and categories, learning what you like with every swipe.
          </p>
        </div>
        <div>
          <a
            href="/sources"
            onClick={onLinkClick('/sources')}
            className="btn-primary inline-flex gap-2"
          >
            <Rss className="w-4 h-4" /> Add your first source
          </a>
        </div>
      </div>
    </div>
  );
}
