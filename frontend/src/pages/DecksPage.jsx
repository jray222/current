import React, { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { getDecks } from '../api';
import { useAuth } from '../context/AuthContext';
import { onLinkClick } from '../lib/router';
import useDeckPolling from '../lib/useDeckPolling';
import { EmptyState, ErrorBanner, PageHeader, Spinner, errorOf } from '../components/ui';
import DeckIcon from '../components/deck/DeckIcon';
import { CollectStatus, DeckCover, ProgressBar, isCollecting, progressLine } from '../components/deck/DeckBits';

export default function DecksPage() {
  const { user } = useAuth();
  const [decks, setDecks] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(() => getDecks().then(setDecks).catch((err) => setError(errorOf(err, 'Could not load decks.'))), []);
  useEffect(() => { load(); }, [load]);
  useDeckPolling(decks?.some(isCollecting), load);

  return (
    <>
      <PageHeader title="Decks" subtitle="One domain of knowledge each"
        actions={user?.is_superuser && (
          <a href="/decks/new" onClick={onLinkClick('/decks/new')} className="btn-primary">
            <Plus className="w-4 h-4" aria-hidden="true" /> New deck
          </a>
        )} />
      <ErrorBanner message={error} />
      {!decks && !error && <Spinner />}
      {decks?.length === 0 && (
        <EmptyState icon={Plus} title="No decks yet">
          <p>{user?.is_superuser ? 'Add one from a topic or a pack.' : 'Ask whoever runs this Dose to add one.'}</p>
        </EmptyState>
      )}
      {decks?.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {decks.map((d) => (
            <li key={d.slug}>
              <a href={`/decks/${d.slug}`} onClick={onLinkClick(`/decks/${d.slug}`)}
                className="card overflow-hidden block hover:shadow-lift transition group">
                <DeckCover deck={d} className="aspect-[16/10] w-full" />
                <div className="p-4 space-y-2">
                  <h2 className="text-xl flex items-center gap-2"><DeckIcon name={d.icon} className="w-5 h-5 text-brand-600 dark:text-brand-300" />{d.title}</h2>
                  {d.subtitle && <p className="text-sm text-muted line-clamp-2">{d.subtitle}</p>}
                  <ProgressBar progress={d.progress} />
                  <p className="text-xs text-muted">{progressLine(d.progress)}</p>
                  <CollectStatus collect={d.collect} compact />
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
