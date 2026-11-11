import React, { useState } from 'react';
import { Bookmark } from 'lucide-react';
import { PageHeader } from '../components/ui';

export default function KeptPage() {
  const [tab, setTab] = useState('unread');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <PageHeader title="Kept Articles" subtitle="Stories you swiped right to save" />
        <div className="flex gap-1.5 self-start sm:self-auto bg-sunk p-1 rounded-2xl">
          <button
            type="button"
            onClick={() => setTab('unread')}
            className={`px-3 py-1.5 text-xs font-bold rounded-xl transition ${
              tab === 'unread' ? 'bg-surface text-ink shadow-soft' : 'text-muted hover:text-ink'
            }`}
          >
            Unread
          </button>
          <button
            type="button"
            onClick={() => setTab('read')}
            className={`px-3 py-1.5 text-xs font-bold rounded-xl transition ${
              tab === 'read' ? 'bg-surface text-ink shadow-soft' : 'text-muted hover:text-ink'
            }`}
          >
            Read
          </button>
        </div>
      </div>

      <div className="card card-pad text-center py-12 space-y-4">
        <div className="w-16 h-16 rounded-3xl bg-volt-100 dark:bg-volt-900/40 text-volt-800 dark:text-volt-300 mx-auto flex items-center justify-center">
          <Bookmark className="w-8 h-8" />
        </div>
        <div className="max-w-md mx-auto space-y-2">
          <h2 className="text-2xl font-display font-semibold text-ink">No kept articles yet</h2>
          <p className="text-sm text-muted">
            Swipe right on any article in your news feed to keep it here. Current will grab clean full text so it’s ready to read whenever you want.
          </p>
        </div>
      </div>
    </div>
  );
}
