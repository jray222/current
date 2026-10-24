import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Eye, Images, RotateCcw, Sailboat, Undo2, X } from 'lucide-react';
import { getDeck, getQuiz, imagePath, recordProgress } from '../api';
import { navigate, onLinkClick } from '../lib/router';
import AuthImage, { preloadImages } from '../components/AuthImage';
import { ErrorBanner, Spinner, errorOf } from '../components/ui';
import useSwipe from '../lib/useSwipe';

const ROUND = 20;

/**
 * Quiz: a photo with the name hidden. Think of it, show the answer, then say
 * whether you knew it. Cards you knew come back later and later; the rest soon.
 */
export default function QuizPage({ slug }) {
  const [deck, setDeck] = useState(null);
  const [queue, setQueue] = useState(null);
  const [pos, setPos] = useState(0);
  const [view, setView] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [tally, setTally] = useState({ knew: 0, again: 0 });
  const [error, setError] = useState('');

  const start = useCallback(async () => {
    try {
      const [d, ids] = await Promise.all([getDeck(slug), getQuiz(slug, ROUND)]);
      setDeck(d);
      setQueue(ids);
      setPos(0);
      setRevealed(false);
      setTally({ knew: 0, again: 0 });
      setView(0);
    } catch (err) {
      setError(errorOf(err, 'Could not start the quiz.'));
    }
  }, [slug]);
  useEffect(() => { start(); }, [start]);

  const byId = useMemo(() => new Map((deck?.cards || []).map((c) => [c.id, c])), [deck]);
  const card = queue ? byId.get(queue[pos]) : null;
  const views = useMemo(() => (deck && card ? deck.facets.filter((f) => card.images[f.key]) : []), [deck, card]);
  const facet = views[view % Math.max(1, views.length)];

  // Each card opens on a random view, so you learn to know it from any side.
  useEffect(() => { if (views.length) setView(Math.floor(Math.random() * views.length)); }, [card?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const next = queue && byId.get(queue[pos + 1]);
    if (next) preloadImages(Object.values(next.images).map((i) => imagePath(i.id)));
  }, [queue, pos, byId]);

  const answer = useCallback((result) => {
    if (!card || !revealed) return;
    recordProgress(card.id, result).catch(() => {});
    setTally((t) => ({ ...t, [result]: t[result] + 1 }));
    setRevealed(false);
    setPos((p) => p + 1);
  }, [card, revealed]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (!revealed && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); setRevealed(true); }
      else if (revealed && (e.key === 'ArrowRight' || e.key === '2')) answer('knew');
      else if (revealed && (e.key === 'ArrowLeft' || e.key === '1')) answer('again');
      else if (e.key === 'ArrowDown' || e.key === 'v') setView((v) => v + 1);
      else if (e.key === 'Escape') navigate(`/decks/${slug}`);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [revealed, answer, slug]);

  const swipe = useSwipe({
    onRight: () => answer('knew'),
    onLeft: () => answer('again'),
    onTap: () => (revealed ? setView((v) => v + 1) : setRevealed(true)),
  });

  if (error) return <div className="p-6"><ErrorBanner message={error} /></div>;
  if (!deck || !queue) return <div className="fixed inset-0 bg-black"><Spinner /></div>;

  const shell = (children) => (
    <div className="fixed inset-0 bg-black text-white flex flex-col items-center justify-center gap-5 p-6 text-center fade-in">{children}</div>
  );
  if (!queue.length) {
    return shell(<>
      <p className="text-lg">No cards with pictures yet. They’re still being gathered.</p>
      <a href={`/decks/${slug}`} onClick={onLinkClick(`/decks/${slug}`)} className="btn bg-white/15 hover:bg-white/25 text-white">Back to the deck</a>
    </>);
  }
  if (pos >= queue.length) {
    return shell(<>
      <p className="text-sm uppercase tracking-widest text-white/60">{deck.title}</p>
      <h1 className="text-4xl">You knew {tally.knew} of {tally.knew + tally.again}</h1>
      <p className="text-white/70 max-w-sm">
        {tally.again ? 'The ones you missed come back in ten minutes; the ones you knew, in a day or more.' : 'Every one. They’ll come back later, spaced further apart.'}
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        <button type="button" className="btn bg-white text-black hover:bg-white/90" onClick={start}><RotateCcw className="w-4 h-4" /> Another round</button>
        <a href={`/decks/${slug}/sail`} onClick={onLinkClick(`/decks/${slug}/sail`)} className="btn bg-white/15 hover:bg-white/25 text-white"><Sailboat className="w-4 h-4" /> Sail through</a>
        <a href={`/decks/${slug}`} onClick={onLinkClick(`/decks/${slug}`)} className="btn bg-white/15 hover:bg-white/25 text-white">Done</a>
      </div>
    </>);
  }

  const image = facet && card.images[facet.key];
  return (
    <div className="fixed inset-0 bg-black text-white overflow-hidden select-none">
      <div className="absolute inset-0 touch-none" {...swipe.handlers} style={swipe.style}>
        {image && (
          <div key={image.id} className="absolute inset-0 fade-in">
            <AuthImage path={imagePath(image.id)} eager className="absolute inset-0 scale-110 blur-2xl opacity-50" />
            <AuthImage path={imagePath(image.id)} eager alt={revealed ? `${card.name}: ${facet.label}` : 'Who is this?'}
              className="absolute inset-0" imgClassName="w-full h-full object-contain" />
          </div>
        )}
      </div>

      <div className="absolute top-0 inset-x-0 pt-safe bg-gradient-to-b from-black/70 to-transparent">
        <div className="h-1 bg-white/15"><div className="h-full bg-brand-400 transition-all" style={{ width: `${(pos / queue.length) * 100}%` }} /></div>
        <div className="flex items-center gap-2 px-3 py-2">
          <a href={`/decks/${slug}`} onClick={onLinkClick(`/decks/${slug}`)} aria-label="Stop the quiz" className="btn-icon hover:bg-white/15"><X className="w-6 h-6" /></a>
          <div className="flex-1 min-w-0">
            <p className="font-bold truncate">Quiz · {deck.title}</p>
            <p className="text-xs text-white/70">{pos + 1} of {queue.length}</p>
          </div>
          {views.length > 1 && (
            <button type="button" onClick={() => setView((v) => v + 1)} className="btn bg-white/15 hover:bg-white/25 text-white !py-1.5">
              <Images className="w-4 h-4" /> {facet.label}
            </button>
          )}
        </div>
      </div>

      <div className="absolute bottom-0 inset-x-0 pb-safe bg-gradient-to-t from-black/90 via-black/60 to-transparent">
        <div className="max-w-xl mx-auto px-4 pt-16 pb-6 space-y-3">
          {!revealed ? (
            <>
              <p className="text-center text-white/80 text-lg">Do you know this one?</p>
              <button type="button" onClick={() => setRevealed(true)} className="btn bg-white text-black hover:bg-white/90 w-full !py-3.5 !text-base">
                <Eye className="w-5 h-5" /> Show the answer
              </button>
            </>
          ) : (
            <div className="space-y-3 fade-in">
              <div aria-live="polite">
                <h1 className="text-4xl leading-none">{card.name}</h1>
                {card.subtitle && <p className="text-white/70 mt-1.5">{card.subtitle}</p>}
              </div>
              {card.cues[facet?.key] && <p><span className="font-bold text-brand-300">{facet.label}:</span> {card.cues[facet.key]}</p>}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button type="button" onClick={() => answer('again')} className="btn bg-white/15 hover:bg-white/25 text-white !py-3.5 !text-base">
                  <Undo2 className="w-5 h-5" /> Not yet
                </button>
                <button type="button" onClick={() => answer('knew')} className="btn bg-moss-500 hover:bg-moss-600 text-white !py-3.5 !text-base">
                  <Check className="w-5 h-5" /> Knew it
                </button>
              </div>
              <p className="text-center text-xs text-white/50">Swipe right if you knew it, left if not.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
