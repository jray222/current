import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Brain, Download, Images, RefreshCw, Sailboat, Shuffle, Trash2 } from 'lucide-react';
import { collectDeck, deleteDeck, exportDeck, getDeck, imagePath } from '../api';
import { useAuth } from '../context/AuthContext';
import { navigate, onLinkClick } from '../lib/router';
import useDeckPolling from '../lib/useDeckPolling';
import AuthImage from '../components/AuthImage';
import { ErrorBanner, PageHeader, Spinner, SuccessBanner, errorOf } from '../components/ui';
import DeckIcon from '../components/deck/DeckIcon';
import PictureChooser from '../components/deck/PictureChooser';
import { CollectStatus, ProgressBar, isCollecting, progressLine } from '../components/deck/DeckBits';

/** A deck's cards as a photo grid, filterable by group; tap one to sail from it. */
export default function DeckPage({ slug }) {
  const { user } = useAuth();
  const [deck, setDeck] = useState(null);
  const [group, setGroup] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [choosing, setChoosing] = useState(null);

  const load = useCallback(() => getDeck(slug).then(setDeck).catch((err) => setError(errorOf(err, 'Could not load this deck.'))), [slug]);
  useEffect(() => { load(); }, [load]);
  useDeckPolling(isCollecting(deck), load);

  const groups = useMemo(() => [...new Set((deck?.cards || []).map((c) => c.group).filter(Boolean))], [deck]);
  if (error) return <ErrorBanner message={error} />;
  if (!deck) return <Spinner />;

  const first = deck.facets[0]?.key;
  const cards = deck.cards.filter((c) => !group || c.group === group);
  const q = group ? `?group=${encodeURIComponent(group)}` : '';
  const sail = `/decks/${slug}/sail${q}`;

  const recollect = async () => {
    setNotice('');
    try {
      await collectDeck(slug, true);
      setNotice('Looking for better pictures. Pictures you picked stay.');
      load();
    } catch (err) { setError(errorOf(err, 'Could not start.')); }
  };
  const download = async () => {
    const pack = await exportDeck(slug);
    const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `${slug}.json` });
    a.click();
    URL.revokeObjectURL(url);
  };
  const remove = async () => {
    if (!window.confirm(`Delete “${deck.title}” and its pictures for everyone? Progress on it is lost too.`)) return;
    await deleteDeck(slug);
    navigate('/decks');
  };

  return (
    <>
      <PageHeader
        back={<a href="/decks" onClick={onLinkClick('/decks')} className="inline-flex items-center gap-1 text-sm font-bold text-muted hover:text-ink mb-2"><ArrowLeft className="w-4 h-4" /> Decks</a>}
        title={<span className="flex items-center gap-2"><DeckIcon name={deck.icon} className="w-7 h-7 text-brand-600 dark:text-brand-300" />{deck.title}</span>}
        subtitle={deck.subtitle}
      />
      <div className="space-y-4 mb-6">
        <CollectStatus collect={deck.collect} />
        <SuccessBanner message={notice} />
        <div className="flex flex-wrap gap-2">
          <a href={sail} onClick={onLinkClick(sail)} className="btn-primary"><Sailboat className="w-4 h-4" /> Sail through</a>
          <a href={`/decks/${slug}/sail?shuffle=1${group ? `&group=${encodeURIComponent(group)}` : ''}`}
            onClick={onLinkClick(`/decks/${slug}/sail?shuffle=1${group ? `&group=${encodeURIComponent(group)}` : ''}`)} className="btn-soft">
            <Shuffle className="w-4 h-4" /> Shuffle
          </a>
          <a href={`/decks/${slug}/quiz`} onClick={onLinkClick(`/decks/${slug}/quiz`)} className="btn-soft">
            <Brain className="w-4 h-4" /> Quiz me{deck.progress.due ? ` (${deck.progress.due} due)` : ''}
          </a>
          <button type="button" onClick={download} className="btn-ghost"><Download className="w-4 h-4" /> Export pack</button>
          {user?.is_superuser && (
            <>
              <button type="button" onClick={recollect} disabled={isCollecting(deck)} className="btn-ghost"><RefreshCw className="w-4 h-4" /> Find better pictures</button>
              <button type="button" onClick={remove} className="btn-ghost hover:!text-brand-700"><Trash2 className="w-4 h-4" /> Delete</button>
            </>
          )}
        </div>
        <div className="max-w-md space-y-1">
          <ProgressBar progress={deck.progress} />
          <p className="text-sm text-muted">{progressLine(deck.progress)}</p>
        </div>
        {deck.collect.status === 'done' && deck.collect.message && user?.is_superuser && (
          <p className="text-xs text-muted">Last gathering noted: {deck.collect.message}</p>
        )}
      </div>

      {groups.length > 1 && (
        <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap pb-1 mb-4" role="group" aria-label="Filter by group">
          <button type="button" className={`chip !text-sm !px-4 !py-1.5 ${!group ? 'chip-on' : ''}`} onClick={() => setGroup('')}>All {deck.cards.length}</button>
          {groups.map((g) => (
            <button key={g} type="button" className={`chip !text-sm !px-4 !py-1.5 ${group === g ? 'chip-on' : ''}`} onClick={() => setGroup(g)}>
              {g}
            </button>
          ))}
        </div>
      )}

      <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {cards.map((c) => {
          const img = c.images[first] || Object.values(c.images)[0];
          const to = `/decks/${slug}/sail?start=${c.slug}${group ? `&group=${encodeURIComponent(group)}` : ''}`;
          const known = c.progress.box >= 3;
          return (
            <li key={c.id} className="relative">
              <a href={to} onClick={onLinkClick(to)} className="block group">
                <div className="relative aspect-[3/4] rounded-2xl overflow-hidden bg-sunk">
                  {img && <AuthImage path={imagePath(img.id, 'thumb')} alt="" className="absolute inset-0 group-hover:scale-[1.03] transition duration-300" />}
                  {c.progress.seen > 0 && (
                    <span className={`absolute top-2 right-2 w-3 h-3 rounded-full ring-2 ring-white ${known ? 'bg-moss-500' : 'bg-brand-300'}`}
                      title={known ? 'Known' : 'Seen'} />
                  )}
                </div>
                <p className="font-bold mt-1.5 leading-tight">{c.name}</p>
                {c.subtitle && <p className="text-xs text-muted truncate">{c.subtitle}</p>}
              </a>
              {user?.is_superuser && (
                <button type="button" onClick={() => setChoosing(c)} disabled={isCollecting(deck)}
                  aria-label={`Change pictures of ${c.name}`} title="Change this card’s pictures"
                  className="absolute top-2 left-2 btn-icon w-9 h-9 bg-black/45 text-white hover:bg-black/65 disabled:opacity-0">
                  <Images className="w-4 h-4" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {choosing && (
        <PictureChooser card={choosing} facets={deck.facets} onClose={() => setChoosing(null)} onChanged={load} />
      )}
    </>
  );
}
