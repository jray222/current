import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, KeyRound, Loader2, LogOut, RefreshCw, Sparkles } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  acceptServerKeys, getAISettings, getServerKeys, rotateDataKeys, signOutEveryone, updateAISettings,
} from '../../api';
import { errorOf, ErrorBanner, Spinner, SuccessBanner } from '../ui';
import Section from './Section';

const SOURCE = {
  app: 'Saved here, stored encrypted.',
  environment: 'Coming from the ANTHROPIC_API_KEY setting on the server.',
};

function AnthropicCard() {
  const [settings, setSettings] = useState(null);
  const [key, setKey] = useState('');
  const [model, setModel] = useState('');
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAISettings().then((s) => { setSettings(s); setModel(s.anthropic_model); })
      .catch((err) => setError(errorOf(err, 'Could not load the AI settings.')));
  }, []);

  const save = async (changes, message) => {
    setError(null);
    setSaved(null);
    try {
      setBusy(true);
      const next = await updateAISettings(changes);
      setSettings(next);
      setModel(next.anthropic_model);
      setKey('');
      setSaved(message);
    } catch (err) {
      setError(errorOf(err, 'Could not save.'));
    } finally {
      setBusy(false);
    }
  };

  if (!settings) return <Section title="AI"><ErrorBanner message={error} />{!error && <Spinner />}</Section>;

  return (
    <Section title="AI (Anthropic Claude)"
      hint="Optional. With a key, Claude can categorize articles from mixed-topic sources into categories. Everything else works without one.">
      <ErrorBanner message={error} />
      <SuccessBanner message={saved} />
      <div className={`rounded-3xl p-4 flex items-center gap-3 ${settings.anthropic_api_key_set ? 'bg-moss-50 dark:bg-moss-900/30' : 'bg-sunk/70'}`}>
        <Sparkles className={`w-6 h-6 shrink-0 ${settings.anthropic_api_key_set ? 'text-moss-600' : 'text-muted'}`} aria-hidden="true" />
        <div>
          <p className="font-bold">{settings.anthropic_api_key_set ? 'An API key is set' : 'No API key'}</p>
          <p className="text-sm text-muted">{settings.key_source ? SOURCE[settings.key_source] : 'Without a key Current categorizes articles using keywords.'}</p>
        </div>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); save({ anthropic_api_key: key.trim() }, 'API key saved.'); }} className="space-y-3">
        <div>
          <label className="label" htmlFor="ai-key">{settings.anthropic_api_key_set ? 'Replace the API key' : 'Anthropic API key'}</label>
          <input id="ai-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-..." className="input font-mono" />
          <p className="text-xs text-muted mt-1.5">Never shown again once saved.</p>
        </div>
        <div className="flex gap-2">
          <button type="submit" disabled={busy || !key.trim()} className="btn-primary"><KeyRound className="w-4 h-4" aria-hidden="true" /> Save key</button>
          {settings.key_source === 'app' && (
            <button type="button" disabled={busy} onClick={() => save({ anthropic_api_key: '' }, 'Saved key removed.')} className="btn-danger">Remove saved key</button>
          )}
        </div>
      </form>
      <form onSubmit={(e) => { e.preventDefault(); save({ anthropic_model: model.trim() }, 'Model saved.'); }} className="space-y-3">
        <div>
          <label className="label" htmlFor="ai-model">Model</label>
          <input id="ai-model" list="ai-models" value={model} onChange={(e) => setModel(e.target.value)} className="input font-mono" />
          <datalist id="ai-models">{settings.suggested_models.map((m) => <option key={m} value={m} />)}</datalist>
        </div>
        <button type="submit" disabled={busy || model.trim() === settings.anthropic_model} className="btn-soft">Save model</button>
      </form>
    </Section>
  );
}

const day = (iso) => (iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'unknown');
const values = (n) => `${n} value${n === 1 ? '' : 's'}`;

// A Fernet key: 32 random bytes, URL-safe base64. Made here, so it never travels until it's in DATA_KEYS.
function newDataKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_');
}

function KeyRow({ label, fingerprint, detail, badge }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-2xl bg-sunk/70 p-3">
      <div className="min-w-0">
        <p className="font-bold">{label}</p>
        <p className="text-xs text-muted break-words">{detail}</p>
      </div>
      <div className="text-right shrink-0">
        {badge && <span className="block text-xs font-bold text-moss-700 dark:text-moss-300">{badge}</span>}
        {fingerprint && <span className="font-mono text-xs text-muted">{fingerprint}</span>}
      </div>
    </div>
  );
}

function NewKey() {
  const [key, setKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(key);
      setCopied(true);
    } catch { /* clipboard blocked: the key is selectable */ }
  };
  if (!key) {
    return <button type="button" onClick={() => setKey(newDataKey())} className="btn-soft"><KeyRound className="w-4 h-4" aria-hidden="true" /> Make a new data key</button>;
  }
  return (
    <div className="space-y-2" data-testid="new-data-key">
      <div className="flex items-center gap-2">
        <code className="flex-1 min-w-0 break-all bg-sunk rounded-2xl px-3 py-2 text-xs select-all">{key}</code>
        <button type="button" onClick={copy} aria-label="Copy key" className="btn-icon text-muted hover:bg-sunk">
          {copied ? <Check className="w-4 h-4 text-moss-600" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
      <ol className="list-decimal pl-5 text-sm text-muted space-y-1">
        <li>Save it in your password manager. Current doesn&apos;t keep this copy.</li>
        <li>Put it at the front of <span className="font-mono">DATA_KEYS</span> in docker-compose.yml, keeping any keys already there after it, separated by commas.</li>
        <li>Restart Current, come back here and choose Re-encrypt.</li>
      </ol>
    </div>
  );
}

