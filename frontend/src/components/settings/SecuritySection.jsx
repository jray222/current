import React, { useState } from 'react';
import { Check, Copy, Loader2, LogOut, ShieldCheck, ShieldOff, ShieldPlus } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  changePassword, confirmTwoFactor, disableTwoFactor, logoutAllDevices, regenerateBackupCodes, setupTwoFactor,
} from '../../api';
import { errorOf, ErrorBanner, SuccessBanner } from '../ui';
import Section from './Section';

function BackupCodesList({ codes }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codes.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked: select the codes instead */ }
  };
  return (
    <div className="banner-warn flex-col !items-stretch gap-3" data-testid="backup-codes">
      <p className="font-bold">
        Save these one-time backup codes somewhere safe. Each can be used once if you lose access to your authenticator app.
      </p>
      <div className="grid grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((c) => <div key={c} className="bg-surface text-ink rounded-xl px-2 py-1.5 text-center select-all">{c}</div>)}
      </div>
      <button type="button" onClick={copy} className="self-start flex items-center gap-2 text-sm font-bold underline cursor-pointer">
        {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
        {copied ? 'Copied!' : 'Copy all codes'}
      </button>
    </div>
  );
}

function PasswordCard() {
  const { logout } = useAuth();
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (form.next !== form.confirm) { setError('New passwords do not match.'); return; }
    try {
      setBusy(true);
      const res = await changePassword(form.current, form.next);
      setSuccess(`${res.message || 'Password updated.'} Signing you out...`);
      setForm({ current: '', next: '', confirm: '' });
      setTimeout(() => logout(), 1500);
    } catch (err) {
      setError(errorOf(err, 'Could not update password.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title="Change password">
      <form onSubmit={submit} className="space-y-3">
        <ErrorBanner message={error} />
        <SuccessBanner message={success} />
        <div>
          <label className="label" htmlFor="pw-current">Current password</label>
          <input id="pw-current" required type="password" autoComplete="current-password" value={form.current} onChange={set('current')} className="input" />
        </div>
        <div>
          <label className="label" htmlFor="pw-new">New password</label>
          <input id="pw-new" required type="password" autoComplete="new-password" value={form.next} onChange={set('next')} className="input" />
          <p className="text-xs text-muted mt-1.5">At least 12 characters, with uppercase, lowercase, a number, and a special character.</p>
        </div>
        <div>
          <label className="label" htmlFor="pw-confirm">Confirm new password</label>
          <input id="pw-confirm" required type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} className="input" />
        </div>
        <button type="submit" disabled={busy} className="btn-primary">
          {busy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />} Update password
        </button>
      </form>
    </Section>
  );
}

function TwoFactorCard() {
  const { user, refreshUser } = useAuth();
  const [setupData, setSetupData] = useState(null);
  const [confirmCode, setConfirmCode] = useState('');
  const [backupCodes, setBackupCodes] = useState(null);
  const [disable, setDisable] = useState({ password: '', code: '' });
  const [regenPassword, setRegenPassword] = useState('');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [busy, setBusy] = useState(false);

  const attempt = async (fn, fallback) => {
    setError(null);
    setSuccess(null);
    try {
      setBusy(true);
      await fn();
    } catch (err) {
      setError(errorOf(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const startSetup = () => attempt(async () => setSetupData(await setupTwoFactor()), 'Could not start 2FA setup.');
  const confirmSetup = (e) => {
    e.preventDefault();
    return attempt(async () => {
      const res = await confirmTwoFactor(confirmCode);
      setBackupCodes(res.backup_codes);
      setSetupData(null);
      setConfirmCode('');
      await refreshUser();
    }, 'Invalid verification code.');
  };
  const handleDisable = (e) => {
    e.preventDefault();
    return attempt(async () => {
      await disableTwoFactor(disable.password, disable.code);
      setDisable({ password: '', code: '' });
      setSuccess('Two-factor authentication has been disabled.');
      await refreshUser();
    }, 'Could not disable 2FA.');
  };
  const regenerate = (e) => {
    e.preventDefault();
    return attempt(async () => {
      setBackupCodes((await regenerateBackupCodes(regenPassword)).backup_codes);
      setRegenPassword('');
    }, 'Could not regenerate backup codes.');
  };

  if (backupCodes) {
    return (
      <Section title="Two-factor authentication">
        <SuccessBanner message="Two-factor authentication is on." />
        <BackupCodesList codes={backupCodes} />
        <button type="button" onClick={() => setBackupCodes(null)} className="btn-soft">Done</button>
      </Section>
    );
  }

  if (setupData) {
    return (
      <Section title="Set up two-factor authentication">
        <form onSubmit={confirmSetup} className="space-y-4">
          <ErrorBanner message={error} />
          <p className="text-muted">Scan this QR code with Google Authenticator, Authy, 1Password or another authenticator app.</p>
          <div className="bg-white p-3 rounded-3xl w-fit mx-auto shadow-soft">
            <img src={setupData.qr_code_base64} alt="2FA QR code" className="w-44 h-44" />
          </div>
          <div className="rounded-2xl bg-sunk p-3 text-center">
            <p className="text-xs text-muted mb-1">Or enter this code by hand:</p>
            <code className="font-mono text-sm tracking-widest font-bold select-all">{setupData.secret}</code>
          </div>
          <div>
            <label className="label" htmlFor="tf-confirm">Enter the 6-digit code to confirm</label>
            <input id="tf-confirm" required autoFocus value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)}
              placeholder="123456" autoComplete="one-time-code" className="input font-mono tracking-widest" />
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => setSetupData(null)} className="btn-soft">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary">
              {busy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />} Confirm &amp; turn on
            </button>
          </div>
        </form>
      </Section>
    );
  }

  return (
    <Section title="Two-factor authentication">
      <ErrorBanner message={error} />
      <SuccessBanner message={success} />
      <div className="rounded-3xl bg-sunk/70 p-4 flex items-center gap-4">
        {user?.totp_enabled ? <ShieldCheck className="w-8 h-8 text-moss-600 shrink-0" aria-hidden="true" /> : <ShieldOff className="w-8 h-8 text-muted shrink-0" aria-hidden="true" />}
        <div className="flex-1">
          <p className="font-bold">Two-factor authentication is {user?.totp_enabled ? 'on' : 'off'}</p>
          <p className="text-sm text-muted">Adds a code from your authenticator app when you sign in.</p>
        </div>
        {!user?.totp_enabled && (
          <button type="button" onClick={startSetup} disabled={busy} className="btn-green shrink-0"><ShieldPlus className="w-4 h-4" aria-hidden="true" /> Turn on</button>
        )}
      </div>

      {user?.totp_enabled && (
        <>
          <form onSubmit={regenerate} className="rounded-3xl bg-sunk/70 p-4 space-y-3">
            <h3 className="font-display font-extrabold">New backup codes</h3>
            <p className="text-sm text-muted">Replaces all the old ones.</p>
            <input required type="password" placeholder="Current password" aria-label="Current password" autoComplete="current-password"
              value={regenPassword} onChange={(e) => setRegenPassword(e.target.value)} className="input" />
            <button type="submit" disabled={busy} className="btn-soft">Make new codes</button>
          </form>
          <form onSubmit={handleDisable} className="rounded-3xl bg-brand-50 dark:bg-brand-900/20 p-4 space-y-3">
            <h3 className="font-display font-extrabold text-brand-800 dark:text-brand-100">Turn off two-factor authentication</h3>
            <input required type="password" placeholder="Current password" aria-label="Password to turn off 2FA" autoComplete="current-password"
              value={disable.password} onChange={(e) => setDisable({ ...disable, password: e.target.value })} className="input" />
            <input required placeholder="Authenticator code or backup code" aria-label="Code to turn off 2FA"
              value={disable.code} onChange={(e) => setDisable({ ...disable, code: e.target.value })} className="input font-mono" />
            <button type="submit" disabled={busy} className="btn-danger">Turn off 2FA</button>
          </form>
        </>
      )}
    </Section>
  );
}

function SessionsCard() {
  const { logout } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const run = async () => {
    setError(null);
    try {
      setBusy(true);
      await logoutAllDevices();
      setSuccess('All sessions revoked. You will need to sign in again.');
      setTimeout(() => logout(), 1500);
    } catch (err) {
      setError(errorOf(err, 'Could not revoke sessions.'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section title="Sign out everywhere" hint="Ends every session on every device, including this one. Use it if you think your account was compromised.">
      <ErrorBanner message={error} />
      <SuccessBanner message={success} />
      <button type="button" onClick={run} disabled={busy} className="btn-danger"><LogOut className="w-4 h-4" aria-hidden="true" /> Sign out of all devices</button>
    </Section>
  );
}

export default function SecuritySection() {
  return (
    <>
      <PasswordCard />
      <TwoFactorCard />
      <SessionsCard />
    </>
  );
}
