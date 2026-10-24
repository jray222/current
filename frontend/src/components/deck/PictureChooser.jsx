import React, { useEffect, useState } from 'react';
import { Check, EyeOff, ExternalLink, Loader2 } from 'lucide-react';
import { chooseImage, getCardImages, hideImage } from '../../api';
import Modal from '../Modal';
import { ErrorBanner, Spinner, errorOf } from '../ui';

/** Owner only: every picture found for one view of a card. Use a better one, or hide a wrong one for good. */
export default function PictureChooser({ card, facet, onClose, onChanged }) {
  const [options, setOptions] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');

  const load = () => getCardImages(card.id, facet.key).then(setOptions).catch((err) => setError(errorOf(err, 'Could not load the pictures.')));
  useEffect(() => { load(); }, [card.id, facet.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (id, fn) => {
    setBusy(id);
    setError('');
    try {
      await fn(id);
      await load();
      onChanged();
    } catch (err) {
      setError(errorOf(err, 'That didn’t work.'));
    } finally {
      setBusy(null);
    }
  };

  const visible = (options || []).filter((o) => o.status !== 'hidden');
  return (
    <Modal open title={`${card.name}: ${facet.label}`} subtitle="Pick the picture that shows it best. Hidden pictures never come back."
      onClose={onClose} maxWidth="sm:max-w-3xl">
      <div className="text-ink">
        <ErrorBanner message={error} />
        {!options && <Spinner />}
        {options && !visible.length && <p className="text-muted">No other pictures were found. Try “Find better pictures” on the deck.</p>}
        <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-2">
          {visible.map((o) => (
            <li key={o.id} className={`rounded-2xl overflow-hidden border-2 ${o.status === 'chosen' ? 'border-brand-500' : 'border-line/60'}`}>
              <div className="aspect-[4/3] bg-sunk">
                {o.preview_url && <img src={o.preview_url} alt={o.title || ''} referrerPolicy="no-referrer" loading="lazy" className="w-full h-full object-cover" />}
              </div>
              <div className="p-2 space-y-1.5">
                <p className="text-xs font-bold line-clamp-2" title={o.title}>{o.title}</p>
                <p className="text-[11px] text-muted truncate">
                  {o.author} · {o.license} ·{' '}
                  <a href={o.page_url} target="_blank" rel="noreferrer" className="underline inline-flex items-center gap-0.5">source <ExternalLink className="w-3 h-3" /></a>
                </p>
                <div className="flex gap-1.5">
                  {o.status === 'chosen' ? (
                    <span className="chip chip-moss flex-1 justify-center"><Check className="w-3.5 h-3.5" /> In use</span>
                  ) : (
                    <button type="button" disabled={busy !== null} onClick={() => act(o.id, chooseImage)} className="btn-primary !px-2 !py-1.5 !text-xs flex-1">
                      {busy === o.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Use this
                    </button>
                  )}
                  <button type="button" disabled={busy !== null} onClick={() => act(o.id, hideImage)} aria-label="Hide this picture" title="Hide this picture"
                    className="btn-soft !px-2 !py-1.5 !text-xs"><EyeOff className="w-3.5 h-3.5" /></button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  );
}
