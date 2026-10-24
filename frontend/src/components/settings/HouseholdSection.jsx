import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, Check, Copy, Globe, Home, Link2, Loader2, Lock, LockOpen, Share2, Ticket, Trash2, UserPlus, Users, XCircle,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  clearUserLock, createInvite, createUser, deactivateUser, getOtherAdmins, getRegistrationSettings, listInvites,
  listUsers, makeResetLink, revokeInvite, updateRegistrationSettings,
} from '../../api';
import { errorOf, ErrorBanner, Spinner } from '../ui';
import Section from './Section';

const STATUS_CHIP = {
  active: 'chip-moss',
  used: '',
  expired: 'chip-amber',
  revoked: '!bg-brand-100 !text-brand-700',
};

// The server builds the link on the public address when one is set (PUBLIC_URL or the
// owner's setting); otherwise it's the address this page is open on.
const inviteLink = (invite) => invite.link || `${window.location.origin}/?invite=${encodeURIComponent(invite.code)}`;

/** Can people outside this network open links on this address? */
const isPrivateAddress = (url) => {
  try {
    const host = new URL(url).hostname;
    return host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host === '::1' || host === '[::1]'
      || /^127\./.test(host) || /^10\./.test(host) || /^192\.168\./.test(host)
      || /^172\.(1[6-9]|2\d|3[01])\./.test(host) || /^169\.254\./.test(host);
  } catch {
    return false;
  }
};

