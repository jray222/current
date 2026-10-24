import React from 'react';
import { Loader2, AlertTriangle } from 'lucide-react';
import AuthImage from '../AuthImage';
import { imagePath } from '../../api';
import DeckIcon from './DeckIcon';

/** Seen and known as one bar: known in moss, seen-but-not-known in teal. */
export function ProgressBar({ progress, className = '' }) {
  const { total, seen, known } = progress || {};
  if (!total) return null;
  const knownPct = (known / total) * 100;
  const seenPct = ((seen - known) / total) * 100;
  return (
    <div className={`h-1.5 rounded-full bg-sunk overflow-hidden flex ${className}`}
      role="img" aria-label={`${known} of ${total} known, ${seen} seen`}>
      <div className="bg-moss-500 h-full" style={{ width: `${knownPct}%` }} />
      <div className="bg-brand-300 h-full" style={{ width: `${seenPct}%` }} />
    </div>
  );
}

export function progressLine(p) {
  if (!p?.total) return '';
  if (!p.seen) return `${p.total} cards, all new`;
  const parts = [`${p.seen} of ${p.total} seen`];
  if (p.known) parts.push(`${p.known} known`);
  if (p.due) parts.push(`${p.due} due`);
  return parts.join(' · ');
}

/** The deck's cover photo, or its icon on a tinted block while it has no pictures yet. */
export function DeckCover({ deck, className = '', size = 'full' }) {
  if (deck.cover_image_id) {
    return <AuthImage path={imagePath(deck.cover_image_id, size)} className={`bg-sunk ${className}`} />;
  }
  return (
    <div className={`flex items-center justify-center bg-brand-50 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300 ${className}`}>
      <DeckIcon name={deck.icon} className="w-12 h-12" />
    </div>
  );
}

/** Collecting pictures: how far along, or what went wrong. */
export function CollectStatus({ collect, compact = false }) {
  if (!collect) return null;
  const { status, done, total, message } = collect;
  if (status === 'queued' || status === 'running') {
    const pct = total ? Math.round((done / total) * 100) : 0;
    return (
      <div className={compact ? 'text-xs text-muted flex items-center gap-1.5' : 'banner-warn items-center'} role="status">
        <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden="true" />
        <span className="flex-1">
          {status === 'queued' ? 'Waiting to gather pictures…' : `Gathering pictures and facts: ${done} of ${total} cards (${pct}%)`}
        </span>
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className={compact ? 'text-xs text-brand-700 flex items-center gap-1.5' : 'banner-error'} role="alert">
        <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>{compact ? 'Couldn’t gather pictures' : message || 'Gathering pictures stopped.'}</span>
      </div>
    );
  }
  return null;
}

export const isCollecting = (deck) => ['queued', 'running'].includes(deck?.collect?.status);
