import React, { useCallback, useEffect, useState } from 'react';
import { Brain, Sailboat, ChevronRight } from 'lucide-react';
import { getDecks, getToday } from '../api';
import { onLinkClick } from '../lib/router';
import useDeckPolling from '../lib/useDeckPolling';
import { ErrorBanner, Spinner, errorOf } from '../components/ui';
import DeckIcon from '../components/deck/DeckIcon';
import { CollectStatus, DeckCover, ProgressBar, isCollecting, progressLine } from '../components/deck/DeckBits';

const longDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });

/** Home: today's deck, big, with Sail and Quiz; the other decks below. */
export default function TodayPage() {
  const [today, setToday] = useState(null);
  const [decks, setDecks] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [t, d] = await Promise.all([getToday(), getDecks()]);
      setToday(t);
      setDecks(d);
    } catch (err) {
      setError(errorOf(err, 'Could not load today’s deck.'));
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  useDeckPolling(decks?.some(isCollecting), load);

  if (error) return <ErrorBanner message={error} />;
  if (!today || !decks) return <Spinner />;

  const deck = today.deck;
  const others = decks.filter((d) => d.slug !== deck?.slug);
  const gathering = decks.find(isCollecting);

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-bold uppercase tracking-wider text-brand-600 dark:text-brand-300">{longDate(today.date)}</p>
        <h1 className="text-3xl sm:text-4xl mt-1">Today’s dose</h1>
      </div>

      {deck ? <TodayHero deck={deck} /> : (
        <div className="card card-pad space-y-3">
          <h2 className="text-xl">Your decks are getting their pictures</h2>
          <p className="text-muted">Dose is gathering openly licensed photos from Wikimedia Commons and iNaturalist. The first deck appears here as soon as it has some.</p>
          {gathering && <CollectStatus collect={gathering.collect} />}
          {!gathering && decks.some((d) => d.collect.status === 'error') && (
            <CollectStatus collect={decks.find((d) => d.collect.status === 'error').collect} />
          )}
        </div>
      )}

      {others.length > 0 && (
        <section>
          <h2 className="text-xl mb-3">Other decks</h2>
          <div className="card divide-y divide-line/70 overflow-hidden">
            {others.map((d) => (
              <a key={d.slug} href={`/decks/${d.slug}`} onClick={onLinkClick(`/decks/${d.slug}`)}
                className="flex items-center gap-4 p-3 hover:bg-sunk transition">
                <DeckCover deck={d} size="thumb" className="w-16 h-16 rounded-2xl overflow-hidden shrink-0" />
                <span className="flex-1 min-w-0">
                  <span className="flex items-center gap-1.5 font-bold"><DeckIcon name={d.icon} className="w-4 h-4 text-muted" />{d.title}</span>
                  <span className="block text-sm text-muted truncate">{progressLine(d.progress)}</span>
                  <CollectStatus collect={d.collect} compact />
                </span>
                <ChevronRight className="w-5 h-5 text-muted" aria-hidden="true" />
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function TodayHero({ deck }) {
  const sail = `/decks/${deck.slug}/sail`;
  const quiz = `/decks/${deck.slug}/quiz`;
  return (
    <article className="card overflow-hidden lg:grid lg:grid-cols-5">
      <a href={sail} onClick={onLinkClick(sail)} className="block lg:col-span-3" aria-label={`Sail through ${deck.title}`}>
        <DeckCover deck={deck} className="aspect-[4/3] lg:aspect-auto lg:h-full w-full" />
      </a>
      <div className="card-pad lg:col-span-2 flex flex-col gap-4">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-bold text-muted"><DeckIcon name={deck.icon} className="w-4 h-4" /> {deck.card_count} cards</p>
          <h2 className="text-3xl mt-1">{deck.title}</h2>
          {deck.subtitle && <p className="text-muted mt-1">{deck.subtitle}</p>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {deck.facets.map((f) => <span key={f.key} className="chip">{f.label}</span>)}
        </div>
        <div className="space-y-1.5">
          <ProgressBar progress={deck.progress} />
          <p className="text-sm text-muted">{progressLine(deck.progress)}</p>
        </div>
        <div className="flex flex-col sm:flex-row lg:flex-col gap-2 mt-auto">
          <a href={sail} onClick={onLinkClick(sail)} className="btn-primary !py-3 !text-base flex-1">
            <Sailboat className="w-5 h-5" aria-hidden="true" /> Sail through
          </a>
          <a href={quiz} onClick={onLinkClick(quiz)} className="btn-soft !py-3 !text-base flex-1">
            <Brain className="w-5 h-5" aria-hidden="true" /> Quiz me{deck.progress.due ? ` (${deck.progress.due} due)` : ''}
          </a>
        </div>
      </div>
    </article>
  );
}
