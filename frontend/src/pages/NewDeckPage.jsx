import React, { useEffect, useState } from 'react';
import { ArrowLeft, FileJson, Loader2, Sparkles } from 'lucide-react';
import { draftDeck, getAISettings, importDeck } from '../api';
import { navigate, onLinkClick } from '../lib/router';
import { ErrorBanner, PageHeader, errorOf } from '../components/ui';
import { Field } from '../components/Modal';
import DeckIcon from '../components/deck/DeckIcon';

const IDEAS = ['Birds of prey of North America', 'The periodic table: elements you can see', 'Famous paintings of the Renaissance',
  'Shakespeare’s plays', 'Common Midwest wildflowers', 'Butterflies of the eastern US', 'Dog breeds', 'World capitals’ landmarks'];

/** Owner only: a new deck, drafted by Claude from a topic or pasted as a pack. Pictures are gathered after. */
export default function NewDeckPage() {
  const [tab, setTab] = useState('claude');
  const [hasKey, setHasKey] = useState(null);
  const [topic, setTopic] = useState('');
  const [count, setCount] = useState(25);
  const [notes, setNotes] = useState('');
  const [packText, setPackText] = useState('');
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    getAISettings().then((s) => {
      setHasKey(s.anthropic_api_key_set);
      if (!s.anthropic_api_key_set) setTab('pack');
    }).catch(() => setHasKey(false));
  }, []);

  const ask = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setDraft(null);
    try {
      setDraft(await draftDeck({ topic, count, notes }));
    } catch (err) {
      setError(errorOf(err, 'Claude could not draft that deck.'));
    } finally {
      setBusy(false);
    }
  };

  const save = async (pack) => {
    setBusy(true);
    setError('');
    try {
      const { slug } = await importDeck(pack);
      navigate(`/decks/${slug}`);
    } catch (err) {
      setError(errorOf(err, 'Could not add the deck.'));
      setBusy(false);
    }
  };

  const savePasted = (e) => {
    e.preventDefault();
    let pack;
    try { pack = JSON.parse(packText); } catch { setError('That isn’t valid JSON.'); return; }
    save(pack);
  };

  const readFile = async (file) => { if (file) setPackText(await file.text()); };

  return (
    <div className="max-w-3xl">
      <PageHeader
        back={<a href="/decks" onClick={onLinkClick('/decks')} className="inline-flex items-center gap-1 text-sm font-bold text-muted hover:text-ink mb-2"><ArrowLeft className="w-4 h-4" /> Decks</a>}
        title="New deck"
        subtitle="Name a domain of knowledge. Dose then gathers openly licensed photos and a short summary for every card."
      />
      <div className="flex gap-2 mb-5" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'claude'} onClick={() => setTab('claude')} className={`chip !text-sm !px-4 !py-2 ${tab === 'claude' ? 'chip-on' : ''}`}>
          <Sparkles className="w-4 h-4" /> Ask Claude
        </button>
        <button type="button" role="tab" aria-selected={tab === 'pack'} onClick={() => setTab('pack')} className={`chip !text-sm !px-4 !py-2 ${tab === 'pack' ? 'chip-on' : ''}`}>
          <FileJson className="w-4 h-4" /> Import a pack
        </button>
      </div>
      <ErrorBanner message={error} />

      {tab === 'claude' && (
        <div className="space-y-5 mt-4">
          {hasKey === false && (
            <div className="banner-warn">
              <p>Drafting needs an Anthropic API key. Add one in <a href="/settings/ai" onClick={onLinkClick('/settings/ai')} className="underline font-bold">Settings › AI</a>, or import a pack instead.</p>
            </div>
          )}
          <form onSubmit={ask} className="card card-pad space-y-4">
            <Field label="Topic" htmlFor="topic">
              <input id="topic" className="input" value={topic} onChange={(e) => setTopic(e.target.value)} required minLength={2} maxLength={200}
                placeholder="Insects of Indiana, the planets, Shakespeare's plays…" />
            </Field>
            <div className="flex flex-wrap gap-1.5">
              {IDEAS.map((i) => <button key={i} type="button" className="chip hover:bg-line" onClick={() => setTopic(i)}>{i}</button>)}
            </div>
            <div className="grid sm:grid-cols-3 gap-4">
              <Field label="About how many cards" htmlFor="count">
                <input id="count" type="number" min={5} max={80} className="input" value={count} onChange={(e) => setCount(Number(e.target.value))} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Anything to know (optional)" htmlFor="notes">
                  <input id="notes" className="input" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500}
                    placeholder="Only ones I'd see in Indiana; show the caterpillar too" />
                </Field>
              </div>
            </div>
            <button type="submit" disabled={busy || hasKey === false} className="btn-primary">
              {busy && !draft ? <><Loader2 className="w-4 h-4 animate-spin" /> Claude is drafting… (up to a minute or two)</> : <><Sparkles className="w-4 h-4" /> Draft the deck</>}
            </button>
          </form>
          {draft && <DraftPreview draft={draft} busy={busy} onSave={() => save(draft)} />}
        </div>
      )}

      {tab === 'pack' && (
        <form onSubmit={savePasted} className="card card-pad space-y-4 mt-4">
          <p className="text-sm text-muted">
            A pack is a JSON file describing the deck: its views (like Bark and Leaf, with photo search words) and its cards.
            Use Export pack on any deck to see the format, edit it, and import it back.
          </p>
          <input type="file" accept="application/json,.json" onChange={(e) => readFile(e.target.files?.[0])} className="text-sm" />
          <textarea className="input font-mono text-xs h-72" value={packText} onChange={(e) => setPackText(e.target.value)}
            placeholder='{"title": "...", "facets": [...], "cards": [...]}' aria-label="Pack JSON" />
          <button type="submit" disabled={busy || !packText.trim()} className="btn-primary">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileJson className="w-4 h-4" />} Add the deck
          </button>
        </form>
      )}
    </div>
  );
}

function DraftPreview({ draft, busy, onSave }) {
  return (
    <section className="card card-pad space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl flex items-center gap-2"><DeckIcon name={draft.icon} className="w-6 h-6 text-brand-600" />{draft.title}</h2>
          {draft.subtitle && <p className="text-muted">{draft.subtitle}</p>}
        </div>
        <button type="button" onClick={onSave} disabled={busy} className="btn-primary shrink-0">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Add it and gather pictures
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <span className="text-sm text-muted mr-1">Views:</span>
        {draft.facets.map((f) => <span key={f.key} className="chip">{f.label}</span>)}
      </div>
      <ol className="divide-y divide-line/70">
        {draft.cards.map((c) => (
          <li key={c.name} className="py-2">
            <p><span className="font-bold">{c.name}</span>{c.subtitle && <span className="text-muted"> · {c.subtitle}</span>}</p>
            {c.summary && <p className="text-sm text-muted">{c.summary}</p>}
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted">Check the facts before you add it: Claude can be wrong. You can export the deck later, fix it, and import it again.</p>
    </section>
  );
}
