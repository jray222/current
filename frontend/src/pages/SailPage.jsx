import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronLeft, ChevronRight, ExternalLink, Images, Info, Pause, Play, RotateCcw, Brain, X,
} from 'lucide-react';
import { getDeck, imagePath, recordProgress } from '../api';
import { useAuth } from '../context/AuthContext';
import { navigate, onLinkClick, useLocation } from '../lib/router';
import AuthImage, { preloadImages } from '../components/AuthImage';
import { ErrorBanner, Spinner, errorOf } from '../components/ui';
import PictureChooser from '../components/deck/PictureChooser';
import useSwipe from '../lib/useSwipe';

const SPEEDS = [3, 5, 8, 12];
const SPEED_KEY = 'dose:sail-seconds';

function savedSpeed() {
  try {
    const v = Number(localStorage.getItem(SPEED_KEY));
    return SPEEDS.includes(v) ? v : 5;
  } catch { return 5; }
}

function shuffled(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** The facets of a card that have a picture, in the deck's order. */
const facetsWithPictures = (deck, card) => deck.facets.filter((f) => card?.images[f.key]);

/**
 * Sail through a deck: one card at a time, full screen, photo first.
 * Swipe sideways (or ←/→) for the next card, tap the photo (or ↑/↓) for its next view.
 * Play advances by itself: every view of a card, then the next card.
 */
export default function SailPage({ slug }) {
  const { search } = useLocation();
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const { user } = useAuth();
  const [deck, setDeck] = useState(null);
  const [order, setOrder] = useState([]);
  const [pos, setPos] = useState(0);
  const [facetIdx, setFacetIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(savedSpeed);
  const [info, setInfo] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const seen = useRef(new Set());

  const load = useCallback(async (keepPlace = false) => {
    try {
      const d = await getDeck(slug);
      setDeck(d);
      if (keepPlace) return;
      const group = params.get('group');
      let cards = d.cards.filter((c) => Object.keys(c.images).length && (!group || c.group === group));
      if (params.get('shuffle')) cards = shuffled(cards);
      setOrder(cards.map((c) => c.id));
      const start = params.get('start');
      setPos(Math.max(0, start ? cards.findIndex((c) => c.slug === start) : 0));
      setFacetIdx(0);
    } catch (err) {
      setError(errorOf(err, 'Could not load this deck.'));
    }
  }, [slug, params]);
  useEffect(() => { load(); }, [load]);

  const byId = useMemo(() => new Map((deck?.cards || []).map((c) => [c.id, c])), [deck]);
  const card = byId.get(order[pos]);
  const views = useMemo(() => (deck && card ? facetsWithPictures(deck, card) : []), [deck, card]);
  const facet = views[Math.min(facetIdx, views.length - 1)];
  const image = facet ? card.images[facet.key] : null;

  const markSeen = useCallback((c) => {
    if (!c || seen.current.has(c.id)) return;
    seen.current.add(c.id);
    recordProgress(c.id, 'seen').catch(() => {});
  }, []);

  const goCard = useCallback((delta) => {
    setInfo(false);
    if (delta > 0) markSeen(card);
    if (pos + delta >= order.length) { setDone(true); setPlaying(false); return; }
    setPos((p) => Math.max(0, Math.min(order.length - 1, p + delta)));
    setFacetIdx(0);
  }, [pos, order.length, card, markSeen]);

  const goFacet = useCallback((delta, { wrapToCard = false } = {}) => {
    const next = facetIdx + delta;
    if (next >= views.length) {
      if (wrapToCard) goCard(1); else setFacetIdx(0);
    } else if (next < 0) {
      setFacetIdx(views.length - 1);
    } else {
      setFacetIdx(next);
    }
  }, [facetIdx, views.length, goCard]);

  // Auto-advance: every view of the card, then the next card.
  const paused = !playing || info || choosing || done;
  useEffect(() => {
    if (paused || !card) return undefined;
    const id = setTimeout(() => goFacet(1, { wrapToCard: true }), seconds * 1000);
    return () => clearTimeout(id);
  }, [paused, card, facetIdx, seconds, goFacet]);

  // Stop the timer while the tab is hidden.
  useEffect(() => {
    const onHide = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', onHide);
    return () => document.removeEventListener('visibilitychange', onHide);
  }, []);

  // The next two cards' pictures load ahead, so swiping never waits.
  useEffect(() => {
    if (!deck) return;
    const ahead = [pos + 1, pos + 2, pos - 1].map((i) => byId.get(order[i])).filter(Boolean);
    preloadImages([
      ...views.map((f) => imagePath(card.images[f.key].id)),
      ...ahead.flatMap((c) => facetsWithPictures(deck, c).map((f) => imagePath(c.images[f.key].id))),
    ]);
  }, [deck, pos, order, byId, card, views]);

  const close = useCallback(() => {
    markSeen(card);
    navigate(`/decks/${slug}`);
  }, [card, markSeen, slug]);

  useEffect(() => {
    const onKey = (e) => {
      if (choosing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'ArrowRight') goCard(1);
      else if (e.key === 'ArrowLeft') goCard(-1);
      else if (e.key === 'ArrowDown') goFacet(1);
      else if (e.key === 'ArrowUp') goFacet(-1);
      else if (e.key === ' ') { e.preventDefault(); setPlaying((p) => !p); }
      else if (e.key === 'i') setInfo((v) => !v);
      else if (e.key === 'Escape') { if (info) setInfo(false); else close(); }
      else return;
      e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [goCard, goFacet, close, choosing, info]);

  const swipe = useSwipe({
    onLeft: () => goCard(1),
    onRight: () => goCard(-1),
    onUp: () => setInfo(true),
    onDown: () => (info ? setInfo(false) : close()),
    onTap: () => goFacet(1),
  });

  const setSpeed = (s) => {
    setSeconds(s);
    try { localStorage.setItem(SPEED_KEY, String(s)); } catch { /* not saved */ }
  };

  if (error) return <div className="p-6"><ErrorBanner message={error} /></div>;
  if (!deck) return <div className="fixed inset-0 bg-black"><Spinner /></div>;
  if (!order.length) {
    return (
      <div className="fixed inset-0 bg-black text-white flex flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-lg">This deck has no pictures yet. They’re still being gathered.</p>
        <a href={`/decks/${slug}`} onClick={onLinkClick(`/decks/${slug}`)} className="btn bg-white/15 hover:bg-white/25 text-white">Back to the deck</a>
      </div>
    );
  }

  if (done) {
    return (
      <div className="fixed inset-0 bg-black text-white flex flex-col items-center justify-center gap-5 p-6 text-center fade-in">
        <p className="text-sm uppercase tracking-widest text-white/60">{deck.title}</p>
        <h1 className="text-4xl">You sailed through {order.length} cards</h1>
        <div className="flex flex-wrap justify-center gap-2">
          <button type="button" className="btn bg-white text-black hover:bg-white/90" onClick={() => { setDone(false); setPos(0); setFacetIdx(0); }}>
            <RotateCcw className="w-4 h-4" /> Again
          </button>
          <a href={`/decks/${slug}/quiz`} onClick={onLinkClick(`/decks/${slug}/quiz`)} className="btn bg-white/15 hover:bg-white/25 text-white">
            <Brain className="w-4 h-4" /> Quiz me
          </a>
          <button type="button" className="btn bg-white/15 hover:bg-white/25 text-white" onClick={close}>Done</button>
        </div>
      </div>
    );
  }

  const cue = card.cues[facet?.key];
  return (
    <div className="fixed inset-0 bg-black text-white overflow-hidden select-none" aria-roledescription="carousel" aria-label={deck.title}>
      {/* The photo: a blurred copy fills the screen behind the whole picture. */}
      <div className="absolute inset-0 touch-none" {...swipe.handlers} style={swipe.style}>
        {image && (
          <div key={image.id} className="absolute inset-0 fade-in">
            <AuthImage path={imagePath(image.id)} eager className="absolute inset-0 scale-110 blur-2xl opacity-50" />
            <AuthImage path={imagePath(image.id)} eager alt={`${card.name}: ${facet.label}`}
              className="absolute inset-0" imgClassName="w-full h-full object-contain" />
          </div>
        )}
      </div>

      {/* Top: close, where you are, play and speed. */}
      <div className="absolute top-0 inset-x-0 pt-safe bg-gradient-to-b from-black/70 to-transparent pointer-events-none">
        <div className="h-1 bg-white/15">
          {!paused && <div key={`${pos}-${facetIdx}-${seconds}`} className="h-full bg-white timer-fill" style={{ animationDuration: `${seconds}s` }} />}
        </div>
        <div className="flex items-center gap-2 px-3 py-2 pointer-events-auto">
          <button type="button" onClick={close} aria-label="Close" className="btn-icon hover:bg-white/15"><X className="w-6 h-6" /></button>
          <div className="flex-1 min-w-0">
            <p className="font-bold truncate">{deck.title}</p>
            <p className="text-xs text-white/70">{pos + 1} of {order.length}</p>
          </div>
          {user?.is_superuser && (
            <button type="button" onClick={() => { setPlaying(false); setChoosing(true); }} aria-label="Change this card’s pictures" title="Change this card’s pictures"
              className="btn-icon hover:bg-white/15"><Images className="w-5 h-5" /></button>
          )}
          <label className="sr-only" htmlFor="sail-speed">Seconds per picture</label>
          <select id="sail-speed" value={seconds} onChange={(e) => setSpeed(Number(e.target.value))}
            className="bg-white/10 rounded-full text-sm font-bold px-2 py-1.5 border-0 focus:ring-0 [&>option]:text-black">
            {SPEEDS.map((s) => <option key={s} value={s}>{s}s</option>)}
          </select>
          <button type="button" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'} title={playing ? 'Pause (space)' : 'Play (space)'}
            className="btn-icon bg-white/15 hover:bg-white/25">
            {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Desktop arrows. */}
      <button type="button" onClick={() => goCard(-1)} disabled={pos === 0} aria-label="Previous card"
        className="hidden md:flex absolute left-3 top-1/2 -translate-y-1/2 btn-icon w-12 h-12 bg-black/40 hover:bg-black/60 disabled:opacity-0">
        <ChevronLeft className="w-7 h-7" />
      </button>
      <button type="button" onClick={() => goCard(1)} aria-label="Next card"
        className="hidden md:flex absolute right-3 top-1/2 -translate-y-1/2 btn-icon w-12 h-12 bg-black/40 hover:bg-black/60">
        <ChevronRight className="w-7 h-7" />
      </button>

      {/* Bottom: the views, the name, what to notice. */}
      <div className={`absolute bottom-0 inset-x-0 pb-safe bg-gradient-to-t from-black/90 via-black/60 to-transparent ${info ? 'max-h-[75vh] overflow-y-auto' : ''}`}>
        <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-16 pb-5 space-y-3">
          {views.length > 1 && (
            <div className="flex gap-1.5 overflow-x-auto no-scrollbar" role="tablist" aria-label="Views">
              {views.map((f, i) => (
                <button key={f.key} type="button" role="tab" aria-selected={i === facetIdx} onClick={() => setFacetIdx(i)}
                  className={`rounded-full px-3 py-1 text-sm font-bold whitespace-nowrap transition ${i === facetIdx ? 'bg-white text-black' : 'bg-white/15 text-white hover:bg-white/25'}`}>
                  {f.label}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0" aria-live="polite">
              <h1 className="text-4xl sm:text-5xl leading-none">{card.name}</h1>
              <p className="text-white/70 mt-1.5 text-sm sm:text-base">
                {card.subtitle}{card.subtitle && card.group ? ' · ' : ''}{card.group}
              </p>
            </div>
            <button type="button" onClick={() => setInfo((v) => !v)} aria-expanded={info} aria-label="More about it"
              className={`btn-icon shrink-0 ${info ? 'bg-white text-black' : 'bg-white/15 hover:bg-white/25'}`}>
              <Info className="w-5 h-5" />
            </button>
          </div>
          {cue && (
            <p className="text-lg leading-snug"><span className="font-bold text-brand-300">{facet.label}:</span> {cue}</p>
          )}
          {card.summary && <p className="text-white/80">{card.summary}</p>}

          {info && (
            <div className="space-y-3 pt-1 fade-in">
              {card.facts.length > 0 && (
                <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {card.facts.map((f) => (
                    <div key={f.label} className="rounded-2xl bg-white/10 px-3 py-2">
                      <dt className="text-xs uppercase tracking-wide text-white/60">{f.label}</dt>
                      <dd className="font-bold">{f.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {card.wiki_extract && <p className="text-sm text-white/80 leading-relaxed">{card.wiki_extract}</p>}
              {card.wiki_url && (
                <a href={card.wiki_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-bold text-brand-300 hover:underline">
                  Wikipedia <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>
          )}

          {image && (
            <p className="text-[11px] text-white/50 truncate">
              Photo: {image.author || 'Unknown'} ·{' '}
              <a href={image.license_url || image.page_url} target="_blank" rel="noreferrer" className="underline hover:text-white">{image.license}</a>
              {' · '}
              <a href={image.page_url} target="_blank" rel="noreferrer" className="underline hover:text-white">
                {image.provider === 'inaturalist' ? 'iNaturalist' : 'Wikimedia Commons'}
              </a>
            </p>
          )}
        </div>
      </div>

      {choosing && (
        <PictureChooser card={card} facets={deck.facets} initialFacet={facet?.key} onClose={() => setChoosing(false)} onChanged={() => load(true)} />
      )}
    </div>
  );
}
