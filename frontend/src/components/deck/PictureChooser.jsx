import React, { useEffect, useMemo, useState } from 'react';
import { Check, EyeOff, ExternalLink, ImageOff, Loader2, RefreshCw, Search } from 'lucide-react';
import { chooseImage, collectCard, getCardImages, hideImage, imagePath } from '../../api';
import AuthImage from '../AuthImage';
import Modal from '../Modal';
import { ErrorBanner, Spinner, SuccessBanner, errorOf } from '../ui';

const sourceKey = (o) => `${o.provider}:${o.page_url || o.title}`;

/**
 * Owner only: one card's pictures, every view at once. Pick a view at the top, then the photo for it
 * from everything found for the card (a bark close-up the leaf search turned up can go on Bark).
 * Look again for the card, or search Commons in your own words for the view.
 */
export default function PictureChooser({ card, facets, initialFacet, onClose, onChanged }) {
  const [facet, setFacet] = useState(initialFacet || facets[0]?.key);
  const [options, setOptions] = useState(null);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = () => getCardImages(card.id).then(setOptions).catch((err) => setError(errorOf(err, 'Could not load the pictures.')));
  useEffect(() => { load(); }, [card.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const label = (key) => facets.find((f) => f.key === key)?.label || key;
  const current = facets.find((f) => f.key === facet);

  // In use, per view.
  const chosen = useMemo(() => Object.fromEntries((options || []).filter((o) => o.status === 'chosen').map((o) => [o.facet, o])), [options]);

  // Every photo once: this view's own row when it has one, else the row of the view it was found for.
  // This view's finds first (your latest search first of all), then the rest.
  const tiles = useMemo(() => {
    const bySource = new Map();
    for (const o of options || []) {
      const k = sourceKey(o);
      const entry = bySource.get(k) || { rows: [] };
      entry.rows.push(o);
      bySource.set(k, entry);
    }
    const list = [];
    for (const { rows } of bySource.values()) {
      const own = rows.find((r) => r.facet === facet);
      if (own?.status === 'hidden') continue;
      const visible = rows.filter((r) => r.status !== 'hidden');
      if (!visible.length) continue;
      const row = own || visible.sort((a, b) => b.score - a.score)[0];
      list.push({ row, own: !!own, usedFor: visible.filter((r) => r.status === 'chosen').map((r) => r.facet), fresh: rows.some((r) => found.includes(r.id)) });
    }
    return list.sort((a, b) => (b.fresh - a.fresh) || (b.own - a.own) || (b.row.score - a.row.score));
  }, [options, facet, found]);

  const run = async (key, fn, message) => {
    setBusy(key);
    setError('');
    setNotice('');
    try {
      const problems = await fn();
      onChanged();
      if (problems?.length) setError(problems.join(' '));
      else if (message) setNotice(message);
    } catch (err) {
      setError(errorOf(err, 'That didn’t work.'));
    } finally {
      setBusy(null);
    }
  };

  const use = (row) => run(row.id, async () => { await chooseImage(row.id, facet); await load(); });
  const hide = (row) => run(`hide-${row.id}`, async () => { await hideImage(row.id); await load(); });
  const lookAgain = () => run('again', async () => {
    const r = await collectCard(card.id);
    setOptions(r.images);
    setFound([]);
    return r.problems;
  }, 'Looked again for every view. Pictures you picked stayed.');
  const search = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    run('search', async () => {
      const r = await collectCard(card.id, { facet, query: q });
      setOptions(r.images);
      setFound(r.found);
      return r.problems;
    });
  };

  return (
    <Modal open title={`${card.name}: pictures`} subtitle="Pick a view, then the photo that shows it best. Pictures you pick are never replaced."
      onClose={onClose} maxWidth="sm:max-w-4xl">
      <div className="text-ink space-y-4">
        <div className="grid grid-cols-4 sm:grid-cols-6 gap-2" role="tablist" aria-label="Views">
          {facets.map((f) => {
            const img = chosen[f.key];
            const on = f.key === facet;
            return (
              <button key={f.key} type="button" role="tab" aria-selected={on} onClick={() => { setFacet(f.key); setFound([]); }}
                className={`text-left rounded-2xl overflow-hidden border-2 transition ${on ? 'border-brand-500' : 'border-line/60 hover:border-line'}`}>
                <div className="aspect-square bg-sunk relative">
                  {img?.downloaded
                    ? <AuthImage path={imagePath(img.id, 'thumb')} className="absolute inset-0" />
                    : <ImageOff className="w-5 h-5 text-muted absolute inset-0 m-auto" aria-hidden="true" />}
                  {img?.picked_by_person && (
                    <span className="absolute top-1 right-1 w-5 h-5 rounded-full bg-moss-500 text-white flex items-center justify-center" title="You picked it">
                      <Check className="w-3 h-3" />
                    </span>
                  )}
                </div>
                <p className={`px-2 py-1 text-xs font-bold truncate ${on ? 'bg-brand-500 text-white' : ''}`}>{f.label}</p>
              </button>
            );
          })}
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          <form onSubmit={search} className="flex gap-2 flex-1">
            <label htmlFor="picture-search" className="sr-only">Search Wikimedia Commons for {current?.label}</label>
            <input id="picture-search" className="input flex-1 min-w-0" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={200}
              placeholder={`Search for ${current?.label.toLowerCase()}, e.g. ${card.subtitle || card.name} ${current?.label.toLowerCase()}`} />
            <button type="submit" disabled={busy !== null || !query.trim()} className="btn-primary shrink-0">
              {busy === 'search' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Search
            </button>
          </form>
          <button type="button" onClick={lookAgain} disabled={busy !== null} className="btn-soft shrink-0">
            {busy === 'again' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Look again for this card
          </button>
        </div>

        <ErrorBanner message={error} />
        <SuccessBanner message={notice} />
        {!options && <Spinner />}
        {options && !tiles.length && <p className="text-muted">No pictures yet. Search for one above, or look again for this card.</p>}
        <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {tiles.map(({ row, own, usedFor, fresh }) => {
            const here = own && row.status === 'chosen';
            return (
              <li key={row.id} className={`rounded-2xl overflow-hidden border-2 ${here ? 'border-brand-500' : 'border-line/60'}`}>
                <div className="aspect-[4/3] bg-sunk relative">
                  {row.downloaded
                    ? <AuthImage path={imagePath(row.id, 'thumb')} alt={row.title || ''} className="absolute inset-0" />
                    : row.preview_url && <img src={row.preview_url} alt={row.title || ''} referrerPolicy="no-referrer" loading="lazy" className="w-full h-full object-cover" />}
                  <div className="absolute top-1.5 left-1.5 flex flex-wrap gap-1">
                    {fresh && <span className="chip !text-[11px] !py-0.5 bg-brand-500 text-white">New</span>}
                    {usedFor.map((k) => <span key={k} className="chip chip-moss !text-[11px] !py-0.5">{label(k)}</span>)}
                    {!own && !usedFor.length && <span className="chip !text-[11px] !py-0.5 bg-surface/90">Found for {label(row.facet)}</span>}
                  </div>
                </div>
                <div className="p-2 space-y-1.5">
                  <p className="text-xs font-bold line-clamp-2" title={row.title}>{row.title}</p>
                  <p className="text-[11px] text-muted truncate">
                    {row.author} · {row.license} ·{' '}
                    <a href={row.page_url} target="_blank" rel="noreferrer" className="underline inline-flex items-center gap-0.5">source <ExternalLink className="w-3 h-3" /></a>
                  </p>
                  <div className="flex gap-1.5">
                    {here ? (
                      <span className="chip chip-moss flex-1 justify-center"><Check className="w-3.5 h-3.5" /> {current?.label}</span>
                    ) : (
                      <button type="button" disabled={busy !== null} onClick={() => use(row)} className="btn-primary !px-2 !py-1.5 !text-xs flex-1 min-w-0">
                        {busy === row.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                        <span className="truncate">Use for {current?.label}</span>
                      </button>
                    )}
                    {own && (
                      <button type="button" disabled={busy !== null} onClick={() => hide(row)} aria-label={`Hide from ${current?.label}`} title={`Hide from ${current?.label} for good`}
                        className="btn-soft !px-2 !py-1.5 !text-xs"><EyeOff className="w-3.5 h-3.5" /></button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </Modal>
  );
}