const utc = (iso) => new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
const fmt = (iso) => utc(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
const time = (iso) => utc(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

// Whether you can make a reset link for someone: admins for members, the instance owner for admins.
const canReset = (me, u) => u.id !== me?.id && u.is_active && !u.is_superuser && (u.is_admin ? me?.is_superuser : me?.is_admin);

function CopyBox({ text, label }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked: the text is selectable */ }
  };
  return (
    <div className="flex gap-2">
      <input readOnly value={text} onFocus={(e) => e.target.select()} aria-label={label} data-testid="copy-box"
        className="input !py-2 text-xs font-mono" />
      <button type="button" onClick={copy} className="btn-soft shrink-0">
        {copied ? <Check className="w-4 h-4 text-moss-600" /> : <Copy className="w-4 h-4" />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

function ResetLinkBox({ made, onClose }) {
  const link = made.link || `${window.location.origin}/?reset=${made.token}`;
  return (
    <div className="banner-ok flex-col !items-stretch gap-2" data-testid="reset-link-box">
      <p className="font-bold">Reset link for {made.username}</p>
      <p className="text-sm">
        Send it to them privately. It works once, until {time(made.expires_at)}, and it&apos;s shown only now. Using it signs
        them out everywhere; two-step verification stays on.
      </p>
      <CopyBox text={link} label={`Reset link for ${made.username}`} />
      <button type="button" onClick={onClose} className="self-start text-sm font-bold underline cursor-pointer">Done</button>
    </div>
  );
}

function Members() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [error, setError] = useState(null);
  const [resetMade, setResetMade] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: '', email: '', password: '', is_admin: false });
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async () => {
    try {
      setUsers(await listUsers());
    } catch (err) {
      setError(errorOf(err, 'Could not load household members.'));
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (me?.is_superuser) getOtherAdmins().then(setAdmins).catch(() => setAdmins([])); }, [me]);

  const run = (fn, fallback) => async (...args) => {
    setError(null);
    try {
      await fn(...args);
    } catch (err) {
      setError(errorOf(err, fallback));
    }
  };
  const deactivate = run(async (id) => { await deactivateUser(id); setConfirm(null); await load(); }, 'Could not deactivate that person.');
  const lift = run(async (id) => { await clearUserLock(id); await load(); }, 'Could not lift the pause.');
  const reset = run(async (u) => setResetMade(await makeResetLink(u.id)), 'Could not make a reset link.');

  const create = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      setBusy(true);
      await createUser({ username: form.username, email: form.email || undefined, password: form.password, is_admin: form.is_admin });
      setForm({ username: '', email: '', password: '', is_admin: false });
      setShowCreate(false);
      await load();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d) => d.msg).join(' ') : errorOf(err, 'Could not add that person.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title="Household members" hint={`Everyone on this Dose shares the same decks. What each person knows stays their own.`}>
      <ErrorBanner message={error} />
      {!users ? <Spinner /> : (
        <ul className="space-y-2.5">
          {users.map((u) => (
            <li key={u.id} className="rounded-3xl border border-line/70 p-3.5 flex flex-wrap items-center gap-3">
              <span className="w-10 h-10 rounded-full bg-moss-500 text-white font-display font-extrabold flex items-center justify-center uppercase shrink-0" aria-hidden="true">{u.username[0]}</span>
              <span className="flex-1 min-w-[8rem]">
                <span className="font-bold block">{u.username}{u.id === me?.id && <span className="text-xs text-moss-700 dark:text-moss-300 ml-1.5">(you)</span>}</span>
                <span className="text-xs text-muted">
                  {u.is_superuser ? 'Owner' : u.is_admin ? 'Admin' : 'Member'} · 2FA {u.totp_enabled ? 'on' : 'off'}{!u.is_active && ' · deactivated'}
                </span>
                {u.locked_until && (
                  <span className="block text-xs text-amber-700 dark:text-amber-300" data-testid="user-paused">
                    Wrong passwords paused sign-in from new devices until {time(u.locked_until)}.
                  </span>
                )}
              </span>
              <span className="flex items-center gap-1.5">
                {u.locked_until && (
                  <button type="button" onClick={() => lift(u.id)} className="btn-soft !px-3 !py-1.5 text-xs"><LockOpen className="w-3.5 h-3.5" aria-hidden="true" /> Lift pause</button>
                )}
                {canReset(me, u) && (
                  <button type="button" onClick={() => reset(u)} data-testid="make-reset-link" className="btn-soft !px-3 !py-1.5 text-xs"><Link2 className="w-3.5 h-3.5" aria-hidden="true" /> Reset link</button>
                )}
                {u.id !== me?.id && u.is_active && me?.is_admin && (confirm === u.id ? (
                  <>
                    <button type="button" onClick={() => deactivate(u.id)} className="btn-danger !px-3 !py-1.5 text-xs">Deactivate</button>
                    <button type="button" onClick={() => setConfirm(null)} className="btn-soft !px-3 !py-1.5 text-xs">No</button>
                  </>
                ) : (
                  <button type="button" onClick={() => setConfirm(u.id)} aria-label={`Deactivate ${u.username}`} className="btn-icon w-9 h-9 text-muted hover:bg-brand-50 hover:text-brand-600"><Trash2 className="w-4 h-4" /></button>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}

      {resetMade && <ResetLinkBox made={resetMade} onClose={() => setResetMade(null)} />}

      {admins.length > 0 && (
        <div className="space-y-2" data-testid="other-admins">
          <h3 className="label">Other households&apos; admins</h3>
          {admins.map((u) => (
            <div key={u.id} className="flex items-center justify-between gap-3 rounded-2xl bg-sunk/70 p-3">
              <span className="min-w-0"><span className="font-bold block truncate">{u.username}</span><span className="text-xs text-muted">Admin of {u.household_name}</span></span>
              <button type="button" onClick={() => reset(u)} className="btn-soft !px-3 !py-1.5 text-xs shrink-0"><Link2 className="w-3.5 h-3.5" aria-hidden="true" /> Reset link</button>
            </div>
          ))}
        </div>
      )}

      {me?.is_admin && (showCreate ? (
        <form onSubmit={create} className="rounded-3xl bg-sunk/70 p-4 space-y-3">
          <input required placeholder="Username" aria-label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="input" />
          <input type="email" placeholder="Email (optional)" aria-label="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="input" />
          <input required type="password" placeholder="Temporary password" aria-label="Temporary password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="input" />
          <label className="flex items-center gap-2 text-sm font-semibold cursor-pointer">
            <input type="checkbox" checked={form.is_admin} onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} className="w-4 h-4 accent-brand-600" />
            Make them an admin
          </label>
          <div className="flex gap-2">
            <button type="button" onClick={() => setShowCreate(false)} className="btn-soft">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary">Add member</button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setShowCreate(true)} className="btn-soft"><UserPlus className="w-4 h-4" aria-hidden="true" /> Add a member with a password</button>
      ))}
    </Section>
  );
}

function NewInviteCard({ invite, onDone, isOwner }) {
  const link = inviteLink(invite);
  const unreachable = isPrivateAddress(link);
  const share = () => navigator.share?.({
    title: 'Your Dose invite',
    text: invite.kind === 'member' ? `Join ${invite.household_name} on Dose` : 'Your invite to Dose',
    url: link,
  }).catch(() => {});
  return (
    <div className="banner-ok flex-col !items-stretch gap-3" data-testid="new-invite">
      <p className="font-bold">
        Invite created. Send this link {invite.note ? `to ${invite.note.replace(/^for\s+/i, '')}` : ''}. It is shown only once.
      </p>
      <CopyBox text={link} label="Invite link" />
      {unreachable && (
        <p className="flex items-start gap-1.5 text-sm bg-amber-50 text-amber-700 dark:bg-amber-600/15 dark:text-amber-200 rounded-2xl p-3">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            This link uses a local address, so it only works on your own network.
            {isOwner ? ' Set your public address above (e.g. your Cloudflare domain) and create a new invite.'
              : ' Open Dose through its public address and create the invite there.'}
          </span>
        </p>
      )}
      <p className="text-sm">
        Or they can enter the code <span className="font-mono tracking-widest select-all font-bold">{invite.code}</span> on the sign-up page.
      </p>
      <div className="flex gap-2">
        {typeof navigator.share === 'function' && <button type="button" onClick={share} className="btn-soft"><Share2 className="w-4 h-4" aria-hidden="true" /> Share</button>}
        <button type="button" onClick={onDone} className="btn-ghost">Done</button>
      </div>
    </div>
  );
}

function Invites() {
  const { user } = useAuth();
  const isOwner = !!user?.is_superuser;
  const [invites, setInvites] = useState(null);
  const [mode, setMode] = useState(null);
  const [publicUrl, setPublicUrl] = useState('');
  const [publicDefault, setPublicDefault] = useState('');
  const [urlDraft, setUrlDraft] = useState('');
  const [urlSaved, setUrlSaved] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(null);
  const [form, setForm] = useState({ kind: 'member', note: '', expires_in_days: 7, max_uses: 1, grants_admin: false });
  const [created, setCreated] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setForm((f) => ({ ...f, kind: 'member' }));
    listInvites().then(setInvites).catch((err) => setError(errorOf(err, 'Could not load invites.')));
    if (isOwner) {
      getRegistrationSettings().then((s) => {
        setMode(s.mode);
        setPublicUrl(s.public_url || '');
        setPublicDefault(s.public_url_default || '');
        setUrlDraft(s.public_url || '');
      }).catch(() => {});
    }
  }, [isOwner]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      setBusy(true);
      const invite = await createInvite({
        ...form,
        note: form.note.trim() || null,
        expires_in_days: Number(form.expires_in_days),
        max_uses: Number(form.max_uses),
        grants_admin: form.kind === 'member' && form.grants_admin,
      });
      setCreated(invite);
      setForm((f) => ({ ...f, note: '' }));
      setInvites(await listInvites());
    } catch (err) {
      setError(errorOf(err, 'Could not create the invite.'));
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (id) => {
    setConfirmRevoke(null);
    try {
      await revokeInvite(id);
      setInvites(await listInvites());
    } catch (err) {
      setError(errorOf(err, 'Could not revoke the invite.'));
    }
  };

  const handleMode = async (next) => {
    try {
      setMode((await updateRegistrationSettings({ mode: next })).mode);
    } catch (err) {
      setError(errorOf(err, 'Could not change who can sign up.'));
    }
  };

  const handlePublicUrl = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      const saved = await updateRegistrationSettings({ public_url: urlDraft.trim() });
      setPublicUrl(saved.public_url || '');
      setUrlDraft(saved.public_url || '');
      setUrlSaved(true);
      setTimeout(() => setUrlSaved(false), 2000);
    } catch (err) {
      setError(errorOf(err, 'Could not save the public address.'));
    }
  };
  const here = window.location.origin;

  if (!user?.is_admin) return null;

  return (
    <Section title="Invite people" hint={isOwner ? 'Hand out invite links so only people you choose can sign up.' : 'Invite people to share your household.'}>
      <ErrorBanner message={error} />

      {isOwner && mode && (
        <div className="rounded-3xl bg-sunk/70 p-4 space-y-3">
          <p className="label !mb-0">Who can sign up</p>
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Who can sign up">
            {[
              { id: 'invite', label: 'Invite only', hint: 'Needs a link from you', Icon: Lock },
              { id: 'open', label: 'Anyone', hint: 'Open sign-up', Icon: Globe },
            ].map(({ id, label, hint, Icon }) => (
              <button key={id} type="button" role="radio" aria-checked={mode === id} onClick={() => handleMode(id)}
                className={`text-left rounded-2xl border-2 px-3.5 py-2.5 transition cursor-pointer ${mode === id ? 'border-brand-400 bg-surface' : 'border-transparent bg-surface/60 hover:bg-surface'}`}>
                <span className="flex items-center gap-1.5 font-bold"><Icon className="w-4 h-4" aria-hidden="true" /> {label}</span>
                <span className="block text-xs text-muted">{hint}</span>
              </button>
            ))}
          </div>
          <form onSubmit={handlePublicUrl} className="space-y-1.5">
            <label htmlFor="public-url" className="label flex items-center gap-1.5"><Link2 className="w-3.5 h-3.5" aria-hidden="true" /> Public address (for invite links)</label>
            <div className="flex gap-2">
              <input id="public-url" type="url" inputMode="url" value={urlDraft} onChange={(e) => setUrlDraft(e.target.value)}
                placeholder={publicDefault || 'https://dose.example.com'} className="input !py-2 text-sm" />
              <button type="submit" disabled={urlDraft.trim() === publicUrl} className="btn-soft shrink-0">{urlSaved ? 'Saved' : 'Save'}</button>
            </div>
            <p className="text-xs text-muted">
              The address people use to reach Dose from the internet, like your Cloudflare domain. Invite links use it
              {publicUrl ? '.' : `; until it's set they use ${here}${isPrivateAddress(here) ? ', which only works on your network' : ''}.`}
            </p>
          </form>
        </div>
      )}

      {!isOwner && isPrivateAddress(here) && !created && (
        <p className="banner-warn"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" /> You&apos;re on a local address, so links made here may only work on your network.</p>
      )}

      {created ? (
        <NewInviteCard invite={created} onDone={() => setCreated(null)} isOwner={isOwner} />
      ) : (
        <form onSubmit={handleCreate} className="space-y-3">
          {isOwner && (
            <div>
              <label className="label" htmlFor="invite-kind">Invite someone to</label>
              <select id="invite-kind" value={form.kind} onChange={set('kind')} className="input cursor-pointer">
                <option value="member">Join your household ({user?.household_name})</option>
                <option value="household">Their own household</option>
              </select>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-3">
              <label className="label" htmlFor="invite-note">Who is it for? (optional)</label>
              <input id="invite-note" value={form.note} onChange={set('note')} maxLength={100} placeholder="e.g. Mom" className="input" />
            </div>
            <div>
              <label className="label" htmlFor="invite-expires">Expires after</label>
              <select id="invite-expires" value={form.expires_in_days} onChange={set('expires_in_days')} className="input cursor-pointer">
                <option value={1}>1 day</option>
                <option value={7}>7 days</option>
                <option value={30}>30 days</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="invite-uses">Can be used</label>
              <select id="invite-uses" value={form.max_uses} onChange={set('max_uses')} className="input cursor-pointer">
                <option value={1}>Once</option>
                <option value={3}>3 times</option>
                <option value={10}>10 times</option>
              </select>
            </div>
            {form.kind === 'member' && (
              <label className="flex items-center gap-2 text-sm font-semibold cursor-pointer select-none sm:pt-7">
                <input type="checkbox" checked={form.grants_admin} onChange={set('grants_admin')} className="w-4 h-4 accent-brand-600" />
                Make them an admin
              </label>
            )}
          </div>
          <button type="submit" disabled={busy} className="btn-primary">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Ticket className="w-4 h-4" aria-hidden="true" />}
            Create invite link
          </button>
        </form>
      )}

      <div className="space-y-2">
        <h3 className="label">Invites</h3>
        {!invites ? <Spinner /> : invites.length === 0 ? (
          <p className="text-sm text-muted">No invites yet.</p>
        ) : (
          <ul className="space-y-2">
            {invites.map((inv) => (
              <li key={inv.id} className="rounded-2xl bg-sunk/70 p-3 flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="font-bold flex items-center gap-2 flex-wrap">
                    {inv.kind === 'member' ? <Users className="w-4 h-4 text-muted" aria-hidden="true" /> : <Home className="w-4 h-4 text-muted" aria-hidden="true" />}
                    <span className="truncate">{inv.note || (inv.kind === 'member' ? `Member of ${inv.household_name}` : 'New household')}</span>
                    <span className={`chip !py-0.5 uppercase ${STATUS_CHIP[inv.status]}`}>{inv.status}</span>
                  </p>
                  <p className="text-xs text-muted">
                    {inv.kind === 'member' ? (inv.grants_admin ? 'Joins as admin' : 'Joins as member') : 'Gets their own household'}
                    {' · '}used {inv.use_count}/{inv.max_uses}
                    {inv.status === 'active' && ` · expires ${fmt(inv.expires_at)}`}
                  </p>
                  {inv.used_by.length > 0 && <p className="text-xs text-muted">Signed up: {inv.used_by.join(', ')}</p>}
                </div>
                {inv.status === 'active' && (confirmRevoke === inv.id ? (
                  <span className="flex items-center gap-1.5 shrink-0">
                    <button type="button" onClick={() => handleRevoke(inv.id)} className="btn-danger !px-3 !py-1.5 text-xs">Revoke</button>
                    <button type="button" onClick={() => setConfirmRevoke(null)} className="btn-soft !px-3 !py-1.5 text-xs">No</button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirmRevoke(inv.id)} aria-label="Revoke invite" title="Revoke this invite"
                    className="btn-icon w-9 h-9 text-muted hover:bg-brand-50 hover:text-brand-600 shrink-0"><XCircle className="w-4 h-4" /></button>
                ))}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}

export default function HouseholdSection() {
  return (
    <>
      <Members />
      <Invites />
    </>
  );
}