/** The instance owner's view of the server's keys: never the keys, only where they are and what they open. */
function ServerKeysCard() {
  const { logout } = useAuth();
  const [keys, setKeys] = useState(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);

  const load = useCallback(async () => {
    try {
      setKeys(await getServerKeys());
    } catch (err) {
      setError(errorOf(err, 'Could not load the server keys.'));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (name, fn, describe) => {
    if (!password) { setError('Enter your password first.'); return; }
    setBusy(name);
    setError(null);
    setDone(null);
    try {
      const result = await fn(password);
      setPassword('');
      if (result.keys) setKeys(result.keys);
      setDone(describe(result));
    } catch (err) {
      setError(errorOf(err, 'That did not work. Try again.'));
    } finally {
      setBusy(null);
    }
  };

  const signOutAll = async () => {
    if (!password) { setError('Enter your password first.'); return; }
    setBusy('signout');
    setError(null);
    try {
      await signOutEveryone(password);
      await logout();
    } catch (err) {
      setError(errorOf(err, 'That did not work. Try again.'));
      setBusy(null);
    }
  };

  const signing = keys?.signing_key;
  const hasDataKeys = keys?.data_keys?.length > 0;

  return (
    <Section title="Server keys" hint="The keys that sign people in and lock 2FA secrets and the stored AI key. Current never shows the keys themselves.">
      <ErrorBanner message={error} />
      <SuccessBanner message={done} />
      {!keys ? <Spinner /> : (
        <div className="space-y-5" data-testid="server-keys">
          {keys.advice.length > 0 && (
            <ul className={`space-y-2 ${keys.problem ? 'banner-error' : 'banner-warn'} flex-col !items-stretch`}>
              {keys.advice.map((a) => (
                <li key={a} className="flex items-start gap-2 text-sm"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" /> <span>{a}</span></li>
              ))}
            </ul>
          )}
          <div className="space-y-2">
            <h3 className="label">Sign-in key</h3>
            <KeyRow label={signing.source === 'file' ? 'A file in the data volume' : 'SECRET_KEY in the environment'}
              detail={`${signing.file ? `${signing.file}. ` : ''}First seen ${day(signing.first_seen)}.`} fingerprint={signing.fingerprint} />
          </div>
          <div className="space-y-2">
            <h3 className="label">Data keys</h3>
            {keys.data_keys.map((k) => (
              <KeyRow key={k.fingerprint} label={k.newest ? 'Newest data key (encrypts)' : 'Older data key'}
                detail={`Opens ${values(k.values)}. First seen ${day(k.first_seen)}.`} fingerprint={k.fingerprint} badge={k.newest ? 'In use' : null} />
            ))}
            {!keys.legacy.retired && (
              <KeyRow label="Key made from the sign-in key"
                detail={`Opens ${values(keys.legacy.values)}.${hasDataKeys ? ' Re-encrypting retires it.' : ' Used until you add a data key.'}`}
                badge={hasDataKeys ? null : 'In use'} />
            )}
            {keys.unreadable.length > 0 && (
              <p className="text-sm text-brand-700 dark:text-brand-300">No key opens {values(keys.unreadable.length)}: {[...new Set(keys.unreadable)].join(', ')}.</p>
            )}
            <NewKey />
          </div>
          <div className="space-y-3 border-t border-line/70 pt-4">
            <div>
              <label className="label" htmlFor="keys-password">Your password, to confirm any of these</label>
              <input id="keys-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="input" />
            </div>
            {keys.problem && (
              <div className="space-y-1">
                <button type="button" disabled={!!busy}
                  onClick={() => act('accept', acceptServerKeys, (r) => (r.unreadable.length
                    ? `Carrying on with the current keys. ${values(r.unreadable.length)} made with the old key stay unreadable; set them up again.`
                    : 'Carrying on with the current keys.'))}
                  className="btn-danger">
                  {busy === 'accept' && <Loader2 className="w-4 h-4 animate-spin" />} Use the current keys from now on
                </button>
                <p className="text-xs text-muted">Only if the old key is gone for good. Putting it back and restarting fixes everything instead.</p>
              </div>
            )}
            {hasDataKeys && !keys.problem && (
              <div className="space-y-1">
                <button type="button" disabled={!!busy}
                  onClick={() => act('rotate', rotateDataKeys, (r) => `Re-encrypted ${values(r.moved)} with ${r.key}.${r.skipped.length ? ` ${values(r.skipped.length)} couldn't be read and were left as they were.` : ''}`)}
                  className="btn-green">
                  {busy === 'rotate' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Re-encrypt with the newest key
                </button>
                <p className="text-xs text-muted">All at once, and safe to run again. Afterwards SECRET_KEY can change without losing anything.</p>
              </div>
            )}
            <div className="space-y-1">
              <button type="button" disabled={!!busy} onClick={signOutAll} className="btn-soft">
                {busy === 'signout' ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogOut className="w-4 h-4" />} Sign everyone out
              </button>
              <p className="text-xs text-muted">
                Every device on this server, yours too, has to sign in again.{keys.signed_everyone_out_at && ` Last done ${day(keys.signed_everyone_out_at)}.`}
              </p>
            </div>
          </div>
        </div>
      )}
    </Section>
  );
}

export default function AISection() {
  return (
    <>
      <AnthropicCard />
      <ServerKeysCard />
    </>
  );
}
